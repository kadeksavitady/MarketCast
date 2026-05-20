"""
src/preprocessing/data_cleaning.py
====================================
Preprocessing data harga bahan pokok dari Neon PostgreSQL.
Alur:
    1. Load dari Neon (harga_historis)
    2. Drop komoditas invalid
    3. Konversi harga 0 → NaN
    4. Fill NaN berdasarkan kategori:
       - Barang segar/musiman  → interpolasi linear
       - Barang pabrikan/stabil → forward fill (+ backward fill ujung)
    5. Drop outlier dengan IQR clipping
    6. Export ke data/processed/harga_historis_clean.csv
"""

import os
import logging
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
from dotenv import load_dotenv
from sqlalchemy import create_engine

warnings.filterwarnings("ignore")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s"
)
log = logging.getLogger("data_cleaning")

# ─────────────────────────────────────────────────────────────
# KONFIGURASI FILL METHOD PER KATEGORI
# ─────────────────────────────────────────────────────────────

# Kategori barang segar/musiman → harga naik-turun mengikuti musim panen
# Fill: interpolasi linear (mempertahankan tren antar titik)
KATEGORI_INTERPOLASI = {
    "CABE",
    "BAWANG",
    "SAYUR MAYUR",
    "IKAN SEGAR",
    "DAGING",
    "TELUR",
    "PALAWIJA",
}

# Kategori barang pabrikan/processed → harga relatif stabil, jarang berubah tiba-tiba
# Fill: forward fill (harga terakhir dipertahankan sampai ada data baru)
KATEGORI_FFILL = {
    "BERAS",
    "GULA",
    "MINYAK GORENG",
    "SUSU",
    "MIE INSTAN",
    "TEPUNG TERIGU",
    "IKAN ASIN",
    "BARANG PENTING LAINNYA",
    "GARAM",
}

# Komoditas yang di-exclude dari pipeline (nama tidak valid / data terlalu sedikit)
EXCLUDE_KOMODITAS = set()  # tambah di sini kalau ada yang perlu di-skip

# ─────────────────────────────────────────────────────────────
# 1. LOAD DATA
# ─────────────────────────────────────────────────────────────

def load_from_neon() -> pd.DataFrame:
    load_dotenv()
    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        raise EnvironmentError("DATABASE_URL tidak ditemukan di .env")

    engine = create_engine(db_url)
    query = """
        SELECT tanggal_data, komoditas, kategori, harga_per_kg
        FROM harga_historis
        ORDER BY komoditas, tanggal_data
    """
    df = pd.read_sql(query, engine)
    log.info(f"Load dari Neon: {len(df):,} baris | {df['komoditas'].nunique()} komoditas")
    return df

# ─────────────────────────────────────────────────────────────
# 2. VALIDASI & FILTER
# ─────────────────────────────────────────────────────────────

def filter_invalid(df: pd.DataFrame) -> pd.DataFrame:
    before = df['komoditas'].nunique()

    # Drop komoditas yang di-exclude
    if EXCLUDE_KOMODITAS:
        df = df[~df['komoditas'].isin(EXCLUDE_KOMODITAS)]
        log.info(f"  Exclude komoditas: {EXCLUDE_KOMODITAS}")

    # Drop komoditas tanpa kategori (kemungkinan data scraping error)
    no_kategori = df[df['kategori'].isna() | (df['kategori'].str.strip() == '')]['komoditas'].unique()
    if len(no_kategori) > 0:
        log.warning(f"  Komoditas tanpa kategori (di-skip): {list(no_kategori)}")
        df = df[~df['komoditas'].isin(no_kategori)]

    after = df['komoditas'].nunique()
    log.info(f"  Filter: {before} → {after} komoditas")
    return df

# ─────────────────────────────────────────────────────────────
# 3. KONVERSI HARGA 0 → NaN
# ─────────────────────────────────────────────────────────────

def zero_to_nan(df: pd.DataFrame) -> pd.DataFrame:
    mask = df['harga_per_kg'] <= 0
    n_zero = mask.sum()
    if n_zero > 0:
        df = df.copy()
        df.loc[mask, 'harga_per_kg'] = np.nan
        log.info(f"  Konversi harga ≤0 → NaN: {n_zero} baris")
        # Log per komoditas
        per_komo = df[mask].groupby('komoditas').size()
        for k, n in per_komo.items():
            log.info(f"    {k}: {n} baris")
    else:
        log.info("  Tidak ada harga ≤0")
    return df

# ─────────────────────────────────────────────────────────────
# 4. FILL NaN BERDASARKAN KATEGORI
# ─────────────────────────────────────────────────────────────

def fill_missing(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df['tanggal_data'] = pd.to_datetime(df['tanggal_data'])
    df = df.sort_values(['komoditas', 'tanggal_data'])

    total_filled_interp = 0
    total_filled_ffill  = 0

    results = []
    for komoditas, group in df.groupby('komoditas'):
        group = group.copy().set_index('tanggal_data')
        kategori = group['kategori'].iloc[0].strip().upper()
        n_nan = group['harga_per_kg'].isna().sum()

        if n_nan == 0:
            results.append(group.reset_index())
            continue

        if kategori in KATEGORI_INTERPOLASI:
            # Interpolasi linear — cocok untuk barang musiman
            group['harga_per_kg'] = (
                group['harga_per_kg']
                .interpolate(method='linear', limit_direction='both')
            )
            total_filled_interp += n_nan
            log.info(f"  [interpolasi] {komoditas} ({kategori}): {n_nan} NaN diisi")

        elif kategori in KATEGORI_FFILL:
            # Forward fill → backward fill untuk ujung awal
            group['harga_per_kg'] = (
                group['harga_per_kg']
                .ffill()
                .bfill()
            )
            total_filled_ffill += n_nan
            log.info(f"  [ffill+bfill] {komoditas} ({kategori}): {n_nan} NaN diisi")

        else:
            log.warning(f"  [SKIP] {komoditas}: kategori '{kategori}' tidak dikenal")

        results.append(group.reset_index())

    df_filled = pd.concat(results, ignore_index=True)
    log.info(f"  Total interpolasi: {total_filled_interp} | ffill: {total_filled_ffill}")
    return df_filled

# ─────────────────────────────────────────────────────────────
# 5. IQR CLIPPING (outlier)
# ─────────────────────────────────────────────────────────────

def iqr_clip(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    n_clipped = 0
    for komoditas, group in df.groupby('komoditas'):
        q1, q3 = group['harga_per_kg'].quantile([0.25, 0.75])
        iqr = q3 - q1
        lower, upper = q1 - 1.5 * iqr, q3 + 1.5 * iqr
        mask = df['komoditas'] == komoditas
        clipped = ((df.loc[mask, 'harga_per_kg'] < lower) |
                   (df.loc[mask, 'harga_per_kg'] > upper)).sum()
        df.loc[mask & (df['harga_per_kg'] < lower), 'harga_per_kg'] = lower
        df.loc[mask & (df['harga_per_kg'] > upper), 'harga_per_kg'] = upper
        n_clipped += clipped
    log.info(f"  IQR clipping: {n_clipped} nilai di-clip")
    return df

# ─────────────────────────────────────────────────────────────
# 6. EXPORT
# ─────────────────────────────────────────────────────────────

def export(df: pd.DataFrame, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    df_export = (df[['tanggal_data', 'komoditas', 'kategori', 'harga_per_kg']]
                 .rename(columns={'tanggal_data': 'tanggal'}))
    df_export.to_csv(output_path, index=False)
    log.info(f"✅ Export: {output_path} — {len(df_export):,} baris | {df_export['komoditas'].nunique()} komoditas")

# ─────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────

def main():
    log.info("=" * 60)
    log.info("  DATA CLEANING PIPELINE — MarketCast")
    log.info("=" * 60)

    output_path = Path("data/processed/harga_historis_clean.csv")

    # Pipeline
    df = load_from_neon()
    df = filter_invalid(df)
    df = zero_to_nan(df)

    nan_before = df['harga_per_kg'].isna().sum()
    log.info(f"\n── Fill Missing Values ({nan_before} NaN total) ──")
    df = fill_missing(df)

    nan_after = df['harga_per_kg'].isna().sum()
    if nan_after > 0:
        log.warning(f"  ⚠️ Masih ada {nan_after} NaN setelah fill — periksa kategori")

    log.info("\n── IQR Clipping ──")
    df = iqr_clip(df)

    log.info("\n── Export ──")
    export(df, output_path)

    log.info("=" * 60)
    log.info("  Selesai. Jalankan clustering.py dengan:")
    log.info(f"  --csv-path {output_path} --source csv")
    log.info("=" * 60)

if __name__ == "__main__":
    main()
