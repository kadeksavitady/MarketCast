import asyncio
import logging
import os
import re
import sys
import sqlite3
from datetime import date
from pathlib import Path
from sqlalchemy import create_engine, text
import pandas as pd
from playwright.async_api import async_playwright
from dotenv import load_dotenv

load_dotenv()

# ── FIX ENCODING WINDOWS ──
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# ── KONFIGURASI ──
LOCAL_DB_PATH = Path("data/raw/siskaperbapo_daily.db")
POSTGRE_URL   = os.getenv("DATABASE_URL", "postgresql://neondb_owner:npg_pSmfVRDaG4P6@ep-little-star-aokx0s6c.c-2.ap-southeast-1.aws.neon.tech/neondb?sslmode=require")
BASE_URL      = "https://siskaperbapo.jatimprov.go.id/harga/tabel"
TIMEOUT_MS    = 60_000 

# Whitelist Menggunakan Lowercase untuk Pencocokan Bebas Case-Sensitive
WHITELIST_KATEGORI = {
    'beras premium': 'BERAS', 'beras medium': 'BERAS',
    'gula kristal putih': 'GULA',
    'minyak goreng curah': 'MINYAK GORENG', 'minyak goreng kemasan premium': 'MINYAK GORENG',
    'minyak goreng kemasan sederhana': 'MINYAK GORENG', 'minyak goreng minyakita': 'MINYAK GORENG',
    'daging sapi paha belakang': 'DAGING', 'daging ayam ras': 'DAGING', 'daging ayam kampung': 'DAGING',
    'telur ayam ras': 'TELUR', 'telur ayam kampung': 'TELUR',
    'susu kental manis merk bendera': 'SUSU', 'susu kental manis merk indomilk': 'SUSU',
    'susu bubuk merk bendera (instant)': 'SUSU', 'susu bubuk merk indomilk (instant)': 'SUSU',
    'jagung pipilan kering': 'PALAWIJA', 'kedelai impor': 'PALAWIJA', 'kedelai lokal': 'PALAWIJA',
    'kacang hijau': 'PALAWIJA', 'kacang tanah': 'PALAWIJA', 'ketela pohon': 'PALAWIJA',
    'bata': 'GARAM', 'halus': 'GARAM',
    'terigu protein sedang (kemasan)': 'TEPUNG',
    'indomie rasa kari ayam': 'MIE INSTAN',
    'cabe merah keriting': 'CABE', 'cabe merah besar': 'CABE', 'cabe rawit merah': 'CABE',
    'bawang merah': 'BAWANG', 'bawang putih sinco/honan': 'BAWANG',
    'ikan asin teri': 'IKAN ASIN',
    'kol/kubis': 'SAYUR MAYUR', 'kentang': 'SAYUR MAYUR', 'tomat merah': 'SAYUR MAYUR',
    'wortel': 'SAYUR MAYUR', 'buncis': 'SAYUR MAYUR',
    'ikan bandeng': 'IKAN SEGAR', 'ikan kembung': 'IKAN SEGAR', 'ikan tuna': 'IKAN SEGAR',
    'ikan tongkol': 'IKAN SEGAR', 'ikan cakalang': 'IKAN SEGAR',
    'gas elpigi 3 kg': 'BARANG PENTING LAINNYA'
}

# Mapping Kosmetik Penulisan Agar Bersih Saat Masuk Database
NAMA_MAP = {
    'bata': 'Garam Bata',
    'halus': 'Garam Halus',
    'gas elpigi 3 kg': 'Gas Elpigi 3 Kg'
}

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("MarketCast-Daily")

# ── DATABASE SEMENTARA (SQLITE LOCAL STAGING) ──
def init_local_db():
    LOCAL_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(LOCAL_DB_PATH) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS harga_historis (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tanggal_data TEXT,
                komoditas TEXT,
                satuan TEXT,
                harga_rp REAL,
                kabkota TEXT DEFAULT 'Surabaya',
                kategori TEXT,
                created_at TEXT DEFAULT (datetime('now','localtime')),
                UNIQUE(tanggal_data, komoditas)
            )
        """)
        conn.commit()

def simpan_lokal(rows):
    inserted = 0
    with sqlite3.connect(LOCAL_DB_PATH) as conn:
        for row in rows:
            try:
                conn.execute("""
                    INSERT OR REPLACE INTO harga_historis 
                    (tanggal_data, komoditas, satuan, harga_rp, kabkota, kategori) 
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (row['tanggal_data'], row['komoditas'], row['satuan'], row['harga_rp'], row['kabkota'], row['kategori']))
                inserted += 1
            except Exception as e:
                log.warning(f"Gagal simpan lokal untuk {row['komoditas']}: {e}")
        conn.commit()
    return inserted

# ── PARSING UTILS ──
def normalisasi_nama(nama):
    if not nama: return ""
    # Membersihkan whitespace hantu eksotis (\xa0 / NBSP) menjadi spasi biasa
    nama_bersih = re.sub(r"[\s\xa0]+", " ", nama)
    nama_bersih = re.sub(r"^[\s\-–\—\•\.]+", "", nama_bersih)
    return nama_bersih.strip()

def parse_harga(text):
    if not text or text.strip() in ("-", ""): return None
    text_main = text.split(',')[0]
    cleaned = re.sub(r"[^\d]", "", text_main)
    try: 
        return float(cleaned)
    except: 
        return None

# ── CORE SCRAPER ──
async def scrape_harian_mandiri(page, tgl):
    tgl_str = tgl.strftime("%Y-%m-%d")
    rows_data = []

    try:
        log.info(f"🌐 Membuka halaman Siskaperbapo untuk {tgl_str}...")
        await page.goto(BASE_URL, wait_until="domcontentloaded", timeout=TIMEOUT_MS)

        date_input = await page.wait_for_selector("input[name='tanggal']", timeout=TIMEOUT_MS)
        await date_input.evaluate(f"""
            (el) => {{
                el.value = '{tgl_str}';
                el.dispatchEvent(new Event('input', {{ bubbles: true }}));
                el.dispatchEvent(new Event('change', {{ bubbles: true }}));
            }}
        """)

        area_el = await page.wait_for_selector("select[name='kabkota']", timeout=TIMEOUT_MS)
        await area_el.select_option(label="Kota Surabaya")

        btn = await page.wait_for_selector("button:has-text('Tampilkan')", timeout=TIMEOUT_MS)
        await btn.click()

        # Tunggu render data aktif agar tidak mengambil tabel kosong
        try:
            await page.wait_for_selector("table tbody tr td", timeout=10_000)
        except Exception:
            log.warning("[!] Tabel merespon lambat, bersiap menggunakan jeda tambahan...")
            await page.wait_for_timeout(3000)

        baris_html = await page.query_selector_all("table tbody tr")

        for row in baris_html:
            cells = await row.query_selector_all("td")
            if len(cells) < 5: continue

            vals = [(await c.inner_text()).strip() for c in cells]
            nama_bersih = normalisasi_nama(vals[1])
            nama_key = nama_bersih.lower()

            if nama_key in WHITELIST_KATEGORI:
                harga = parse_harga(vals[4])
                if harga is not None:  # Mengizinkan harga 0.0 masuk demi keutuhan 43 komoditas
                    # Terapkan standardisasi nama kapitalisasi
                    if nama_key in NAMA_MAP:
                        nama_final = NAMA_MAP[nama_key]
                    else:
                        nama_final = nama_bersih.title() if not nama_bersih.isupper() else nama_bersih

                    rows_data.append({
                        'tanggal_data': tgl_str,
                        'komoditas': nama_final,
                        'satuan': vals[2],
                        'harga_rp': harga,  # Sinkron dengan nama kolom database utama
                        'kabkota': 'Surabaya',
                        'kategori': WHITELIST_KATEGORI[nama_key]
                    })

        return rows_data
    except Exception as e:
        log.error(f"❌ Detail Error Scrape: {e}")
        return []

# ── TRANSAKSI CLOUD NEON ──
def push_ke_neon(data_rows):
    if not POSTGRE_URL:
        log.error("❌ DATABASE_URL tidak dikonfigurasi di env. Sinkronisasi cloud gagal.")
        return
    
    log.info("☁️ Memulai migrasi data staging ke Neon Cloud...")
    try:
        df = pd.DataFrame(data_rows)
        engine = create_engine(POSTGRE_URL)
        
        # Eksekusi Upsert (ON CONFLICT DO NOTHING) agar id unik tanggal+komoditas terjaga aman
        with engine.begin() as conn:
            for _, row in df.iterrows():
                conn.execute(text("""
                    INSERT INTO harga_historis (tanggal_data, komoditas, satuan, harga_rp, kabkota, kategori)
                    VALUES (:tanggal_data, :komoditas, :satuan, :harga_rp, :kabkota, :kategori)
                    ON CONFLICT (tanggal_data, komoditas) DO NOTHING
                """), row.to_dict())
        log.info(f"✅ SINKRONISASI SUKSES! {len(df)} data harian berhasil diunggah ke Neon Singapore.")
    except Exception as e:
        log.error(f"❌ Gagal mengirim data ke Neon: {e}")

async def job_update_harian():
    hari_ini = date.today()
    log.info(f"🚀 Memulai Pipeline Harian: {hari_ini}")
    init_local_db()

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
                # 1. Isolasi Tahap Staging: Simpan ke SQLite Lokal
                jumlah_lokal = simpan_lokal(data_rows)
                log.info("-" * 60)
                log.info(f"📊 [STAGING] Sukses mencatat {jumlah_lokal} data di SQLite Lokal ({LOCAL_DB_PATH.name})")
                log.info("-" * 60)

                # 2. Interaksi CLI untuk Validasi Sebelum Push Cloud
                print(f"\n💡 Data hari ini ({hari_ini.isoformat()}) berhasil disimpan di database lokal.")
                pilihan = input("👉 Apakah Anda ingin mengunggah data ini ke Neon Cloud sekarang? (y/n): ").strip().lower()
                
                if pilihan == 'y':
                    push_ke_neon(data_rows)
                else:
                    log.info("⏸️ Sinkronisasi ditunda. Data harian tetap aman tersimpan di staging lokal.")
            else:
                log.warning("⚠️ Tidak ada data valid yang berhasil diekstrak hari ini.")

        except Exception as e:
            log.error(f"❌ Gagal Menjalankan Pipeline Harian: {e}")
        finally:
            await browser.close()

if __name__ == "__main__":
    # Menghindari blocking event loop async akibat fungsi input() CLI
    loop = asyncio.get_event_loop()
    loop.run_until_complete(job_update_harian())