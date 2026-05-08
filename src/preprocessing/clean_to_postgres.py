import sqlite3
import pandas as pd
from sqlalchemy import create_engine
import re
import os
from dotenv import load_dotenv

# --- KONFIGURASI ---
load_dotenv()

DB_USER = os.getenv("DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD")
DB_HOST = "127.0.0.1"
DB_PORT = os.getenv("DB_PORT")
DB_NAME = os.getenv("DB_NAME")

POSTGRE_URL = f"postgresql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
SQLITE_PATH = "data/raw/siskaperbapo.db"
PROCESSED_PATH = "data/processed/harga_historis.csv"

# --- KAMUS KONVERSI SATUAN KE KG ---
# Semua harga akan dibagi dengan angka ini agar menjadi harga/kg
SATUAN_KONVERSI = {
    "kg": 1.0,
    "1 liter": 0.92,      # Densitas minyak goreng
    "370 gr/kl": 0.370,   # Susu kental manis
    "400 gr/dos": 0.400,  # Susu bubuk
    "bungkus": 0.085,     # Indomie (85gr)
    "ekor": 1.0           # Estimasi Ayam Kampung (1kg/ekor)
}

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

CATEGORY_MAP = {
    'Beras Premium': 'BERAS', 'Beras Medium': 'BERAS', 'Gula Kristal Putih': 'GULA',
    'Minyak Goreng Curah': 'MINYAK GORENG', 'Minyak Goreng Kemasan Premium': 'MINYAK GORENG',
    'Minyak Goreng Kemasan Sederhana': 'MINYAK GORENG', 'Minyak Goreng MINYAKITA': 'MINYAK GORENG',
    'Daging Sapi Paha Belakang': 'DAGING', 'Daging Ayam Ras': 'DAGING', 'Daging Ayam Kampung': 'DAGING',
    'Telur Ayam Ras': 'TELUR', 'Telur Ayam Kampung': 'TELUR',
    'Susu Kental Manis Merk Bendera': 'SUSU', 'Susu Kental Manis Merk Indomilk': 'SUSU',
    'Susu Bubuk Merk Bendera (Instant)':'SUSU', 'Susu Bubuk Merk Indomilk (Instant)':'SUSU',
    'Jagung Pipilan Kering': 'PALAWIJA', 'Kedelai Impor': 'PALAWIJA', 'Kedelai Lokal': 'PALAWIJA',
    'Kacang Hijau': 'PALAWIJA', 'Kacang Tanah': 'PALAWIJA', 'Ketela Pohon': 'PALAWIJA',
    'Garam Bata': 'GARAM', 'Garam Halus': 'GARAM', 'Terigu Protein Sedang (Kemasan)': 'TEPUNG',
    'Indomie Rasa Kari Ayam': 'MIE INSTAN',
    'Cabe Merah Keriting': 'CABE', 'Cabe Merah Besar': 'CABE', 'Cabe Rawit Merah': 'CABE',
    'Bawang Merah': 'BAWANG', 'Bawang Putih Sinco/Honan': 'BAWANG', 'Ikan Asin Teri': 'IKAN ASIN',
    'Kol/Kubis': 'SAYUR MAYUR', 'Kentang': 'SAYUR MAYUR', 'Tomat Merah': 'SAYUR MAYUR',
    'Wortel': 'SAYUR MAYUR', 'Buncis': 'SAYUR MAYUR',
    'Ikan Bandeng': 'IKAN SEGAR', 'Ikan Kembung': 'IKAN SEGAR', 'Ikan Tuna': 'IKAN SEGAR',
    'Ikan Tongkol': 'IKAN SEGAR', 'Ikan Cakalang': 'IKAN SEGAR', 'Gas Elpiji 3 Kg': 'BARANG PENTING LAINNYA'
}

WHITELIST_LOWER_MAP = {item.lower(): item for item in WHITELIST_ITEMS}

def clean_komoditas_name(name):
    if not name: return ""
    cleaned = re.sub(r'^[0-9\s\-]+', '', str(name)).strip()
    cleaned = re.sub(r'\s+', ' ', cleaned)
    return cleaned

def preprocess_and_migrate(dry_run=True):
    print("🚀 Memulai pembersihan & standardisasi data...")
    
    if not os.path.exists(SQLITE_PATH):
        print(f"❌ Database mentah tidak ditemukan!")
        return

    # 1. Load Data
    conn = sqlite3.connect(SQLITE_PATH)
    df = pd.read_sql("SELECT * FROM harga_bahan_pokok", conn)
    conn.close()

    # 2. Pembersihan Dasar
    df['komoditas_clean'] = df['komoditas'].apply(clean_komoditas_name)
    df['komoditas_lower'] = df['komoditas_clean'].str.lower()

    # 3. Filter Whitelist & Harga Positif
    df_filtered = df[
        (df['komoditas_lower'].isin(WHITELIST_LOWER_MAP.keys())) & 
        (df['harga_rp'] > 0)
    ].copy()

    # 4. Standardisasi Satuan ke KG (Logika Baru dari Clustering)
    print("⚖️ Melakukan standardisasi satuan ke kilogram...")
    df_filtered['satuan_clean'] = df_filtered['satuan'].str.lower().str.strip()
    
    # Map faktor konversi, default ke 1.0 jika tidak ada di kamus
    df_filtered['faktor_konversi'] = df_filtered['satuan_clean'].map(SATUAN_KONVERSI).fillna(1.0)
    
    # Hitung harga per kg
    df_filtered['harga_per_kg'] = df_filtered['harga_rp'] / df_filtered['faktor_konversi']

    # 5. Penataan Kolom Final
    df_filtered['komoditas'] = df_filtered['komoditas_lower'].map(WHITELIST_LOWER_MAP)
    df_filtered['kategori'] = df_filtered['komoditas'].map(CATEGORY_MAP)
    df_filtered['tanggal_data'] = pd.to_datetime(df_filtered['tanggal_data'])
    
    # Hapus kolom temporer
    cols_to_keep = ['tanggal_data', 'komoditas', 'kategori', 'harga_per_kg', 'satuan_clean', 'faktor_konversi']
    df_final = df_filtered[cols_to_keep].copy()
    df_final = df_final.rename(columns={'satuan_clean': 'satuan_original'})

    # 6. Hapus Duplikat
    df_final = df_final.drop_duplicates(subset=['tanggal_data', 'komoditas'], keep='last')
    df_final = df_final.sort_values(['komoditas', 'tanggal_data'])

    # 7. Simpan CSV & Migrasi
    os.makedirs(os.path.dirname(PROCESSED_PATH), exist_ok=True)
    df_final.to_csv(PROCESSED_PATH, index=False)
    print(f"📂 File berhasil disimpan ke: {PROCESSED_PATH}")

    if not dry_run:
        try:
            engine = create_engine(POSTGRE_URL)
            # Tabel 'harga_historis' sekarang berisi harga yang sudah ter-standardisasi
            df_final.to_sql('harga_historis', engine, if_exists='replace', index=False)
            print("🏁 Migrasi ke PostgreSQL (Harga per KG) berhasil!")
        except Exception as e:
            print(f"❌ Gagal migrasi: {e}")

if __name__ == "__main__":
    preprocess_and_migrate(dry_run=False)