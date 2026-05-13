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

    CARA PAKAI:
        from config import init_mlflow
        init_mlflow()  # panggil sekali di awal, aman dipanggil lagi

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
# CLUSTER MAP — fallback hardcode
# ─────────────────────────────────────────────────────────────
# Dipakai HANYA jika cluster_assignments.csv belum ada
# (misalnya: pertama kali setup, atau saat testing tanpa run preprocessing).
# Sumber aktual: load_cluster_map() baca dari CSV hasil pipeline.
#
# Hasil clustering K-Means K=3 dari preprocessing_clustering.py:
#   Cluster 0: CV tinggi (avg 0.358), tren datar  → komoditas volatile
#   Cluster 1: CV menengah (avg 0.095), tren naik → komoditas inflasi
#   Cluster 2: CV rendah (avg 0.030), harga mahal → komoditas stabil
CLUSTER_MAP_FALLBACK = {
    "Cluster 0: Labil & Murah (\u2192Datar)": [
        "Cabe Merah Besar", "Cabe Merah Keriting",
        "Cabe Rawit Merah", "Tomat Merah",
    ],
    "Cluster 1: Labil & Murah (\u2191Inflasi)": [
        "Bawang Merah", "Bawang Putih Sinco/Honan",
        "Beras Medium", "Beras Premium",
        "Daging Ayam Ras", "Gula Kristal Putih",
        "Ikan Bandeng", "Ikan Cakalang", "Ikan Kembung",
        "Ikan Tongkol", "Ikan Tuna",
        "Indomie Rasa Kari Ayam", "Jagung Pipilan Kering",
        "Kedelai Impor", "Kedelai Lokal",
        "Minyak Goreng Curah", "Minyak Goreng Kemasan Premium",
        "Minyak Goreng Kemasan Sederhana", "Minyak Goreng MINYAKITA",
        "Susu Kental Manis Merk Bendera", "Susu Kental Manis Merk Indomilk",
        "Telur Ayam Kampung", "Telur Ayam Ras",
        "Terigu Protein Sedang (Kemasan)",
    ],
    "Cluster 2: Stabil & Mahal (\u2192Datar)": [
        "Daging Ayam Kampung", "Daging Sapi Paha Belakang",
        "Ikan Asin Teri",
        "Susu Bubuk Merk Bendera (Instant)",
        "Susu Bubuk Merk Indomilk (Instant)",
    ],
}

# Lookup dua arah: label pendek ↔ nama cluster penuh
# Label pendek dipakai di MLflow tags dan CLI --champion
CLUSTER_SHORT_TO_FULL = {
    "C0_LabilDatar"  : "Cluster 0: Labil & Murah (\u2192Datar)",
    "C1_LabilInflasi": "Cluster 1: Labil & Murah (\u2191Inflasi)",
    "C2_StabilMahal" : "Cluster 2: Stabil & Mahal (\u2192Datar)",
}
CLUSTER_FULL_TO_SHORT = {v: k for k, v in CLUSTER_SHORT_TO_FULL.items()}


# ─────────────────────────────────────────────────────────────
# DYNAMIC CLUSTER LOADER
# ─────────────────────────────────────────────────────────────
def load_cluster_map(csv_path: Path = CSV_CLUSTER_ASSIGN) -> dict:
    if not csv_path.exists():
        logging.getLogger("config").warning(
            f"{csv_path} tidak ditemukan — pakai CLUSTER_MAP_FALLBACK"
        )
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
    """
    full = get_cluster(komoditas, cluster_map)
    return CLUSTER_FULL_TO_SHORT.get(full, full)


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

    return {
        "mae"  : round(float(mae),   2),
        "rmse" : round(float(rmse),  2),
        "mape" : round(float(mape),  4),
        "smape": round(float(smape), 4),
    }