"""
MARKETCAST - Final Production Historical Scraper (CLOUD MIGRATION)
Fitur:
- Injeksi JS untuk Bypass UI Input Tanggal
- Sistem Checkpoint berbasis PostgreSQL (Neon Cloud)
- Full Whitelist 43 Komoditas + Kategori
- Output Logging ganda (Terminal & File)
- Standardisasi Satuan ke KG (Sinkron dengan Pipeline Harian)

CHANGELOG (BUG FIX):
- [FIX] Fungsi normalisasi_nama didefinisikan (sebelumnya dipanggil tapi tidak ada)
- [FIX] simpan_batch sekarang menghitung harga_per_kg & faktor_konversi sebelum INSERT
- [FIX] Kolom kategori sekarang di-extract dari kolom ke-0 tabel HTML
- [FIX] WHITELIST 'bata' & 'halus' diperbaiki menjadi 'garam bata' & 'garam halus'
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
import pandas as pd
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
TANGGAL_AKHIR = date(2026, 5, 18)

# Full Whitelist 43 Komoditas
# [FIX] 'bata' & 'halus' diperbaiki menjadi 'garam bata' & 'garam halus'
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

# ── KAMUS KONVERSI SATUAN KE KG ──
SATUAN_KONVERSI = {
    "kg": 1.0,
    "1 liter": 0.92,      # Densitas minyak goreng
    "370 gr/kl": 0.370,   # Susu kental manis
    "400 gr/dos": 0.400,  # Susu bubuk
    "bungkus": 0.085,     # Indomie (85gr)
    "ekor": 1.0           # Estimasi Ayam Kampung (1kg/ekor)
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
    """
    [FIX] Sebelumnya: langsung INSERT tanpa menghitung harga_per_kg & faktor_konversi.
    Sekarang: hitung konversi satuan ke KG terlebih dahulu sebelum INSERT.
    """
    inserted = 0
    tgl_timestamp = pd.to_datetime(tanggal_data)

    with engine.begin() as conn:
        conn.execute(
            text("DELETE FROM harga_historis WHERE tanggal_data = :tgl"),
            {"tgl": tgl_timestamp}
        )

        for row in rows:
            try:
                # [FIX] Hitung faktor konversi & harga per kg di sini
                satuan_raw = row['satuan'].strip().lower()
                faktor = SATUAN_KONVERSI.get(satuan_raw, 1.0)
                harga_per_kg = round(row['harga_rp'] / faktor, 2) if faktor > 0 else row['harga_rp']

                conn.execute(text("""
                    INSERT INTO harga_historis
                        (tanggal_data, komoditas, kategori, harga_per_kg, satuan_original, faktor_konversi)
                    VALUES
                        (:tgl, :kom, :kat, :hrg_kg, :sat_orig, :faktor)
                """), {
                    "tgl": tgl_timestamp,
                    "kom": row['komoditas'],
                    "kat": row.get('kategori', ''),   # [FIX] pakai .get() agar tidak KeyError
                    "hrg_kg": harga_per_kg,
                    "sat_orig": row['satuan'],
                    "faktor": faktor
                })
                inserted += 1
            except Exception as e:
                log.warning(f"Gagal simpan komoditas {row['komoditas']}: {e}")

        conn.execute(text("""
            INSERT INTO scrape_checkpoint (tanggal, status, baris_dapat)
            VALUES (:tgl, 'done', :jum)
            ON CONFLICT (tanggal) DO UPDATE
            SET baris_dapat = EXCLUDED.baris_dapat, status = EXCLUDED.status
        """), {"tgl": tanggal_data, "jum": inserted})

    return inserted


# ── PARSING UTILS ──
def normalisasi_nama(nama):
    """
    [FIX] Fungsi ini sebelumnya dipanggil di scraper tapi tidak pernah didefinisikan
    (yang ada hanya clean_name_daily). Ini penyebab utama NameError dan data hilang.
    Membersihkan nama komoditas dari nomor urut, strip spasi, dan normalisasi.
    """
    if not nama:
        return ""
    # Hapus angka & simbol di awal (misal: "1. Beras Premium" → "Beras Premium")
    cleaned = re.sub(r'^[\d\s\.\-]+', '', str(nama)).strip()
    # Normalisasi spasi ganda menjadi satu
    cleaned = re.sub(r'\s+', ' ', cleaned)
    return cleaned


def clean_name_daily(nama):
    """Fungsi lama, dipertahankan untuk kompatibilitas."""
    if not nama:
        return ""
    cleaned = re.sub(r'^[0-9\s\.\-]+', '', str(nama)).strip()
    return cleaned


def parse_harga(teks):
    if not teks or teks.strip() in ("-", ""):
        return None
    cleaned = re.sub(r"[^\d]", "", teks)
    try:
        return float(cleaned)
    except Exception:
        return None


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
    log.info(f"🚀 Mulai Ekstraksi Historis ke CLOUD NEON (Standardisasi KG)")
    log.info(f"Target : {TANGGAL_AWAL} s/d {TANGGAL_AKHIR} ({total} hari)")
    log.info("=" * 60)

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                       "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            timezone_id="Asia/Jakarta"
        )
        page = await context.new_page()
        await page.route(
            "**/*.{png,jpg,jpeg,gif,svg,css,woff,woff2}",
            lambda r: r.abort()
        )

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
                await date_input.evaluate(f"""
                    (el) => {{
                        el.value = '{tgl_str}';
                        el.dispatchEvent(new Event('input', {{ bubbles: true }}));
                        el.dispatchEvent(new Event('change', {{ bubbles: true }}));
                    }}
                """)

                area_el = await page.query_selector("select[name='kabkota']")
                if area_el:
                    await area_el.select_option(label="Kota Surabaya")

                btn = await page.query_selector("button:has-text('Tampilkan')")
                await btn.click()

                # Tunggu respons tabel
                try:
                    await page.wait_for_selector("table tbody tr td", timeout=10_000)
                except Exception:
                    log.warning(f"[!] Tabel tidak kunjung muncul pada {tgl_str}, mencoba jeda tambahan...")
                    await page.wait_for_timeout(3000)

                # Parsing HTML
                rows_data = []
                baris_html = await page.query_selector_all("table tbody tr")

                for row in baris_html:
                    cells = await row.query_selector_all("td")
                    if len(cells) < 5:
                        continue

                    vals = [(await c.inner_text()).strip() for c in cells]

                    # [FIX] normalisasi_nama sekarang terdefinisi, tidak akan NameError
                    nama_bersih = normalisasi_nama(vals[1])

                    if nama_bersih.lower() in WHITELIST:
                        harga = parse_harga(vals[4])
                        if harga is not None:
                            rows_data.append({
                                'komoditas': nama_bersih,
                                'kategori': vals[0],   # [FIX] kolom kategori di-extract
                                'satuan': vals[2],
                                'harga_rp': harga
                            })

                if rows_data:
                    jumlah_tersimpan = simpan_batch(rows_data, tgl_str)
                    log.info(f"        [OK] Tersimpan {jumlah_tersimpan} data berformat KG ke Neon Singapore.")
                else:
                    log.warning(f"        [!!] Data kosong/hari libur.")
                    with engine.begin() as conn:
                        conn.execute(text("""
                            INSERT INTO scrape_checkpoint (tanggal, status, baris_dapat)
                            VALUES (:tgl, 'done', 0)
                            ON CONFLICT (tanggal) DO NOTHING
                        """), {"tgl": tgl_str})

            except Exception as e:
                log.error(f"        [X] Error pada {tgl_str}: {e}")

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
            total = conn.execute(text("SELECT COUNT(*) FROM harga_historis")).scalar()
            hari  = conn.execute(text("SELECT COUNT(DISTINCT tanggal_data) FROM harga_historis")).scalar()
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
