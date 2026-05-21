from sqlalchemy import text
from src.core.config import engine, logger

RAW_WHITELIST = {
    'Beras Premium': 'BERAS', 'Beras Medium': 'BERAS', 'Gula Kristal Putih': 'GULA',
    'Minyak Goreng Curah': 'MINYAK GORENG', 'Minyak Goreng Kemasan Premium': 'MINYAK GORENG',
    'Minyak Goreng Kemasan Sederhana': 'MINYAK GORENG', 'Minyak Goreng MINYAKITA': 'MINYAK GORENG',
    'Daging Sapi Paha Belakang': 'DAGING', 'Daging Ayam Ras': 'DAGING', 'Daging Ayam Kampung': 'DAGING',
    'Telur Ayam Ras': 'TELUR', 'Telur Ayam Kampung': 'TELUR',
    'Susu Kental Manis Merk Bendera': 'SUSU', 'Susu Kental Manis Merk Indomilk': 'SUSU',
    'Susu Bubuk Merk Bendera (Instant)': 'SUSU', 'Susu Bubuk Merk Indomilk (Instant)': 'SUSU',
    'Jagung Pipilan Kering': 'PALAWIJA', 'Kedelai Impor': 'PALAWIJA', 'Kedelai Lokal': 'PALAWIJA',
    'KACANG HIJAU': 'PALAWIJA', 'KACANG TANAH': 'PALAWIJA', 'KETELA POHON': 'PALAWIJA',
    'Bata': 'GARAM', 'Halus': 'GARAM', 'Terigu Protein Sedang (Kemasan)': 'TEPUNG',
    'Indomie Rasa Kari Ayam': 'MIE INSTAN', 'Cabe Merah Keriting': 'CABE',
    'Cabe Merah Besar': 'CABE', 'Cabe Rawit Merah': 'CABE', 'Bawang Merah': 'BAWANG',
    'Bawang Putih Sinco/Honan': 'BAWANG', 'Ikan Asin Teri': 'IKAN ASIN',
    'KOL/KUBIS': 'SAYUR MAYUR', 'KENTANG': 'SAYUR MAYUR', 'Tomat Merah': 'SAYUR MAYUR',
    'WORTEL': 'SAYUR MAYUR', 'BUNCIS': 'SAYUR MAYUR', 'Ikan Bandeng': 'IKAN SEGAR',
    'Ikan Kembung': 'IKAN SEGAR', 'Ikan Tuna': 'IKAN SEGAR', 'Ikan Tongkol': 'IKAN SEGAR',
    'Ikan Cakalang': 'IKAN SEGAR', 'GAS ELPIGI 3 Kg': 'BARANG PENTING LAINNYA',
}

COMMODITY_CATALOG = {}
for nama, kategori in RAW_WHITELIST.items():
    slug = nama.lower().replace(" ", "_").replace("/", "_").replace("(", "").replace(")", "")
    COMMODITY_CATALOG[slug] = {
        "nama": nama, "kategori": kategori,
        "satuan": "tabung" if kategori == "BARANG PENTING LAINNYA" else "kg",
        "harga_ref": 15000,
    }

def load_harga_terkini():
    """Ambil harga terbaru per komoditas dari Neon saat startup"""
    if not engine: return
    try:
        with engine.connect() as conn:
            rows = conn.execute(text("""
                SELECT DISTINCT ON (komoditas) komoditas, harga_per_kg
                FROM harga_historis ORDER BY komoditas, tanggal_data DESC
            """)).fetchall()
        
        for row in rows:
            nama, harga = row[0], float(row[1])
            for slug, info in COMMODITY_CATALOG.items():
                if info["nama"] == nama:
                    COMMODITY_CATALOG[slug]["harga_ref"] = int(harga)
                    break
        logger.info(f"Harga terkini berhasil dimuat untuk {len(rows)} komoditas")
    except Exception as e:
        logger.warning(f"Gagal load harga terkini: {e}")