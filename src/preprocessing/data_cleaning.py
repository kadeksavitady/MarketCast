"""
src/preprocessing/data_cleaning.py
====================================
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
def get_db_engine():
    load_dotenv()
    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        raise EnvironmentError("DATABASE_URL tidak ditemukan di .env")
    return create_engine(db_url)

def load_from_neon(engine) -> pd.DataFrame:
    query = """
        SELECT tanggal_data, komoditas, kategori, harga_per_kg
        FROM harga_historis
        ORDER BY komoditas, tanggal_data
    """
    df = pd.read_sql(query, engine)
    log.info(f"Load dari Neon: {len(df):,} baris | {df['komoditas'].nunique()} komoditas")
    return df

def patch_kategori(df: pd.DataFrame) -> pd.DataFrame:
    """
    Menambal kategori yang kosong berdasarkan nama komoditas 
    hasil adaptasi dari query UPDATE SQL (menggunakan LOWER).
    """
    df = df.copy()
    
    # Mapping eksak 43 komoditas menggunakan huruf kecil semua (standar LOWER)
    kategori_map = {
        'beras premium': 'BERAS',
        'beras medium': 'BERAS',
        'gula kristal putih': 'GULA',
        'minyak goreng curah': 'MINYAK GORENG',
        'minyak goreng kemasan premium': 'MINYAK GORENG',
        'minyak goreng kemasan sederhana': 'MINYAK GORENG',
        'minyak goreng minyakita': 'MINYAK GORENG',
        'daging sapi paha belakang': 'DAGING',
        'daging ayam ras': 'DAGING',
        'daging ayam kampung': 'DAGING',
        'telur ayam ras': 'TELUR',
        'telur ayam kampung': 'TELUR',
        'susu kental manis merk bendera': 'SUSU',
        'susu kental manis merk indomilk': 'SUSU',
        'susu bubuk merk bendera (instant)': 'SUSU',
        'susu bubuk merk indomilk (instant)': 'SUSU',
        'jagung pipilan kering': 'PALAWIJA',
        'kedelai impor': 'PALAWIJA',
        'kedelai lokal': 'PALAWIJA',
        'kacang hijau': 'PALAWIJA',
        'kacang tanah': 'PALAWIJA',
        'ketela pohon': 'PALAWIJA',
        'bata': 'GARAM',
        'halus': 'GARAM',
        'terigu protein sedang (kemasan)': 'TEPUNG TERIGU',
        'indomie rasa kari ayam': 'MIE INSTAN',
        'cabe merah keriting': 'CABE',
        'cabe merah besar': 'CABE',
        'cabe rawit merah': 'CABE',
        'bawang merah': 'BAWANG',
        'bawang putih sinco/honan': 'BAWANG',
        'ikan asin teri': 'IKAN ASIN',
        'kol/kubis': 'SAYUR MAYUR',
        'kentang': 'SAYUR MAYUR',
        'tomat merah': 'SAYUR MAYUR',
        'wortel': 'SAYUR MAYUR',
        'buncis': 'SAYUR MAYUR',
        'ikan bandeng': 'IKAN SEGAR',
        'ikan kembung': 'IKAN SEGAR',
        'ikan tuna': 'IKAN SEGAR',
        'ikan tongkol': 'IKAN SEGAR',
        'ikan cakalang': 'IKAN SEGAR',
        'gas elpigi 3 kg': 'BARANG PENTING LAINNYA'
    }

    # Cari baris yang kategorinya kosong/null
    mask_kosong = df['kategori'].isna() | (df['kategori'].str.strip() == '')
    
    if mask_kosong.any():
        n_kosong = mask_kosong.sum()
        log.info(f"  [HOTFIX] Menambal {n_kosong:,} baris yang kategorinya kosong...")
        
        # Eksekusi mirip SQL: Ubah nama komoditas ke huruf kecil dulu (LOWER), baru dicocokkan (map)
        kategori_baru = df.loc[mask_kosong, 'komoditas'].str.lower().map(kategori_map)
        
        # Timpa ke dataframe utama (yang tidak match akan pakai nilai aslinya/NaN)
        df.loc[mask_kosong, 'kategori'] = kategori_baru.fillna(df.loc[mask_kosong, 'kategori'])
        
        # Cek apakah masih ada data bocor/gagal ter-map
        sisa_kosong = df['kategori'].isna() | (df['kategori'].str.strip() == '')
        if sisa_kosong.any():
            komo_gagal = df[sisa_kosong]['komoditas'].unique()
            log.warning(f"  ⚠️ Peringatan: Masih ada komoditas gagal ditambal kategorinya: {komo_gagal}")

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
        # Log pelacakan granular per komoditas
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
# 6. EXPORT: NEON DB (DATA) & MLFLOW (SCALER/METADATA)
# ─────────────────────────────────────────────────────────────
def export_results(df: pd.DataFrame, scalers_dict: dict, engine, uri: str) -> None:
    # ── PUSH DATA KE NEON DB ──
    try:
        log.info("  Mengirim data bersih ke tabel 'harga_historis_clean' di Neon PostgreSQL...")
        
        # Rapikan nama kolom (tanggal_data -> tanggal) agar seragam untuk pipeline selanjutnya
        df_export = df[['tanggal_data', 'komoditas', 'kategori', 'harga_per_kg', 'harga_scaled']].copy()
        df_export.rename(columns={'tanggal_data': 'tanggal'}, inplace=True)
        
        # if_exists='replace' akan menimpa tabel lama jika ada. Sangat aman untuk pipeline batch!
        df_export.to_sql('harga_historis_clean', engine, if_exists='replace', index=False)
        log.info(f"✅ Data bersih ({len(df_export):,} baris) berhasil disimpan ke Database!")
    except Exception as e:
        log.error(f"❌ Gagal push ke Database: {e}")
        return # Hentikan jika DB gagal, percuma lanjut ke MLflow

# ─────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────
def main():
    log.info("=" * 60)
    log.info("  DATA CLEANING PIPELINE — MarketCast")
    log.info("=" * 60)

    engine = get_db_engine()

    # Pipeline
    df = load_from_neon(engine)
    df = patch_kategori(df)
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

    log.info("\n── Exporting (Database) ──")
    export_results(df, engine)

    engine.dispose() # Putuskan koneksi DB dengan aman
    
    log.info("=" * 60)
    log.info("  Selesai. Jalankan clustering.py dengan:")
    log.info("  Data ada di Neon DB.")
    log.info("=" * 60)

if __name__ == "__main__":
    main()
