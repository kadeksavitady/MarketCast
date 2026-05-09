import argparse
import logging
import shutil
import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats
from sklearn.cluster import KMeans
from sklearn.preprocessing import MinMaxScaler
import joblib

warnings.filterwarnings("ignore")
logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
log = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# Label cluster — satu tempat, dipakai export & MLflow
# ─────────────────────────────────────────────────────────────────────────────
CLUSTER_LABEL_MAP = {
    0: "Cluster 0: Labil & Murah (\u2192Datar)",
    1: "Cluster 1: Labil & Murah (\u2191Inflasi)",
    2: "Cluster 2: Stabil & Mahal (\u2192Datar)",
}

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
        engine = create_engine(
            f"postgresql://{args.pg_user}:{args.pg_password}"
            f"@{args.pg_host}:{args.pg_port}/{args.pg_db}"
        )
        df = pd.read_sql("SELECT * FROM harga_historis", engine)

    log.info(f"Loaded {len(df):,} rows. Siap untuk clustering.")
    return df

# ─────────────────────────────────────────────────────────────────────────────
# 2. PREPROCESSING
# ─────────────────────────────────────────────────────────────────────────────

def preprocess_for_clustering(df: pd.DataFrame) -> pd.DataFrame:
    """Hanya menangani outlier karena satuan sudah kg dari hulu."""
    log.info("─── PREPROCESSING CLUSTERING ───")
    df = df.copy()
    df["tanggal_data"] = pd.to_datetime(df["tanggal_data"])

    for komoditas, group in df.groupby("komoditas"):
        q1, q3 = group["harga_per_kg"].quantile([0.25, 0.75])
        iqr = q3 - q1
        lower, upper = q1 - 1.5 * iqr, q3 + 1.5 * iqr
        mask = df["komoditas"] == komoditas
        df.loc[mask & (df["harga_per_kg"] < lower), "harga_per_kg"] = lower
        df.loc[mask & (df["harga_per_kg"] > upper), "harga_per_kg"] = upper

    return df

# ─────────────────────────────────────────────────────────────────────────────
# 3. FEATURE ENGINEERING & CLUSTERING
# ─────────────────────────────────────────────────────────────────────────────

def build_features(df: pd.DataFrame) -> pd.DataFrame:
    features = []
    for komoditas, group in df.groupby("komoditas"):
        prices = group.sort_values("tanggal_data")["harga_per_kg"].values
        days   = (group["tanggal_data"] - group["tanggal_data"].min()).dt.days.values

        mean_p = np.mean(prices)
        cv     = np.std(prices) / mean_p if mean_p > 0 else 0
        slope  = (stats.linregress(days, prices).slope * 365 / mean_p
                  if len(days) > 1 else 0)

        features.append({
            "komoditas"  : komoditas,
            "mean_harga" : mean_p,
            "cv"         : cv,
            "trend_slope": slope,
        })
    return pd.DataFrame(features).set_index("komoditas")


def run_clustering_pipeline(feat_df: pd.DataFrame, k: int, output_dir: Path):
    cols     = ["cv", "mean_harga", "trend_slope"]
    scaler   = MinMaxScaler()
    X_scaled = scaler.fit_transform(feat_df[cols])

    km = KMeans(n_clusters=k, random_state=42, n_init=20).fit(X_scaled)
    feat_df = feat_df.copy()
    feat_df["cluster"] = km.labels_

    feat_df["dist"] = 0.0
    for cid in range(k):
        mask  = feat_df["cluster"] == cid
        dists = np.linalg.norm(X_scaled[mask] - km.cluster_centers_[cid], axis=1)
        feat_df.loc[mask, "dist"] = dists

    feat_df["is_centroid"] = False
    for cid in range(k):
        nearest = feat_df[feat_df["cluster"] == cid]["dist"].idxmin()
        feat_df.loc[nearest, "is_centroid"] = True

    scaler_path = output_dir / "minmax_scaler.joblib"
    joblib.dump(scaler, scaler_path)

    return feat_df, X_scaled, scaler_path

# ─────────────────────────────────────────────────────────────────────────────
# 4. EXPORT
# ─────────────────────────────────────────────────────────────────────────────

def export_pipeline_inputs(df_clean: pd.DataFrame, feat_final: pd.DataFrame,
                            output_dir: Path) -> None:
    """
    Export semua file yang dibutuhkan pipeline selanjutnya:
        1. data_preprocessed.csv       → outputs/clustering/ + data/processed/
        2. cluster_assignments.csv     → outputs/clustering/
        3. centroid_representatives.csv→ outputs/clustering/
        4. cluster_features.csv        → outputs/clustering/ + data/processed/
           (CV, mean_harga, trend_slope, cluster per komoditas)
           ↑ dipakai substitution engine untuk cari komoditas serupa
    """
    processed_dir = Path("data/processed")
    processed_dir.mkdir(parents=True, exist_ok=True)

    # ── 1. data_preprocessed.csv ─────────────────────────────────────────────
    df_export = (df_clean
                 .rename(columns={"tanggal_data": "tanggal"})
                 [["tanggal", "komoditas", "harga_per_kg"]])
    df_export.to_csv(output_dir / "data_preprocessed.csv", index=False)
    df_export.to_csv(processed_dir / "data_preprocessed.csv", index=False)
    log.info(f"✅ data_preprocessed.csv  — {len(df_export):,} baris, "
             f"{df_export['komoditas'].nunique()} komoditas")
    log.info(f"   → outputs/clustering/ + data/processed/")

    # ── 2. cluster_assignments.csv ───────────────────────────────────────────
    assignments = feat_final[["cluster"]].copy()
    assignments["cluster_label"] = assignments["cluster"].map(CLUSTER_LABEL_MAP)
    assignments.index.name = "komoditas"
    assignments[["cluster_label"]].to_csv(output_dir / "cluster_assignments.csv")
    log.info(f"✅ cluster_assignments.csv — {len(assignments)} komoditas")
    for cid, label in CLUSTER_LABEL_MAP.items():
        n = (assignments["cluster_label"] == label).sum()
        log.info(f"   Cluster {cid}: {n} komoditas — {label}")

    # ── 3. centroid_representatives.csv ─────────────────────────────────────
    centroids = feat_final[feat_final["is_centroid"]].index.tolist()
    pd.DataFrame({"komoditas": centroids}).to_csv(
        output_dir / "centroid_representatives.csv", index=False
    )
    log.info(f"✅ centroid_representatives.csv — {centroids}")

    # ── 4. cluster_features.csv ──────────────────────────────────────────────
    feat_export = feat_final[["cv", "mean_harga", "trend_slope",
                               "cluster", "dist", "is_centroid"]].copy()
    feat_export["cluster_label"] = feat_export["cluster"].map(CLUSTER_LABEL_MAP)
    feat_export.index.name = "komoditas"
    feat_export.to_csv(output_dir / "cluster_features.csv")
    shutil.copy(output_dir / "cluster_features.csv",
                processed_dir / "cluster_features.csv")
    log.info(f"✅ cluster_features.csv — CV, mean_harga, trend_slope per komoditas")
    log.info(f"   → outputs/clustering/ + data/processed/")


def export_centroid_timeseries(df_clean: pd.DataFrame, feat_final: pd.DataFrame,
                                output_dir: Path) -> None:
    for komo in feat_final[feat_final["is_centroid"]].index:
        slug   = komo.lower().replace(" ", "_")
        sub_df = (df_clean[df_clean["komoditas"] == komo]
                  [["tanggal_data", "harga_per_kg"]]
                  .copy())
        sub_df.columns = ["ds", "y"]
        sub_df.to_csv(output_dir / f"ts_centroid_{slug}.csv", index=False)
    log.info("✅ ts_centroid_*.csv disimpan untuk semua centroid")

# ─────────────────────────────────────────────────────────────────────────────
# 5. MLflow LOGGING
# ─────────────────────────────────────────────────────────────────────────────

def log_to_mlflow(feat_df: pd.DataFrame, output_dir: Path,
                  scaler_path: Path, uri: str) -> None:
    """
    Log ke MLflow:
        Params    : k
        Metrics   : ukuran tiap cluster
        Metrics   : CV, mean_harga, trend_slope, cluster, is_centroid
                    per komoditas → dipakai substitution engine
        Artifacts : semua file di output_dir (CSV + scaler)
    """
    # Cek koneksi dulu — hindari retry 4 menit kalau MLflow mati
    try:
        import requests
        requests.get(f"{uri}/health", timeout=3)
    except Exception:
        log.warning(f"⚠️ MLflow tidak dapat dijangkau di {uri} — skip logging")
        return

    try:
        import mlflow
        mlflow.set_tracking_uri(uri)
        mlflow.set_experiment("siskaperbapo-clustering")

        with mlflow.start_run(run_name="KMeans-Final"):

            # ── Params ───────────────────────────────────────────────────────
            mlflow.log_param("k", feat_df["cluster"].nunique())

            # ── Metrics: ukuran cluster ───────────────────────────────────────
            for cid in sorted(feat_df["cluster"].unique()):
                n = (feat_df["cluster"] == cid).sum()
                mlflow.log_metric(f"cluster_{cid}_size", int(n))

            # ── Metrics: fitur per komoditas ──────────────────────────────────
            # Format key: {nama_komoditas}__{fitur}
            # Substitution engine bisa query: "cari CV mirip cabai merah besar"
            for komoditas, row in feat_df.iterrows():
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

            log.info("✅ MLflow params & metrics ter-log")

            # ── Artifacts: semua file output ──────────────────────────────────
            mlflow.log_artifacts(output_dir.as_posix(),
                                 artifact_path="clustering_results")
            log.info(f"✅ Artifacts di-upload: {output_dir.as_posix()}")

    except Exception as e:
        log.error(f"❌ MLflow Error: {e}")

# ─────────────────────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Clustering pipeline PBL-MarketCast"
    )
    parser.add_argument("--source", choices=["csv", "postgres"], default="csv")
    parser.add_argument("--csv-path", default="data/processed/harga_historis.csv")
    parser.add_argument("--output-dir", default="outputs/clustering")
    parser.add_argument("--k", type=int, default=3)
    parser.add_argument("--mlflow-uri", default="http://localhost:5000")
    args = parser.parse_args()

    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    # ── Pipeline ──────────────────────────────────────────────────────────────
    df_raw   = load_data(args)
    df_clean = preprocess_for_clustering(df_raw)
    feat_df  = build_features(df_clean)

    feat_final, X_scaled, scaler_path = run_clustering_pipeline(
        feat_df, args.k, out_dir
    )

    # ── Export ────────────────────────────────────────────────────────────────
    export_pipeline_inputs(df_clean, feat_final, out_dir)
    export_centroid_timeseries(df_clean, feat_final, out_dir)

    # ── MLflow ────────────────────────────────────────────────────────────────
    log_to_mlflow(feat_final, out_dir, scaler_path, args.mlflow_uri)

    log.info("=" * 60)
    log.info("Clustering selesai. outputs/clustering/ siap untuk train_all.py")
    log.info("=" * 60)


if __name__ == "__main__":
    main()