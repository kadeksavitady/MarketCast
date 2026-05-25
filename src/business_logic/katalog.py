from sqlalchemy import text
from src.core.config import engine, logger

WHITELIST_MAP = {
    'Beras Premium': 'BERAS', 'Beras Medium': 'BERAS',
    'Gula Kristal Putih': 'GULA',
    'Minyak Goreng Curah': 'MINYAK GORENG', 'Minyak Goreng Kemasan Premium': 'MINYAK GORENG',
    'Minyak Goreng Kemasan Sederhana': 'MINYAK GORENG', 'Minyak Goreng MINYAKITA': 'MINYAK GORENG',
    'Daging Sapi Paha Belakang': 'DAGING', 'Daging Ayam Ras': 'DAGING', 'Daging Ayam Kampung': 'DAGING',
    'Telur Ayam Ras': 'TELUR', 'Telur Ayam Kampung': 'TELUR',
    'Susu Kental Manis Merk Bendera': 'SUSU', 'Susu Kental Manis Merk Indomilk': 'SUSU',
    'Susu Bubuk Merk Bendera (Instant)': 'SUSU', 'Susu Bubuk Merk Indomilk (Instant)': 'SUSU',
    'Jagung Pipilan Kering': 'PALAWIJA', 'Kedelai Impor': 'PALAWIJA', 'Kedelai Lokal': 'PALAWIJA',
    'KACANG HIJAU': 'PALAWIJA', 'KACANG TANAH': 'PALAWIJA', 'KETELA POHON': 'PALAWIJA',
    'Bata': 'GARAM', 'Halus': 'GARAM',
    'Terigu Protein Sedang (Kemasan)': 'TEPUNG',
    'Indomie Rasa Kari Ayam': 'MIE INSTAN',
    'Cabe Merah Keriting': 'CABE', 'Cabe Merah Besar': 'CABE', 'Cabe Rawit Merah': 'CABE',
    'Bawang Merah': 'BAWANG', 'Bawang Putih Sinco/Honan': 'BAWANG',
    'Ikan Asin Teri': 'IKAN ASIN',
    'KOL/KUBIS': 'SAYUR MAYUR', 'KENTANG': 'SAYUR MAYUR', 'Tomat Merah': 'SAYUR MAYUR',
    'WORTEL': 'SAYUR MAYUR', 'BUNCIS': 'SAYUR MAYUR',
    'Ikan Bandeng': 'IKAN SEGAR', 'Ikan Kembung': 'IKAN SEGAR', 'Ikan Tuna': 'IKAN SEGAR',
    'Ikan Tongkol': 'IKAN SEGAR', 'Ikan Cakalang': 'IKAN SEGAR',
    'GAS ELPIGI 3 Kg': 'BARANG PENTING LAINNYA'
}

# cluster 1 adalah Labil & Murah (→Datar)
# cluster 2 adalah Labil & Murah (↑Inflasi)
# cluster 3 adalah Stabil & Mahal (→Datar)
CLUSTER_MAP = {
    'Daging Ayam Kampung': 'cluster 3',
    'Daging Sapi Paha Belakang': 'cluster 3',
    'Ikan Asin Teri': 'cluster 3',
    'Susu Bubuk Merk Bendera (Instant)': 'cluster 3',
    'Susu Bubuk Merk Indomilk (Instant)': 'cluster 3',
    'BUNCIS': 'cluster 2',
    'Garam Bata': 'cluster 2',
    'Bawang Merah': 'cluster 2',
    'Bawang Putih Sinco/Honan': 'cluster 2',
    'Beras Medium': 'cluster 2',
    'Beras Premium': 'cluster 2',
    'Daging Ayam Ras': 'cluster 2',
    'GAS ELPIGI 3 Kg': 'cluster 2',
    'Gula Kristal Putih': 'cluster 2',
    'Garam Halus': 'cluster 2',
    'Ikan Bandeng': 'cluster 2',
    'Ikan Cakalang': 'cluster 2',
    'Ikan Kembung': 'cluster 2',
    'Ikan Tongkol': 'cluster 2',
    'Ikan Tuna': 'cluster 2',
    'Indomie Rasa Kari Ayam': 'cluster 2',
    'Jagung Pipilan Kering': 'cluster 2',
    'KACANG HIJAU': 'cluster 2',
    'KACANG TANAH': 'cluster 2',
    'KENTANG': 'cluster 2',
    'KETELA POHON': 'cluster 2',
    'KENTANG': 'cluster 2',
    'KOL/KUBIS': 'cluster 2',
    'Kedelai Impor': 'cluster 2',
    'Kedelai Lokal': 'cluster 2',
    'Minyak Goreng Curah': 'cluster 2',
    'Minyak Goreng Kemasan Premium': 'cluster 2',
    'Minyak Goreng Kemasan Sederhana': 'cluster 2',
    'Minyak Goreng MINYAKITA': 'cluster 2',
    'Susu Kental Manis Merk Bendera': 'cluster 2',
    'Susu Kental Manis Merk Indomilk': 'cluster 2',
    'Telur Ayam Kampung': 'cluster 2',
    'Telur Ayam Ras': 'cluster 2',
    'Terigu Protein Sedang (Kemasan)': 'cluster 2',
    'WORTEL': 'cluster 2',
    'Cabe Merah Besar': 'cluster 1',
    'Cabe Merah Keriting': 'cluster 1',
    'Cabe Rawit Merah': 'cluster 1',
    'Tomat Merah': 'cluster 1',
}

COMMODITY_CATALOG = {}
for nama, kategori in WHITELIST_MAP.items():
    slug = nama.lower().replace(" ", "_").replace("/", "_").replace("(", "").replace(")", "")
    id_cluster = CLUSTER_MAP.get(nama, 'cluster_1')

    # --- PERBAIKAN: Tentukan satuan berdasarkan nama barang ---
    nama_lower = nama.lower()
    if "elpigi" in nama_lower:
        satuan_item = "Tabung 3kg"
    elif "susu kental manis" in nama_lower:
        satuan_item = "Kaleng"
    elif "garam" in nama_lower and "bata" in nama_lower:
        satuan_item = "Bata"
    elif "mie instan" in nama_lower:
        satuan_item = "Bungkus"
    else:
        satuan_item = "kg" # Default untuk beras, daging, sayur, dll

    # --- Masukkan ke dalam katalog ---
    COMMODITY_CATALOG[slug] = {
        "nama": nama, 
        "kategori": kategori,
        "satuan": satuan_item, # 🚨 Gunakan variabel yang sudah difilter
        "faktor_konversi": 1.0, 
        "harga_ref": 0, 
        "cluster": id_cluster
    }

def load_harga_terkini():
    """Ambil harga dan satuan terbaru per komoditas dari Neon saat startup"""
    if not engine: return
    try:
        with engine.connect() as conn:
            rows = conn.execute(text("""
                SELECT DISTINCT ON (komoditas) komoditas, harga_per_kg, satuan_original, faktor_konversi
                FROM harga_historis
                WHERE harga_per_kg > 0
                ORDER BY komoditas, tanggal_data DESC
            """)).fetchall()
        
        matched_count = 0
        for row in rows:
            nama_dari_db = str(row[0]).strip().lower()
            harga_kg = float(row[1])
            satuan_orig = str(row[2]) if row[2] else "kg"
            faktor = float(row[3]) if (row[3] and float(row[3]) > 0) else 1.0

            db_clean = "".join(c for c in nama_dari_db if c.isalnum())

            for slug, info in COMMODITY_CATALOG.items():
                nama_di_katalog = info["nama"].strip().lower()
                katalog_clean = "".join(c for c in nama_di_katalog if c.isalnum())
                
                if (katalog_clean == db_clean) or (katalog_clean in db_clean) or (db_clean in katalog_clean):
                    COMMODITY_CATALOG[slug]["harga_ref"] = int(harga_kg)
                    COMMODITY_CATALOG[slug]["satuan"] = satuan_orig
                    COMMODITY_CATALOG[slug]["faktor_konversi"] = faktor
                    matched_count += 1
                    break

        logger.info(f"Harga terkini berhasil dimuat untuk {len(rows)} komoditas")
    except Exception as e:
        logger.warning(f"Gagal load harga terkini: {e}")