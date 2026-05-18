"""
MARKETCAST - Unified Historical Scraper
Fitur:
- Injeksi JS untuk Bypass UI Input Tanggal
- Sistem Checkpoint berbasis PostgreSQL (Neon Cloud)
- Full Whitelist 43 Komoditas + Kategori
- Dual-write: SQLite (lokal/backup) + Neon (cloud/primary)
- Output Logging ganda (Terminal & File)
- Fallback otomatis ke SQLite jika Neon tidak tersedia
"""

import asyncio
import re
import sys
import os
import sqlite3
import logging
import argparse
from datetime import date, timedelta
from pathlib import Path
from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from playwright.async_api import async_playwright

load_dotenv()

# ── FIX ENCODING WINDOWS ──
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# ── KONFIGURASI ──
BASE_URL    = "https://siskaperbapo.jatimprov.go.id/harga/tabel"
DB_PATH     = Path("data/raw/siskaperbapo.db")
NEON_CONN   = os.getenv("DATABASE_URL")
TIMEOUT_MS  = 60_000

TANGGAL_AWAL  = date(2021, 5, 1)
TANGGAL_AKHIR = date(2026, 5, 18)

# ── WHITELIST 43 KOMODITAS ──
WHITELIST_MAP = {
    'Beras Premium': 'BERAS',
    'Beras Medium': 'BERAS',
    'Gula Kristal Putih': 'GULA',
    'Minyak Goreng Curah': 'MINYAK GORENG',
    'Minyak Goreng Kemasan Premium': 'MINYAK GORENG',
    'Minyak Goreng Kemasan Sederhana': 'MINYAK GORENG',
    'Minyak Goreng MINYAKITA': 'MINYAK GORENG',
    'Daging Sapi Paha Belakang': 'DAGING',
    'Daging Ayam Ras': 'DAGING',
    'Daging Ayam Kampung': 'DAGING',
    'Telur Ayam Ras': 'TELUR',
    'Telur Ayam Kampung': 'TELUR',
    'Susu Kental Manis Merk Bendera': 'SUSU',
    'Susu Kental Manis Merk Indomilk': 'SUSU',
    'Susu Bubuk Merk Bendera (Instant)': 'SUSU',
    'Susu Bubuk Merk Indomilk (Instant)': 'SUSU',
    'Jagung Pipilan Kering': 'PALAWIJA',
    'Kedelai Impor': 'PALAWIJA',
    'Kedelai Lokal': 'PALAWIJA',
    'Kacang Hijau': 'PALAWIJA',
    'Kacang Tanah': 'PALAWIJA',
    'Ketela Pohon': 'PALAWIJA',
    'Garam Bata': 'GARAM',
    'Garam Halus': 'GARAM',
    'Terigu Protein Sedang (Kemasan)': 'TEPUNG',
    'Indomie Rasa Kari Ayam': 'MIE INSTAN',
    'Cabe Merah Keriting': 'CABE',
    'Cabe Merah Besar': 'CABE',
    'Cabe Rawit Merah': 'CABE',
    'Bawang Merah': 'BAWANG',
    'Bawang Putih Sinco/Honan': 'BAWANG',
    'Ikan Asin Teri': 'IKAN ASIN',
    'Kol/Kubis': 'SAYUR MAYUR',
    'Kentang': 'SAYUR MAYUR',
    'Tomat Merah': 'SAYUR MAYUR',
    'Wortel': 'SAYUR MAYUR',
    'Buncis': 'SAYUR MAYUR',
    'Ikan Bandeng': 'IKAN SEGAR',
    'Ikan Kembung': 'IKAN SEGAR',
    'Ikan Tuna': 'IKAN SEGAR',
    'Ikan Tongkol': 'IKAN SEGAR',
    'Ikan Cakalang': 'IKAN SEGAR',
    'Gas Elpiji 3 Kg': 'BARANG PENTING LAINNYA',
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

# ════════════════════════════════════════
# NEON (PRIMARY)
# ════════════════════════════════════════
def init_neon():
    if not NEON_CONN:
        log.warning("DATABASE_URL tidak ditemukan — hanya SQLite yang aktif.")
        return None
    try:
        engine = create_engine(NEON_CONN, pool_pre_ping=True, pool_recycle=300)
        with engine.begin() as conn:
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS harga_historis (
                    id           SERIAL PRIMARY KEY,
                    tanggal_data DATE        NOT NULL,
                    komoditas    TEXT        NOT NULL,
                    satuan       TEXT,
                    harga        NUMERIC,
                    kategori     TEXT,
                    created_at   TIMESTAMP   DEFAULT NOW(),
                    UNIQUE (tanggal_data, komoditas)
                )
            """))
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS scrape_checkpoint (
                    tanggal      DATE        PRIMARY KEY,
                    status       VARCHAR(50) NOT NULL,
                    baris_dapat  INTEGER     DEFAULT 0
                )
            """))
        log.info("✓ Neon: koneksi berhasil & tabel siap.")
        return engine
    except Exception as e:
        log.error(f"Gagal konek ke Neon: {e} — fallback ke SQLite saja.")
        return None

def neon_sudah_diproses(engine, tanggal: date) -> bool:
    try:
        with engine.connect() as conn:
            row = conn.execute(
                text("SELECT status FROM scrape_checkpoint WHERE tanggal = :tgl"),
                {"tgl": tanggal.isoformat()}
            ).fetchone()
        return row is not None and row[0] == "done"
    except:
        return False

def neon_simpan_batch(engine, rows: list, tanggal_data: str) -> int:
    inserted = 0
    try:
        with engine.begin() as conn:
            # Hapus dulu data tanggal ini agar tidak duplikat
            conn.execute(
                text("DELETE FROM harga_historis WHERE tanggal_data = :tgl"),
                {"tgl": tanggal_data}
            )
            for row in rows:
                conn.execute(text("""
                    INSERT INTO harga_historis (tanggal_data, komoditas, satuan, harga, kategori)
                    VALUES (:tgl, :kom, :sat, :hrg, :kat)
                """), {
                    "tgl": tanggal_data,
                    "kom": row["komoditas"],
                    "sat": row["satuan"],
                    "hrg": row["harga"],
                    "kat": row["kategori"],
                })
                inserted += 1
            conn.execute(text("""
                INSERT INTO scrape_checkpoint (tanggal, status, baris_dapat)
                VALUES (:tgl, 'done', :jum)
                ON CONFLICT (tanggal) DO UPDATE
                SET status = EXCLUDED.status, baris_dapat = EXCLUDED.baris_dapat
            """), {"tgl": tanggal_data, "jum": inserted})
        log.info(f"         [Neon] ✓ {inserted} baris tersimpan.")
    except Exception as e:
        log.error(f"         [Neon] Gagal simpan {tanggal_data}: {e}")
    return inserted

def neon_tandai_kosong(engine, tanggal_data: str):
    try:
        with engine.begin() as conn:
            conn.execute(text("""
                INSERT INTO scrape_checkpoint (tanggal, status, baris_dapat)
                VALUES (:tgl, 'done', 0)
                ON CONFLICT (tanggal) DO NOTHING
            """), {"tgl": tanggal_data})
    except Exception as e:
        log.warning(f"         [Neon] Gagal tandai kosong {tanggal_data}: {e}")

# ════════════════════════════════════════
# SQLITE (BACKUP LOKAL)
# ════════════════════════════════════════
def init_sqlite():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS harga_historis (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                tanggal_data TEXT,
                komoditas    TEXT,
                satuan       TEXT,
                harga        REAL,
                kategori     TEXT,
                created_at   TEXT DEFAULT (datetime('now','localtime')),
                UNIQUE (tanggal_data, komoditas)
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS scrape_checkpoint (
                tanggal      TEXT PRIMARY KEY,
                status       TEXT NOT NULL,
                baris_dapat  INTEGER DEFAULT 0
            )
        """)
        conn.commit()
    log.info("✓ SQLite: database lokal siap.")

def sqlite_sudah_diproses(tanggal: date) -> bool:
    with sqlite3.connect(DB_PATH) as conn:
        row = conn.execute(
            "SELECT status FROM scrape_checkpoint WHERE tanggal = ?",
            (tanggal.isoformat(),)
        ).fetchone()
    return row is not None and row[0] == "done"

def sqlite_simpan_batch(rows: list, tanggal_data: str) -> int:
    inserted = 0
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("DELETE FROM harga_historis WHERE tanggal_data = ?", (tanggal_data,))
        for row in rows:
            try:
                conn.execute("""
                    INSERT INTO harga_historis (tanggal_data, komoditas, satuan, harga, kategori)
                    VALUES (?, ?, ?, ?, ?)
                """, (tanggal_data, row["komoditas"], row["satuan"], row["harga"], row["kategori"]))
                inserted += 1
            except Exception as e:
                log.warning(f"         [SQLite] Gagal simpan {row['komoditas']}: {e}")
        conn.execute(
            "INSERT OR REPLACE INTO scrape_checkpoint (tanggal, status, baris_dapat) VALUES (?, 'done', ?)",
            (tanggal_data, inserted)
        )
        conn.commit()
    log.info(f"         [SQLite] ✓ {inserted} baris tersimpan.")
    return inserted

def sqlite_tandai_kosong(tanggal_data: str):
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            "INSERT OR IGNORE INTO scrape_checkpoint (tanggal, status, baris_dapat) VALUES (?, 'done', 0)",
            (tanggal_data,)
        )
        conn.commit()

# ════════════════════════════════════════
# CHECKPOINT — cek keduanya
# ════════════════════════════════════════
def sudah_diproses(neon_engine, tanggal: date) -> bool:
    # Kalau Neon aktif, checkpoint dari Neon
    if neon_engine:
        return neon_sudah_diproses(neon_engine, tanggal)
    # Fallback ke SQLite
    return sqlite_sudah_diproses(tanggal)

# ════════════════════════════════════════
# PARSING UTILS
# ════════════════════════════════════════
def normalisasi_nama(nama: str) -> str:
    if not nama: return ""
    return re.sub(r'^[0-9\s\.\-–]+', '', str(nama)).strip()

def parse_harga(text: str):
    if not text: return None
    text = text.strip()
    if text in ("-", "0", ""): return None
    cleaned = re.sub(r"[^\d]", "", text.split(',')[0])
    try: return float(cleaned)
    except: return None

# ════════════════════════════════════════
# CORE SCRAPER
# ════════════════════════════════════════
async def run_scraper():
    init_sqlite()
    neon_engine = init_neon()

    tgl_target = []
    curr = TANGGAL_AWAL
    while curr <= TANGGAL_AKHIR:
        tgl_target.append(curr)
        curr += timedelta(days=1)

    total = len(tgl_target)
    log.info("=" * 60)
    log.info(f"🚀 Mulai Ekstraksi Historis")
    log.info(f"Target : {TANGGAL_AWAL} s/d {TANGGAL_AKHIR} ({total} hari)")
    log.info(f"Storage: {'Neon + SQLite' if neon_engine else 'SQLite saja'}")
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

            if sudah_diproses(neon_engine, tgl):
                log.info(f"[{idx:>4}/{total}] {tgl_str} - Dilewati (sudah di checkpoint)")
                continue

            log.info(f"[{idx:>4}/{total}] Memproses: {tgl_str}")

            try:
                # 1. Injeksi tanggal
                date_input = await page.wait_for_selector("input[name='tanggal']", timeout=TIMEOUT_MS)
                await date_input.evaluate(f"""
                    (el) => {{
                        el.value = '{tgl_str}';
                        el.dispatchEvent(new Event('input', {{ bubbles: true }}));
                        el.dispatchEvent(new Event('change', {{ bubbles: true }}));
                    }}
                """)

                # 2. Pilih Surabaya
                await page.wait_for_selector("select[name='kabkota']", timeout=TIMEOUT_MS)
                await page.select_option("select[name='kabkota']", label="Kota Surabaya")

                # 3. Klik Tampilkan
                btn = await page.wait_for_selector("button:has-text('Tampilkan')", timeout=TIMEOUT_MS)
                await btn.click()
                await page.wait_for_selector("table", timeout=15000)

                # 4. Parsing tabel
                rows_data = []
                for row in await page.query_selector_all("table tbody tr"):
                    cells = await row.query_selector_all("td")
                    if len(cells) < 5: continue
                    vals = [(await c.inner_text()).strip() for c in cells]
                    nama = normalisasi_nama(vals[1])
                    if nama in WHITELIST_MAP:
                        harga = parse_harga(vals[4])
                        if harga:
                            rows_data.append({
                                "komoditas": nama,
                                "satuan":    vals[2],
                                "harga":     harga,
                                "kategori":  WHITELIST_MAP[nama],
                            })

                # 5. Simpan
                if rows_data:
                    sqlite_simpan_batch(rows_data, tgl_str)
                    if neon_engine:
                        neon_simpan_batch(neon_engine, rows_data, tgl_str)
                    log.info(f"         [OK] {len(rows_data)} komoditas tersimpan.")
                else:
                    log.warning(f"         [!!] Data kosong / hari libur.")
                    sqlite_tandai_kosong(tgl_str)
                    if neon_engine:
                        neon_tandai_kosong(neon_engine, tgl_str)

            except Exception as e:
                log.error(f"         [X] Error pada {tgl_str}: {e}")

            await asyncio.sleep(4.0)

        await browser.close()

    log.info("=" * 60)
    log.info("EKSTRAKSI HISTORIS SELESAI")
    log.info("=" * 60)

# ════════════════════════════════════════
# VERIFIKASI CLI
# ════════════════════════════════════════
def verifikasi_hasil(neon_engine=None):
    # Prioritas Neon, fallback SQLite
    if neon_engine:
        print("\n🔍 Verifikasi dari Neon Cloud...")
        try:
            with neon_engine.connect() as conn:
                total = conn.execute(text("SELECT COUNT(*) FROM harga_historis")).scalar()
                hari  = conn.execute(text("SELECT COUNT(DISTINCT tanggal_data) FROM harga_historis")).scalar()
                print(f"📈 Total: {total:,} baris dari {hari} hari aktif")
                rekap = conn.execute(text("""
                    SELECT tanggal_data, COUNT(*) FROM harga_historis
                    GROUP BY tanggal_data ORDER BY tanggal_data DESC LIMIT 10
                """)).fetchall()
                print("\n📊 10 Tanggal Terakhir:")
                for r in rekap:
                    print(f"   {r[0]} : {r[1]:>2} komoditas")
            return
        except Exception as e:
            print(f"⚠️  Neon gagal ({e}), fallback ke SQLite...")

    print("\n🔍 Verifikasi dari SQLite lokal...")
    with sqlite3.connect(DB_PATH) as conn:
        total = conn.execute("SELECT COUNT(*) FROM harga_historis").fetchone()[0]
        hari  = conn.execute("SELECT COUNT(DISTINCT tanggal_data) FROM harga_historis").fetchone()[0]
        print(f"📈 Total: {total:,} baris dari {hari} hari aktif")
        rekap = conn.execute("""
            SELECT tanggal_data, COUNT(*) FROM harga_historis
            GROUP BY tanggal_data ORDER BY tanggal_data DESC LIMIT 10
        """).fetchall()
        print("\n📊 10 Tanggal Terakhir:")
        for r in rekap:
            print(f"   {r[0]} : {r[1]:>2} komoditas")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="MarketCast Historical Scraper")
    parser.add_argument("--verify", action="store_true", help="Hanya rekap database")
    args = parser.parse_args()

    if args.verify:
        neon_engine = init_neon()
        verifikasi_hasil(neon_engine)
    else:
        asyncio.run(run_scraper())
        neon_engine = init_neon()
        verifikasi_hasil(neon_engine)