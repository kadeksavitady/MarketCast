"""
src/training/config.py
======================
Single source of truth untuk semua konstanta, path, dan utilitas
di seluruh pipeline training PBL-MarketCast.

URUTAN EKSEKUSI PIPELINE:
    Tahap 0  preprocessing_clustering.py  → data_preprocessed.csv
                                          → cluster_assignments.csv
                                          → centroid_representatives.csv
    Tahap 2  train_all.py --mode tournament → 9 MLflow runs (3 model × 3 centroid)
    Tahap 3a train_all.py --mode specialize → 37 komoditas × model juara cluster
                                              (40 total − 3 centroid = 37 non-centroid)
    Output   model_registry_map.yaml       → dipakai Tahap 3b (business logic)
"""

import os
import logging
import numpy as np
import pandas as pd
from pathlib import Path
from sklearn.metrics import mean_absolute_error, mean_squared_error

# ─────────────────────────────────────────────────────────
# MLFLOW
# ─────────────────────────────────────────────────────────
MLFLOW_TRACKING_URI  = os.getenv("MLFLOW_TRACKING_URI", "http://localhost:5000")
MLFLOW_EXP_TOURNAMENT  = "MarketCast-Tournament"      # Tahap 2
MLFLOW_EXP_SPECIALIZE  = "MarketCast-Specialization"  # Tahap 3a

# ─────────────────────────────────────────────────────────
# PATH — semua relatif terhadap root repo
# ─────────────────────────────────────────────────────────
DIR_CLUSTERING  = Path("outputs/clustering")
DIR_MODELS      = Path("outputs/models")
DIR_REGISTRY    = Path("outputs/registry")
DIR_TMP         = Path("D:/tmp")
DIR_TMP.mkdir(parents=True, exist_ok=True)

CSV_PREPROCESSED   = DIR_CLUSTERING / "harga_historis.csv"
CSV_CLUSTER_ASSIGN = DIR_CLUSTERING / "cluster_assignments.csv"
CSV_CENTROID       = DIR_CLUSTERING / "centroid_representatives.csv"

# Output Tahap 2 → 3a
YAML_MODEL_REGISTRY = DIR_REGISTRY / "model_registry_map.yaml"

# ─────────────────────────────────────────────────────────
# SATUAN KONVERSI → harga per kg
# Audit lengkap: lihat preprocessing_clustering.py
# ─────────────────────────────────────────────────────────
SATUAN_TO_KG = {
    "kg"        : 1.000,
    "1 liter"   : 0.920,   # densitas minyak goreng ~0.92 g/ml
    "370 gr/kl" : 0.370,   # 1 kaleng susu kental = 370 g
    "400 gr/dos": 0.400,   # 1 dos susu bubuk = 400 g
    "bungkus"   : 0.085,   # 1 bungkus Indomie = 85 g
    "ekor"      : 1.200,   # bobot hidup ayam kampung dewasa ~1.2 kg
                            # basis: avg harga ekor Rp63.590 ÷ 1.2 = Rp52.991/kg
                            # konsisten dengan log pipeline preprocessing
}

# ─────────────────────────────────────────────────────────
# SPLIT STRATEGY
# ─────────────────────────────────────────────────────────
# 80/20 split — bukan fixed TEST_DAYS.
# Alasan: tiap komoditas punya panjang series berbeda akibat
# missing dates & drop gap. Fixed 30 hari bisa jadi >20% untuk
# komoditas dengan data lebih sedikit → evaluasi tidak fair.
TRAIN_RATIO   = 0.80   # 80% train
FORECAST_DAYS = 30     # horizon prediksi ke depan (konsisten semua model)
MIN_TRAIN_ROWS = 180   # minimal data train setelah split (6 bulan)

# ─────────────────────────────────────────────────────────
# CLUSTER MAP — dibaca dinamis dari CSV, ini hanya fallback
# Kalau CSV_CLUSTER_ASSIGN ada, load_cluster_map() dipakai.
# Kalau tidak ada (first run), fallback ke hardcode ini.
# ─────────────────────────────────────────────────────────
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

# Label pendek → nama cluster penuh (untuk reverse lookup)
CLUSTER_SHORT_TO_FULL = {
    "C0_LabilDatar"  : "Cluster 0: Labil & Murah (\u2192Datar)",
    "C1_LabilInflasi": "Cluster 1: Labil & Murah (\u2191Inflasi)",
    "C2_StabilMahal" : "Cluster 2: Stabil & Mahal (\u2192Datar)",
}
CLUSTER_FULL_TO_SHORT = {v: k for k, v in CLUSTER_SHORT_TO_FULL.items()}


# ─────────────────────────────────────────────────────────
# DYNAMIC CLUSTER LOADER
# ─────────────────────────────────────────────────────────
def load_cluster_map(csv_path: Path = CSV_CLUSTER_ASSIGN) -> dict:
    """
    Baca cluster_assignments.csv hasil preprocessing_clustering.py.
    Return dict: {cluster_label: [komoditas, ...]}

    Lebih robust dari hardcode — kalau whitelist 40 komoditas terpenuhi
    semua di data, map ini otomatis mencerminkan kondisi aktual tanpa
    perlu edit manual config.
    """
    if not csv_path.exists():
        log = logging.getLogger("config")
        log.warning(f"{csv_path} tidak ditemukan — pakai CLUSTER_MAP_FALLBACK")
        return CLUSTER_MAP_FALLBACK

    df = pd.read_csv(csv_path)

    # Deteksi nama kolom — preprocessing bisa export berbeda
    col_komoditas = next((c for c in df.columns
                          if "komoditas" in c.lower()), "komoditas")
    col_cluster   = next((c for c in df.columns
                          if "cluster" in c.lower() and "label" in c.lower()),
                         next((c for c in df.columns
                               if "cluster" in c.lower()), "cluster_label"))

    result = {}
    for _, row in df.iterrows():
        label     = str(row[col_cluster]).strip()
        komoditas = str(row[col_komoditas]).strip()
        result.setdefault(label, []).append(komoditas)

    return result


def load_centroid_list(csv_path: Path = CSV_CENTROID) -> list:
    """
    Baca centroid_representatives.csv.
    Return list nama komoditas centroid (3 wakil cluster).
    """
    if not csv_path.exists():
        # Fallback: ambil centroid pertama tiap cluster dari CLUSTER_MAP_FALLBACK
        return [members[0] for members in CLUSTER_MAP_FALLBACK.values()]

    df = pd.read_csv(csv_path)
    col = next((c for c in df.columns if "komoditas" in c.lower()), df.columns[0])
    return df[col].str.strip().tolist()


# ─────────────────────────────────────────────────────────
# CLUSTER LOOKUP UTILS
# ─────────────────────────────────────────────────────────
def get_cluster(komoditas: str, cluster_map: dict = None) -> str:
    """Return nama cluster penuh untuk komoditas tertentu."""
    cmap = cluster_map or load_cluster_map()
    for cluster, members in cmap.items():
        if komoditas in members:
            return cluster
    return "unknown"


def get_cluster_short(komoditas: str, cluster_map: dict = None) -> str:
    """Return label pendek cluster untuk MLflow tags dan plot."""
    full = get_cluster(komoditas, cluster_map)
    return CLUSTER_FULL_TO_SHORT.get(full, full)


# ─────────────────────────────────────────────────────────
# LOGGING
# ─────────────────────────────────────────────────────────
def get_logger(name: str) -> logging.Logger:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        datefmt="%H:%M:%S",
    )
    return logging.getLogger(name)


# ─────────────────────────────────────────────────────────
# METRICS
# ─────────────────────────────────────────────────────────
def compute_metrics(y_true: np.ndarray, y_pred: np.ndarray) -> dict:
    """
    MAE   : error rata-rata dalam Rupiah — paling mudah dikomunikasikan
    RMSE  : penalti besar untuk meleset jauh — penting untuk spike harga
    MAPE  : error relatif (%) — standar jurnal forecasting pangan
    SMAPE : symmetric MAPE — robust untuk perbandingan lintas komoditas
    """
    y_true = np.array(y_true, dtype=float)
    y_pred = np.array(y_pred, dtype=float)

    mae  = mean_absolute_error(y_true, y_pred)
    rmse = np.sqrt(mean_squared_error(y_true, y_pred))

    nonzero = y_true != 0
    mape    = (np.mean(np.abs((y_true[nonzero] - y_pred[nonzero])
                               / y_true[nonzero])) * 100) if nonzero.any() else 0.0

    smape = (np.mean(2 * np.abs(y_pred - y_true)
                     / (np.abs(y_true) + np.abs(y_pred) + 1e-8)) * 100)

    return {
        "mae"  : round(float(mae),   2),
        "rmse" : round(float(rmse),  2),
        "mape" : round(float(mape),  4),
        "smape": round(float(smape), 4),
    }
