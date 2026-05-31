"""
src/training/data_loader.py
============================
Load data dari Neon PostgreSQL (harga_historis_clean) dan
siapkan series per komoditas untuk pipeline training.

ARSITEKTUR DATA FLOW:
    Neon DB (harga_historis_clean)
        ↓ load_preprocessed()
        ↓ DataFrame [tanggal, komoditas, harga_per_kg]
        ↓ prepare_series()
        ↓ dict {series_full, dates_full, cluster, ...}
        ↓ model_sarima / model_prophet / model_xgboost
            → hybrid expanding+sliding splits (dihandle di dalam model)

KENAPA BACA DARI NEON, BUKAN CSV LOKAL:
    - Tiga anggota tim bekerja di laptop berbeda
    - Neon = single source of truth yang selalu up-to-date
    - data_cleaning.py sudah handle: NaN fill, IQR clip, zero-price removal
    - Tidak ada urgensi simpan ke disk lokal
"""

import os
import pandas as pd
import numpy as np
from pathlib import Path
from dotenv import load_dotenv
from sqlalchemy import create_engine

from config import (
    DATABASE_URL,
    TRAIN_RATIO, MIN_TRAIN_ROWS,
    get_logger, get_cluster_short, load_cluster_map,
)

log = get_logger("data_loader")


# ══════════════════════════════════════════════════════════════
# 1. LOAD DARI NEON DB
# ══════════════════════════════════════════════════════════════

def load_preprocessed() -> pd.DataFrame:
    """
    Load data harga dari tabel harga_historis_clean di Neon PostgreSQL.

    Tabel ini adalah output dari data_cleaning.py yang sudah:
        - Drop harga <= 0
        - Fill NaN dengan interpolasi (barang segar) atau ffill (pabrikan)
        - IQR clipping untuk outlier

    Returns:
        DataFrame dengan kolom: [tanggal, komoditas, harga_per_kg]
    """
    load_dotenv()
    db_url = DATABASE_URL or os.getenv("DATABASE_URL")
    if not db_url:
        raise EnvironmentError(
            "DATABASE_URL tidak ditemukan di .env\n"
            "Tambahkan: DATABASE_URL=postgresql://user:pass@host/db"
        )

    engine = create_engine(db_url)
    try:
        df = pd.read_sql(
            """
            SELECT tanggal_data  AS tanggal,
                   komoditas,
                   harga_per_kg
            FROM   harga_historis_clean
            ORDER  BY komoditas, tanggal_data
            """,
            engine,
        )
    finally:
        engine.dispose()

    df["tanggal"]      = pd.to_datetime(df["tanggal"])
    df["harga_per_kg"] = pd.to_numeric(df["harga_per_kg"], errors="coerce")
    df.dropna(subset=["harga_per_kg"], inplace=True)

    n_kom = df["komoditas"].nunique()
    log.info(f"Loaded {len(df):,} rows dari Neon | {n_kom} komoditas")
    log.info(f"Rentang: {df['tanggal'].min().date()} → {df['tanggal'].max().date()}")
    return df[["tanggal", "komoditas", "harga_per_kg"]]


# ══════════════════════════════════════════════════════════════
# 2. PREPARE SERIES PER KOMODITAS
# ══════════════════════════════════════════════════════════════

def prepare_series(df: pd.DataFrame, komoditas: str,
                   cluster_map: dict = None) -> dict:
    """
    Siapkan time series untuk satu komoditas.

    Output dict berisi:
        series_full  : np.ndarray nilai harga penuh (dipakai model untuk hybrid split)
        dates_full   : DatetimeIndex tanggal penuh
        cluster      : label pendek cluster (C0_..., C1_..., C2_...)
        train/test   : split 80/20 sebagai referensi (model bisa override dengan hybrid)

    GAP FILLING:
        resample("D") mengisi hari yang tidak ada data dengan NaN.
        ffill(limit=3) mengisi gap kecil (≤3 hari) — misalnya weekend pasar tutup.
        Gap >3 hari di-drop karena data_cleaning.py seharusnya sudah handle
        gap besar. Kalau masih ada, berarti anomali data baru post-cleaning.
    """
    grp = (df[df["komoditas"] == komoditas]
           .set_index("tanggal")["harga_per_kg"]
           .sort_index())

    if len(grp) == 0:
        raise ValueError(f"Komoditas '{komoditas}' tidak ditemukan di data.")

    # Resample harian — isi gap kecil yang mungkin terbentuk
    grp      = grp.resample("D").mean()
    n_before = grp.isna().sum()
    grp      = grp.ffill(limit=3)   # max 3 hari gap (weekend/libur)
    n_after  = grp.isna().sum()

    if n_after > 0:
        log.warning(f"{komoditas}: drop {n_after} gap > 3 hari")
        grp = grp.dropna()
    if n_before > 0:
        log.info(f"{komoditas}: fill {n_before - n_after} gap kecil, "
                 f"drop {n_after} gap besar")

    values = grp.values
    dates  = grp.index
    n      = len(values)

    # Guard minimum data
    if n < MIN_TRAIN_ROWS:
        raise ValueError(
            f"{komoditas}: data terlalu sedikit ({n} hari < "
            f"MIN_TRAIN_ROWS={MIN_TRAIN_ROWS}). Tidak bisa ditraining."
        )

    # Split 80/20 sebagai referensi — model hybrid override ini dengan splits sendiri
    split       = int(n * TRAIN_RATIO)
    train       = values[:split]
    test        = values[split:]
    dates_train = dates[:split]
    dates_test  = dates[split:]

    cluster = get_cluster_short(komoditas, cluster_map)

    log.info(
        f"{komoditas} [{cluster}]: "
        f"total={n} | train={len(train)} ({len(train)/n*100:.0f}%) | "
        f"test={len(test)} ({len(test)/n*100:.0f}%)"
    )

    return {
        "komoditas"  : komoditas,
        "cluster"    : cluster,
        # Full series — dipakai model untuk hybrid expanding+sliding splits
        "series_full": values,
        "dates_full" : dates,
        # Holdout split — referensi, bisa di-override model
        "train"      : train,
        "test"       : test,
        "dates_train": dates_train,
        "dates_test" : dates_test,
        "n"          : n,
        "n_train"    : len(train),
        "n_test"     : len(test),
        "train_pct"  : round(len(train) / n, 4),
    }


# ══════════════════════════════════════════════════════════════
# 3. BATCH LOAD
# ══════════════════════════════════════════════════════════════

def load_all_series(df: pd.DataFrame,
                    komoditas_list: list,
                    cluster_map: dict = None) -> dict:
    """
    Batch load semua komoditas dalam list.
    Komoditas yang gagal (data kurang / tidak ditemukan) di-skip dengan warning.
    """
    result   = {}
    n_failed = 0
    cmap     = cluster_map or load_cluster_map()

    for kom in komoditas_list:
        try:
            result[kom] = prepare_series(df, kom, cmap)
        except Exception as e:
            log.warning(f"Skip {kom}: {e}")
            n_failed += 1

    log.info(f"Batch load: {len(result)} berhasil | {n_failed} gagal")
    return result
