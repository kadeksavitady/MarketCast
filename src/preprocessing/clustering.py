import os
import sys  
import argparse
import logging
import warnings
import tempfile
from typing import Tuple, List, Optional
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats
from sklearn.preprocessing import MinMaxScaler
import matplotlib.pyplot as plt  
from sklearn.cluster import KMeans 
import joblib

# Set path root proyek agar import internal tidak hancur
root_path = str(Path(__file__).resolve().parents[2])
if root_path not in sys.path:
    sys.path.append(root_path)

import mlflow
from src.training.config import init_mlflow
import mlflow.sklearn
from mlflow.tracking import MlflowClient

from dotenv import load_dotenv
from sqlalchemy import create_engine

warnings.filterwarnings("ignore")
logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
log = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# 1. DATA LOADING (NEON DB)
# ─────────────────────────────────────────────────────────────────────────────
def get_db_engine():
    load_dotenv()
    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        raise EnvironmentError("DATABASE_URL tidak ditemukan di .env")
    return create_engine(db_url)

def load_data(engine) -> pd.DataFrame:
    query = "SELECT * FROM harga_historis_clean"
    df = pd.read_sql(query, engine)
    df["tanggal"] = pd.to_datetime(df["tanggal"])
    log.info(f"Loaded {len(df):,} rows dari Neon DB. Siap untuk clustering.")
    return df

# ─────────────────────────────────────────────────────────────────────────────
# 2. FEATURE ENGINEERING
# ─────────────────────────────────────────────────────────────────────────────
def build_features(df: pd.DataFrame) -> pd.DataFrame:
    features = []
    for komoditas, group in df.groupby("komoditas"):
        prices = group.sort_values("tanggal")["harga_per_kg"].values
        days   = (group["tanggal"] - group["tanggal"].min()).dt.days.values

        mean_p = np.mean(prices)
        cv     = np.std(prices) / mean_p if mean_p > 0 else 0
        
        # Trend slope dikali 365 / mean_p = persentase inflasi tahunan!
        slope  = (stats.linregress(days, prices).slope * 365 / mean_p
                  if len(days) > 1 else 0)

        features.append({
            "komoditas"  : komoditas,
            "mean_harga" : mean_p,
            "cv"         : cv,
            "trend_slope": slope,
        })
    return pd.DataFrame(features).set_index("komoditas")

def find_optimal_k(X_scaled: np.ndarray, max_k: int = 10) -> Tuple[list, list, str]:
    """ Elbow Method + Silhouette Score untuk menentukan k optimal. """
    from sklearn.metrics import silhouette_score
    import tempfile

    inertias    = []
    silhouettes = [None]  # k=1 tidak ada silhouette

    for k in range(1, max_k + 1):
        km = KMeans(n_clusters=k, random_state=42, n_init=10).fit(X_scaled)
        inertias.append(km.inertia_)
        if k >= 2:
            sil = silhouette_score(X_scaled, km.labels_)
            silhouettes.append(round(sil, 4))
        log.info(f"  k={k}: inertia={km.inertia_:.2f}"
                 + (f" | silhouette={silhouettes[-1]:.4f}" if k >= 2 else ""))

    # Tentukan k optimal dari silhouette tertinggi
    sil_values    = [s for s in silhouettes if s is not None]
    k_optimal_sil = sil_values.index(max(sil_values)) + 2  # offset karena mulai k=2
    log.info(f"  k optimal (silhouette): {k_optimal_sil} "
             f"(score={max(sil_values):.4f})")

    # Plot dual-axis: Elbow + Silhouette
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 5))
    fig.suptitle("Penentuan Jumlah Cluster Optimal", fontsize=13, fontweight="bold")

    # Elbow
    ax1.plot(range(1, max_k + 1), inertias, "bx-", lw=2, markersize=8)
    ax1.axvline(x=3, color="red", lw=2, linestyle="--",
                label=f"k=3 (dipilih)")
    ax1.set_xlabel("Jumlah Cluster (k)")
    ax1.set_ylabel("Inertia (WCSS)")
    ax1.set_title("Elbow Method")
    ax1.legend()
    ax1.grid(alpha=0.3)

    # Silhouette
    k_range  = range(2, max_k + 1)
    ax2.plot(k_range, sil_values, "ro-", lw=2, markersize=8)
    ax2.axvline(x=k_optimal_sil, color="green", lw=2, linestyle="--",
                label=f"k={k_optimal_sil} (silhouette optimal)")
    ax2.axvline(x=3, color="red", lw=2, linestyle="--",
                label="k=3 (dipilih)" if k_optimal_sil != 3 else None)
    ax2.set_xlabel("Jumlah Cluster (k)")
    ax2.set_ylabel("Silhouette Score")
    ax2.set_title("Silhouette Score")
    ax2.legend()
    ax2.grid(alpha=0.3)

    plt.tight_layout()
    plot_path = "/tmp/elbow_silhouette_plot.png"
    fig.savefig(plot_path, dpi=120, bbox_inches="tight")
    plt.close(fig)

    return inertias, silhouettes, plot_path

# ─────────────────────────────────────────────────────────────────────────────
# 3. RUN PIPELINE OMNIBUS (KONSOLIDASI SINGLE RUN)
# ─────────────────────────────────────────────────────────────────────────────
def run_and_log_clustering_pipeline(df_clean: pd.DataFrame, feat_df: pd.DataFrame, k: int, mlflow_experiment: str = "MarketCast-Clustering"):
    """
    Menjalankan KMeans, membungkus seluruh parameter (cv, mean, trend_slope) ke CSV,
    mengirimkannya murni via log_artifact, lalu mendaftarkannya ke Model Registry.
    """
    # ── TAHAP 1: EKSEKUSI STATISTIKA KMEANS LOKAL ──
    cols     = ["cv", "mean_harga", "trend_slope"]
    scaler   = MinMaxScaler()
    X_scaled = scaler.fit_transform(feat_df[cols])

    km = KMeans(n_clusters=k, random_state=42, n_init=20).fit(X_scaled)
    feat_final = feat_df.copy()
    feat_final["cluster"] = km.labels_

    # Hitung Jarak Centroid
    feat_final["dist"] = 0.0
    for cid in range(k):
        mask  = feat_final["cluster"] == cid
        dists = np.linalg.norm(X_scaled[mask] - km.cluster_centers_[cid], axis=1)
        feat_final.loc[mask, "dist"] = dists

    feat_final["is_centroid"] = False
    for cid in range(k):
        nearest = feat_final[feat_final["cluster"] == cid]["dist"].idxmin()
        feat_final.loc[nearest, "is_centroid"] = True

    # Pelabelan Dinamis
    feat_final["cluster_label"] = ""
    overall_harga = feat_final["mean_harga"].median()
    overall_cv    = feat_final["cv"].median()
    
    for cid in range(k):
        mask = feat_final["cluster"] == cid
        med_harga = feat_final.loc[mask, "mean_harga"].median()
        med_cv    = feat_final.loc[mask, "cv"].median()
        med_slope = feat_final.loc[mask, "trend_slope"].median()
        
        harga_lbl = "Mahal" if med_harga > overall_harga else "Murah"
        cv_lbl    = "Labil" if med_cv > overall_cv else "Stabil"
        
        if med_slope > 0.01:
            tren_lbl = "↑Inflasi"
        elif med_slope < -0.01:
            tren_lbl = "↓Deflasi"
        else:
            tren_lbl = "→Datar"
            
        label = f"Cluster {cid}: {cv_lbl} & {harga_lbl} ({tren_lbl})"
        feat_final.loc[mask, "cluster_label"] = label
        log.info(f"  [Auto-Label] {label} (Median Harga: Rp{med_harga:,.0f})")

    # ── TAHAP 2: INTEGRASI MLFLOW REGISTRY (SINGLE RUN CLEANPAYLOAD) ──
    init_mlflow()
    mlflow.set_experiment(mlflow_experiment)
    client = MlflowClient()
    REGISTRY_NAME = "Metadata__Clustering"

    log.info(f"\n=======================================================")
    log.info(f"Mulai Proses Registrasi Metadata Clustering ke MLflow...")
    log.info(f"=======================================================")

    with mlflow.start_run(run_name="KMeans-Final-Orchestration") as run:
        mlflow.log_param("k", k)
        mlflow.set_tags({
            "step": "preprocessing_clustering",
            "project": "PBL-MarketCast",
            "type": "metadata_export"
        })

        # Mengamankan ukuran cluster dasar sebagai metrik makro
        for cid in sorted(feat_final["cluster"].unique()):
            n = (feat_final["cluster"] == cid).sum()
            mlflow.log_metric(f"cluster_{cid}_size", int(n))

        # ── TAHAP 2: INTEGRASI MLFLOW REGISTRY (KONSOLIDASI AMAN) ──
        # Membuka gerbang folder sementara ephemeral (Clean Local)
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            
            # 1. Eksekusi Elbow Plot dan simpan di tmp_path
            inertias = []
            for i in range(1, 11):
                km_test = KMeans(n_clusters=i, random_state=42, n_init=10).fit(X_scaled)
                inertias.append(km_test.inertia_)

            plt.figure(figsize=(8,4))
            plt.plot(range(1, 11), inertias, 'bx-')
            plt.savefig(tmp_path / "elbow_plot.png")
            plt.close()

            # 2. Simpan dulu scaler penunjang ke folder lokal sementara
            joblib.dump(scaler, tmp_path / "minmax_scaler.joblib")
            
            # 3. Export cluster_assignments.csv UTAMA (Berisi cv, mean, slope, cluster, label)
            assignments = feat_final[["cv", "mean_harga", "trend_slope", "cluster", "cluster_label", "dist", "is_centroid"]].copy()
            assignments.index.name = "komoditas"
            
            # 🌟 KUNCI SUKSES TIM BACKEND: Bungkus ke sub-folder khusus untuk diselundupkan ke Registry
            model_artifacts_dir = tmp_path / "model_artifacts"
            os.makedirs(model_artifacts_dir, exist_ok=True)
            assignments.to_csv(model_artifacts_dir / "cluster_assignments.csv")
            
            # 4. Export data_preprocessed.csv (WAJIB UNTUK PIPELINE TRAINING MODEL BASELINE!)
            df_export = df_clean[["tanggal", "komoditas", "harga_per_kg"]].copy()
            df_export.to_csv(tmp_path / "data_preprocessed.csv", index=False)
            
            # 5. Export centroid_representatives.csv (Pelengkap struktural config.py)
            centroids = feat_final[feat_final["is_centroid"]].index.tolist()
            pd.DataFrame({"komoditas": centroids}).to_csv(tmp_path / "centroid_representatives.csv", index=False)
            
            # 6. Export Centroid Timeseries
            for komo in centroids:
                slug = komo.lower().replace(" ", "_")
                sub_df = df_clean[df_clean["komoditas"] == komo][["tanggal", "harga_per_kg"]].copy()
                sub_df.columns = ["ds", "y"]
                sub_df.to_csv(tmp_path / f"ts_centroid_{slug}.csv", index=False)

            # 🚀 FIX CRITICAL: Terbangkan berkas penunjang (data_preprocessed, dkk) ke folder artifacts utama
            log.info("   🚀 Mengirim berkas preprocessed dan penunjang klaster ke DagsHub Artifacts...")
            mlflow.log_artifacts(tmp_path.as_posix(), artifact_path="clustering_results")
            
            # 🎯 TAHAP UTAMA: Log Model Sklearn SEKALIGUS menautkan folder CSV utama di dalamnya!
            log.info(f"   Mendaftarkan objek '{REGISTRY_NAME}' beserta berkas CSV Parameter ke Model Registry...")
            mlflow.sklearn.log_model(
                sk_model=scaler, 
                artifact_path="Metadata__Clustering_Package", 
                code_paths=[str(model_artifacts_dir / "cluster_assignments.csv")],
                registered_model_name=REGISTRY_NAME
            )

        # ── TAHAP 3: LOCK ALIAS PRODUCTION VIA CLIENT API ──
        log.info(f"   Mengunci versi terbaru '{REGISTRY_NAME}' ke label / alias 'production'...")
        
        # Karena pendaftaran sudah sukses di atas, kita tinggal minta Client mengambil versi terbaru di server
        versions = client.get_registered_model(REGISTRY_NAME).latest_versions
        latest_version = versions[0].version if versions else "1"
        
        # Set status ke @production agar FastAPI tim backend bisa langsung panggil
        client.set_registered_model_alias(
            name=REGISTRY_NAME, 
            alias="production", 
            version=latest_version
        )
        
        log.info(f"✅ BERHASIL TOTAL! {REGISTRY_NAME} v{latest_version} resmi aktif berstatus PRODUCTION.")
        log.info(f"   Anak backend sekarang bisa menarik CSV parameter langsung dari gerbang Model Registry!")
        
# ─────────────────────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Clustering pipeline PBL-MarketCast"
    )
    parser.add_argument("--k", type=int, default=3)
    parser.add_argument("--mlflow-uri", default="https://dagshub.com/kadeksavitady/MarketCast.mlflow")
    args = parser.parse_args()

    # ── Pipeline ──────────────────────────────────────────────────────────────
    log.info("=" * 60)
    log.info("  CLUSTERING PIPELINE — MarketCast")
    log.info("=" * 60)

    engine = get_db_engine()
    df_clean = load_data(engine)
    feat_df  = build_features(df_clean)
    cols = ["cv", "mean_harga", "trend_slope"]
    scaler = MinMaxScaler()
    X_scaled = scaler.fit_transform(feat_df[cols])
    log.info("Menjalankan Elbow Method untuk menentukan optimal k...")
    find_optimal_k(X_scaled, max_k=10) # Ini akan save /tmp/elbow_plot.png
    log.info("Elbow plot telah disimpan di /tmp/elbow_plot.png. Silakan cek untuk validasi nilai k.")
    run_and_log_clustering_pipeline(df_clean, feat_df, args.k)
    
    engine.dispose()

    log.info("=" * 60)
    log.info("Clustering selesai. Data hasil Clustering aman di MLflow DagsHub dan siap untuk train_all.py")
    log.info("=" * 60)

if __name__ == "__main__":
    main()