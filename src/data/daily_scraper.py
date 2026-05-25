"""
MARKETCAST - Final Production Daily Scraper (GITHUB ACTIONS READY)
Fitur:
- Fully Automated (Tanpa CLI Prompt) untuk CI/CD
- 3 Jurus Pasti Anti-Buta (100 Entries, Scroll, Wait)
- Standardisasi Skema DB (harga_per_kg, satuan_original, faktor_konversi)
- Idempotent Delete-Insert untuk Mencegah Duplikasi
"""

import asyncio
import logging
import os
import re
import sys
from datetime import date
from sqlalchemy import create_engine, text
from playwright.async_api import async_playwright
from dotenv import load_dotenv

load_dotenv()

# ── FIX ENCODING WINDOWS ──
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# ── KONFIGURASI ──
POSTGRE_URL = os.getenv("DATABASE_URL")
BASE_URL    = "https://siskaperbapo.jatimprov.go.id/harga/tabel"
TIMEOUT_MS  = 60_000 

if not POSTGRE_URL:
    print("❌ ERROR: DATABASE_URL tidak ditemukan di environment!")
    sys.exit(1)

# Skema Whitelist yang sama persis dengan Historical
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

WHITELIST_LOWER = {k.lower(): k for k in WHITELIST_MAP.keys()}

# ── RENAME DISPLAY NAME ──
RENAME_KOMODITAS = {
    "Bata":  "Garam Bata",
    "Halus": "Garam Halus",
}

SATUAN_KONVERSI = {
    "kg": 1.0, "1 liter": 0.92, "370 gr/kl": 0.370,
    "400 gr/dos": 0.400, "bungkus": 0.085, "ekor": 1.0
}

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("MarketCast-Daily")

engine = create_engine(POSTGRE_URL, pool_pre_ping=True, pool_recycle=300)

# ── PARSING UTILS ──
def normalisasi_nama(nama):
    if not nama: return ""
    cleaned = re.sub(r'^[\d\s\.\-]+', '', str(nama)).strip()
    return re.sub(r'\s+', ' ', cleaned)

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
        await page.goto(BASE_URL, wait_until="domcontentloaded", timeout=TIMEOUT_MS)

        date_input = await page.wait_for_selector("input[name='tanggal']")
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

            vals = [(await c.inner_text()).strip() for c in cells]
            nama_mentah = normalisasi_nama(vals[1]).lower()

            if nama_mentah in WHITELIST_LOWER:
                nama_asli = WHITELIST_LOWER[nama_mentah]
                harga_raw = parse_harga(vals[4])
                satuan_raw = vals[2].lower().strip()
                
                # Biarkan mengeksekusi biarpun harga_raw = 0 (untuk integritas 43 komoditas)
                if harga_raw is not None: 
                    faktor = SATUAN_KONVERSI.get(satuan_raw, 1.0)
                    harga_per_kg = round(harga_raw / faktor, 2) if faktor > 0 else harga_raw
                    
                    rows_data.append({
                        'tanggal_data': tgl_str,
                        'komoditas': RENAME_KOMODITAS.get(nama_asli, nama_asli),
                        'kategori': WHITELIST_MAP[nama_asli],
                        'harga_per_kg': harga_per_kg,
                        'satuan_original': satuan_raw,
                        'faktor_konversi': faktor
                    })

        return rows_data
    except Exception as e:
        log.error(f"❌ Error Scrape Harian: {e}")
        return []

# ── TRANSAKSI CLOUD NEON ──
def push_ke_neon(data_rows, tgl_str):
    if not data_rows:
        return 0
        
    inserted = 0
    log.info("☁️ Memulai migrasi data harian ke Neon Cloud...")
    try:
        with engine.begin() as conn:
            # 1. Hapus data hari ini jika sudah ada (Mencegah duplikasi saat di-run ulang)
            conn.execute(
                text("DELETE FROM harga_historis WHERE tanggal_data = :tgl"),
                {"tgl": tgl_str}
            )
            
            # 2. Masukkan data baru yang sudah terstandardisasi
            for row in data_rows:
                try:
                    conn.execute(text("""
                        INSERT INTO harga_historis 
                            (tanggal_data, komoditas, kategori, harga_per_kg, satuan_original, faktor_konversi)
                        VALUES 
                            (:tanggal_data, :komoditas, :kategori, :harga_per_kg, :satuan_original, :faktor_konversi)
                    """), row)
                    inserted += 1
                except Exception as e:
                    log.warning(f"Gagal upload {row['komoditas']}: {e}")
                    
        log.info(f"✅ SINKRONISASI SUKSES! {inserted} data harian mendarat di Neon Singapore.")
        return inserted
    except Exception as e:
        log.error(f"❌ Transaksi Neon Gagal: {e}")
        return 0

async def job_update_harian():
    hari_ini = date.today().strftime("%Y-%m-%d")
    log.info(f"🚀 Memulai Pipeline Otomatis Harian: {hari_ini}")

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            viewport={'width': 1920, 'height': 1080}
        )
        page = await context.new_page()
        await page.route("**/*.{png,jpg,jpeg,gif,svg,css,woff,woff2}", lambda r: r.abort())

        try:
            data_rows = await scrape_harian(page, hari_ini)

            if data_rows:
                log.info(f"📊 Berhasil menarik {len(data_rows)} data. Langsung memompa ke Cloud...")
                # LANGSUNG DI-PUSH KE NEON TANPA VALIDASI (Otomatisasi Penuh)
                push_ke_neon(data_rows, hari_ini)
            else:
                log.warning("⚠️ Data kosong hari ini (kemungkinan server siskaperbapo error/libur).")

        except Exception as e:
            log.error(f"❌ Pipeline Gagal: {e}")
        finally:
            await browser.close()

if __name__ == "__main__":
    asyncio.run(job_update_harian())