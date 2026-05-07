"""
╔══════════════════════════════════════════════════════════════════╗
║   MARKETCAST - Historical Scraper (5 Tahun Harian)               ║
║   Database : SQLite (siskaperbapo.db)                            ║
║   Fitur    : 365 Hari/Tahun, Pause/Resume, Retry Otomatis        ║
╚══════════════════════════════════════════════════════════════════╝

Instalasi:
    pip install playwright pandas openpyxl
    playwright install chromium

Jalankan:   
    python historical_scraper.py
"""

import asyncio
import re
import sqlite3
import logging
from datetime import datetime, date, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeout

# ─────────────────────────────────────────────────────────────
# KONFIGURASI
# ─────────────────────────────────────────────────────────────
BASE_URL   = "https://siskaperbapo.jatimprov.go.id/harga/tabel/?kabkota=surabayakot"
DB_PATH    = Path("data/raw/siskaperbapo.db")
TIMEZONE   = ZoneInfo("Asia/Jakarta")
HEADLESS   = False # Set False agar bisa memantau prosesnya langsung
TIMEOUT_MS = 30_000
RETRY_MAX  = 3
DELAY_ANTAR_REQUEST = 2.0  # Menghindari blokir/rate limit

# # REVISI: Rentang historis 5 tahun kebelakang sesuai Resume Diskusi 
# TANGGAL_AKHIR  = date.today()
# TANGGAL_AWAL   = TANGGAL_AKHIR.replace(year=TANGGAL_AKHIR.year - 5)

# MENGAMBIL GAP TANGGAL SCRAPER TERAKHIR SAMPAI HARI INI (25 APRIL 2026 - 7 MEI 2026)
TANGGAL_AWAL  = date(2026, 4, 25) 
TANGGAL_AKHIR = date.today()

# REVISI: Frekuensi harian (1 hari) untuk menangkap pola seasonality 
STEP_HARI = 1

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────
# DATABASE — init semua tabel [cite: 148]
# ─────────────────────────────────────────────────────────────
def init_db():
    # Pastikan folder data/raw sudah ada
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS harga_bahan_pokok (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                tanggal_scrape  TEXT NOT NULL,
                tanggal_data    TEXT,
                komoditas       TEXT,
                satuan          TEXT,
                harga_rp        REAL,
                kabkota         TEXT DEFAULT 'Surabaya',
                created_at      TEXT DEFAULT (datetime('now','localtime')),
                UNIQUE(tanggal_scrape, komoditas)
            )
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS scrape_checkpoint (
                tanggal      TEXT PRIMARY KEY,
                status       TEXT NOT NULL,
                baris_dapat  INTEGER DEFAULT 0,
                catatan      TEXT,
                updated_at   TEXT DEFAULT (datetime('now','localtime'))
            )
        """)

        conn.execute("CREATE INDEX IF NOT EXISTS idx_tgl ON harga_bahan_pokok(tanggal_scrape)")
        conn.commit()
    log.info(f"Database siap → {DB_PATH.resolve()}")


def sudah_diproses(tanggal: date) -> bool:
    with sqlite3.connect(DB_PATH) as conn:
        row = conn.execute(
            "SELECT status FROM scrape_checkpoint WHERE tanggal = ?",
            (tanggal.isoformat(),)
        ).fetchone()
    return row is not None and row[0] == "done"


def tandai_checkpoint(tanggal: date, status: str, baris: int = 0, catatan: str = ""):
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("""
            INSERT INTO scrape_checkpoint (tanggal, status, baris_dapat, catatan)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(tanggal) DO UPDATE SET
                status      = excluded.status,
                baris_dapat = excluded.baris_dapat,
                catatan     = excluded.catatan,
                updated_at  = datetime('now','localtime')
        """, (tanggal.isoformat(), status, baris, catatan))
        conn.commit()


def simpan_batch(rows: list[dict]) -> int:
    if not rows:
        return 0
    inserted = 0
    with sqlite3.connect(DB_PATH) as conn:
        for row in rows:
            try:
                conn.execute("""
                    INSERT OR IGNORE INTO harga_bahan_pokok
                        (tanggal_scrape, tanggal_data, komoditas, satuan, harga_rp, kabkota)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (
                    row["tanggal_scrape"],
                    row.get("tanggal_data"),
                    row.get("komoditas"),
                    row.get("satuan"),
                    row.get("harga_rp"),
                    row.get("kabkota", "Surabaya"),
                ))
                if conn.execute("SELECT changes()").fetchone()[0]:
                    inserted += 1
            except Exception as e:
                log.warning(f"Gagal simpan baris {row}: {e}")
        conn.commit()
    return inserted


def progres_ringkasan():
    with sqlite3.connect(DB_PATH) as conn:
        total_done  = conn.execute("SELECT COUNT(*) FROM scrape_checkpoint WHERE status='done'").fetchone()[0]
        total_error = conn.execute("SELECT COUNT(*) FROM scrape_checkpoint WHERE status='error'").fetchone()[0]
        total_baris = conn.execute("SELECT COUNT(*) FROM harga_bahan_pokok").fetchone()[0]
    return total_done, total_error, total_baris


# ─────────────────────────────────────────────────────────────
# PARSING & SCRAPING
# ─────────────────────────────────────────────────────────────
def parse_harga(text: str):
    if not text:
        return None
    cleaned = re.sub(r"\.(?=\d{3})", "", text.strip())
    cleaned = cleaned.replace(",", ".")
    try:
        return float(cleaned)
    except ValueError:
        return None


def baris_valid(cells: list[str]) -> bool:
    joined = " ".join(cells).strip()
    if not joined:
        return False
    tokens = re.findall(r"\S+", joined)
    if all(re.fullmatch(r"\d{1,2}", t) for t in tokens):
        return False
    if all(re.fullmatch(r"\d{1,2}:\d{2}", t) for t in tokens):
        return False
    bulan = {"jan","feb","mar","apr","may","jun","jul","aug","sep","oct","nov","dec",
             "januari","februari","maret","april","mei","juni","juli","agustus",
             "september","oktober","november","desember"}
    if any(t.lower() in bulan for t in tokens):
        return False
    if all(re.fullmatch(r"20[1-3]\d", t) for t in tokens):
        return False
    return True


async def scrape_tanggal(page, target: date) -> list[dict]:
    tgl_str = target.strftime("%Y-%m-%d")
    try:
        await page.goto(BASE_URL, wait_until="networkidle", timeout=TIMEOUT_MS)
    except PlaywrightTimeout:
        log.warning(f"  [{tgl_str}] Timeout load halaman")

    date_set = False
    for selector in ["input[type='date']", "input[name*='tanggal']", "input[id*='tanggal']"]:
        el = await page.query_selector(selector)
        if el:
            # Menggunakan JS Injection karena Read-Only 
            await el.evaluate(f"(el) => el.value = '{tgl_str}'")
            await el.dispatch_event("change")
            await page.wait_for_timeout(2000)
            date_set = True
            break

    if not date_set:
        for btn_sel in ["button[type='submit']", ".btn-search"]:
            btn = await page.query_selector(btn_sel)
            if btn:
                await btn.click()
                await page.wait_for_timeout(1500)
                break

    try:
        await page.wait_for_selector("table", timeout=TIMEOUT_MS)
    except PlaywrightTimeout:
        return []

    headers = []
    for sel in ["table thead th", "table tr:first-child th"]:
        els = await page.query_selector_all(sel)
        if els:
            headers = [(await el.inner_text()).strip() for el in els]
            break

    hasil = []
    row_els = await page.query_selector_all("table tbody tr")
    for row_el in row_els:
        cells   = await row_el.query_selector_all("td")
        vals    = [(await c.inner_text()).strip() for c in cells]

        if not baris_valid(vals):
            continue

        row_dict = {"tanggal_scrape": tgl_str, "tanggal_data": tgl_str, "kabkota": "Surabaya"}

        if headers and len(headers) == len(vals):
            paired = dict(zip(headers, vals))
            for k, v in paired.items():
                kl = k.lower()
                if any(x in kl for x in ["komodit", "nama", "bahan", "barang"]):
                    row_dict["komoditas"] = v
                elif any(x in kl for x in ["satuan", "unit"]):
                    row_dict["satuan"] = v
                elif any(x in kl for x in ["harga", "price", "rp"]):
                    row_dict["harga_rp"] = parse_harga(v)
        else:
            if len(vals) >= 4:
                row_dict.update({"komoditas": vals[1], "satuan": vals[2], "harga_rp": parse_harga(vals[3])})
            elif len(vals) == 3:
                row_dict.update({"komoditas": vals[0], "satuan": vals[1], "harga_rp": parse_harga(vals[2])})
            else:
                continue

        if not row_dict.get("komoditas") or re.fullmatch(r"[\d\s.,]+", row_dict.get("komoditas", "")):
            continue
        hasil.append(row_dict)

    return hasil


# ─────────────────────────────────────────────────────────────
# MAIN LOOP
# ─────────────────────────────────────────────────────────────
async def main():
    init_db()

    semua_tanggal = []
    t = TANGGAL_AWAL
    while t <= TANGGAL_AKHIR:
        semua_tanggal.append(t)
        t += timedelta(days=STEP_HARI)

    total = len(semua_tanggal)
    done, error, _ = progres_ringkasan()

    log.info(f"📅 Rentang  : {TANGGAL_AWAL} → {TANGGAL_AKHIR}")
    log.info(f"🔢 Target   : {total} hari (Harian)")
    log.info(f"✅ Selesai  : {done} | ❌ Error: {error} | ⏭ Sisa: {total - done}")

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=HEADLESS)
        context = await browser.new_context(user_agent="Mozilla/5.0...", locale="id-ID")
        page = await context.new_page()
        await page.route("**/*.{png,jpg,jpeg,gif,svg,woff,ttf,ico}", lambda r: r.abort())

        try:
            for idx, tgl in enumerate(semua_tanggal, 1):
                if sudah_diproses(tgl):
                    continue

                tgl_str = tgl.isoformat()
                log.info(f"[{idx:>4}/{total}] Scraping {tgl_str} ...")

                berhasil = False
                for attempt in range(1, RETRY_MAX + 1):
                    try:
                        rows = await scrape_tanggal(page, tgl)
                        inserted = simpan_batch(rows)
                        tandai_checkpoint(tgl, "done", inserted)
                        log.info(f"         ✔ {inserted} item disimpan")
                        berhasil = True
                        break
                    except Exception as e:
                        log.warning(f"         ✗ Percobaan {attempt}/{RETRY_MAX}: {e}")
                        await asyncio.sleep(3)

                if not berhasil:
                    tandai_checkpoint(tgl, "error", 0, "Retry failed")

                if idx % 10 == 0:
                    done_now, _, total_rows = progres_ringkasan()
                    sisa = total - done_now
                    eta = round(sisa * (DELAY_ANTAR_REQUEST + 4) / 60, 1)
                    log.info(f"\n── Progres: {done_now}/{total} | {total_rows} baris | ETA ~{eta} mnt ──\n")

                await asyncio.sleep(DELAY_ANTAR_REQUEST)

        except KeyboardInterrupt:
            log.info("\n⏸ Dihentikan oleh user.")
        finally:
            await browser.close()

    log.info("🏁 Selesai.")

if __name__ == "__main__":
    asyncio.run(main())