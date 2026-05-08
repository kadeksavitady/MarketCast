import argparse
import logging
import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from scipy import stats
from sklearn.cluster import KMeans
from sklearn.metrics import silhouette_score
from sklearn.preprocessing import MinMaxScaler
import joblib  # Untuk simpan scaler

warnings.filterwarnings("ignore")
logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
log = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# 1. DATA LOADING
# ─────────────────────────────────────────────────────────────────────────────

def load_data(args):
    """Load data dari CSV hasil cleaning hulu atau PostgreSQL."""
    if args.source == "csv":
        path = Path(args.csv_path)
        if not path.exists():
            log.error(f"File hasil cleaning tidak ditemukan di {path}")
            sys.exit(1)
        df = pd.read_csv(path)
    else:
        from sqlalchemy import create_engine
        engine = create_engine(f"postgresql://{args.pg_user}:{args.pg_password}@{args.pg_host}:{args.pg_port}/{args.pg_db}")
        df = pd.read_sql("SELECT * FROM harga_historis", engine)
    
    log.info(f"Loaded {len(df):,} rows. Siap untuk clustering.")
    return df

# ─────────────────────────────────────────────────────────────────────────────
# 2. SIMPLIFIED PREPROCESSING
# ─────────────────────────────────────────────────────────────────────────────

def preprocess_for_clustering(df: pd.DataFrame) -> pd.DataFrame:
    """Hanya menangani outlier karena satuan sudah kg dari hulu."""
    log.info("─── PREPROCESSING CLUSTERING ───")
    df = df.copy()
    df["tanggal_data"] = pd.to_datetime(df["tanggal_data"])
    
    # Winsorizing Outliers (Clamp ke IQR 1.5)
    for komoditas, group in df.groupby("komoditas"):
        q1, q3 = group["harga_per_kg"].quantile([0.25, 0.75])
        iqr = q3 - q1
        lower, upper = q1 - 1.5 * iqr, q3 + 1.5 * iqr
        df.loc[(df["komoditas"] == komoditas) & (df["harga_per_kg"] < lower), "harga_per_kg"] = lower
        df.loc[(df["komoditas"] == komoditas) & (df["harga_per_kg"] > upper), "harga_per_kg"] = upper
    
    return df

# ─────────────────────────────────────────────────────────────────────────────
# 3. FEATURE ENGINEERING & CLUSTERING
# ─────────────────────────────────────────────────────────────────────────────

def build_features(df):
    features = []
    for komoditas, group in df.groupby("komoditas"):
        prices = group.sort_values("tanggal_data")["harga_per_kg"].values
        days = (group["tanggal_data"] - group["tanggal_data"].min()).dt.days.values
        
        mean_p = np.mean(prices)
        cv = np.std(prices) / mean_p if mean_p > 0 else 0
        slope = stats.linregress(days, prices).slope * 365 / mean_p if len(days) > 1 else 0
        
        features.append({
            "komoditas": komoditas,
            "mean_harga": mean_p,
            "cv": cv,
            "trend_slope": slope
        })
    return pd.DataFrame(features).set_index("komoditas")

def run_clustering_pipeline(feat_df, k, output_dir):
    cols = ["cv", "mean_harga", "trend_slope"]
    scaler = MinMaxScaler()
    X_scaled = scaler.fit_transform(feat_df[cols])
    
    km = KMeans(n_clusters=k, random_state=42, n_init=20).fit(X_scaled)
    feat_df["cluster"] = km.labels_
    
    # Hitung Centroid Terdekat
    for cid in range(k):
        mask = feat_df["cluster"] == cid
        dists = np.linalg.norm(X_scaled[mask] - km.cluster_centers_[cid], axis=1)
        feat_df.loc[mask, "dist"] = dists
    
    feat_df["is_centroid"] = False
    for cid in range(k):
        nearest = feat_df[feat_df["cluster"] == cid]["dist"].idxmin()
        feat_df.loc[nearest, "is_centroid"] = True

    # Simpan Scaler (Penting untuk MLflow Artifact)
    scaler_path = output_dir / "minmax_scaler.joblib"
    joblib.dump(scaler, scaler_path)
    
    return feat_df, X_scaled, scaler_path

# ─────────────────────────────────────────────────────────────────────────────
# 4. EXPORT & MLFLOW
# ─────────────────────────────────────────────────────────────────────────────

def log_to_mlflow(feat_df, output_dir, scaler_path, uri):
    try:
        import mlflow
        mlflow.set_tracking_uri(uri)
        mlflow.set_experiment("siskaperbapo-clustering")
        
        with mlflow.start_run(run_name="KMeans-Final"):
            # Log Params
            mlflow.log_param("k", feat_df["cluster"].nunique())
            
            # CEK: Pastikan folder output ada isinya sebelum upload
            if any(output_dir.iterdir()):
                # Gunakan .as_posix() agar Windows path (backslashes) 
                # dikonversi ke format yang dipahami MLflow/Docker
                mlflow.log_artifacts(output_dir.as_posix(), artifact_path="clustering_results")
                log.info(f"✅ Berhasil upload artifacts dari: {output_dir.as_posix()}")
            else:
                log.warning("⚠️ Folder output kosong! Tidak ada yang di-upload.")
                
    except Exception as e:
        log.error(f"❌ MLflow Error: {e}")

# ─────────────────────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", choices=["csv", "postgres"], default="csv")
    parser.add_argument("--csv-path", default="data/processed/harga_historis.csv")
    parser.add_argument("--output-dir", default="outputs/clustering")
    parser.add_argument("--k", type=int, default=3)
    args = parser.parse_args()
    
    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    
    # Pipeline Execution
    df_raw = load_data(args)
    df_clean = preprocess_for_clustering(df_raw)
    feat_df = build_features(df_clean)
    
    feat_final, X_scaled, scaler_path = run_clustering_pipeline(feat_df, args.k, out_dir)
    
    # Export Centroids for Modeling (Langkah 5)
    for komo in feat_final[feat_final["is_centroid"]].index:
        slug = komo.lower().replace(" ", "_")
        sub_df = df_clean[df_clean["komoditas"] == komo][["tanggal_data", "harga_per_kg"]]
        sub_df.columns = ["ds", "y"]
        sub_df.to_csv(out_dir / f"ts_centroid_{slug}.csv", index=False)

    log_to_mlflow(feat_final, out_dir, scaler_path, "http://localhost:5000")
    log.info("Misi Clustering Selesai! Data siap untuk Modeling.")

if __name__ == "__main__":
    main()