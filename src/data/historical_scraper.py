"""
MARKETCAST - Final Production Scraper
Fitur:
- Injeksi JS untuk Bypass UI Input Tanggal
- Sistem Checkpoint (Resume otomatis jika terputus)
- Full Whitelist 43 Komoditas
- Output Logging ganda (Terminal & File)
"""

import asyncio
import re
import sys
import sqlite3
import logging
import argparse
from datetime import date, timedelta
from pathlib import Path
from playwright.async_api import async_playwright

# ── FIX ENCODING WINDOWS ──
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# ── KONFIGURASI ──
BASE_URL   = "https://siskaperbapo.jatimprov.go.id/harga/tabel"
DB_PATH    = Path("data/raw/siskaperbapo_fixed.db")
TIMEOUT_MS = 60_000

TANGGAL_AWAL  = date(2026, 4, 25)
TANGGAL_AKHIR = date(2026, 5, 1)

# Full Whitelist 43 Komoditas
WHITELIST = {
    'Beras Premium', 'Beras Medium', 'Gula Kristal Putih',
    'Minyak Goreng Curah', 'Minyak Goreng Kemasan Premium',
    'Minyak Goreng Kemasan Sederhana', 'Minyak Goreng MINYAKITA',
    'Daging Sapi Paha Belakang', 'Daging Ayam Ras', 'Daging Ayam Kampung',
    'Telur Ayam Ras', 'Telur Ayam Kampung',
    'Susu Kental Manis Merk Bendera', 'Susu Kental Manis Merk Indomilk',
    'Susu Bubuk Merk Bendera (Instant)', 'Susu Bubuk Merk Indomilk (Instant)',
    'Jagung Pipilan Kering', 'Garam Bata', 'Garam Halus',
    'Terigu Protein Sedang (Kemasan)', 'Kedelai Impor', 'Kedelai Lokal',
    'Indomie Rasa Kari Ayam', 'Cabe Merah Keriting', 'Cabe Merah Besar',
    'Cabe Rawit Merah', 'Bawang Merah', 'Bawang Putih Sinco/Honan',
    'Ikan Asin Teri', 'Kacang Hijau', 'Kacang Tanah', 'Ketela Pohon',
    'Kol/Kubis', 'Kentang', 'Tomat Merah', 'Wortel', 'Buncis',
    'Ikan Bandeng', 'Ikan Kembung', 'Ikan Tuna', 'Ikan Tongkol',
    'Ikan Cakalang', 'Gas Elpiji 3 Kg',
}

# ── SETUP LOGGING ──
Path("data").mkdir(parents=True, exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("data/scraper.log", encoding="utf-8")
    ]
)
log = logging.getLogger(__name__)

# ── DATABASE & CHECKPOINT ──
def init_db():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS harga_bahan_pokok (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tanggal_data TEXT,
                komoditas TEXT,
                satuan TEXT,
                harga_rp REAL,
                kabkota TEXT DEFAULT 'Surabaya',
                created_at TEXT DEFAULT (datetime('now','localtime')),
                UNIQUE(tanggal_data, komoditas)
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS scrape_checkpoint (
                tanggal TEXT PRIMARY KEY,
                status TEXT NOT NULL,
                baris_dapat INTEGER DEFAULT 0
            )
        """)
        conn.commit()

def sudah_diproses(tanggal: date) -> bool:
    with sqlite3.connect(DB_PATH) as conn:
        row = conn.execute("SELECT status FROM scrape_checkpoint WHERE tanggal = ?", (tanggal.isoformat(),)).fetchone()
    return row is not None and row[0] == "done"

def simpan_batch(rows, tanggal_data):
    inserted = 0
    with sqlite3.connect(DB_PATH) as conn:
        for row in rows:
            try:
                conn.execute("""
                    INSERT OR REPLACE INTO harga_bahan_pokok 
                    (tanggal_data, komoditas, satuan, harga_rp) 
                    VALUES (?, ?, ?, ?)
                """, (tanggal_data, row['komoditas'], row['satuan'], row['harga_rp']))
                inserted += 1
            except Exception as e:
                log.warning(f"Gagal simpan komoditas {row['komoditas']}: {e}")
        conn.execute("""
            INSERT OR REPLACE INTO scrape_checkpoint (tanggal, status, baris_dapat) 
            VALUES (?, 'done', ?)
        """, (tanggal_data, inserted))
        conn.commit()
    return inserted

# ── PARSING UTILS ──
def normalisasi_nama(nama):
    return re.sub(r"^[\s\-–]+", "", nama).strip()

def parse_harga(text):
    if not text or text.strip() in ("-", "0", ""): return None
    cleaned = re.sub(r"[^\d]", "", text)
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
    log.info(f"Target Ekstraksi : {TANGGAL_AWAL} s/d {TANGGAL_AKHIR} ({total} hari)")
    log.info("=" * 60)

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            timezone_id="Asia/Jakarta"
        )
        page = await context.new_page()
        
        # Block resource yang tidak perlu agar loading jauh lebih ringan
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
                log.info(f"[{idx:>3}/{total}] {tgl_str} - Dilewati (Sudah ada di DB)")
                continue
                
            log.info(f"[{idx:>3}/{total}] Memproses: {tgl_str}")
            
            try:
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
                rows_data = []
                baris_html = await page.query_selector_all("table tbody tr")
                
                for row in baris_html:
                    cells = await row.query_selector_all("td")
                    vals = [(await c.inner_text()).strip() for c in cells]
                    
                    if len(vals) >= 5:
                        nama_bersih = normalisasi_nama(vals[1])
                        if nama_bersih in WHITELIST:
                            harga = parse_harga(vals[4])
                            if harga:
                                rows_data.append({
                                    'komoditas': nama_bersih,
                                    'satuan': vals[2],
                                    'harga_rp': harga
                                })
                
                # 5. Penyimpanan Data
                if rows_data:
                    jumlah_tersimpan = simpan_batch(rows_data, tgl_str)
                    log.info(f"         [OK] Tersimpan {jumlah_tersimpan} data komoditas.")
                else:
                    log.warning(f"         [!!] Tidak ada komoditas whitelist yang terekstrak.")
                    # Tetap catat checkpoint agar tidak diloop berulang kali bila server memang kosong
                    with sqlite3.connect(DB_PATH) as conn:
                        conn.execute("INSERT OR REPLACE INTO scrape_checkpoint (tanggal, status, baris_dapat) VALUES (?, 'done', 0)", (tgl_str,))
                        conn.commit()
                        
            except Exception as e:
                log.error(f"         [X] Error pada {tgl_str}: {e}")
                
            await asyncio.sleep(2.0) # Jeda aman agar tidak diblokir server

        await browser.close()
        
    log.info("=" * 60)
    log.info("EKSTRAKSI SELESAI")
    log.info("=" * 60)

# ── VERIFIKASI CLI ──
def verifikasi_hasil():
    with sqlite3.connect(DB_PATH) as conn:
        rekap = conn.execute("SELECT tanggal_data, COUNT(*) FROM harga_bahan_pokok GROUP BY tanggal_data ORDER BY tanggal_data").fetchall()
        print("\n📊 REKAPITULASI DATABASE:")
        for r in rekap:
            print(f"   {r[0]} : {r[1]:>2} Komoditas")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="MarketCast Main Scraper")
    parser.add_argument("--verify", action="store_true", help="Hanya memunculkan rekap database")
    args = parser.parse_args()

    if args.verify:
        verifikasi_hasil()
    else:
        asyncio.run(run_scraper())
        verifikasi_hasil()