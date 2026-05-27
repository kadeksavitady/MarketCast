"""
MARKETCAST - Model Expiry Monitor
Cek apakah model sudah lebih dari 365 hari sejak training terakhir.
Kalau iya, buat GitHub Issue sebagai notifikasi ke developer.
"""

import os
import sys
import logging
from datetime import datetime, timezone
import requests
import mlflow
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
log = logging.getLogger("MarketCast-ModelMonitor")

# ── KONFIGURASI ──
MLFLOW_TRACKING_URI      = os.getenv("MLFLOW_TRACKING_URI")
MLFLOW_TRACKING_USERNAME = os.getenv("MLFLOW_TRACKING_USERNAME")
MLFLOW_TRACKING_PASSWORD = os.getenv("MLFLOW_TRACKING_PASSWORD")
GITHUB_TOKEN             = os.getenv("GITHUB_TOKEN")
GITHUB_REPO              = os.getenv("GITHUB_REPO", "kadeksavitady/MarketCast")
DEVELOPER_EMAILS         = os.getenv("DEVELOPER_EMAILS", "")

EXPERIMENT_NAME  = "MarketCast-Specialization"
EXPIRY_DAYS      = 365


def setup_mlflow():
    """Konfigurasi koneksi ke Dagshub MLflow."""
    if not all([MLFLOW_TRACKING_URI, MLFLOW_TRACKING_USERNAME, MLFLOW_TRACKING_PASSWORD]):
        log.error("❌ Kredensial MLflow tidak lengkap. Cek environment variables.")
        sys.exit(1)

    os.environ["MLFLOW_TRACKING_USERNAME"] = MLFLOW_TRACKING_USERNAME
    os.environ["MLFLOW_TRACKING_PASSWORD"] = MLFLOW_TRACKING_PASSWORD
    mlflow.set_tracking_uri(MLFLOW_TRACKING_URI)
    log.info(f"✅ MLflow terhubung ke: {MLFLOW_TRACKING_URI}")


def get_latest_training_date() -> datetime | None:
    """
    Ambil tanggal run terbaru dari experiment MarketCast-Specialization.
    Return datetime (UTC) atau None kalau tidak ditemukan.
    """
    client = mlflow.tracking.MlflowClient()

    # Cari experiment by name
    experiment = client.get_experiment_by_name(EXPERIMENT_NAME)
    if not experiment:
        log.error(f"❌ Experiment '{EXPERIMENT_NAME}' tidak ditemukan di MLflow.")
        return None

    experiment_id = experiment.experiment_id
    log.info(f"📋 Experiment ditemukan: '{EXPERIMENT_NAME}' (ID: {experiment_id})")

    # Ambil semua run, urutkan dari yang terbaru
    runs = client.search_runs(
        experiment_ids=[experiment_id],
        order_by=["start_time DESC"],
        max_results=1  # cukup ambil 1 terbaru
    )

    if not runs:
        log.warning("⚠️ Belum ada run di experiment ini.")
        return None

    latest_run = runs[0]
    # start_time dari MLflow dalam milidetik (Unix timestamp)
    latest_ts_ms = latest_run.info.start_time
    latest_dt = datetime.fromtimestamp(latest_ts_ms / 1000, tz=timezone.utc)

    log.info(f"🕒 Run terbaru: '{latest_run.info.run_name}' pada {latest_dt.strftime('%Y-%m-%d %H:%M:%S')} UTC")
    return latest_dt


def hitung_usia_model(trained_at: datetime) -> int:
    """Hitung berapa hari sejak tanggal training."""
    now = datetime.now(tz=timezone.utc)
    selisih = now - trained_at
    return selisih.days


def buat_github_issue(usia_hari: int, trained_at: datetime):
    """Buat GitHub Issue sebagai notifikasi ke developer."""
    if not GITHUB_TOKEN:
        log.error("❌ GITHUB_TOKEN tidak ditemukan. Tidak bisa buat issue.")
        return False

    tanggal_training  = trained_at.strftime("%d %B %Y")
    tanggal_sekarang  = datetime.now().strftime("%d %B %Y")

    # Hitung rentang data untuk retraining
    tahun_sekarang    = datetime.now().year
    tahun_mulai_data  = tahun_sekarang - 5

    # Bangun daftar assignee dari DEVELOPER_EMAILS kalau ada
    # (GitHub issue assignee pakai username, bukan email — ini untuk body saja)
    mention_emails = ""
    if DEVELOPER_EMAILS:
        emails = [e.strip() for e in DEVELOPER_EMAILS.split(",") if e.strip()]
        mention_emails = "\n**Developer yang perlu ditindaklanjuti:**\n" + \
                         "\n".join(f"- {email}" for email in emails)

    title = f"⚠️ [MODEL ALERT] Model sudah {usia_hari} hari — Retraining diperlukan"

    body = f"""## 🔔 Notifikasi Expiry Model MarketCast

> Issue ini dibuat otomatis oleh sistem monitoring MarketCast.

---

### 📊 Status Model Saat Ini

| Info | Detail |
|------|--------|
| **Tanggal Training Terakhir** | {tanggal_training} |
| **Tanggal Cek** | {tanggal_sekarang} |
| **Usia Model** | **{usia_hari} hari** (batas: {EXPIRY_DAYS} hari) |
| **Experiment MLflow** | `{EXPERIMENT_NAME}` |
| **Status** | ❌ **PERLU RETRAINING** |

---

### 🛠️ Tindakan yang Diperlukan

Model prediksi harga pangan MarketCast sudah melewati batas **{EXPIRY_DAYS} hari** sejak training terakhir.  
Performa prediksi kemungkinan sudah menurun karena pola harga pasar telah berubah.

**Langkah retraining:**

1. **Siapkan data terbaru** — gunakan data 5 tahun terakhir:
   - Rentang data: **{tahun_mulai_data} s/d {tahun_sekarang}**
   - Sumber: tabel `harga_historis` di Neon DB (sudah ter-update via daily scraper)

2. **Jalankan ulang pipeline clustering** (`siskaperbapo-clustering`) di Dagshub

3. **Jalankan ulang pipeline modeling** (`MarketCast-Specialization`) di Dagshub

4. **Verifikasi** hasil run terbaru di MLflow Dagshub:  
   🔗 https://dagshub.com/kadeksavitady/MarketCast.mlflow

5. **Tutup issue ini** setelah retraining selesai dan model baru ter-register

---

### 📎 Referensi

- MLflow Dagshub: https://dagshub.com/kadeksavitady/MarketCast
- Neon DB: cek `harga_historis` untuk ketersediaan data
{mention_emails}

---
*Auto-generated by `src/monitoring/model_monitor.py` — MarketCast Model Monitor*
"""

    url     = f"https://api.github.com/repos/{GITHUB_REPO}/issues"
    headers = {
        "Authorization": f"Bearer {GITHUB_TOKEN}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28"
    }
    payload = {
        "title": title,
        "body": body,
        "labels": ["model-alert", "retraining-needed"]
    }

    response = requests.post(url, json=payload, headers=headers)

    if response.status_code == 201:
        issue_url = response.json().get("html_url")
        log.info(f"✅ GitHub Issue berhasil dibuat: {issue_url}")
        return True
    else:
        log.error(f"❌ Gagal buat GitHub Issue: {response.status_code} — {response.text}")
        return False


def cek_label_ada(label_name: str) -> bool:
    """Cek apakah label sudah ada di repo, kalau belum buat."""
    if not GITHUB_TOKEN:
        return False

    headers = {
        "Authorization": f"Bearer {GITHUB_TOKEN}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28"
    }

    # Cek apakah label sudah ada
    url = f"https://api.github.com/repos/{GITHUB_REPO}/labels/{label_name}"
    res = requests.get(url, headers=headers)
    if res.status_code == 200:
        return True

    # Buat label kalau belum ada
    colors = {
        "model-alert": "d93f0b",        # merah
        "retraining-needed": "e4e669"   # kuning
    }
    create_url = f"https://api.github.com/repos/{GITHUB_REPO}/labels"
    requests.post(create_url, json={
        "name": label_name,
        "color": colors.get(label_name, "ededed")
    }, headers=headers)
    return True


def issue_aktif_sudah_ada() -> bool:
    """
    Cek apakah sudah ada issue aktif dengan label 'model-alert'.
    Mencegah duplikasi issue kalau minggu lalu sudah dibuat tapi belum ditutup.
    """
    if not GITHUB_TOKEN:
        return False

    headers = {
        "Authorization": f"Bearer {GITHUB_TOKEN}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28"
    }
    url    = f"https://api.github.com/repos/{GITHUB_REPO}/issues"
    params = {"state": "open", "labels": "model-alert"}
    res    = requests.get(url, headers=headers, params=params)

    if res.status_code == 200 and len(res.json()) > 0:
        existing = res.json()[0]
        log.info(f"ℹ️ Issue aktif sudah ada: {existing.get('html_url')} — skip buat issue baru.")
        return True
    return False


def run():
    log.info("=" * 60)
    log.info("🔍 MarketCast Model Monitor — Mulai pengecekan...")
    log.info("=" * 60)

    # 1. Setup MLflow
    setup_mlflow()

    # 2. Ambil tanggal training terakhir
    trained_at = get_latest_training_date()
    if not trained_at:
        log.error("❌ Tidak bisa ambil tanggal training. Monitor berhenti.")
        sys.exit(1)

    # 3. Hitung usia model
    usia = hitung_usia_model(trained_at)
    log.info(f"📅 Usia model saat ini: {usia} hari")

    # 4. Evaluasi
    if usia < EXPIRY_DAYS:
        sisa = EXPIRY_DAYS - usia
        log.info(f"✅ Model masih valid. Sisa {sisa} hari sebelum perlu retraining.")
        return

    # 5. Model sudah expired — pastikan label ada lalu buat issue
    log.warning(f"⚠️ Model sudah {usia} hari! Melampaui batas {EXPIRY_DAYS} hari.")

    # Pastikan label tersedia di repo
    for label in ["model-alert", "retraining-needed"]:
        cek_label_ada(label)

    # Cegah duplikasi issue
    if issue_aktif_sudah_ada():
        log.info("✅ Issue sudah ada, tidak perlu buat duplikat. Selesai.")
        return

    # Buat issue baru
    berhasil = buat_github_issue(usia, trained_at)
    if berhasil:
        log.info("🎯 Notifikasi berhasil dikirim ke GitHub Issues.")
    else:
        log.error("❌ Notifikasi gagal dikirim.")
        sys.exit(1)


if __name__ == "__main__":
    run()