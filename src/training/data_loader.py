"""
src/training/data_loader.py
============================
Load & split data dari output preprocessing_clustering.py.
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
    path = Path(csv_path)
    if not path.exists():
        raise FileNotFoundError(
            f"File tidak ditemukan: {path}\n"
            "Jalankan preprocessing/clustering.py terlebih dahulu."
        )

    df = pd.read_csv(path)

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
    df["tanggal"]      = pd.to_datetime(df["tanggal"])
    df["harga_per_kg"] = pd.to_numeric(df["harga_per_kg"], errors="coerce")
    df.dropna(subset=["harga_per_kg"], inplace=True)

    n_kom = df["komoditas"].nunique()
    log.info(f"Loaded {len(df):,} rows | {n_kom} komoditas")
    log.info(f"Rentang: {df['tanggal'].min().date()} → {df['tanggal'].max().date()}")
    return df[["tanggal", "komoditas", "harga_per_kg"]]


def prepare_series(df: pd.DataFrame, komoditas: str,
                   cluster_map: dict = None) -> dict:
    grp = (df[df["komoditas"] == komoditas]
           .set_index("tanggal")["harga_per_kg"]
           .sort_index())

    if len(grp) == 0:
        raise ValueError(f"Komoditas '{komoditas}' tidak ditemukan di data.")

    grp      = grp.resample("D").mean()
    n_before = grp.isna().sum()
    grp      = grp.ffill(limit=3)
    n_after  = grp.isna().sum()

    if n_after > 0:
        log.warning(f"{komoditas}: {n_after} gap > 3 hari di-drop")
        grp = grp.dropna()
    if n_before > 0:
        log.info(f"{komoditas}: fill {n_before - n_after} gap kecil, "
                 f"drop {n_after} gap besar")

    values = grp.values
    dates  = grp.index
    n      = len(values)

    split   = int(n * TRAIN_RATIO)
    n_test  = n - split
    n_train = split

    # FIX: guard train set terlalu kecil
    if n_train < MIN_TRAIN_ROWS:
        raise ValueError(
            f"{komoditas}: train set terlalu kecil ({n_train} rows < "
            f"MIN_TRAIN_ROWS={MIN_TRAIN_ROWS}). Total data: {n} rows."
        )

    # FIX: guard test set kosong
    if n_test == 0:
        raise ValueError(
            f"{komoditas}: test set kosong setelah split 80/20. "
            f"Total data: {n} rows."
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
