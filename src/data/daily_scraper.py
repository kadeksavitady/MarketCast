import asyncio
import logging
import os
import re
from datetime import date
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from sqlalchemy import create_engine
import pandas as pd
from playwright.async_api import async_playwright

# --- KONFIGURASI PRODUKSI (DOCKER) ---
# Di Docker, host-nya adalah 'db'. 
# Catatan: Kalau dijalankan di GitHub Actions, URL ini harus diubah atau pakai environment variable!
POSTGRE_URL = os.getenv("DATABASE_URL", "postgresql://postgres:marketcast_pbl@db:5432/marketcast_db")
BASE_URL = "https://siskaperbapo.jatimprov.go.id/harga/tabel"

# 43 Item sesuai kesepakatan tim
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
log = logging.getLogger("MarketCast-Automation")

def clean_name_daily(name):
    """Sama dengan preprocess.py agar data konsisten."""
    if not name: return ""
    cleaned = re.sub(r'^[0-9\s\-]+', '', str(name)).strip()
    return cleaned

def parse_harga(text):
    if not text or text.strip() in ("-", "0", ""): return None
    cleaned = re.sub(r"[^\d]", "", text)
    try: return float(cleaned)
    except: return None

async def scrape_harian_mandiri(page, tgl):
    """Fungsi ekstraksi data mandiri khusus untuk daily_scraper"""
    tgl_str = tgl.strftime("%Y-%m-%d")
    rows_data = []
    
    try:
        await page.goto(BASE_URL, wait_until="domcontentloaded", timeout=60000)
        
        # 1. Bypass Tanggal dengan JS Evaluation
        date_input = await page.query_selector("input[name='tanggal']")
        await date_input.evaluate(f"""
            (el) => {{
                el.value = '{tgl_str}';
                el.dispatchEvent(new Event('input', {{ bubbles: true }}));
                el.dispatchEvent(new Event('change', {{ bubbles: true }}));
            }}
        """)
        
        # 2. Set Area Kota Surabaya
        area_el = await page.query_selector("select[name='kabkota']")
        if area_el: await area_el.select_option(label="Kota Surabaya")
            
        # 3. Eksekusi Pencarian
        btn = await page.query_selector("button:has-text('Tampilkan')")
        await btn.click()
        
        # Tunggu respons tabel
        await page.wait_for_timeout(3000)
        
        # 4. Parsing HTML
        baris_html = await page.query_selector_all("table tbody tr")
        
        for row in baris_html:
            cells = await row.query_selector_all("td")
            vals = [(await c.inner_text()).strip() for c in cells]
            
            if len(vals) >= 5:
                nama_bersih = re.sub(r"^[\s\-–]+", "", vals[1]).strip()
                if nama_bersih in WHITELIST_MAP:
                    harga = parse_harga(vals[4])
                    if harga:
                        rows_data.append({
                            'tanggal_data': tgl_str, # Tambahkan tanggal untuk DB
                            'komoditas': nama_bersih,
                            'satuan': vals[2],
                            'harga_rp': harga
                        })
        return rows_data
    except Exception as e:
        log.error(f"Gagal scrape {tgl_str}: {e}")
        return []

async def job_update_harian():
    hari_ini = date.today()
    log.info(f"🔄 Menjalankan automasi penarikan data: {hari_ini}")
    
    async with async_playwright() as p:
        # headless=True WAJIB untuk Docker / GitHub Actions
        browser = await p.chromium.launch(headless=True)
        # Block resource tidak penting agar cepat
        context = await browser.new_context()
        page = await context.new_page()
        await page.route("**/*.{png,jpg,jpeg,gif,svg,css,woff,woff2}", lambda r: r.abort())
        
        try:
            # 1. Gunakan fungsi mandiri
            rows = await scrape_harian_mandiri(page, hari_ini)
            
            if rows:
                df = pd.DataFrame(rows)
                
                # 2. Cleaning Nama
                df['komoditas'] = df['komoditas'].apply(clean_name_daily)
                
                # 3. Filtering & Mapping Kategori
                df_clean = df[df['komoditas'].isin(WHITELIST_MAP.keys())].copy()
                df_clean['kategori'] = df_clean['komoditas'].map(WHITELIST_MAP)
                
                # Pastikan nama kolom match dengan harga_historis (Postgres)
                if 'harga_rp' in df_clean.columns:
                    df_clean = df_clean.rename(columns={'harga_rp': 'harga'})

                # 4. Injeksi ke PostgreSQL
                if not df_clean.empty:
                    # Filter hanya kolom yang dibutuhkan DB
                    cols_to_db = ['tanggal_data', 'komoditas', 'satuan', 'harga']
                    df_to_db = df_clean[cols_to_db]
                    
                    try:
                        engine = create_engine(POSTGRE_URL)
                        df_to_db.to_sql('harga_historis', engine, if_exists='append', index=False)
                        log.info(f"✅ Sukses! {len(df_to_db)} data baru mendarat di Postgres.")
                    except Exception as db_err:
                        log.error(f"❌ Gagal koneksi/insert ke Database: {db_err}")
                else:
                    log.warning("⚠️ Data ditemukan tapi tidak ada yang masuk whitelist.")
            else:
                log.warning("⚠️ Siskaperbapo belum menyediakan data untuk hari ini / tabel kosong.")
                
        except Exception as e:
            log.error(f"❌ Automation Error: {e}")
        finally:
            await browser.close()

async def main():
    scheduler = AsyncIOScheduler()
    scheduler.add_job(
        job_update_harian, 
        CronTrigger(hour=9, minute=0), 
        name="MarketCast_Daily_Pipeline"
    )
    scheduler.start()
    log.info("🚀 MarketCast Scheduler Aktif (Standby setiap 09:00 WIB)")
    
    try:
        while True:
            await asyncio.sleep(1000)
    except (KeyboardInterrupt, SystemExit):
        scheduler.shutdown()

if __name__ == "__main__":
    # Pilih salah satu:
    # 1. Untuk testing langsung sekarang:
    asyncio.run(job_update_harian())
    
    # 2. Untuk dijalankan sebagai service 24/7 (Docker):
    # asyncio.run(main())