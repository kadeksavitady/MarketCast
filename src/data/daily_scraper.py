from bs4 import BeautifulSoup
import re, logging, os, sys
from datetime import date, timedelta
from sqlalchemy import create_engine, text
from dotenv import load_dotenv
import requests

load_dotenv()

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

POSTGRE_URL = os.getenv("DATABASE_URL")
TABEL_URL   = "https://siskaperbapo.jatimprov.go.id/harga/tabel.nodesign/"
SCRAPER_API_KEY = os.getenv("SCRAPER_API_KEY")


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

# ── CORE SCRAPER HARIAN ──
async def scrape_harian(page, tgl_str):
    rows_data = []
    try:
        log.info(f"🌐 Membuka Siskaperbapo untuk {tgl_str}...")
        await page.goto(BASE_URL, wait_until="networkidle", timeout=TIMEOUT_MS)

        date_input = await page.wait_for_selector("input[name='tanggal']", timeout=TIMEOUT_MS)
        await date_input.evaluate(f"""
            (el) => {{
                el.value = '{tgl_str}';
                el.dispatchEvent(new Event('input', {{ bubbles: true }}));
                el.dispatchEvent(new Event('change', {{ bubbles: true }}));
            }}
        """)

        area_el = await page.query_selector("select[name='kabkota']")
        if area_el: await area_el.select_option(label="Kota Surabaya")

        btn = await page.query_selector("button:has-text('Tampilkan')")
        await btn.click()

        # ==========================================
        # 1. Tunggu respons tabel
        try:
            await page.wait_for_selector('table tbody tr', state='visible', timeout=15000)
        except Exception:
            log.warning("[!] Tabel merespon lambat...")
            await page.wait_for_timeout(3000)
            
        # 2. Paksa "Show Entries" ke 100
        try:
            dropdown = await page.query_selector('select[name$="length"]')
            if dropdown: 
                await dropdown.select_option(value='100')
                await page.wait_for_timeout(2000)
        except: pass
        
        # 3. Paksa Scroll ke Bawah
        await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        await page.wait_for_timeout(1000)
        # ==========================================

        baris_html = await page.query_selector_all("table tbody tr")

        for row in baris_html:
            cells = await row.query_selector_all("td")
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
    log.info(f"🚀 Memulai Pipeline Otomatis Harian: {hari_ini}")

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-setuid-sandbox", "--disable-blink-features=AutomationControlled"]
        )
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            viewport={'width': 1920, 'height': 1080}
        )
        page = await context.new_page()
        await page.route("**/*.{png,jpg,jpeg,gif,svg,css,woff,woff2}", lambda r: r.abort())

        try:
            data_rows = await scrape_harian(page, hari_ini)

    if data_rows:
        push_ke_neon(data_rows, hari_ini)
    else:
        log.error("❌ Tidak ada data hari ini. Pipeline dianggap gagal.")
        sys.exit(1)

if __name__ == "__main__":
    main()