"""
preprocessing_clustering.py
============================
Siskaperbapo Price Prediction Project
Tim: 3 orang | Matkul: ML-Ops + Data Mining + Teknologi Web Service

Pipeline:
    1. Load data dari PostgreSQL (atau CSV fallback untuk dev)
    2. Normalisasi & standarisasi satuan → semua ke harga/kg equivalent
    3. Preprocessing: outlier handling, feature engineering time series
    4. Clustering K-Means dengan fitur: CV + Mean + Trend Slope
    5. Validasi k optimal dengan Silhouette Score + Elbow Method
    6. Pilih 1 komoditas centroid per cluster (wakil representatif)
    7. Export hasil ke CSV + log ke MLflow

Cara pakai:
    # Dari PostgreSQL (production):
    python preprocessing_clustering.py --source postgres

    # Dari CSV (development / fallback):
    python preprocessing_clustering.py --source csv --csv-path data/processed_marketcast.csv

    # Langsung pakai k tertentu (skip validasi):
    python preprocessing_clustering.py --source csv --csv-path data/processed_marketcast.csv --k 3
"""

import argparse
import logging
import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
import seaborn as sns
from scipy import stats
from sklearn.cluster import KMeans
from sklearn.metrics import silhouette_score
from sklearn.preprocessing import MinMaxScaler

warnings.filterwarnings("ignore")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# KONSTANTA
# ─────────────────────────────────────────────────────────────────────────────

# Faktor konversi satuan → per-kg equivalent
# Logika: harga_normalized = harga_raw / faktor → sebanding dengan harga/kg
SATUAN_KONVERSI = {
    # Sudah per-kg, tidak perlu konversi
    "kg": 1.0,

    # Minyak goreng kemasan: 1 liter ≈ 0.92 kg (densitas minyak goreng)
    # Referensi: densitas minyak goreng ~0.91-0.93 g/ml
    "1 liter": 0.92,

    # Susu kental manis: kemasan 370 gr = 0.370 kg
    "370 gr/kl": 0.370,

    # Susu bubuk: kemasan 400 gr = 0.400 kg
    "400 gr/dos": 0.400,

    # Indomie: 1 bungkus = 85 gr = 0.085 kg (ukuran standar Indomie)
    "bungkus": 0.085,

    # Ayam kampung: 1 ekor ≈ 1.0 kg siap masak (estimasi konservatif)
    # Catatan: ini estimasi — dokumentasikan sebagai limitasi
    "ekor": 1.0,
}

# Komoditas yang basisnya non-kg — perlu flag khusus di laporan
KOMODITAS_NON_KG_FLAG = {
    "Minyak Goreng Kemasan Premium": "1 liter",
    "Minyak Goreng Kemasan Sederhana": "1 liter",
    "Minyak Goreng MINYAKITA": "1 liter",
    "Susu Kental Manis Merk Bendera": "370 gr/kl",
    "Susu Kental Manis Merk Indomilk": "370 gr/kl",
    "Susu Bubuk Merk Bendera (Instant)": "400 gr/dos",
    "Susu Bubuk Merk Indomilk (Instant)": "400 gr/dos",
    "Indomie Rasa Kari Ayam": "bungkus",
    "Daging Ayam Kampung": "ekor",
}

# ─────────────────────────────────────────────────────────────────────────────
# 1. DATA LOADING
# ─────────────────────────────────────────────────────────────────────────────

def load_from_postgres(host, port, db, user, password):
    """Load data langsung dari PostgreSQL."""
    try:
        from sqlalchemy import create_engine
        engine = create_engine(
            f"postgresql://{user}:{password}@{host}:{port}/{db}"
        )
        query = """
            SELECT id, tanggal_scrape, tanggal_data, satuan, harga, komoditas, kategori
            FROM harga_bahan_pokok
            WHERE harga > 0
            ORDER BY tanggal_data, komoditas
        """
        df = pd.read_sql(query, engine)
        log.info(f"Loaded {len(df):,} rows dari PostgreSQL")
        return df
    except Exception as e:
        log.error(f"Gagal connect ke PostgreSQL: {e}")
        sys.exit(1)


def load_from_csv(csv_path):
    """Load data dari CSV (fallback untuk development)."""
    path = Path(csv_path)
    if not path.exists():
        log.error(f"File tidak ditemukan: {csv_path}")
        sys.exit(1)

    df = pd.read_csv(path)
    log.info(f"Loaded {len(df):,} rows dari CSV: {csv_path}")
    return df

def load_from_sqlite(db_path):
    """Load data dari file SQLite (.db)."""
    import sqlite3
    
    path = Path(db_path)
    if not path.exists():
        log.error(f"File Database tidak ditemukan: {db_path}")
        sys.exit(1)

    try:
        conn = sqlite3.connect(db_path)
        
        # HAPUS 'tanggal_scrape' dari baris SELECT di bawah ini
        query = """
            SELECT tanggal_data, satuan, harga_rp AS harga, komoditas,
                'UMUM' AS kategori
            FROM harga_bahan_pokok
            WHERE harga_rp > 0
            ORDER BY tanggal_data, komoditas
        """
        
        df = pd.read_sql_query(query, conn)
        conn.close()
        
        log.info(f"Loaded {len(df):,} rows dari SQLite DB: {db_path}")
        return df
        
    except Exception as e:
        log.error(f"Gagal connect atau baca SQLite: {e}")
        sys.exit(1)

# ─────────────────────────────────────────────────────────────────────────────
# 2. PREPROCESSING
# ─────────────────────────────────────────────────────────────────────────────

def preprocess(df: pd.DataFrame) -> pd.DataFrame:
    """
    Pipeline preprocessing lengkap:
    - Validasi kolom
    - Type casting
    - Filter data invalid
    - Normalisasi satuan → harga per-kg equivalent
    - Outlier handling per komoditas (IQR method)
    - Sort dan index
    """
    log.info("─── MULAI PREPROCESSING ───")

    # ── 2.1 Validasi kolom wajib
    required_cols = {"tanggal_data", "satuan", "harga", "komoditas"}
    missing = required_cols - set(df.columns)
    if missing:
        log.error(f"Kolom hilang: {missing}")
        sys.exit(1)

    # ── 2.2 Type casting
    df = df.copy()
    df["tanggal_data"] = pd.to_datetime(df["tanggal_data"])
    df["harga"] = pd.to_numeric(df["harga"], errors="coerce")

    # Normalisasi string: strip whitespace, lowercase satuan
    df["satuan"] = df["satuan"].astype(str).str.strip().str.lower()
    df["komoditas"] = df["komoditas"].astype(str).str.strip()
    if "kategori" in df.columns:
        df["kategori"] = df["kategori"].astype(str).str.strip().str.upper()

    # ── 2.3 Filter data invalid
    n_before = len(df)
    df = df[df["harga"] > 0].copy()          # hapus harga nol atau negatif
    df = df.dropna(subset=["harga", "tanggal_data", "komoditas"]).copy()
    n_after = len(df)
    log.info(f"  Filter invalid: {n_before - n_after} baris dihapus ({n_before:,} → {n_after:,})")

    # ── 2.4 Normalisasi satuan → harga per-kg equivalent
    log.info("  Normalisasi satuan...")

    # Map satuan ke faktor konversi
    # Perlu re-map karena satuan sudah di-lowercase
    satuan_map_lower = {k.lower(): v for k, v in SATUAN_KONVERSI.items()}

    # Cek satuan yang tidak dikenali
    satuan_unik = df["satuan"].unique()
    tidak_dikenali = set(satuan_unik) - set(satuan_map_lower.keys())
    if tidak_dikenali:
        log.warning(f"  Satuan tidak dikenali (akan di-skip): {tidak_dikenali}")
        df = df[~df["satuan"].isin(tidak_dikenali)].copy()

    df["faktor_konversi"] = df["satuan"].map(satuan_map_lower)
    df["harga_per_kg"] = df["harga"] / df["faktor_konversi"]

    # Flag komoditas non-kg
    df["is_non_kg_original"] = df["komoditas"].isin(KOMODITAS_NON_KG_FLAG.keys())

    log.info(f"  Komoditas dengan satuan non-kg yang dikonversi:")
    for k, s in KOMODITAS_NON_KG_FLAG.items():
        faktor = SATUAN_KONVERSI.get(s, "?")
        komoditas_data = df[df["komoditas"] == k]
        if len(komoditas_data) > 0:
            avg_raw = komoditas_data["harga"].mean()
            avg_norm = komoditas_data["harga_per_kg"].mean()
            log.info(f"    {k}: {s} (÷{faktor}) | avg raw={avg_raw:,.0f} → avg/kg={avg_norm:,.0f}")

    # ── 2.5 Outlier handling per komoditas (IQR method)
    log.info("  Outlier handling per komoditas (IQR × 1.5)...")
    df_clean_list = []
    outlier_summary = {}

    for komoditas, group in df.groupby("komoditas"):
        harga = group["harga_per_kg"]
        q1 = harga.quantile(0.25)
        q3 = harga.quantile(0.75)
        iqr = q3 - q1
        lower = q1 - 1.5 * iqr
        upper = q3 + 1.5 * iqr

        mask_valid = (harga >= lower) & (harga <= upper)
        n_outlier = (~mask_valid).sum()

        if n_outlier > 0:
            outlier_summary[komoditas] = {
                "n_outlier": n_outlier,
                "pct_outlier": n_outlier / len(group) * 100,
                "lower_bound": lower,
                "upper_bound": upper,
            }
            # Clamp outlier ke batas (winsorizing), tidak dihapus
            # Alasan: menghapus data time series bisa buat gap → lebih baik clamp
            group = group.copy()
            group.loc[harga < lower, "harga_per_kg"] = lower
            group.loc[harga > upper, "harga_per_kg"] = upper

        df_clean_list.append(group)

    df = pd.concat(df_clean_list).reset_index(drop=True)

    if outlier_summary:
        log.info(f"  Komoditas dengan outlier yang di-clamp (winsorize):")
        for k, info in sorted(outlier_summary.items(), key=lambda x: -x[1]["pct_outlier"]):
            log.info(f"    {k}: {info['n_outlier']} outlier ({info['pct_outlier']:.1f}%)")

    # ── 2.6 Sort
    df = df.sort_values(["komoditas", "tanggal_data"]).reset_index(drop=True)

    log.info(f"  Preprocessing selesai: {len(df):,} rows, {df['komoditas'].nunique()} komoditas")
    log.info(f"  Rentang tanggal: {df['tanggal_data'].min().date()} → {df['tanggal_data'].max().date()}")
    log.info("─── PREPROCESSING SELESAI ───\n")

    return df


# ─────────────────────────────────────────────────────────────────────────────
# 3. FEATURE ENGINEERING UNTUK CLUSTERING
# ─────────────────────────────────────────────────────────────────────────────

def build_clustering_features(df: pd.DataFrame) -> pd.DataFrame:
    """
    Hitung 3 fitur per komoditas untuk clustering:
    - CV (Coefficient of Variation) = std / mean → volatilitas relatif
    - Mean harga/kg                              → level harga
    - Trend Slope                                → arah pergerakan 5 tahun

    Return: DataFrame dengan index=komoditas, kolom=3 fitur
    """
    log.info("─── FEATURE ENGINEERING CLUSTERING ───")

    features = []

    for komoditas, group in df.groupby("komoditas"):
        group = group.sort_values("tanggal_data")
        harga = group["harga_per_kg"].values
        tanggal_num = (group["tanggal_data"] - group["tanggal_data"].min()).dt.days.values

        # Fitur 1: Mean
        mean_harga = np.mean(harga)

        # Fitur 2: CV (Coefficient of Variation)
        # Menggunakan std/mean — mengukur volatilitas relatif
        # Kenapa CV bukan std: agar bisa dibandingkan antar komoditas dengan level harga berbeda
        # (std Daging Sapi 1000 vs std Indomie 10 — tidak apple-to-apple, CV membandingkan relatif)
        cv = np.std(harga) / mean_harga if mean_harga > 0 else 0

        # Fitur 3: Trend Slope (regresi linear harga vs waktu)
        # Normalized: slope per hari → slope per tahun (365 hari)
        if len(tanggal_num) > 1:
            slope, intercept, r_value, p_value, std_err = stats.linregress(tanggal_num, harga)
            # Normalisasi slope: bagi dengan mean agar sebanding antar komoditas
            # (slope Rp 10/hari untuk Daging Sapi 124k berbeda maknanya vs Indomie 3k)
            trend_slope_normalized = (slope * 365) / mean_harga  # % perubahan per tahun
        else:
            trend_slope_normalized = 0.0
            r_value = 0.0
            p_value = 1.0

        kategori = group["kategori"].iloc[0] if "kategori" in group.columns else "UNKNOWN"

        features.append({
            "komoditas": komoditas,
            "kategori": kategori,
            "mean_harga": mean_harga,
            "cv": cv,
            "trend_slope_pct_per_year": trend_slope_normalized,
            "std_harga": np.std(harga),
            "min_harga": np.min(harga),
            "max_harga": np.max(harga),
            "n_obs": len(harga),
            "is_non_kg_original": group["is_non_kg_original"].iloc[0],
        })

    feat_df = pd.DataFrame(features).set_index("komoditas")

    log.info(f"  Feature matrix: {feat_df.shape[0]} komoditas × 3 fitur clustering")
    log.info("\n  Preview fitur clustering:")
    preview = feat_df[["cv", "mean_harga", "trend_slope_pct_per_year"]].copy()
    preview.columns = ["CV", "Mean Harga/kg", "Trend (%/tahun)"]
    for k, row in preview.sort_values("CV", ascending=False).iterrows():
        log.info(f"    {k:<45} CV={row['CV']:.4f}  Mean={row['Mean Harga/kg']:>10,.0f}  Trend={row['Trend (%/tahun)']:>+.3f}")

    log.info("─── FEATURE ENGINEERING SELESAI ───\n")
    return feat_df


# ─────────────────────────────────────────────────────────────────────────────
# 4. VALIDASI K OPTIMAL
# ─────────────────────────────────────────────────────────────────────────────

def validate_optimal_k(X_scaled: np.ndarray, feat_df: pd.DataFrame,
                        k_range: range = range(2, 8),
                        output_dir: Path = Path("outputs")) -> int:
    """
    Cari k optimal menggunakan:
    - Silhouette Score (lebih tinggi = lebih baik, range -1 s/d 1)
    - Inertia / Elbow Method (cari siku)

    Return: k optimal berdasarkan silhouette score tertinggi
    """
    log.info("─── VALIDASI K OPTIMAL ───")

    silhouette_scores = []
    inertias = []

    for k in k_range:
        km = KMeans(n_clusters=k, random_state=42, n_init=20)
        labels = km.fit_predict(X_scaled)
        sil = silhouette_score(X_scaled, labels)
        silhouette_scores.append(sil)
        inertias.append(km.inertia_)
        log.info(f"  k={k}: Silhouette={sil:.4f}, Inertia={km.inertia_:.2f}")

    optimal_k = list(k_range)[np.argmax(silhouette_scores)]
    log.info(f"\n  ✓ K Optimal: k={optimal_k} (Silhouette Score tertinggi: {max(silhouette_scores):.4f})")

    # Plot validasi
    output_dir.mkdir(parents=True, exist_ok=True)
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 5))
    fig.suptitle("Validasi K Optimal untuk K-Means Clustering", fontsize=14, fontweight="bold", y=1.02)

    k_list = list(k_range)

    # Silhouette Score
    ax1.plot(k_list, silhouette_scores, "o-", color="#7c6aff", linewidth=2, markersize=8)
    ax1.axvline(optimal_k, color="#f87171", linestyle="--", alpha=0.7, label=f"k optimal={optimal_k}")
    ax1.scatter([optimal_k], [max(silhouette_scores)], color="#f87171", s=150, zorder=5)
    ax1.set_xlabel("Jumlah Cluster (k)")
    ax1.set_ylabel("Silhouette Score")
    ax1.set_title("Silhouette Score\n(lebih tinggi = cluster lebih distinct)")
    ax1.legend()
    ax1.grid(True, alpha=0.3)

    # Elbow / Inertia
    ax2.plot(k_list, inertias, "s-", color="#3ecf8e", linewidth=2, markersize=8)
    ax2.axvline(optimal_k, color="#f87171", linestyle="--", alpha=0.7, label=f"k optimal={optimal_k}")
    ax2.set_xlabel("Jumlah Cluster (k)")
    ax2.set_ylabel("Inertia (Within-cluster Sum of Squares)")
    ax2.set_title("Elbow Method\n(cari titik siku)")
    ax2.legend()
    ax2.grid(True, alpha=0.3)

    plt.tight_layout()
    save_path = output_dir / "01_validasi_k_optimal.png"
    plt.savefig(save_path, dpi=150, bbox_inches="tight")
    plt.close()
    log.info(f"  Plot disimpan: {save_path}")
    log.info("─── VALIDASI K SELESAI ───\n")

    return optimal_k, dict(zip(k_list, silhouette_scores)), dict(zip(k_list, inertias))


# ─────────────────────────────────────────────────────────────────────────────
# 5. K-MEANS CLUSTERING
# ─────────────────────────────────────────────────────────────────────────────

def run_clustering(feat_df: pd.DataFrame, k: int,
                   output_dir: Path = Path("outputs")) -> pd.DataFrame:
    """
    Jalankan K-Means dengan k terpilih.
    Return: feat_df dengan kolom tambahan cluster, distance_to_centroid, is_centroid
    """
    log.info(f"─── K-MEANS CLUSTERING (k={k}) ───")

    # Ambil 3 fitur clustering, normalisasi ke [0,1]
    cluster_features = ["cv", "mean_harga", "trend_slope_pct_per_year"]
    X = feat_df[cluster_features].values
    scaler = MinMaxScaler()
    X_scaled = scaler.fit_transform(X)

    # Fit K-Means
    km = KMeans(n_clusters=k, random_state=42, n_init=50, max_iter=500)
    labels = km.fit_predict(X_scaled)
    centroids_scaled = km.cluster_centers_

    # Assign cluster label ke feat_df
    feat_df = feat_df.copy()
    feat_df["cluster"] = labels

    # Hitung jarak tiap komoditas ke centroid cluster-nya
    distances = []
    for i, (idx, row) in enumerate(feat_df.iterrows()):
        cluster_id = labels[i]
        centroid = centroids_scaled[cluster_id]
        point = X_scaled[i]
        dist = np.linalg.norm(point - centroid)
        distances.append(dist)
    feat_df["distance_to_centroid"] = distances

    # Centroid representative: komoditas paling dekat ke centroid per cluster
    centroids_repr = []
    for cluster_id in range(k):
        cluster_mask = feat_df["cluster"] == cluster_id
        cluster_data = feat_df[cluster_mask]
        nearest_idx = cluster_data["distance_to_centroid"].idxmin()
        centroids_repr.append(nearest_idx)

    feat_df["is_centroid"] = feat_df.index.isin(centroids_repr)

    # Beri nama deskriptif per cluster berdasarkan karakteristik
    cluster_profiles = []
    for cluster_id in range(k):
        cluster_data = feat_df[feat_df["cluster"] == cluster_id]
        avg_cv = cluster_data["cv"].mean()
        avg_mean = cluster_data["mean_harga"].mean()
        avg_trend = cluster_data["trend_slope_pct_per_year"].mean()

        # Label otomatis berdasarkan threshold
        volatility = "Labil" if avg_cv > feat_df["cv"].median() else "Stabil"
        price_level = "Mahal" if avg_mean > feat_df["mean_harga"].median() else "Murah"
        trend_dir = "↑Inflasi" if avg_trend > 0.02 else ("↓Deflasi" if avg_trend < -0.02 else "→Datar")

        label = f"Cluster {cluster_id}: {volatility} & {price_level} ({trend_dir})"
        cluster_profiles.append({
            "cluster_id": cluster_id,
            "label": label,
            "avg_cv": avg_cv,
            "avg_mean_harga": avg_mean,
            "avg_trend_pct_per_year": avg_trend,
            "n_komoditas": len(cluster_data),
            "centroid_representative": feat_df[feat_df["cluster"] == cluster_id]["distance_to_centroid"].idxmin(),
        })
        feat_df.loc[feat_df["cluster"] == cluster_id, "cluster_label"] = label

    cluster_profile_df = pd.DataFrame(cluster_profiles)

    # Log ringkasan
    log.info(f"\n  Final Silhouette Score: {silhouette_score(X_scaled, labels):.4f}")
    log.info("\n  ═══ HASIL CLUSTERING ═══")
    for _, prof in cluster_profile_df.iterrows():
        log.info(f"\n  ┌─ {prof['label']}")
        log.info(f"  │  Jumlah komoditas : {prof['n_komoditas']}")
        log.info(f"  │  Avg CV           : {prof['avg_cv']:.4f}")
        log.info(f"  │  Avg Mean Harga   : Rp {prof['avg_mean_harga']:,.0f}/kg")
        log.info(f"  │  Avg Trend        : {prof['avg_trend_pct_per_year']:+.3f}%/tahun")
        log.info(f"  └─ Wakil Centroid   : ★ {prof['centroid_representative']}")

        members = feat_df[feat_df["cluster"] == prof["cluster_id"]].index.tolist()
        log.info(f"     Anggota          : {', '.join(members)}")

    log.info("\n  ═══ KOMODITAS CENTROID (WAKIL REPRESENTATIF) ═══")
    for repr_komoditas in centroids_repr:
        row = feat_df.loc[repr_komoditas]
        log.info(f"  ★ {repr_komoditas}")
        log.info(f"    Cluster  : {row['cluster_label']}")
        log.info(f"    CV       : {row['cv']:.4f}")
        log.info(f"    Mean     : Rp {row['mean_harga']:,.0f}/kg")
        log.info(f"    Trend    : {row['trend_slope_pct_per_year']:+.4f}%/tahun")
        log.info(f"    Jarak ke centroid: {row['distance_to_centroid']:.4f}")

    log.info("─── CLUSTERING SELESAI ───\n")

    return feat_df, cluster_profile_df, scaler, X_scaled, centroids_scaled


# ─────────────────────────────────────────────────────────────────────────────
# 6. VISUALISASI
# ─────────────────────────────────────────────────────────────────────────────

def plot_clustering_results(feat_df: pd.DataFrame, X_scaled: np.ndarray,
                             output_dir: Path = Path("outputs")):
    """Buat 3 plot: scatter 2D, feature distribution, price time series centroid."""
    output_dir.mkdir(parents=True, exist_ok=True)
    k = feat_df["cluster"].nunique()
    colors = ["#7c6aff", "#3ecf8e", "#f59e0b", "#f87171", "#60a5fa"][:k]

    # ── Plot 1: Scatter CV vs Mean Harga (colored by cluster)
    fig, axes = plt.subplots(1, 2, figsize=(15, 6))
    fig.suptitle("Clustering Komoditas Pangan Surabaya — Siskaperbapo", fontsize=13, fontweight="bold")

    ax = axes[0]
    for cluster_id in range(k):
        mask = feat_df["cluster"] == cluster_id
        cluster_data = feat_df[mask]
        ax.scatter(cluster_data["cv"], cluster_data["mean_harga"],
                   c=colors[cluster_id], s=80, alpha=0.85,
                   label=f"Cluster {cluster_id} (n={mask.sum()})", zorder=3)

        # Annotate centroid representative
        centroid_mask = mask & feat_df["is_centroid"]
        if centroid_mask.any():
            centroid = feat_df[centroid_mask]
            ax.scatter(centroid["cv"], centroid["mean_harga"],
                       c=colors[cluster_id], s=250, marker="*", edgecolors="black",
                       linewidths=1.5, zorder=5, label=f"Centroid C{cluster_id}")
            for idx, row in centroid.iterrows():
                ax.annotate(idx, (row["cv"], row["mean_harga"]),
                            textcoords="offset points", xytext=(8, 4),
                            fontsize=7.5, fontweight="bold",
                            bbox=dict(boxstyle="round,pad=0.2", facecolor="white", alpha=0.7))

    # Annotate semua titik
    for idx, row in feat_df[~feat_df["is_centroid"]].iterrows():
        ax.annotate(idx, (row["cv"], row["mean_harga"]),
                    textcoords="offset points", xytext=(4, 2),
                    fontsize=6, color="gray", alpha=0.8)

    ax.set_xlabel("CV (Coefficient of Variation) — Volatilitas Relatif")
    ax.set_ylabel("Mean Harga per kg (Rp)")
    ax.set_title("CV vs Mean Harga")
    ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, p: f"Rp {x:,.0f}"))
    ax.legend(loc="upper left", fontsize=8)
    ax.grid(True, alpha=0.3)

    # ── Plot 2: CV vs Trend Slope
    ax2 = axes[1]
    for cluster_id in range(k):
        mask = feat_df["cluster"] == cluster_id
        cluster_data = feat_df[mask]
        ax2.scatter(cluster_data["cv"], cluster_data["trend_slope_pct_per_year"],
                    c=colors[cluster_id], s=80, alpha=0.85,
                    label=f"Cluster {cluster_id}", zorder=3)

        centroid_mask = mask & feat_df["is_centroid"]
        if centroid_mask.any():
            centroid = feat_df[centroid_mask]
            ax2.scatter(centroid["cv"], centroid["trend_slope_pct_per_year"],
                        c=colors[cluster_id], s=250, marker="*", edgecolors="black",
                        linewidths=1.5, zorder=5)
            for idx, row in centroid.iterrows():
                ax2.annotate(idx, (row["cv"], row["trend_slope_pct_per_year"]),
                             textcoords="offset points", xytext=(8, 4),
                             fontsize=7.5, fontweight="bold",
                             bbox=dict(boxstyle="round,pad=0.2", facecolor="white", alpha=0.7))

    ax2.axhline(0, color="gray", linestyle="--", alpha=0.5)
    ax2.set_xlabel("CV (Coefficient of Variation)")
    ax2.set_ylabel("Trend Slope (%/tahun)")
    ax2.set_title("CV vs Trend Slope")
    ax2.legend(loc="upper left", fontsize=8)
    ax2.grid(True, alpha=0.3)

    plt.tight_layout()
    save_path = output_dir / "02_clustering_scatter.png"
    plt.savefig(save_path, dpi=150, bbox_inches="tight")
    plt.close()
    log.info(f"  Plot clustering disimpan: {save_path}")


def plot_centroid_time_series(df_processed: pd.DataFrame, feat_df: pd.DataFrame,
                               output_dir: Path = Path("outputs")):
    """Plot time series harga historis untuk masing-masing komoditas centroid."""
    centroids = feat_df[feat_df["is_centroid"]].index.tolist()
    k = len(centroids)
    colors = ["#7c6aff", "#3ecf8e", "#f59e0b", "#f87171", "#60a5fa"][:k]

    fig, axes = plt.subplots(k, 1, figsize=(14, 4 * k), sharex=True)
    if k == 1:
        axes = [axes]
    fig.suptitle("Time Series Harga — Komoditas Centroid Representative\n(Akan Dimodelkan di Tahap Turnamen Baseline)",
                 fontsize=12, fontweight="bold")

    for i, (komoditas, ax) in enumerate(zip(centroids, axes)):
        data = df_processed[df_processed["komoditas"] == komoditas].sort_values("tanggal_data")
        row = feat_df.loc[komoditas]

        ax.plot(data["tanggal_data"], data["harga_per_kg"],
                color=colors[i], linewidth=1.2, alpha=0.9)
        ax.fill_between(data["tanggal_data"], data["harga_per_kg"],
                        alpha=0.15, color=colors[i])

        # Rolling mean 30 hari
        rolling = data.set_index("tanggal_data")["harga_per_kg"].rolling(30, min_periods=1).mean()
        ax.plot(rolling.index, rolling.values, color=colors[i], linewidth=2.5,
                linestyle="--", alpha=0.8, label="30-day rolling mean")

        cluster_label = row["cluster_label"]
        ax.set_title(
            f"★ {komoditas} | {cluster_label}\n"
            f"CV={row['cv']:.4f}  Mean=Rp{row['mean_harga']:,.0f}/kg  "
            f"Trend={row['trend_slope_pct_per_year']:+.3f}%/tahun",
            fontsize=10, loc="left"
        )
        ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, p: f"Rp {x:,.0f}"))
        ax.set_ylabel("Harga/kg (Rp)")
        ax.legend(fontsize=8, loc="upper left")
        ax.grid(True, alpha=0.3)

    axes[-1].set_xlabel("Tanggal")
    plt.tight_layout()
    save_path = output_dir / "03_centroid_time_series.png"
    plt.savefig(save_path, dpi=150, bbox_inches="tight")
    plt.close()
    log.info(f"  Plot time series centroid disimpan: {save_path}")


# ─────────────────────────────────────────────────────────────────────────────
# 7. EXPORT HASIL
# ─────────────────────────────────────────────────────────────────────────────

def export_results(df_processed: pd.DataFrame, feat_df: pd.DataFrame,
                   cluster_profile_df: pd.DataFrame,
                   output_dir: Path = Path("outputs")):
    """Export semua hasil ke CSV untuk dipakai di tahap berikutnya."""
    output_dir.mkdir(parents=True, exist_ok=True)

    # 7.1 Data preprocessed (harga_per_kg, sudah clean)
    df_export = df_processed[["tanggal_data", "komoditas", "kategori",
                               "harga_per_kg", "satuan", "faktor_konversi",
                               "is_non_kg_original"]].copy()
    df_export.to_csv(output_dir / "data_preprocessed.csv", index=False)
    log.info(f"  Exported: data_preprocessed.csv ({len(df_export):,} rows)")

    # 7.2 Cluster assignments (semua komoditas + fitur + cluster info)
    feat_export = feat_df.reset_index()
    feat_export.to_csv(output_dir / "cluster_assignments.csv", index=False)
    log.info(f"  Exported: cluster_assignments.csv ({len(feat_export)} komoditas)")

    # 7.3 Centroid representatives (hanya 3 wakil)
    centroids = feat_df[feat_df["is_centroid"]].reset_index()
    centroids.to_csv(output_dir / "centroid_representatives.csv", index=False)
    log.info(f"  Exported: centroid_representatives.csv ({len(centroids)} komoditas)")

    # 7.4 Cluster profiles
    cluster_profile_df.to_csv(output_dir / "cluster_profiles.csv", index=False)
    log.info(f"  Exported: cluster_profiles.csv")

    # 7.5 Time series per centroid (siap untuk modeling)
    centroids_list = feat_df[feat_df["is_centroid"]].index.tolist()
    for komoditas in centroids_list:
        ts_data = df_processed[df_processed["komoditas"] == komoditas][
            ["tanggal_data", "harga_per_kg"]
        ].sort_values("tanggal_data")
        ts_data.columns = ["ds", "y"]  # format Prophet-ready
        slug = komoditas.lower().replace(" ", "_").replace("/", "_")
        fname = output_dir / f"timeseries_centroid_{slug}.csv"
        ts_data.to_csv(fname, index=False)
        log.info(f"  Exported: {fname.name} ({len(ts_data)} rows, Prophet-ready format ds/y)")

    log.info(f"\n  Semua output tersimpan di: {output_dir.resolve()}")


# ─────────────────────────────────────────────────────────────────────────────
# 8. MLflow LOGGING (opsional)
# ─────────────────────────────────────────────────────────────────────────────

def log_to_mlflow(feat_df: pd.DataFrame, cluster_profile_df: pd.DataFrame,
                  silhouette_scores: dict, inertias: dict,
                  optimal_k: int, output_dir: Path,
                  mlflow_uri: str = "http://localhost:5000"):
    """Log hasil clustering ke MLflow untuk tracking."""
    try:
        import mlflow
        mlflow.set_tracking_uri(mlflow_uri)
        mlflow.set_experiment("siskaperbapo-clustering")

        with mlflow.start_run(run_name=f"kmeans-k{optimal_k}"):
            # Params
            mlflow.log_param("k_optimal", optimal_k)
            mlflow.log_param("features", "cv,mean_harga,trend_slope_pct_per_year")
            mlflow.log_param("scaler", "MinMaxScaler")
            mlflow.log_param("outlier_method", "winsorize_IQR_1.5")
            mlflow.log_param("n_komoditas", len(feat_df))

            # Metrics
            mlflow.log_metric("silhouette_score_optimal", silhouette_scores[optimal_k])
            for k, score in silhouette_scores.items():
                mlflow.log_metric(f"silhouette_k{k}", score)
            for k, inertia in inertias.items():
                mlflow.log_metric(f"inertia_k{k}", inertia)

            # Centroid representatives
            centroids = feat_df[feat_df["is_centroid"]].index.tolist()
            for i, c in enumerate(centroids):
                mlflow.log_param(f"centroid_cluster{i}", c)

            # Artifacts
            for f in output_dir.glob("*.png"):
                mlflow.log_artifact(str(f), "plots")
            for f in output_dir.glob("*.csv"):
                mlflow.log_artifact(str(f), "data")

        log.info(f"  MLflow logged ke: {mlflow_uri}")
        log.info(f"  Buka UI: {mlflow_uri}")

    except Exception as e:
        log.warning(f"  MLflow logging gagal (service mungkin belum jalan): {e}")
        log.warning("  Lanjut tanpa MLflow — hasil tetap tersimpan di local.")


# ─────────────────────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Preprocessing + Clustering Siskaperbapo Data"
    )
    parser.add_argument(
        "--source", choices=["postgres", "csv", "sqlite"], default="sqlite",
        help="Sumber data: postgres, csv, atau sqlite (default: sqlite)"
    )
    # Argumen baru khusus untuk file .db kalian
    parser.add_argument("--sqlite-path", default="data/raw/siskaperbapo.db",
                        help="Path ke file SQLite DB (jika --source sqlite)")
    
    parser.add_argument("--csv-path", default="data/processed_marketcast.csv",
                        help="Path ke file CSV (jika --source csv)")
    
    # parser.add_argument(
    #     "--source", choices=["postgres", "csv"], default="csv",
    #     help="Sumber data: postgres atau csv (default: csv)"
    # )
    # parser.add_argument("--csv-path", default="data/processed_marketcast.csv",
    #                     help="Path ke file CSV (jika --source csv)")
    # PostgreSQL args
    parser.add_argument("--pg-host", default="localhost")
    parser.add_argument("--pg-port", default="5432")
    parser.add_argument("--pg-db", default="siskaperbapo")
    parser.add_argument("--pg-user", default="admin")
    parser.add_argument("--pg-password", default="password123")
    # Clustering args
    parser.add_argument("--k", type=int, default=None,
                        help="Paksa k tertentu (skip validasi). Jika tidak diisi, otomatis dicari.")
    parser.add_argument("--k-min", type=int, default=2, help="K minimum untuk dicari (default: 2)")
    parser.add_argument("--k-max", type=int, default=7, help="K maksimum untuk dicari (default: 7)")
    # Output args
    parser.add_argument("--output-dir", default="outputs/clustering",
                        help="Direktori output (default: outputs/clustering)")
    parser.add_argument("--mlflow-uri", default="http://localhost:5000",
                        help="MLflow tracking URI (default: http://localhost:5000)")
    parser.add_argument("--no-mlflow", action="store_true",
                        help="Skip MLflow logging")

    args = parser.parse_args()
    output_dir = Path(args.output_dir)

    log.info("═" * 60)
    log.info("  SISKAPERBAPO — Preprocessing & Clustering Pipeline")
    log.info("═" * 60)

    # ── Load data
    if args.source == "postgres":
        df_raw = load_from_postgres(
            args.pg_host, args.pg_port, args.pg_db,
            args.pg_user, args.pg_password
        )
    elif args.source == "sqlite":
        # Panggil fungsi baru kita!
        df_raw = load_from_sqlite(args.sqlite_path)
    else:
        df_raw = load_from_csv(args.csv_path)

    # # ── Load data
    # if args.source == "postgres":
    #     df_raw = load_from_postgres(
    #         args.pg_host, args.pg_port, args.pg_db,
    #         args.pg_user, args.pg_password
    #     )
    # else:
    #     df_raw = load_from_csv(args.csv_path)

    # ── Preprocessing
    df_processed = preprocess(df_raw)

    # ── Feature engineering
    feat_df = build_clustering_features(df_processed)

    # ── Normalisasi fitur untuk clustering
    cluster_features = ["cv", "mean_harga", "trend_slope_pct_per_year"]
    X = feat_df[cluster_features].values
    scaler = MinMaxScaler()
    X_scaled = scaler.fit_transform(X)

    # ── Validasi k (jika tidak di-override)
    if args.k is not None:
        k = args.k
        log.info(f"K di-override ke k={k} (skip validasi)")
        silhouette_scores = {}
        inertias = {}
    else:
        k, silhouette_scores, inertias = validate_optimal_k(
            X_scaled, feat_df, k_range=range(args.k_min, args.k_max + 1),
            output_dir=output_dir
        )

    # ── Clustering
    feat_df, cluster_profile_df, scaler, X_scaled, centroids_scaled = run_clustering(
        feat_df, k, output_dir=output_dir
    )

    # ── Visualisasi
    log.info("─── VISUALISASI ───")
    plot_clustering_results(feat_df, X_scaled, output_dir=output_dir)
    plot_centroid_time_series(df_processed, feat_df, output_dir=output_dir)
    log.info("─── VISUALISASI SELESAI ───\n")

    # ── Export
    log.info("─── EXPORT HASIL ───")
    export_results(df_processed, feat_df, cluster_profile_df, output_dir=output_dir)
    log.info("─── EXPORT SELESAI ───\n")

    # ── MLflow
    if not args.no_mlflow and silhouette_scores:
        log.info("─── MLFLOW LOGGING ───")
        log_to_mlflow(feat_df, cluster_profile_df, silhouette_scores, inertias,
                      k, output_dir, mlflow_uri=args.mlflow_uri)
        log.info("─── MLFLOW SELESAI ───\n")

    # ── Summary akhir
    log.info("═" * 60)
    log.info("  PIPELINE SELESAI")
    log.info("═" * 60)
    log.info(f"\n  K optimal     : {k}")
    log.info(f"  Output dir    : {output_dir.resolve()}")
    log.info(f"\n  File yang dihasilkan:")
    for f in sorted(output_dir.glob("*")):
        log.info(f"    {f.name}")
    log.info(f"\n  ★ KOMODITAS CENTROID (wakil untuk turnamen model baseline):")
    for _, row in feat_df[feat_df["is_centroid"]].iterrows():
        log.info(f"    - {row.name}  [{row['cluster_label']}]")
    log.info("\n  Next step: jalankan training pipeline dengan 3 komoditas centroid ini")
    log.info("  menggunakan 3 model baseline (SARIMA, Prophet, XGBoost)")


if __name__ == "__main__":
    main()
