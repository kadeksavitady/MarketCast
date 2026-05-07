import asyncio
import logging
import os
from datetime import date
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from sqlalchemy import create_engine
import pandas as pd
import re

# Import fungsi inti dari file sebelah
# Pastikan historical_scraper.py ada di folder yang sama (src/data/)
from historical_scraper import scrape_tanggal 

# --- KONFIGURASI PRODUKSI (DOCKER) ---
# Di Docker, host-nya adalah 'db' (nama service di docker-compose)
POSTGRE_URL = "postgresql://postgres:marketcast_pbl@db:5432/marketcast_db"

# 43 Item sesuai kesepakatan tim (Flat List untuk filter .isin)
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

async def job_update_harian():
    hari_ini = date.today()
    log.info(f"🔄 Menjalankan automasi penarikan data: {hari_ini}")
    
    from playwright.async_api import async_playwright
    async with async_playwright() as p:
        # headless=True WAJIB untuk Docker
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        
        try:
            # 1. Gunakan fungsi dari historical_scraper
            rows = await scrape_tanggal(page, hari_ini)
            
            if rows:
                df = pd.DataFrame(rows)
                
                # 2. Cleaning Nama secara agresif
                df['komoditas'] = df['komoditas'].apply(clean_name_daily)
                
                # 3. Filtering & Mapping Kategori
                # Hanya ambil yang ada di whitelist
                df_clean = df[df['komoditas'].isin(WHITELIST_MAP.keys())].copy()
                df_clean['kategori'] = df_clean['komoditas'].map(WHITELIST_MAP)
                
                # Pastikan nama kolom match dengan harga_historis (Postgres)
                if 'harga_rp' in df_clean.columns:
                    df_clean = df_clean.rename(columns={'harga_rp': 'harga'})

                # 4. Injeksi ke PostgreSQL
                if not df_clean.empty:
                    engine = create_engine(POSTGRE_URL)
                    df_clean.to_sql('harga_historis', engine, if_exists='append', index=False)
                    log.info(f"✅ Sukses! {len(df_clean)} data baru mendarat di Postgres.")
                else:
                    log.warning("⚠️ Data ditemukan tapi tidak ada yang masuk whitelist.")
            else:
                log.warning("⚠️ Siskaperbapo belum menyediakan data untuk hari ini.")
                
        except Exception as e:
            log.error(f"❌ Automation Error: {e}")
        finally:
            await browser.close()

async def main():
    scheduler = AsyncIOScheduler()
    # Atur jam 9 pagi (saat data pasar biasanya sudah masuk sistem)
    scheduler.add_job(
        job_update_harian, 
        CronTrigger(hour=9, minute=0), 
        name="MarketCast_Daily_Pipeline"
    )
    
    scheduler.start()
    log.info("🚀 MarketCast Scheduler Aktif (Standby setiap 09:00 WIB)")
    
    # Jalankan sekali saat start untuk testing (opsional)
    # await job_update_harian() 

    try:
        while True:
            await asyncio.sleep(1000)
    except (KeyboardInterrupt, SystemExit):
        scheduler.shutdown()

if __name__ == "__main__":
    # asyncio.run(main())
    asyncio.run(job_update_harian())