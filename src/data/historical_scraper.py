"""
MARKETCAST - Final Production Historical Scraper (CLOUD MIGRATION)
Fitur:
- Injeksi JS untuk Bypass UI Input Tanggal
- Sistem Checkpoint berbasis PostgreSQL (Neon Cloud)
- Full Whitelist 43 Komoditas + Kategori
- Output Logging ganda (Terminal & File)
"""

import asyncio
import re
import sys
import os
import logging
import argparse
from datetime import date, timedelta
from pathlib import Path
from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from playwright.async_api import async_playwright

# ── FIX ENCODING WINDOWS ──
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# ── KONFIGURASI CLOUD & TARGET ──
load_dotenv()
POSTGRE_URL = os.getenv("DATABASE_URL")

if not POSTGRE_URL:
    print("❌ ERROR: DATABASE_URL tidak ditemukan di file .env!")
    sys.exit(1)

engine = create_engine(POSTGRE_URL, pool_pre_ping=True, pool_recycle=300)

BASE_URL   = "https://siskaperbapo.jatimprov.go.id/harga/tabel"
TIMEOUT_MS = 60_000

TANGGAL_AWAL  = date(2021, 5, 7)
TANGGAL_AKHIR = date(2026, 5, 10)

# Full Whitelist 43 Komoditas (Disamakan persis dengan daily_scraper)
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

# ── SETUP LOGGING ──
Path("data").mkdir(parents=True, exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("data/scraper_historis.log", encoding="utf-8")
    ]
)
log = logging.getLogger("MarketCast-Historis")

# ── DATABASE & CHECKPOINT (NEON CLOUD) ──
def init_db():
    """Memastikan tabel checkpoint ada di database Cloud."""
    with engine.begin() as conn:
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS scrape_checkpoint (
                tanggal DATE PRIMARY KEY,
                status VARCHAR(50) NOT NULL,
                baris_dapat INTEGER DEFAULT 0
            )
        """))

def sudah_diproses(tanggal: date) -> bool:
    with engine.connect() as conn:
        row = conn.execute(
            text("SELECT status FROM scrape_checkpoint WHERE tanggal = :tgl"), 
            {"tgl": tanggal.isoformat()}
        ).fetchone()
    return row is not None and row[0] == "done"

def simpan_batch(rows, tanggal_data):
    inserted = 0
    with engine.begin() as conn:
        # Hapus data tanggal ini jika sudah ada (Metode aman cegah duplikasi tanpa Primary Key)
        conn.execute(text("DELETE FROM harga_historis WHERE tanggal_data = :tgl"), {"tgl": tanggal_data})
        
        for row in rows:
            try:
                conn.execute(text("""
                    INSERT INTO harga_historis (tanggal_data, komoditas, satuan, harga, kategori) 
                    VALUES (:tgl, :kom, :sat, :hrg, :kat)
                """), {
                    "tgl": tanggal_data,
                    "kom": row['komoditas'],
                    "sat": row['satuan'],
                    "hrg": row['harga'],
                    "kat": row['kategori']
                })
                inserted += 1
            except Exception as e:
                log.warning(f"Gagal simpan komoditas {row['komoditas']}: {e}")
        
        # Update Checkpoint menggunakan UPSERT khas PostgreSQL
        conn.execute(text("""
            INSERT INTO scrape_checkpoint (tanggal, status, baris_dapat) 
            VALUES (:tgl, 'done', :jum)
            ON CONFLICT (tanggal) DO UPDATE 
            SET baris_dapat = EXCLUDED.baris_dapat, status = EXCLUDED.status
        """), {"tgl": tanggal_data, "jum": inserted})
        
    return inserted

# ── PARSING UTILS ──
def clean_name_daily(nama):
    if not nama: return ""
    cleaned = re.sub(r'^[0-9\s\.\-]+', '', str(nama)).strip()
    return cleaned

def parse_harga(text_val):
    if not text_val: return None
    text_val = text_val.strip()
    if text_val in ("-", "0", ""): return None
    
    text_main = text_val.split(',')[0]
    cleaned = re.sub(r"[^\d]", "", text_main)
    try: return float(cleaned)
    except: return None

# ── CORE SCRAPER ──
async def run_scraper():
    init_db()
    
    tgl_target = []
    curr = TANGGAL_AWAL
    while curr <= TANGGAL_AKHIR:
        tgl_target.append(curr)
        curr += timedelta(days=1)

    total = len(tgl_target)
    log.info("=" * 60)
    log.info(f"🚀 Mulai Ekstraksi Historis ke CLOUD NEON")
    log.info(f"Target : {TANGGAL_AWAL} s/d {TANGGAL_AKHIR} ({total} hari)")
    log.info("=" * 60)

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            timezone_id="Asia/Jakarta"
        )
        page = await context.new_page()
        await page.route("**/*.{png,jpg,jpeg,gif,svg,css,woff,woff2}", lambda r: r.abort())
        
        try:
            await page.goto(BASE_URL, wait_until="domcontentloaded", timeout=TIMEOUT_MS)
        except Exception as e:
            log.error(f"Gagal memuat halaman utama: {e}")
            await browser.close()
            return

        for idx, tgl in enumerate(tgl_target, 1):
            tgl_str = tgl.strftime("%Y-%m-%d")
            
            if sudah_diproses(tgl):
                log.info(f"[{idx:>4}/{total}] {tgl_str} - Dilewati (Sudah ada di Checkpoint Cloud)")
                continue
                
            log.info(f"[{idx:>4}/{total}] Memproses: {tgl_str}")
            
            try:
                date_input = await page.query_selector("input[name='tanggal']")
                await date_input.evaluate(f"(el, val) => {{ el.value = val; el.dispatchEvent(new Event('change', {{ bubbles: true }})); }}", tgl_str)
                
                await page.select_option("select[name='kabkota']", label="Kota Surabaya")
                await page.click("button:has-text('Tampilkan')")
                
                # Jeda 5 detik karena data historis Siskaperbapo butuh waktu load lebih lama
                await page.wait_for_timeout(5000)
                
                rows_data = []
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
                                'komoditas': nama_bersih,
                                'satuan': vals[2],
                                'harga': harga,
                                'kategori': WHITELIST_MAP[nama_bersih]
                            })
                
                if rows_data:
                    jumlah_tersimpan = simpan_batch(rows_data, tgl_str)
                    log.info(f"        [OK] Tersimpan {jumlah_tersimpan} data ke Neon Singapore.")
                else:
                    log.warning(f"        [!!] Data kosong/hari libur.")
                    with engine.begin() as conn:
                        conn.execute(text("INSERT INTO scrape_checkpoint (tanggal, status, baris_dapat) VALUES (:tgl, 'done', 0) ON CONFLICT (tanggal) DO NOTHING"), {"tgl": tgl_str})
                        
            except Exception as e:
                log.error(f"        [X] Error pada {tgl_str}: {e}")
                
            # Jeda sopan santun agar IP tidak di-banned
            await asyncio.sleep(4.0) 

        await browser.close()
        
    log.info("=" * 60)
    log.info("EKSTRAKSI HISTORIS SELESAI")
    log.info("=" * 60)

# ── VERIFIKASI CLI ──
def verifikasi_hasil():
    print("\n🔍 Memeriksa Database Cloud Neon...")
    try:
        with engine.connect() as conn:
            # Menggunakan syntax PostgreSQL
            total = conn.execute(text("SELECT COUNT(*) FROM harga_historis")).scalar()
            hari = conn.execute(text("SELECT COUNT(DISTINCT tanggal_data) FROM harga_historis")).scalar()
            print(f"📈 TOTAL KESELURUHAN DATA: {total} baris (dari {hari} hari aktif)")
            
            rekap = conn.execute(text("""
                SELECT tanggal_data, COUNT(*) 
                FROM harga_historis 
                GROUP BY tanggal_data 
                ORDER BY tanggal_data DESC 
                LIMIT 10
            """)).fetchall()
            
            print("\n📊 10 TANGGAL TERAKHIR DI DATABASE:")
            for r in rekap:
                print(f"   {r[0]} : {r[1]:>2} Komoditas")
    except Exception as e:
        print(f"❌ Gagal memverifikasi: {e}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="MarketCast Historical Scraper")
    parser.add_argument("--verify", action="store_true", help="Hanya memunculkan rekap database")
    args = parser.parse_args()

    if args.verify:
        verifikasi_hasil()
    else:
        asyncio.run(run_scraper())
        verifikasi_hasil()