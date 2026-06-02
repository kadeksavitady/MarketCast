import os
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

import mlflow
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
# 2.5 HELPER FUNCTION: REGISTRY METADATA (TARUH DI SINI)
# ─────────────────────────────────────────────────────────────────────────────
def register_clustering_metadata_to_mlflow(feat_df: pd.DataFrame, X_scaled, scaler, mlflow_experiment: str = "MarketCast-Preprocessing"):
    """
    Menyimpan hasil clustering ke CSV, melakukan logging artifact,
    dan mendaftarkannya sebagai 'Model' resmi di MLflow Registry sesuai permintaan Backend.
    """
    # 1. Inisialisasi MLflow Client dan Experiment
    mlflow.set_experiment(mlflow_experiment)
    client = MlflowClient()
    
    # Tentukan nama registrasi sesuai request Backend
    REGISTRY_NAME = "Metadata__Clustering"
    
    log.info(f"\n=======================================================")
    log.info(f"Mulai Proses Registrasi Metadata Clustering ke MLflow...")
    log.info(f"=======================================================")

    with mlflow.start_run(run_name="Clustering_Metadata_Export") as run:
        # Atur Tags untuk mempermudah pencarian di UI
        mlflow.set_tags({
            "step": "preprocessing_clustering",
            "project": "PBL-MarketCast",
            "type": "metadata"
        })

        # ── TAHAP 1: SAVE & LOG ARTIFACT (CSV) ──
        # Buat folder temporary jika belum ada
        os.makedirs("/tmp/clustering", exist_ok=True)
        csv_path = "/tmp/clustering/cluster_assignments.csv"
        # Simpan hasil dataframe clustering ke CSV lokal sementara
        feat_df.to_csv(csv_path, index=True)
        log.info(f"  ✓ Berhasil menyimpan CSV sementara di: {csv_path}")
        
        # WAJIB: Log file CSV tersebut menggunakan mlflow.log_artifact sesuai request
        mlflow.log_artifact(csv_path, artifact_path="clustering_outputs")
        log.info(f"  ✅ CSV berhasil di-log sebagai artifact di MLflow.")

        # ── TAHAP 2: REGISTER SEBAGAI MODEL IMAJINER ──
        # Karena MLflow Registry mewajibkan adanya objek 'Model', kita daftarkan 
        # objek 'scaler' (MinMaxScaler) sebagai perwakilan model imajiner kita.
        # Ini trik standar MLOps jika ingin meregistrasi metadata murni.
        log.info(f"  Mendaftarkan ke Model Registry dengan nama '{REGISTRY_NAME}'...")
        
        # Log model scaler-nya terlebih dahulu
        mlflow.sklearn.log_model(scaler, artifact_path="scaler_model")
        model_uri = f"runs:/{run.info.run_id}/scaler_model"
        # Daftarkan ke Model Registry
        mv = mlflow.register_model(model_uri=model_uri, name=REGISTRY_NAME)
        log.info(f"  ✓ Model berhasil terdaftar sebagai Version {mv.version}")

        # ── TAHAP 3: SET STATUS KE PRODUCTION ──
        # Set versi terbaru ini langsung menggunakan alias atau stage 'Production'
        log.info(f"  Mengeset versi {mv.version} ke label / alias 'production'...")
        # Menggunakan set_registered_model_alias (Direkomendasikan untuk MLflow modern)
        client.set_registered_model_alias(
            name=REGISTRY_NAME,
            alias="production",
            version=mv.version
        )
        
        log.info(f"✅ {REGISTRY_NAME} v{mv.version} sukses berstatus PRODUCTION dengan artifact CSV!")
        log.info(f"=======================================================\n")
        
    return run.info.run_id

# ─────────────────────────────────────────────────────────────────────────────
# 3. CLUSTERING
# ─────────────────────────────────────────────────────────────────────────────
def run_clustering_pipeline(feat_df: pd.DataFrame, k: int):
    cols     = ["cv", "mean_harga", "trend_slope"]
    scaler   = MinMaxScaler()
    X_scaled = scaler.fit_transform(feat_df[cols])

    km = KMeans(n_clusters=k, random_state=42, n_init=20).fit(X_scaled)
    feat_df = feat_df.copy()
    feat_df["cluster"] = km.labels_

    # Cari Centroid
    feat_df["dist"] = 0.0
    for cid in range(k):
        mask  = feat_df["cluster"] == cid
        dists = np.linalg.norm(X_scaled[mask] - km.cluster_centers_[cid], axis=1)
        feat_df.loc[mask, "dist"] = dists

    feat_df["is_centroid"] = False
    for cid in range(k):
        nearest = feat_df[feat_df["cluster"] == cid]["dist"].idxmin()
        feat_df.loc[nearest, "is_centroid"] = True

    # DYNAMIC LABELING (Berdasarkan kondisi nyata data di memori)
    feat_df["cluster_label"] = ""
    overall_harga = feat_df["mean_harga"].median()
    overall_cv    = feat_df["cv"].median()
    
    for cid in range(k):
        mask = feat_df["cluster"] == cid
        med_harga = feat_df.loc[mask, "mean_harga"].median()
        med_cv    = feat_df.loc[mask, "cv"].median()
        med_slope = feat_df.loc[mask, "trend_slope"].median()
        
        # Logika Bisnis: Bandingkan median cluster dengan median total 43 komoditas
        harga_lbl = "Mahal" if med_harga > overall_harga else "Murah"
        cv_lbl    = "Labil" if med_cv > overall_cv else "Stabil"
        
        # Logika Tren: Jika tren di atas 1% pertahun (0.01) -> Inflasi
        if med_slope > 0.01:
            tren_lbl = "↑Inflasi"
        elif med_slope < -0.01:
            tren_lbl = "↓Deflasi"
        else:
            tren_lbl = "→Datar"
            
        label = f"Cluster {cid}: {cv_lbl} & {harga_lbl} ({tren_lbl})"
        feat_df.loc[mask, "cluster_label"] = label
        log.info(f"  [Auto-Label] {label} (Median Harga: Rp{med_harga:,.0f})")
    # ── PEMANGGILAN OTOMASI REGISTRY (SISIPKAN DI SINI SEBELUM RETURN) ──
    try:
        register_clustering_metadata_to_mlflow(feat_df, X_scaled, scaler)
    except Exception as e:
        log.error(f"⚠️ Gagal mengotomasi registry clustering: {e}")
           
    return feat_df, X_scaled, scaler

# ─────────────────────────────────────────────────────────────────────────────
# 4. EXPORT EXPORT & MLFLOW LOGGING (TEMPFILE)
# ─────────────────────────────────────────────────────────────────────────────
def export_and_log_to_mlflow(df_clean: pd.DataFrame, feat_final: pd.DataFrame,
                             scaler, uri: str, k: int) -> None:
    """
    Export semua file yang dibutuhkan pipeline selanjutnya:
        2. cluster_assignments.csv     → artifacts mlflow
        3. centroid_representatives.csv→ artifacts mlflow
           (CV, mean_harga, trend_slope, cluster per komoditas)
           ↑ dipakai substitution engine untuk cari komoditas serupa
    """
    try:
        import requests
        requests.get(uri.rstrip("/") + "/api/2.0/mlflow/experiments/list", timeout=5)
    except Exception:
        log.warning(f"⚠️ MLflow tidak dapat dijangkau di {uri} — skip logging")
        return

    try:
        import mlflow, dagshub
        dagshub.init('MarketCast', 'kadeksavitady', mlflow=True)
        mlflow.set_tracking_uri(uri)
        mlflow.set_experiment("siskaperbapo-clustering")

        with mlflow.start_run(run_name="KMeans-Final"):
            mlflow.log_param("k", k)

            for cid in sorted(feat_final["cluster"].unique()):
                n = (feat_final["cluster"] == cid).sum()
                mlflow.log_metric(f"cluster_{cid}_size", int(n))

            for komoditas, row in feat_final.iterrows():
                prefix = (komoditas.lower()
                                   .replace(" ", "_")
                                   .replace("/", "_")
                                   .replace("(", "")
                                   .replace(")", ""))[:30]
                mlflow.log_metrics({
                    f"{prefix}__cv"         : round(float(row["cv"]), 6),
                    f"{prefix}__mean_harga" : round(float(row["mean_harga"]), 2),
                    f"{prefix}__trend_slope": round(float(row["trend_slope"]), 6),
                    f"{prefix}__cluster"    : int(row["cluster"]),
                    f"{prefix}__is_centroid": int(row["is_centroid"]),
                })
            
            with tempfile.TemporaryDirectory() as tmpdir:
                tmp_path = Path(tmpdir)
                
                joblib.dump(scaler, tmp_path / "minmax_scaler.joblib")
                
                # ── 1. data_preprocessed.csv ─────────────────────────────────────────────
                df_export = df_clean[["tanggal", "komoditas", "harga_per_kg"]].copy()
                df_export.to_csv(tmp_path / "data_preprocessed.csv", index=False)
                
                # ── 2. cluster_assignments.csv ───────────────────────────────────────────
                # Export Label sekarang langsung tarik dari kolom data yang udah dinamis!
                assignments = feat_final[["cluster", "cluster_label"]].copy()
                assignments.index.name = "komoditas"
                assignments.to_csv(tmp_path / "cluster_assignments.csv")
                
                # ── 3. centroid_representatives.csv ─────────────────────────────────────
                centroids = feat_final[feat_final["is_centroid"]].index.tolist()
                pd.DataFrame({"komoditas": centroids}).to_csv(
                    tmp_path / "centroid_representatives.csv", index=False
                )
                
                # ── 4. cluster_features.csv ──────────────────────────────────────────────
                feat_export = feat_final[["cv", "mean_harga", "trend_slope",
                                           "cluster", "cluster_label", "dist", "is_centroid"]].copy()
                feat_export.index.name = "komoditas"
                feat_export.to_csv(tmp_path / "cluster_features.csv")
                
                # export centroid timeseries
                for komo in centroids:
                    slug   = komo.lower().replace(" ", "_")
                    sub_df = (df_clean[df_clean["komoditas"] == komo]
                              [["tanggal", "harga_per_kg"]].copy())
                    sub_df.columns = ["ds", "y"]
                    sub_df.to_csv(tmp_path / f"ts_centroid_{slug}.csv", index=False)

                mlflow.log_artifacts(tmp_path.as_posix(), artifact_path="clustering_results")
                log.info("✅ Semua file CSV & Scaler berhasil di-upload ke MLflow, laptop tetap bersih!")

    except Exception as e:
        log.error(f"❌ MLflow Error: {e}")
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
    feat_final, X_scaled, scaler = run_clustering_pipeline(feat_df, args.k)

    # ── Export & MLflow ────────────────────────────────────────────────────────────────
    export_and_log_to_mlflow(df_clean, feat_final, scaler, args.mlflow_uri, args.k)
    engine.dispose()

    log.info("=" * 60)
    log.info("Clustering selesai. Data hasil Clustering aman di MLflow DagsHub dan siap untuk train_all.py")
    log.info("=" * 60)

if __name__ == "__main__":
    main()