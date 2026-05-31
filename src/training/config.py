"""
src/training/config.py
======================
Single source of truth untuk semua konstanta, path, dan utilitas
di seluruh pipeline training PBL-MarketCast.

INFRASTRUKTUR DOCKER (docker-compose.yml):
──────────────────────────────────────────────────────────────
  Service   Container                 Port
  db        marketcast_db_container   host:5433 → container:5432
  adminer   marketcast_adminer        host:8080 → container:8080
  mlflow    marketcast_mlflow         host:5000 → container:5000
  Network   marketcast_network (bridge)

  Training TIDAK dijalankan via Docker service —
  dijalankan lokal: cd src/training && python train_all.py
  Koneksi ke DB & MLflow lewat port yang di-expose Docker.
"""

import os
import logging
from dotenv import load_dotenv
load_dotenv()
import numpy as np
import pandas as pd
from pathlib import Path
from sklearn.metrics import mean_absolute_error, mean_squared_error

# ─────────────────────────────────────────────────────────────
# KONEKSI DATABASE
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://postgres:password123@localhost:5433/marketcast_dw"
)
# Komponen individual — dipakai SQLAlchemy dan psycopg2 secara langsung
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = int(os.getenv("DB_PORT", "5433"))          # host port, bukan container port
DB_USER = os.getenv("DB_USER", "postgres")
DB_PASS = os.getenv("DB_PASSWORD", "password123")
DB_NAME = os.getenv("DB_NAME", "marketcast_dw")

# MLFLOW + DAGSHUB
DAGSHUB_USER  = os.getenv("DAGSHUB_USER",  "kadeksavitady")
DAGSHUB_REPO  = os.getenv("DAGSHUB_REPO",  "MarketCast")
DAGSHUB_TOKEN = os.getenv("DAGSHUB_TOKEN", "")

# URI aktif: DagsHub jika token tersedia, lokal jika tidak
_DAGSHUB_URI = f"https://dagshub.com/{DAGSHUB_USER}/{DAGSHUB_REPO}.mlflow"
_LOCAL_URI   = "http://localhost:5000"

MLFLOW_TRACKING_URI   = os.getenv("MLFLOW_TRACKING_URI",
                                   _DAGSHUB_URI if DAGSHUB_TOKEN else _LOCAL_URI)
MLFLOW_EXP_TOURNAMENT = "MarketCast-Tournament"
MLFLOW_EXP_SPECIALIZE = "MarketCast-Specialization"

# Flag idempotency — dagshub.init() hanya dipanggil SEKALI per proses
# meskipun init_mlflow() dipanggil berkali-kali (dari train_all + tiap model)
_MLFLOW_INITIALIZED = False
_ACTIVE_URI         = ""


def init_mlflow() -> str:
    """
    Inisialisasi koneksi MLflow — idempoten, aman dipanggil berkali-kali.

    KENAPA IDEMPOTEN PENTING:
        train_all.py memanggil init_mlflow() di run_tournament/run_specialize.
        Lalu tiap model (train_sarima, train_prophet, train_xgboost) juga
        memanggil init_mlflow() di dalam fungsinya sendiri.
        Tanpa flag, dagshub.init() terpanggil 10× per tournament run —
        menyebabkan re-print "Initialized MLflow..." berulang dan
        potensi reset credential di tengah jalan.

        Dengan flag _MLFLOW_INITIALIZED: pemanggilan pertama melakukan setup,
        pemanggilan berikutnya langsung return URI yang sudah aktif.

    Returns:
        str: URI aktif (DagsHub atau lokal)
    """
    global _MLFLOW_INITIALIZED, _ACTIVE_URI
    import mlflow

    # Short-circuit: sudah diinit, langsung return
    if _MLFLOW_INITIALIZED:
        return _ACTIVE_URI

    _log = logging.getLogger("config")

    if DAGSHUB_TOKEN:
        try:
            import dagshub
            # Credentials via env — tidak membutuhkan interactive login
            os.environ["MLFLOW_TRACKING_USERNAME"] = DAGSHUB_USER
            os.environ["MLFLOW_TRACKING_PASSWORD"] = DAGSHUB_TOKEN
            dagshub.init(
                repo_name  = DAGSHUB_REPO,
                repo_owner = DAGSHUB_USER,
                mlflow     = True,
            )
            _ACTIVE_URI = _DAGSHUB_URI
            _log.info(f"MLflow → DagsHub: {_ACTIVE_URI}")

        except ImportError:
            _log.warning(
                "dagshub tidak terinstall. pip install dagshub\n"
                "Fallback ke MLflow lokal."
            )
            _ACTIVE_URI = _LOCAL_URI
            mlflow.set_tracking_uri(_ACTIVE_URI)

        except Exception as e:
            _log.warning(f"DagsHub init gagal ({e}). Fallback ke lokal.")
            _ACTIVE_URI = _LOCAL_URI
            mlflow.set_tracking_uri(_ACTIVE_URI)
    else:
        _ACTIVE_URI = MLFLOW_TRACKING_URI
        mlflow.set_tracking_uri(_ACTIVE_URI)
        _log.info(
            f"DAGSHUB_TOKEN tidak ditemukan → MLflow lokal: {_ACTIVE_URI}\n"
            "Set DAGSHUB_TOKEN di .env untuk koneksi ke DagsHub."
        )

    _MLFLOW_INITIALIZED = True
    return _ACTIVE_URI

# ─────────────────────────────────────────────────────────────
# PATH — semua relatif terhadap root repo
# ─────────────────────────────────────────────────────────────
DIR_CLUSTERING = Path("outputs/clustering")   # output Tahap 0
DIR_MODELS     = Path("outputs/models")       # model pkl lokal (opsional)
DIR_REGISTRY   = Path("outputs/registry")     # model_registry_map.yaml

CSV_PREPROCESSED   = DIR_CLUSTERING / "data_preprocessed.csv"
CSV_CLUSTER_ASSIGN = DIR_CLUSTERING / "cluster_assignments.csv"
CSV_CENTROID       = DIR_CLUSTERING / "centroid_representatives.csv"
YAML_MODEL_REGISTRY = DIR_REGISTRY  / "model_registry_map.yaml"

SATUAN_TO_KG = {
    "kg"        : 1.000,
    "1 liter"   : 0.920,
    "370 gr/kl" : 0.370,
    "400 gr/dos": 0.400,
    "bungkus"   : 0.085,
    "ekor"      : 1.200,
}

TRAIN_RATIO    = 0.80   # 80% pertama → train, 20% akhir → test
FORECAST_DAYS  = 30     # hari ke depan yang diprediksi (semua model)
MIN_TRAIN_ROWS = 180    # minimum data train = 6 bulan (guard data terlalu pendek)

# ─────────────────────────────────────────────────────────────
# DYNAMIC CLUSTER LOADER
# ─────────────────────────────────────────────────────────────
def _download_clustering_artifacts() -> bool:
    """
    Download clustering artifacts dari MLflow DagHub ke outputs/clustering/.
    Dipanggil otomatis kalau CSV tidak ada di disk lokal.
    Return True kalau berhasil, False kalau gagal.
    """
    _log = logging.getLogger("config")
    try:
        import mlflow, dagshub
        dagshub.init(repo_name=DAGSHUB_REPO, repo_owner=DAGSHUB_USER, mlflow=True)
        client = mlflow.tracking.MlflowClient()

        # Cari run KMeans-Final terbaru di experiment siskaperbapo-clustering
        exp = client.get_experiment_by_name("siskaperbapo-clustering")
        if exp is None:
            _log.warning("Experiment siskaperbapo-clustering tidak ditemukan di MLflow")
            return False

        runs = client.search_runs(
            exp.experiment_id,
            filter_string="tags.mlflow.runName = \'KMeans-Final\'",
            order_by=["attributes.start_time DESC"],
            max_results=1,
        )
        if not runs:
            _log.warning("Tidak ada run KMeans-Final di MLflow")
            return False

        run_id = runs[0].info.run_id
        _log.info(f"Download clustering artifacts dari run {run_id[:8]}...")

        DIR_CLUSTERING.mkdir(parents=True, exist_ok=True)
        mlflow.artifacts.download_artifacts(
            run_id=run_id,
            artifact_path="clustering_results",
            dst_path=str(DIR_CLUSTERING.parent.parent),
        )
        _log.info(f"✅ Clustering artifacts berhasil di-download ke {DIR_CLUSTERING}")
        return True

    except Exception as e:
        _log.warning(f"Gagal download clustering artifacts: {e}")
        return False


def load_cluster_map(csv_path: Path = CSV_CLUSTER_ASSIGN) -> dict:
    _log = logging.getLogger("config")

    # Kalau CSV tidak ada, coba download dari MLflow dulu
    if not csv_path.exists():
        _log.info(f"{csv_path} tidak ada — mencoba download dari MLflow...")
        success = _download_clustering_artifacts()
        if not success or not csv_path.exists():
            _log.warning("Download gagal — pakai CLUSTER_MAP_FALLBACK")
            return CLUSTER_MAP_FALLBACK

    df            = pd.read_csv(csv_path)
    col_komoditas = next((c for c in df.columns if "komoditas" in c.lower()),
                         "komoditas")
    col_cluster   = next(
        (c for c in df.columns if "cluster" in c.lower() and "label" in c.lower()),
        next((c for c in df.columns if "cluster" in c.lower()), "cluster_label")
    )

    result = {}
    for _, row in df.iterrows():
        cluster   = str(row[col_cluster]).strip()
        komoditas = str(row[col_komoditas]).strip()
        result.setdefault(cluster, []).append(komoditas)

    _log.info(f"Cluster map loaded: {len(result)} cluster, "
              f"{sum(len(v) for v in result.values())} komoditas")
    return result


def load_centroid_list(csv_path: Path = CSV_CENTROID) -> list:
    """
    Baca centroid_representatives.csv.
    Return: list 3 nama komoditas yang menjadi wakil setiap cluster.

    Fallback: ambil elemen pertama tiap cluster dari CLUSTER_MAP_FALLBACK
    jika CSV belum ada.
    """
    if not csv_path.exists():
        return [members[0] for members in CLUSTER_MAP_FALLBACK.values()]
    df  = pd.read_csv(csv_path)
    col = next((c for c in df.columns if "komoditas" in c.lower()), df.columns[0])
    return df[col].str.strip().tolist()


# ─────────────────────────────────────────────────────────────
# CLUSTER LOOKUP UTILS
# ─────────────────────────────────────────────────────────────
def get_cluster(komoditas: str, cluster_map: dict = None) -> str:
    """Return nama cluster penuh untuk satu komoditas."""
    cmap = cluster_map or load_cluster_map()
    for cluster, members in cmap.items():
        if komoditas in members:
            return cluster
    return "unknown"


def get_cluster_short(komoditas: str, cluster_map: dict = None) -> str:
    """
    Return label pendek cluster (C0_LabilDatar, dst).
    Dipakai sebagai tag di MLflow dan argumen --champion di CLI.

    DYNAMIC LABEL SUPPORT:
    Label cluster dari clustering.py bersifat dinamis — bisa berubah
    sesuai karakteristik data terkini. Fungsi ini meng-handle dua format:
        Format lama (hardcode): "Cluster 0: Labil & Murah (→Datar)"
        Format baru (dinamis) : "Cluster 0: Labil & Mahal (→Datar)"
    Keduanya akan di-map ke "C0_<label>" berdasarkan nomor cluster.
    """
    full = get_cluster(komoditas, cluster_map)

    # Dynamic mapping: ekstrak nomor cluster dari label string
    # Format: "Cluster N: ..." → "CN_<slug>"
    import re
    match = re.match(r"Cluster\s+(\d+):\s*(.+)", full)
    if match:
        cid   = match.group(1)
        desc  = match.group(2).strip()
        # Buat slug dari deskripsi: "Labil & Mahal (→Datar)" → "LabilMahalDatar"
        slug  = re.sub(r"[^a-zA-Z0-9]", "", desc.replace("→", "").replace("↑", "").replace("↓", ""))
        return f"C{cid}_{slug}"

    # Fallback: return full label kalau tidak bisa di-parse
    return full

# ─────────────────────────────────────────────────────────────
# LOGGING
# ─────────────────────────────────────────────────────────────
def get_logger(name: str) -> logging.Logger:
    """
    Logger terpusat dengan format konsisten di semua modul.
    Format: HH:MM:SS | LEVEL | nama_modul | pesan
    """
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        datefmt="%H:%M:%S",
    )
    return logging.getLogger(name)


# ─────────────────────────────────────────────────────────────
# METRICS
# ─────────────────────────────────────────────────────────────
def compute_metrics(y_true: np.ndarray, y_pred: np.ndarray) -> dict:
    from sklearn.metrics import r2_score
    y_true = np.array(y_true, dtype=float)
    y_pred = np.array(y_pred, dtype=float)

    mae   = mean_absolute_error(y_true, y_pred)
    rmse  = np.sqrt(mean_squared_error(y_true, y_pred))

    nonzero = y_true != 0
    mape    = (np.mean(np.abs(
                   (y_true[nonzero] - y_pred[nonzero]) / y_true[nonzero]
               )) * 100) if nonzero.any() else 0.0

    smape = np.mean(
        2 * np.abs(y_pred - y_true) / (np.abs(y_true) + np.abs(y_pred) + 1e-8)
    ) * 100

    # R² — seberapa baik model menjelaskan variansi data
    # R²=1 sempurna, R²=0 sama dengan prediksi rata-rata, R²<0 lebih buruk dari rata-rata
    r2 = r2_score(y_true, y_pred) if len(y_true) > 1 else 0.0

    return {
        "mae"  : round(float(mae),   2),
        "rmse" : round(float(rmse),  2),
        "mape" : round(float(mape),  4),
        "smape": round(float(smape), 4),
        "r2"   : round(float(r2),    4),
    }