from bs4 import BeautifulSoup
import re, logging, os, sys
from datetime import date, timedelta
from sqlalchemy import create_engine, text
from dotenv import load_dotenv
import cloudscraper

load_dotenv()

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

POSTGRE_URL = os.getenv("DATABASE_URL")
TABEL_URL   = "https://siskaperbapo.jatimprov.go.id/harga/tabel.nodesign/"

if not POSTGRE_URL:
    print("❌ ERROR: DATABASE_URL tidak ditemukan!")
    sys.exit(1)

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
    'GAS ELPIGI 3 Kg': 'BARANG PENTING LAINNYA',
}
WHITELIST_LOWER  = {k.lower(): k for k in WHITELIST_MAP.keys()}
RENAME_KOMODITAS = {"Bata": "Garam Bata", "Halus": "Garam Halus"}
SATUAN_KONVERSI  = {
    "kg": 1.0, "1 liter": 0.92, "370 gr/kl": 0.370,
    "400 gr/dos": 0.400, "bungkus": 0.085, "ekor": 1.0
}

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("MarketCast-Daily")
engine = create_engine(POSTGRE_URL, pool_pre_ping=True, pool_recycle=300)

# ── UTILS ──
def parse_harga(teks):
    if not teks or teks.strip() in ("-", ""): return None
    cleaned = re.sub(r"[^\d]", "", teks.split(',')[0])
    try: return float(cleaned)
    except: return None

def fetch_dari_siskaperbapo(tgl_str):
    """Ambil data dari Siskaperbapo untuk tanggal tertentu."""
    try:
        scraper = cloudscraper.create_scraper(
            browser={"browser": "chrome", "platform": "windows", "mobile": False}
        )
        resp = scraper.post(
            TABEL_URL,
            data={"tanggal": tgl_str, "kabkota": "surabayakota", "pasar": ""},
            headers={
                "Origin":  "https://siskaperbapo.jatimprov.go.id",
                "Referer": "https://siskaperbapo.jatimprov.go.id/harga/tabel",
            },
            timeout=30
        )
        resp.raise_for_status()

        soup  = BeautifulSoup(resp.text, "html.parser")
        table = soup.find("table")
        if not table: return []

        rows_data = []
        for row in table.find_all("tr"):
            cells = row.find_all("td")
            if len(cells) < 5: continue
            span = cells[1].find("span", class_="price-tooltip-enabled")
            if not span: continue
            nama_mentah = span.get_text(strip=True).lower()
            if nama_mentah not in WHITELIST_LOWER: continue
            nama_asli  = WHITELIST_LOWER[nama_mentah]
            harga_raw  = parse_harga(cells[4].get_text(strip=True))
            satuan_raw = cells[2].get_text(strip=True).lower()
            if harga_raw is not None:
                faktor = SATUAN_KONVERSI.get(satuan_raw, 1.0)
                rows_data.append({
                    "tanggal_data":    tgl_str,
                    "komoditas":       RENAME_KOMODITAS.get(nama_asli, nama_asli),
                    "kategori":        WHITELIST_MAP[nama_asli],
                    "harga_per_kg":    round(harga_raw / faktor, 2) if faktor > 0 else harga_raw,
                    "satuan_original": satuan_raw,
                    "faktor_konversi": faktor,
                })
        return rows_data
    except Exception as e:
        log.error(f"❌ Gagal fetch {tgl_str}: {e}")
        return []

# ── CORE FUNCTIONS ──
def patch_zeros(tgl_str):
    """
    Cek data di Neon untuk tgl_str.
    Kalau ada harga 0, ambil data terbaru dari Siskaperbapo
    dan update yang sudah berubah jadi non-zero.
    """
    try:
        with engine.connect() as conn:
            zeros = conn.execute(text("""
                SELECT komoditas FROM harga_historis
                WHERE tanggal_data = :tgl AND harga_per_kg = 0
            """), {"tgl": tgl_str}).fetchall()
    except Exception as e:
        log.error(f"❌ Gagal cek zeros di Neon: {e}")
        return

    if not zeros:
        log.info(f"✅ Data {tgl_str} sudah lengkap, tidak ada yang perlu di-patch")
        return

    nama_zeros = {r[0] for r in zeros}
    log.info(f"🔍 {len(nama_zeros)} komoditas masih 0 pada {tgl_str}: {', '.join(sorted(nama_zeros))}")
    log.info(f"   Cek apakah sudah update di Siskaperbapo...")

    data_fresh = fetch_dari_siskaperbapo(tgl_str)
    if not data_fresh:
        log.warning(f"⚠️ Tidak bisa ambil data fresh untuk {tgl_str}, skip patch")
        return

    updated = 0
    try:
        with engine.begin() as conn:
            for row in data_fresh:
                # Hanya update kalau sebelumnya 0 DAN sekarang sudah non-zero
                if row["komoditas"] in nama_zeros and row["harga_per_kg"] > 0:
                    conn.execute(text("""
                        UPDATE harga_historis
                        SET harga_per_kg    = :harga,
                            satuan_original = :satuan,
                            faktor_konversi = :faktor
                        WHERE tanggal_data = :tgl
                          AND komoditas    = :komoditas
                    """), {
                        "harga":     row["harga_per_kg"],
                        "satuan":    row["satuan_original"],
                        "faktor":    row["faktor_konversi"],
                        "tgl":       tgl_str,
                        "komoditas": row["komoditas"],
                    })
                    updated += 1
    except Exception as e:
        log.error(f"❌ Gagal patch Neon: {e}")
        return

    if updated:
        log.info(f"✅ Patch sukses: {updated} komoditas diperbarui untuk {tgl_str}")
    else:
        log.info(f"ℹ️ Siskaperbapo {tgl_str} masih 0, belum ada update hari ini")

def push_ke_neon(data_rows, tgl_str):
    """Insert data baru (delete dulu kalau sudah ada)."""
    if not data_rows: return 0
    inserted = 0
    try:
        with engine.begin() as conn:
            conn.execute(
                text("DELETE FROM harga_historis WHERE tanggal_data = :tgl"),
                {"tgl": tgl_str}
            )
            for row in data_rows:
                try:
                    conn.execute(text("""
                        INSERT INTO harga_historis
                            (tanggal_data, komoditas, kategori, harga_per_kg,
                             satuan_original, faktor_konversi)
                        VALUES
                            (:tanggal_data, :komoditas, :kategori, :harga_per_kg,
                             :satuan_original, :faktor_konversi)
                    """), row)
                    inserted += 1
                except Exception as e:
                    log.warning(f"Gagal insert {row['komoditas']}: {e}")
        log.info(f"✅ {inserted} data masuk ke Neon untuk {tgl_str}")
        return inserted
    except Exception as e:
        log.error(f"❌ Transaksi Neon gagal: {e}")
        return 0

# ── MAIN ──
def main():
    kemarin  = (date.today() - timedelta(days=1)).strftime("%Y-%m-%d")
    hari_ini = date.today().strftime("%Y-%m-%d")

    log.info("=" * 50)
    log.info(f"🚀 MarketCast Daily Pipeline: {hari_ini}")
    log.info("=" * 50)

    # Step 1: Patch zeros dari kemarin kalau ada
    log.info(f"[Step 1] Cek & patch zeros untuk {kemarin}...")
    patch_zeros(kemarin)

    # Step 2: Scrape hari ini
    log.info(f"[Step 2] Scrape data hari ini: {hari_ini}...")
    data_rows = fetch_dari_siskaperbapo(hari_ini)
    nonzero   = sum(1 for r in data_rows if r["harga_per_kg"] > 0)
    log.info(f"   Dapat {len(data_rows)} komoditas | harga > 0: {nonzero}")

    if data_rows:
        push_ke_neon(data_rows, hari_ini)
    else:
        log.error("❌ Tidak ada data hari ini. Pipeline dianggap gagal.")
        sys.exit(1)

if __name__ == "__main__":
    main()