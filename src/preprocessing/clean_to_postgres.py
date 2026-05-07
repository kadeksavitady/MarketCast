import sqlite3
import pandas as pd
from sqlalchemy import create_engine
import re
import os
from dotenv import load_dotenv

# --- KONFIGURASI ---
load_dotenv()  # Mengambil data dari file .env

DB_USER = os.getenv("DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD")
DB_HOST = "127.0.0.1"
DB_PORT = os.getenv("DB_PORT")
DB_NAME = os.getenv("DB_NAME")

# Gabungkan menjadi URL koneksi
POSTGRE_URL = f"postgresql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"

SQLITE_PATH = "data/raw/siskaperbapo.db"
PROCESSED_PATH = "data/processed/harga_historis.csv"

# 43 Komoditas Whitelist sesuai hasil diskusi tim 
WHITELIST_ITEMS = [
    'Beras Premium', 'Beras Medium', 'Gula Kristal Putih', 'Minyak Goreng Curah',
    'Minyak Goreng Kemasan Premium', 'Minyak Goreng Kemasan Sederhana', 'Minyak Goreng MINYAKITA',
    'Daging Sapi Paha Belakang', 'Daging Ayam Ras', 'Daging Ayam Kampung', 'Telur Ayam Ras',
    'Telur Ayam Kampung', 'Susu Kental Manis Merk Bendera', 'Susu Kental Manis Merk Indomilk',
    'Susu Bubuk Merk Bendera (Instant)', 'Susu Bubuk Merk Indomilk (Instant)', 'Jagung Pipilan Kering',
    'Garam Bata', 'Garam Halus', 'Terigu Protein Sedang (Kemasan)', 'Kedelai Impor', 'Kedelai Lokal',
    'Indomie Rasa Kari Ayam', 'Cabe Merah Keriting', 'Cabe Merah Besar', 'Cabe Rawit Merah',
    'Bawang Merah', 'Bawang Putih Sinco/Honan', 'Ikan Asin Teri', 'Kacang Hijau', 'Kacang Tanah',
    'Ketela Pohon', 'Kol/Kubis', 'Kentang', 'Tomat Merah', 'Wortel', 'Buncis',
    'Ikan Bandeng', 'Ikan Kembung', 'Ikan Tuna', 'Ikan Tongkol', 'Ikan Cakalang', 'Gas Elpiji 3 Kg'
]

# Pemetaan absolut komoditas ke kategorinya
CATEGORY_MAP = {
    'Beras Premium': 'BERAS', 'Beras Medium': 'BERAS',
    'Gula Kristal Putih': 'GULA',
    'Minyak Goreng Curah': 'MINYAK GORENG', 'Minyak Goreng Kemasan Premium': 'MINYAK GORENG',
    'Minyak Goreng Kemasan Sederhana': 'MINYAK GORENG', 'Minyak Goreng MINYAKITA': 'MINYAK GORENG',
    'Daging Sapi Paha Belakang': 'DAGING', 'Daging Ayam Ras': 'DAGING', 'Daging Ayam Kampung': 'DAGING',
    'Telur Ayam Ras': 'TELUR', 'Telur Ayam Kampung': 'TELUR',
    'Susu Kental Manis Merk Bendera': 'SUSU', 'Susu Kental Manis Merk Indomilk': 'SUSU',
    'Susu Bubuk Merk Bendera (Instant)': 'SUSU', 'Susu Bubuk Merk Indomilk (Instant)': 'SUSU',
    'Jagung Pipilan Kering': 'PALAWIJA', 'Kedelai Impor': 'PALAWIJA', 'Kedelai Lokal': 'PALAWIJA',
    'Kacang Hijau': 'PALAWIJA', 'Kacang Tanah': 'PALAWIJA', 'Ketela Pohon': 'PALAWIJA',
    'Garam Bata': 'GARAM', 'Garam Halus': 'GARAM',
    'Terigu Protein Sedang (Kemasan)': 'TEPUNG',
    'Indomie Rasa Kari Ayam': 'MIE INSTAN',
    'Cabe Merah Keriting': 'CABE', 'Cabe Merah Besar': 'CABE', 'Cabe Rawit Merah': 'CABE',
    'Bawang Merah': 'BAWANG', 'Bawang Putih Sinco/Honan': 'BAWANG',
    'Ikan Asin Teri': 'IKAN ASIN',
    'Kol/Kubis': 'SAYUR MAYUR', 'Kentang': 'SAYUR MAYUR', 'Tomat Merah': 'SAYUR MAYUR',
    'Wortel': 'SAYUR MAYUR', 'Buncis': 'SAYUR MAYUR',
    'Ikan Bandeng': 'IKAN SEGAR', 'Ikan Kembung': 'IKAN SEGAR', 'Ikan Tuna': 'IKAN SEGAR',
    'Ikan Tongkol': 'IKAN SEGAR', 'Ikan Cakalang': 'IKAN SEGAR',
    'Gas Elpiji 3 Kg': 'BARANG PENTING LAINNYA'
}

WHITELIST_LOWER_MAP = {item.lower(): item for item in WHITELIST_ITEMS}
CATEGORY_LOWER_MAP = {item.lower(): item for item in CATEGORY_MAP.keys()}

def clean_komoditas_name(name):
    """Membersihkan nomor, spasi, dan tanda hubung di awal teks secara agresif."""
    if not name: return ""
    # Regex ini menghapus semua angka, spasi, dan tanda hubung di AWAL string 
    cleaned = re.sub(r'^[0-9\s\-]+', '', str(name)).strip()
    cleaned = re.sub(r'\s+', ' ', cleaned) # Hapus spasi ganda di tengah kata
    return cleaned

def preprocess_and_migrate(dry_run=True):
    print("🚀 Memulai pembersihan data MarketCast...")
    
    if not os.path.exists(SQLITE_PATH):
        print(f"❌ Database mentah tidak ditemukan di {SQLITE_PATH}")
        return

    # 1. Load Data Mentah 
    conn = sqlite3.connect(SQLITE_PATH)
    df = pd.read_sql("SELECT * FROM harga_bahan_pokok", conn)
    conn.close()

    # 2. Pembersihan Nama dengan Fungsi yang Sudah Diperbaiki
    df['komoditas_clean'] = df['komoditas'].apply(clean_komoditas_name)
    
    # 3. Pengecekan Case-Insensitive (ubah sementara ke huruf kecil)
    df['komoditas_lower'] = df['komoditas_clean'].str.lower()

    # 4. Filter Whitelist: Hanya ambil 43 item pangan
    df_filtered = df[
        (df['komoditas_lower'].isin(WHITELIST_LOWER_MAP.keys())) & 
        (df['harga_rp'] > 0)
    ].copy()

    # 5. PEMBERSIHAN LANJUTAN & PENATAAN KOLOM
    # A. Kembalikan ke format baku (Title Case) di kolom komoditas_clean
    df_filtered['komoditas_clean'] = df_filtered['komoditas_lower'].map(WHITELIST_LOWER_MAP)
    
    # B. Hapus kolom yang sudah tidak dipakai (raw komoditas, lower, kabkota, created_at)
    df_filtered = df_filtered.drop(columns=['komoditas', 'komoditas_lower', 'kabkota', 'created_at'])

    # C. Rename kolom yang bersih menjadi nama standar untuk database
    df_filtered = df_filtered.rename(columns={
        'komoditas_clean': 'komoditas', 
        'harga_rp': 'harga'
    })

    # D. Standarisasi Satuan 
    df_filtered['satuan'] = df_filtered['satuan'].str.lower().str.strip()
    
    # E. Konversi Tanggal 
    df_filtered['tanggal_data'] = pd.to_datetime(df_filtered['tanggal_data'])
    
    # F. Hapus Duplikat 
    df_filtered = df_filtered.drop_duplicates(subset=['tanggal_data', 'komoditas'], keep='last')
    
    # G. Rapikan Kategori (Sekarang pasti berhasil karena 'komoditas' sudah Title Case lagi)
    df_filtered['kategori'] = df_filtered['komoditas'].map(CATEGORY_MAP)

    # 6. Sanity Check: Pastikan data tidak kosong
    print(f"🔍 Contoh data bersih: {df_filtered['komoditas'].unique()[:5]}")
    print(f"📊 Total data lolos filter: {len(df_filtered)} baris")

    if df_filtered.empty:
        print("⚠️ PERINGATAN: Data hasil filter KOSONG. Periksa kembali nama di WHITELIST_ITEMS.")
        return

    # 7. Simpan ke Interim 
    os.makedirs(os.path.dirname(PROCESSED_PATH), exist_ok=True)
    df_filtered.to_csv(PROCESSED_PATH, index=False)
    print(f"📂 File processed CSV berhasil dibuat di: {PROCESSED_PATH}")

    # 8. Migrasi ke PostgreSQL
    if not dry_run:
        try:
            engine = create_engine(POSTGRE_URL)
            # Sesuaikan nama tabel dengan ERD: 'harga_historis'
            df_filtered.to_sql('harga_historis', engine, if_exists='replace', index=False)
            print("🏁 Migrasi ke PostgreSQL berhasil!")
        except Exception as e:
            print(f"❌ Gagal migrasi: {e}")

if __name__ == "__main__":
    # Eksekusi migrasi nyata ke database
    preprocess_and_migrate(dry_run=False)