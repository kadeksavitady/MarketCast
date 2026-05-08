"""
src/training/data_loader.py
============================
Load & split data dari output preprocessing_clustering.py.

POSISI DALAM PIPELINE:
    Input  ← outputs/clustering/data_preprocessed.csv  (Tahap 0)
    Output → dict {train, test, series_full, ...}       (Tahap 2 & 3a)

SPLIT STRATEGY: 80/20
    Bukan fixed TEST_DAYS karena tiap komoditas punya panjang
    series berbeda akibat missing dates & gap > 3 hari.
    Fixed 30 hari bisa jadi > 20% untuk komoditas data pendek
    → evaluasi tidak fair antar komoditas.

    Contoh:
        Komoditas A: 1800 baris → train=1440, test=360
        Komoditas B: 900 baris  → train=720,  test=180
    Proporsi selalu 80/20, horizon prediksi tetap 30 hari.

PENANGANAN MISSING DATES:
    Siskaperbapo tidak selalu rekam setiap hari (libur, dst).
    → Resample ke frekuensi harian
    → Forward-fill gap ≤ 3 hari (pasar tutup 1-3 hari lazim)
    → Gap > 3 hari di-drop (bukan di-interpolate — interpolasi
       pada gap panjang akan menciptakan tren palsu)
"""

import pandas as pd
import numpy as np
from pathlib import Path
from config import (
    CSV_PREPROCESSED, TRAIN_RATIO, FORECAST_DAYS, MIN_TRAIN_ROWS,
    get_logger, get_cluster_short, load_cluster_map
)

log = get_logger("data_loader")


def load_preprocessed(csv_path: Path = CSV_PREPROCESSED) -> pd.DataFrame:
    """
    Load data_preprocessed.csv hasil preprocessing_clustering.py.
    Auto-detect nama kolom (pipeline bisa export dengan nama berbeda).
    Return DataFrame: [tanggal, komoditas, harga_per_kg]
    """
    path = Path(csv_path)
    if not path.exists():
        raise FileNotFoundError(
            f"File tidak ditemukan: {path}\n"
            "Jalankan preprocessing_clustering.py terlebih dahulu."
        )

    df = pd.read_csv(path)

    # Auto-detect kolom tanggal dan harga
    date_col  = next((c for c in df.columns
                      if c.lower() in ("tanggal_data", "tanggal", "date", "ds")),
                     df.columns[0])
    price_col = next((c for c in df.columns
                      if "harga_per_kg" in c.lower() or c.lower() in ("harga", "y", "price")),
                     "harga")
    kom_col   = next((c for c in df.columns
                      if "komoditas" in c.lower() or "commodity" in c.lower()),
                     "komoditas")

    df = df.rename(columns={
        date_col : "tanggal",
        price_col: "harga_per_kg",
        kom_col  : "komoditas",
    })
    df["tanggal"]     = pd.to_datetime(df["tanggal"])
    df["harga_per_kg"] = pd.to_numeric(df["harga_per_kg"], errors="coerce")
    df.dropna(subset=["harga_per_kg"], inplace=True)

    n_kom = df["komoditas"].nunique()
    log.info(f"Loaded {len(df):,} rows | {n_kom} komoditas")
    log.info(f"Rentang: {df['tanggal'].min().date()} → {df['tanggal'].max().date()}")
    return df[["tanggal", "komoditas", "harga_per_kg"]]


def prepare_series(df: pd.DataFrame, komoditas: str,
                   cluster_map: dict = None) -> dict:
    """
    Siapkan train/test split 80/20 untuk satu komoditas.

    Returns dict:
        komoditas     : str
        cluster       : label pendek cluster
        series_full   : np.ndarray semua nilai (setelah resample & fill)
        train         : np.ndarray 80% awal
        test          : np.ndarray 20% akhir
        dates_full    : DatetimeIndex
        dates_train   : DatetimeIndex
        dates_test    : DatetimeIndex
        n             : int total panjang series
        n_train       : int
        n_test        : int
        train_pct     : float aktual (mendekati 0.80)
    """
    grp = (df[df["komoditas"] == komoditas]
           .set_index("tanggal")["harga_per_kg"]
           .sort_index())

    if len(grp) == 0:
        raise ValueError(f"Komoditas '{komoditas}' tidak ditemukan di data.")

    # Resample harian, fill gap pendek
    grp              = grp.resample("D").mean()
    n_before         = grp.isna().sum()
    grp              = grp.ffill(limit=3)
    n_after          = grp.isna().sum()

    if n_after > 0:
        log.warning(f"{komoditas}: {n_after} gap > 3 hari di-drop")
        grp = grp.dropna()
    if n_before > 0:
        log.info(f"{komoditas}: fill {n_before - n_after} gap kecil, "
                 f"drop {n_after} gap besar")

    values = grp.values
    dates  = grp.index
    n      = len(values)

    # 80/20 split
    split   = int(n * TRAIN_RATIO)
    n_test  = n - split
    n_train = split

    # Validasi minimum
    if n_train < MIN_TRAIN_ROWS:
        raise ValueError(
            f"{komoditas}: train set terlalu kecil ({n_train} rows < "
            f"MIN_TRAIN_ROWS={MIN_TRAIN_ROWS}). Total data: {n} rows."
        )

    train       = values[:split]
    test        = values[split:]
    dates_train = dates[:split]
    dates_test  = dates[split:]
    cluster     = get_cluster_short(komoditas, cluster_map)

    log.info(
        f"{komoditas} [{cluster}]: "
        f"total={n} | train={n_train} ({n_train/n*100:.0f}%) | "
        f"test={n_test} ({n_test/n*100:.0f}%)"
    )

    return {
        "komoditas"  : komoditas,
        "cluster"    : cluster,
        "series_full": values,
        "train"      : train,
        "test"       : test,
        "dates_full" : dates,
        "dates_train": dates_train,
        "dates_test" : dates_test,
        "n"          : n,
        "n_train"    : n_train,
        "n_test"     : n_test,
        "train_pct"  : round(n_train / n, 4),
    }


def load_all_series(df: pd.DataFrame,
                    komoditas_list: list,
                    cluster_map: dict = None) -> dict:
    """
    Batch loader: siapkan data untuk banyak komoditas sekaligus.
    Return dict: {komoditas: prepare_series_result}
    Komoditas yang gagal di-skip dengan warning (tidak raise).
    """
    result    = {}
    n_failed  = 0
    cmap      = cluster_map or load_cluster_map()

    for kom in komoditas_list:
        try:
            result[kom] = prepare_series(df, kom, cmap)
        except Exception as e:
            log.warning(f"Skip {kom}: {e}")
            n_failed += 1

    log.info(f"Batch load: {len(result)} berhasil | {n_failed} gagal")
    return result
