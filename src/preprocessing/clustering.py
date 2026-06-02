import os
import sys  
import argparse
import logging
import warnings
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats
from sklearn.cluster import KMeans
from sklearn.preprocessing import MinMaxScaler
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

# ─────────────────────────────────────────────────────────────────────────────
# 3. RUN PIPELINE OMNIBUS (KONSOLIDASI SINGLE RUN)
# ─────────────────────────────────────────────────────────────────────────────
def run_and_log_clustering_pipeline(df_clean: pd.DataFrame, feat_df: pd.DataFrame, k: int, mlflow_experiment: str = "MarketCast-Clustering"):
    """
    Menjalankan algoritma KMeans secara lokal, mengotomasi penamaan klaster secara dinamis,
    lalu menyatukan semua pengiriman berkas artefak dan pendaftaran model registry 
    ke dalam SATU sesi pelacakan tunggal yang aman.
    """
    # ── TAHAP 1: EKSEKUSI STATISTIKA KMEANS ──
    cols     = ["cv", "mean_harga", "trend_slope"]
    scaler   = MinMaxScaler()
    X_scaled = scaler.fit_transform(feat_df[cols])

    km = KMeans(n_clusters=k, random_state=42, n_init=20).fit(X_scaled)
    feat_final = feat_df.copy()
    feat_final["cluster"] = km.labels_

    # Menghitung Jarak Centroid
    feat_final["dist"] = 0.0
    for cid in range(k):
        mask  = feat_final["cluster"] == cid
        dists = np.linalg.norm(X_scaled[mask] - km.cluster_centers_[cid], axis=1)
        feat_final.loc[mask, "dist"] = dists

    feat_final["is_centroid"] = False
    for cid in range(k):
        nearest = feat_final[feat_final["cluster"] == cid]["dist"].idxmin()
        feat_final.loc[nearest, "is_centroid"] = True

    # Pelabelan Dinamis Klaster
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

    # ── TAHAP 2: ORKESTRASI LOGGING MLFLOW (SATU PINTU) ──
    init_mlflow()
    mlflow.set_experiment(mlflow_experiment)
    client = MlflowClient()
    REGISTRY_NAME = "Metadata__Clustering"

    log.info(f"\n{"=" * 60}")
    log.info(f"Mulai Orkestrasi Satu Atap ke Experiment: {mlflow_experiment}")
    log.info(f"{"=" * 60}")

    # Nama Run disesuaikan menjadi KMeans-Final-Orchestration agar terbaca config.py
    with mlflow.start_run(run_name="KMeans-Final-Orchestration") as run:
        mlflow.log_param("k", k)
        mlflow.set_tags({
            "step": "preprocessing_clustering",
            "project": "PBL-MarketCast",
            "type": "production_registry"
        })

        # Log Ukuran Tiap Cluster
        for cid in sorted(feat_final["cluster"].unique()):
            n = (feat_final["cluster"] == cid).sum()
            mlflow.log_metric(f"cluster_{cid}_size", int(n))

        # Log Metrics Komoditas secara Batching (Optimasi performa pengiriman data)
        metrics_batch = {}
        for komoditas, row in feat_final.iterrows():
            prefix = (komoditas.lower().replace(" ", "_").replace("/", "_").replace("(", "").replace(")", ""))[:30]
            metrics_batch.update({
                f"{prefix}__cv"         : round(float(row["cv"]), 6),
                f"{prefix}__mean_harga" : round(float(row["mean_harga"]), 2),
                f"{prefix}__trend_slope": round(float(row["trend_slope"]), 6),
                f"{prefix}__cluster"    : int(row["cluster"]),
                f"{prefix}__is_centroid": int(row["is_centroid"]),
            })
        mlflow.log_metrics(metrics_batch)

        # Pembuatan File & Upload Artifacts via Temporary Directory (EPHEMERAL CLEANUP)
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            
            # Dump berkas model jangkar scaler ke memori sementara
            joblib.dump(scaler, tmp_path / "minmax_scaler.joblib")
            
            # 1. data_preprocessed.csv
            df_export = df_clean[["tanggal", "komoditas", "harga_per_kg"]].copy()
            df_export.to_csv(tmp_path / "data_preprocessed.csv", index=False)
            
            # 2. cluster_assignments.csv
            assignments = feat_final[["cluster", "cluster_label"]].copy()
            assignments.index.name = "komoditas"
            assignments.to_csv(tmp_path / "cluster_assignments.csv")
            
            # 3. centroid_representatives.csv
            centroids = feat_final[feat_final["is_centroid"]].index.tolist()
            pd.DataFrame({"komoditas": centroids}).to_csv(tmp_path / "centroid_representatives.csv", index=False)
            
            # 4. cluster_features.csv
            feat_export = feat_final[["cv", "mean_harga", "trend_slope", "cluster", "cluster_label", "dist", "is_centroid"]].copy()
            feat_export.index.name = "komoditas"
            feat_export.to_csv(tmp_path / "cluster_features.csv")
            
            # 5. Centroid Timeseries
            for komo in centroids:
                slug = komo.lower().replace(" ", "_")
                sub_df = df_clean[df_clean["komoditas"] == komo][["tanggal", "harga_per_kg"]].copy()
                sub_df.columns = ["ds", "y"]
                sub_df.to_csv(tmp_path / f"ts_centroid_{slug}.csv", index=False)

            # Kirim seluruh berkas sekaligus ke dalam folder penampung khusus di awan
            mlflow.log_artifacts(tmp_path.as_posix(), artifact_path="clustering_results")
            log.info("   ✅ Seluruh file CSV paket klaster berhasil diterbangkan ke DagsHub.")

        # ── TAHAP 3: REGISTRASI MODEL SCALE INLINE TERINTEGRASI ──
        log.info(f"   Mendaftarkan objek '{REGISTRY_NAME}' ke gerbang Model Registry...")
        
        # Mendaftarkan objek model secara langsung menggunakan parameter inline
        # Ini taktik jitu memotong bug 'Unable to find a logged_model' akibat delay S3 DagsHub
        mlflow.sklearn.log_model(
            sk_model=scaler, 
            artifact_path="scaler_model"
        )

        log.info(f"   Mendaftarkan '{REGISTRY_NAME}' ke gerbang Model Registry...")
        # 2. Daftarkan secara eksplisit menggunakan URI Run aktif
        model_uri = f"runs:/{run.info.run_id}/scaler_model"
        mv = mlflow.register_model(model_uri=model_uri, name=REGISTRY_NAME)
        log.info(f"   ✓ Model sukses terdaftar sebagai Version {mv.version}")

        # Kunci versi terbaru tersebut ke status PRODUCTION untuk kebutuhan API
        client.set_registered_model_alias(
            name=REGISTRY_NAME,
            alias="production",
            version=mv.version
        )
        log.info(f"🎉 SUKSES! {REGISTRY_NAME} v{mv.version} resmi mengudara dengan status @production!")
        log.info(f"{"=" * 60}\n")
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
    run_and_log_clustering_pipeline(df_clean, feat_df, args.k)
    
    engine.dispose()

    log.info("=" * 60)
    log.info("Clustering selesai. Data hasil Clustering aman di MLflow DagsHub dan siap untuk train_all.py")
    log.info("=" * 60)

if __name__ == "__main__":
    main()