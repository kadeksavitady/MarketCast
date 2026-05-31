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
        
        # Logika Tren: Jika tren di atas 5% pertahun (0.05) -> Inflasi
        if med_slope > 0.05:
            tren_lbl = "↑Inflasi"
        elif med_slope < -0.05:
            tren_lbl = "↓Deflasi"
        else:
            tren_lbl = "→Datar"
            
        label = f"Cluster {cid}: {cv_lbl} & {harga_lbl} ({tren_lbl})"
        feat_df.loc[mask, "cluster_label"] = label
        log.info(f"  [Auto-Label] {label} (Median Harga: Rp{med_harga:,.0f})")
        
    return feat_df, X_scaled, scaler

# ─────────────────────────────────────────────────────────────────────────────
# 4. EXPORT
# ─────────────────────────────────────────────────────────────────────────────

def export_pipeline_inputs(df_clean: pd.DataFrame, feat_final: pd.DataFrame,
                            scaler, uri: str) -> None:
    """
    Export semua file yang dibutuhkan pipeline selanjutnya:
        2. cluster_assignments.csv     → outputs/clustering/
        3. centroid_representatives.csv→ outputs/clustering/
           (CV, mean_harga, trend_slope, cluster per komoditas)
           ↑ dipakai substitution engine untuk cari komoditas serupa
    """

    # ── 1. data_preprocessed.csv ─────────────────────────────────────────────
    df_export = (df_clean
                 .rename(columns={"tanggal": "tanggal"})
                 [["tanggal", "komoditas", "harga_per_kg"]])
    df_export.to_csv(output_dir / "data_preprocessed.csv", index=False)
    log.info(f"✅ data_preprocessed.csv  — {len(df_export):,} baris, "
             f"{df_export['komoditas'].nunique()} komoditas")

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
    log.info(f"✅ cluster_features.csv — CV, mean_harga, trend_slope per komoditas")


def export_centroid_timeseries(df_clean: pd.DataFrame, feat_final: pd.DataFrame,
                                output_dir: Path) -> None:
    for komo in feat_final[feat_final["is_centroid"]].index:
        slug   = komo.lower().replace(" ", "_")
        sub_df = (df_clean[df_clean["komoditas"] == komo]
                  [["tanggal", "harga_per_kg"]]
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
        requests.get(uri.rstrip("/") + "/api/2.0/mlflow/experiments/list", timeout=5)
    except Exception:
        log.warning(f"⚠️ MLflow tidak dapat dijangkau di {uri} — skip logging")
        return

    try:
        import mlflow, dagshub
        dagshub.init('MarketCast', 'kadeksavitady', mlflow=True)
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
    parser.add_argument("--csv-path", default="data/processed/harga_historis_clean.csv")
    parser.add_argument("--output-dir", default="outputs/clustering")
    parser.add_argument("--k", type=int, default=3)
    parser.add_argument("--mlflow-uri", default="https://dagshub.com/kadeksavitady/MarketCast.mlflow")
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