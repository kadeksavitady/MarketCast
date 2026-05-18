import asyncio
import logging
import os
import re
from datetime import date
from sqlalchemy import create_engine, text
import pandas as pd
from playwright.async_api import async_playwright

# --- KONFIGURASI ---
POSTGRE_URL = os.getenv("DATABASE_URL", "postgresql://neondb_owner:npg_pSmfVRDaG4P6@ep-little-star-aokx0s6c.c-2.ap-southeast-1.aws.neon.tech/neondb?sslmode=require")
BASE_URL    = "https://siskaperbapo.jatimprov.go.id/harga/tabel"
TIMEOUT_MS  = 60_000  # ← TAMBAHAN: definisi timeout

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

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("MarketCast-Daily")

def clean_name_daily(name):
    if not name: return ""
    return re.sub(r'^[0-9\s\.\-]+', '', str(name)).strip()

def parse_harga(text):
    if not text: return None
    text = text.strip()
    if text in ("-", "0", ""): return None
    text_main = text.split(',')[0]
    cleaned = re.sub(r"[^\d]", "", text_main)
    try: return float(cleaned)
    except: return None

async def scrape_harian_mandiri(page, tgl):
    tgl_str = tgl.strftime("%Y-%m-%d")
    rows_data = []

    try:
        log.info(f"🌐 Membuka halaman Siskaperbapo untuk {tgl_str}...")
        await page.goto(BASE_URL, wait_until="networkidle", timeout=TIMEOUT_MS)

        # 1. Injeksi Tanggal — tunggu elemen muncul dulu
        date_input = await page.wait_for_selector("input[name='tanggal']", timeout=TIMEOUT_MS)
        await date_input.evaluate(f"""
            (el) => {{
                el.value = '{tgl_str}';
                el.dispatchEvent(new Event('input', {{ bubbles: true }}));
                el.dispatchEvent(new Event('change', {{ bubbles: true }}));
            }}
        """)  # ← TAMBAHAN: isi evaluate yang sebelumnya kosong

        # 2. Pilih Surabaya
        await page.wait_for_selector("select[name='kabkota']", timeout=TIMEOUT_MS)
        await page.select_option("select[name='kabkota']", label="Kota Surabaya")

        # 3. Klik Tampilkan
        btn = await page.wait_for_selector("button:has-text('Tampilkan')", timeout=TIMEOUT_MS)
        await btn.click()

        # 4. Tunggu tabel muncul
        await page.wait_for_selector('table', timeout=15000)

        # 5. Parsing Tabel
        baris_html = await page.query_selector_all("table tbody tr")

        for row in baris_html:
            cells = await row.query_selector_all("td")
            if len(cells) < 5: continue

            vals = [(await c.inner_text()).strip() for c in cells]
            nama_bersih = clean_name_daily(vals[1])

            if nama_bersih in WHITELIST_MAP:
                harga = parse_harga(vals[4])
                if harga:
                    rows_data.append({
                        'tanggal_data': tgl_str,
                        'komoditas': nama_bersih,
                        'satuan': vals[2],
                        'harga': harga,
                        'kategori': WHITELIST_MAP[nama_bersih]
                    })

        log.info(f"✓ {len(rows_data)} komoditas ditemukan.")
        return rows_data

    except Exception as e:
        log.error(f"❌ Detail Error Scrape: {e}")
        return []

async def job_update_harian():
    hari_ini = date.today()
    log.info(f"🚀 Memulai Pipeline Harian: {hari_ini}")

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        )
        page = await context.new_page()
        await page.route("**/*.{png,jpg,jpeg,gif,svg,css,woff,woff2}", lambda r: r.abort())

        try:
            data_rows = await scrape_harian_mandiri(page, hari_ini)

            if data_rows:
                df = pd.DataFrame(data_rows)
                engine = create_engine(POSTGRE_URL)

                # Buat tabel kalau belum ada
                with engine.begin() as conn:
                    conn.execute(text("""
                        CREATE TABLE IF NOT EXISTS harga_historis (
                            id           SERIAL PRIMARY KEY,
                            tanggal_data DATE NOT NULL,
                            komoditas    TEXT NOT NULL,
                            satuan       TEXT,
                            harga        NUMERIC,
                            kategori     TEXT,
                            created_at   TIMESTAMP DEFAULT NOW(),
                            UNIQUE (tanggal_data, komoditas)
                        )
                    """))

                # Upsert aman — skip kalau tanggal+komoditas sudah ada
                with engine.begin() as conn:
                    for _, row in df.iterrows():
                        conn.execute(text("""
                            INSERT INTO harga_historis (tanggal_data, komoditas, satuan, harga, kategori)
                            VALUES (:tanggal_data, :komoditas, :satuan, :harga, :kategori)
                            ON CONFLICT (tanggal_data, komoditas) DO NOTHING
                        """), row.to_dict())

                log.info(f"✅ SUKSES! {len(df)} data berhasil dikirim ke Neon.")
            else:
                log.warning("⚠️ Tidak ada data yang berhasil ditarik hari ini.")

        except Exception as e:
            log.error(f"❌ Gagal Menjalankan Job: {e}")
        finally:
            await browser.close()

if __name__ == "__main__":
    asyncio.run(job_update_harian())