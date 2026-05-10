import asyncio
import logging
import os
import re
from datetime import date
from sqlalchemy import create_engine
import pandas as pd
from playwright.async_api import async_playwright

# --- KONFIGURASI ---
# Menggunakan DATABASE_URL dari GitHub Secrets/Neon
POSTGRE_URL = os.getenv("DATABASE_URL", "postgresql://neondb_owner:npg_pSmfVRDaG4P6@ep-little-star-aokx0s6c.c-2.ap-southeast-1.aws.neon.tech/neondb?sslmode=require")
BASE_URL = "https://siskaperbapo.jatimprov.go.id/harga/tabel"

# 43 Item Whitelist sesuai kesepakatan tim
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

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("MarketCast-Daily")

def clean_name_daily(name):
    """Menghilangkan angka urut dan spasi berlebih."""
    if not name: return ""
    cleaned = re.sub(r'^[0-9\s\.\-]+', '', str(name)).strip()
    return cleaned

def parse_harga(text):
    """
    Mengonversi format Rp 15.750,00 menjadi 15750.0.
    Menghilangkan bagian desimal setelah koma.
    """
    if not text: return None
    text = text.strip()
    if text in ("-", "0", ""): return None
    
    # Ambil angka sebelum koma desimal (format Indo: 15.000,00)
    text_main = text.split(',')[0]
    # Buang semua karakter kecuali angka (membuang titik ribuan)
    cleaned = re.sub(r"[^\d]", "", text_main)
    
    try: 
        return float(cleaned)
    except: 
        return None

async def scrape_harian_mandiri(page, tgl):
    tgl_str = tgl.strftime("%Y-%m-%d")
    rows_data = []
    
    try:
        log.info(f"🌐 Membuka halaman Siskaperbapo untuk {tgl_str}...")
        await page.goto(BASE_URL, wait_until="networkidle", timeout=60000)
        
        # 1. Injeksi Tanggal
        date_input = await page.query_selector("input[name='tanggal']")
        await date_input.evaluate(f"(el, val) => {{ el.value = val; el.dispatchEvent(new Event('change', {{ bubbles: true }})); }}", tgl_str)
        
        # 2. Pilih Surabaya
        await page.select_option("select[name='kabkota']", label="Kota Surabaya")
            
        # 3. Klik Tampilkan
        await page.click("button:has-text('Tampilkan')")
        
        # Beri waktu ekstra karena data Siskaperbapo sering lambat muncul
        await page.wait_for_timeout(5000)
        
        # 4. Parsing Tabel
        # Pastikan kita mengambil baris yang ada datanya (bukan header kategori)
        baris_html = await page.query_selector_all("table tbody tr")
        
        for row in baris_html:
            cells = await row.query_selector_all("td")
            if len(cells) < 5: continue # Lewati baris kosong/header
            
            vals = [(await c.inner_text()).strip() for c in cells]
            nama_raw = vals[1]
            nama_bersih = clean_name_daily(nama_raw)
            
            if nama_bersih in WHITELIST_MAP:
                # Kolom 3: Harga Kemarin | Kolom 4: Harga Sekarang
                # Kita ambil Kolom 4 (Index 4)
                harga = parse_harga(vals[4])
                
                if harga:
                    rows_data.append({
                        'tanggal_data': tgl_str,
                        'komoditas': nama_bersih,
                        'satuan': vals[2],
                        'harga': harga,
                        'kategori': WHITELIST_MAP[nama_bersih]
                    })
        
        return rows_data
    except Exception as e:
        log.error(f"❌ Detail Error Scrape: {e}")
        return []

async def job_update_harian():
    hari_ini = date.today()
    log.info(f"🚀 Memulai Pipeline Harian: {hari_ini}")
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        # Tambahkan User-Agent agar tidak terdeteksi bot
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        )
        page = await context.new_page()
        # Matikan gambar untuk kecepatan
        await page.route("**/*.{png,jpg,jpeg,gif,svg,css}", lambda r: r.abort())
        
        try:
            data_rows = await scrape_harian_mandiri(page, hari_ini)
            
            if data_rows:
                df = pd.DataFrame(data_rows)
                
                # Injeksi ke PostgreSQL Neon
                engine = create_engine(POSTGRE_URL)
                # Gunakan table name 'harga_historis' sesuai request terakhirmu
                df.to_sql('harga_historis', engine, if_exists='append', index=False)
                log.info(f"✅ SUKSES! {len(df)} data berhasil dikirim ke Neon Singapore.")
            else:
                log.warning("⚠️ Tidak ada data yang berhasil ditarik hari ini.")
                
        except Exception as e:
            log.error(f"❌ Gagal Menjalankan Job: {e}")
        finally:
            await browser.close()

if __name__ == "__main__":
    # Menjalankan langsung untuk testing
    asyncio.run(job_update_harian())