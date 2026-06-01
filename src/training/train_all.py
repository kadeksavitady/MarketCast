"""
src/training/train_all.py
==========================
Orchestrator pipeline training PBL-MarketCast.

POSISI DALAM PIPELINE KESELURUHAN:
    ← Input : outputs/clustering/data_preprocessed.csv        (Tahap 0)
              outputs/clustering/cluster_assignments.csv       (Tahap 0)
              outputs/clustering/centroid_representatives.csv  (Tahap 0)
    → Output: MLflow runs di DagsHub                          (Tahap 2 & 3a)
              outputs/registry/model_registry_map.yaml        (→ Tahap 3b)

DUA MODE EKSEKUSI:
    --mode tournament  (Tahap 2)
        Semua centroid × 3 model = 9 runs
        Semua model pakai parameter default per cluster
        Experiment: MarketCast-Tournament
        Output: leaderboard → pilih 1 juara per cluster di DagsHub MLflow UI

    --mode specialize  (Tahap 3a)
        SEMUA komoditas (centroid + non-centroid) × model juara cluster masing-masing
        Hyperparameter tuning diaktifkan per model:
            SARIMA   → GridSearch 36 kombinasi + prior knowledge cluster
            Prophet  → Optuna TPE 15 trial + early stopping (patience=5)
            XGBoost  → Optuna TPE 30 trial + early stopping (patience=5)
        Experiment: MarketCast-Specialization
        Output: model_registry_map.yaml → dipakai FastAPI & business logic
        Catatan: centroid di-retrain ulang di sini (bukan skip) agar semua
                 komoditas punya model_uri valid di registry untuk FastAPI serving

ARSITEKTUR PEMANGGILAN MODEL:
    Semua model dipanggil via _call_model() — satu titik dispatch yang
    meneruskan training_mode ke semua model:
        tournament → semua model pakai parameter default
        specialize → semua model aktifkan hyperparameter tuning
    Keputusan mode ada di train_all.py, bukan di masing-masing model.

CARA PAKAI:
    # Tahap 2 — turnamen baseline (jalankan dari root repo)
    python src/training/train_all.py --mode tournament

    # Tahap 3a — tanpa --champion (auto-load dari MLflow Registry @champion alias)
    python src/training/train_all.py --mode specialize

    # Satu komoditas / satu model (debugging)
    python src/training/train_all.py --mode tournament \
        --model sarima --komoditas "Telur Ayam Ras"

ENVIRONMENT VARS YANG DIBUTUHKAN (.env):
    DAGSHUB_TOKEN  → wajib untuk log ke DagsHub MLflow
    DAGSHUB_USER   → default "kadeksavitady"
    DAGSHUB_REPO   → default "MarketCast"
"""

import sys
import yaml
import argparse
import traceback
import pandas as pd
from pathlib import Path
from datetime import datetime
 
from config import (
    MLFLOW_TRACKING_URI, MLFLOW_EXP_TOURNAMENT, MLFLOW_EXP_SPECIALIZE,
    init_mlflow,
    YAML_MODEL_REGISTRY, DIR_REGISTRY, CSV_PREPROCESSED,
    load_cluster_map, load_centroid_list,
    get_logger,
)
from data_loader import load_preprocessed, load_all_series
from model_sarima  import train_sarima
from model_prophet import train_prophet
from model_xgboost import train_xgboost
import dagshub
 
log = get_logger("train_all")
 
MODEL_REGISTRY = {
    "sarima"  : train_sarima,
    "prophet" : train_prophet,
    "xgboost" : train_xgboost,
}
 
# ══════════════════════════════════════════════════════════════
# HELPER: pemanggilan model dengan training_mode
# ══════════════════════════════════════════════════════════════
def _call_model(model_name: str, komoditas: str, data: dict,
                mlflow_experiment: str, training_mode: str) -> dict:
    """
    Wrapper pemanggilan model yang meneruskan training_mode.
 
    KENAPA wrapper ini diperlukan:
        Tidak semua model punya parameter training_mode — hanya SARIMA.
        Prophet dan XGBoost tidak mengenal parameter ini.
        Solusi: SARIMA menerima training_mode secara eksplisit.
        Prophet/XGBoost signature-nya tidak berubah sama sekali.
 
        Dengan wrapper ini, train_all.py tidak perlu if/else per model —
        cukup satu titik panggilan yang bersih.
 
    training_mode:
        "tournament"  → SARIMA pakai auto_arima (AIC stepwise)
        "specialize"  → SARIMA pakai GridSearch 36 kombinasi + prior cluster
        (diabaikan oleh Prophet dan XGBoost)
    """
    fn = MODEL_REGISTRY[model_name]
    return fn(
        komoditas,
        data,
        mlflow_experiment=mlflow_experiment,
        mode=training_mode,
    )
 
 
# ══════════════════════════════════════════════════════════════
# TAHAP 2 — TURNAMEN BASELINE
# ══════════════════════════════════════════════════════════════
def run_tournament(models: list, komoditas_list: list,
                   all_data: dict, cluster_map: dict) -> list:
    """
    3 centroid × 3 model = 9 runs.
    training_mode="tournament" → SARIMA pakai auto_arima.
    """
    import mlflow
    init_mlflow()
 
    TRAINING_MODE = "tournament"   # ← deklarasi eksplisit di sini
 
    results  = []
    n_total  = len(models) * len(komoditas_list)
    n_done   = 0
    n_failed = 0
 
    log.info("=" * 65)
    log.info("  TAHAP 2 — TURNAMEN BASELINE MODEL")
    log.info(f"  {len(models)} model × {len(komoditas_list)} centroid = {n_total} runs")
    log.info(f"  SARIMA mode : auto_arima (AIC stepwise)")
    log.info(f"  Experiment  : {MLFLOW_EXP_TOURNAMENT}")
    log.info(f"  MLflow      : {MLFLOW_TRACKING_URI}")
    log.info("=" * 65)
 
    for komoditas in komoditas_list:
        data = all_data.get(komoditas)
        if data is None:
            log.error(f"Data tidak tersedia untuk {komoditas} — skip")
            n_failed += len(models)
            continue
 
        for model_name in models:
            n_done += 1
            log.info(f"\n[{n_done}/{n_total}] {model_name.upper()} × {komoditas}")
            try:
                # training_mode="tournament" diteruskan ke model
                result = _call_model(
                    model_name, komoditas, data,
                    mlflow_experiment=MLFLOW_EXP_TOURNAMENT,
                    training_mode=TRAINING_MODE,
                )
                result["model_name"] = model_name
                results.append(result)
                m = result["metrics"]
                log.info(
                    f"  ✓ MAE={m['mae']:>10,.0f}  "
                    f"MAPE={m['mape']:>6.2f}%  "
                    f"SMAPE={m['smape']:>6.2f}%  "
                    f"R²={m.get('r2', 0):>6.4f}"
                )
            except Exception as e:
                n_failed += 1
                log.error(f"  ✗ GAGAL: {e}")
                log.debug(traceback.format_exc())
 
    _print_tournament_leaderboard(results)
    
    # ══════════════════════════════════════════════════════════════
    # LOGIKA AUTO-REGISTRY @CHAMPION (THE FINAL JUDGE)
    # ══════════════════════════════════════════════════════════════
    from mlflow.tracking import MlflowClient
    client = MlflowClient()
    
    # TODO: Metrik bisa diubah sesuai hasil riset jurnalmu nanti (misal "rmse")
    TARGET_METRIC = "mape" 
    
    log.info(f"\n  ── AUTO-REGISTER CHAMPION (Berdasarkan {TARGET_METRIC.upper()}) ──")
    
    # Ekstrak hasil ke DataFrame untuk mempermudah pencarian juara
    df_res = pd.DataFrame([
        {
            "cluster": r["data"]["cluster"],
            "model_name": r["model_name"],
            "model_uri": r["model_uri"],
            "metric_val": r["metrics"][TARGET_METRIC]
        } for r in results
    ])
    
    if not df_res.empty:
        # Cari index dengan nilai metrik TERKECIL untuk masing-masing cluster
        best_idx = df_res.groupby("cluster")["metric_val"].idxmin()
        best_models = df_res.loc[best_idx]
        
        # Daftarkan masing-masing juara ke Registry
        for _, row in best_models.iterrows():
            cluster_name = row['cluster']
            winner_model = row['model_name']
            model_uri = row['model_uri']
            metric_val = row['metric_val']
            
            # Format reg_name sesuai gambar: Murni nama clusternya saja (tanpa Champion_)
            reg_name = f"{cluster_name}"
            
            log.info(f" Juara {cluster_name} adalah {winner_model.upper()} ({TARGET_METRIC}={metric_val:.4f})")
            _register_to_mlflow_registry(
                komoditas=cluster_name,  # fungsi _register_to_mlflow_registry mu butuh param 'komoditas' untuk log
                model_uri=model_uri,
                reg_name=reg_name,
                alias_name="champion",
                client=client
            )

    log.info(f"\n✓ Tournament: {len(results)}/{n_total} runs | {n_failed} gagal")
    log.info(f"  → Juara berhasil diregister dengan alias @champion")
    log.info(f"  → Buka MLflow UI: {MLFLOW_TRACKING_URI}")
    log.info(f"  → Lanjut jalankan: python src/training/train_all.py --mode specialize")
    return results
 
def _print_tournament_leaderboard(results: list):
    if not results:
        return
    rows = [{"komoditas": r["komoditas"], "cluster": r["data"]["cluster"],
              "model": r["model_name"], **r["metrics"]} for r in results]
    lb   = pd.DataFrame(rows).sort_values(["cluster", "mape"])
    log.info("\n" + "=" * 65)
    log.info("  LEADERBOARD TURNAMEN (sorted by MAPE per cluster)")
    log.info("=" * 65)
    log.info(f"\n{lb.to_string(index=False)}")
    log.info("\n── Best model per cluster ────────────────────────────────")
    best = lb.loc[lb.groupby("cluster")["mape"].idxmin()]
    cols = [c for c in ['cluster','model','mape','smape','r2'] if c in best.columns]
    log.info(f"\n{best[cols].to_string(index=False)}")
 
 
# ══════════════════════════════════════════════════════════════
# TAHAP 3a — SPESIALISASI
# ══════════════════════════════════════════════════════════════
def run_specialize(champion_map: dict, all_data: dict,
                   cluster_map: dict) -> dict:
    """
    Training SEMUA komoditas (centroid + non-centroid) dengan model champion.
    training_mode="specialize" → SARIMA pakai GridSearch 36 kombinasi + prior.
 
    KENAPA centroid juga di-retrain di sini:
        Centroid yang di-train di Tournament punya model_uri valid,
        tapi mode-nya "tournament" (auto_arima).
        Di Specialize, centroid di-retrain dengan mode="specialize"
        (GridSearch) sehingga semua komoditas — termasuk centroid —
        punya model yang lebih optimal untuk production serving.
    """
    import mlflow
    from mlflow.tracking import MlflowClient
    init_mlflow()
 
    client = MlflowClient()
    TRAINING_MODE = "specialize"   # ← deklarasi eksplisit di sini
 
    centroid_list   = load_centroid_list()
    all_komoditas   = list(all_data.keys())
    full_train_list = all_komoditas   # centroid tidak di-filter
 
    log.info("=" * 65)
    log.info("  TAHAP 3a — SPESIALISASI")
    log.info(f"  {len(full_train_list)} komoditas total (centroid + non-centroid)")
    log.info(f"  SARIMA mode : GridSearch 36 kombinasi + prior knowledge cluster")
    log.info(f"  Champion map: {champion_map}")
    log.info(f"  Experiment  : {MLFLOW_EXP_SPECIALIZE}")
    log.info("=" * 65)
 
    registry = {}
    n_done   = 0
    n_failed = 0
    n_total  = len(full_train_list)
 
    for komoditas in full_train_list:
        data = all_data.get(komoditas)
        if data is None:
            log.warning(f"Skip {komoditas}: data tidak tersedia")
            n_failed += 1
            continue
 
        cluster_short = data["cluster"]
        model_name    = champion_map.get(cluster_short)
 
        if model_name is None:
            log.warning(
                f"Skip {komoditas}: tidak ada champion untuk cluster "
                f"'{cluster_short}'."
            )
            n_failed += 1
            continue
 
        is_centroid = komoditas in centroid_list
        n_done += 1
        label = "[CENTROID]" if is_centroid else ""
        log.info(f"[{n_done}/{n_total}] {model_name.upper()} × {komoditas} "
                 f"[{cluster_short}] {label}")
 
        try:
            # training_mode="specialize" diteruskan ke model
            result = _call_model(
                model_name, komoditas, data,
                mlflow_experiment=MLFLOW_EXP_SPECIALIZE,
                training_mode=TRAINING_MODE,
            )
 
            run_id    = result.get("run_id",    "")
            model_uri = result.get("model_uri", "")
 
            if not model_uri:
                log.error(
                    f"  ✗ model_uri kosong untuk {komoditas} (run_id={run_id}). "
                    "Run berhasil tapi model tidak ter-log ke MLflow."
                )
                n_failed += 1
                continue

            # Map nama model agar kapitalisasinya sesuai dengan gambar (SARIMA, XGBoost, Prophet)
            model_map = {"sarima": "SARIMA", "xgboost": "XGBoost", "prophet": "Prophet"}
            proper_model_name = model_map.get(model_name.lower(), model_name.upper())
            
            # Format reg_name sesuai gambar: ModelName_Nama Komoditas Asli (spasi tetap dipertahankan)
            reg_name = f"{proper_model_name}_{komoditas}"

            # ── Panggil Fungsi Helper Registry ──
            _, mv_version = _register_to_mlflow_registry(
                model_uri=model_uri, 
                reg_name=reg_name, 
                alias_name="production", 
                client=client
            )

            registry[komoditas] = {
                "cluster"      : cluster_short,
                "model"        : model_name,
                "mlflow_run_id": run_id,
                "model_uri"    : model_uri,
                "mape"         : result["metrics"]["mape"],
                "mae"          : result["metrics"]["mae"],
                "is_centroid"  : is_centroid,
                "registry_name" : reg_name,    # ── Menyimpan nama registry untuk backup
                "version"       : mv_version, # ── Menyimpan versi model
            }
            log.info(f"  ✓ MAPE={result['metrics']['mape']:.2f}%  uri={model_uri} | Registry: {reg_name}@production (v{mv.version})")
 
        except Exception as e:
            n_failed += 1
            log.error(f"  ✗ GAGAL: {e}")
            log.debug(traceback.format_exc())
 
    # Validasi coverage sebelum simpan
    empty_uris = [k for k, v in registry.items() if not v.get("model_uri")]
    if empty_uris:
        log.error(
            f"PERINGATAN: {len(empty_uris)} komoditas punya model_uri kosong: "
            f"{empty_uris}\nFastAPI AKAN crash saat load model ini."
        )
 
    _save_registry(registry)
 
    log.info(f"\n{'='*65}")
    log.info(f"  SPESIALISASI SELESAI")
    log.info(f"  Berhasil : {len(registry)}/{n_total}")
    log.info(f"  Gagal    : {n_failed}")
    log.info(f"  Coverage : {len([k for k, v in registry.items() if v.get('model_uri')])} "
             f"komoditas punya model_uri valid")
    log.info(f"  Registry : {YAML_MODEL_REGISTRY}")
    log.info(f"{'='*65}")
    return registry

def _register_to_mlflow_registry(model_uri: str, reg_name: str, alias_name: str, client) -> tuple:
    """
    Mendaftarkan model ke MLflow Model Registry dengan nama dan alias dinamis.
    - Specialize -> alias: 'production'
    - Tournament -> alias: 'champion'
    """
    import mlflow
    
    log.info(f"  Mendaftarkan ke DagsHub Registry sebagai '{reg_name}@{alias_name}'...")
    
    # 1. Register Model
    mv = mlflow.register_model(model_uri=model_uri, name=reg_name)

    # 2. Set Alias
    client.set_registered_model_alias(
        name=reg_name,
        alias=alias_name,
        version=mv.version
    )
    return reg_name, mv.version

def _save_registry(registry: dict):
    import mlflow, tempfile, os

    DIR_REGISTRY.mkdir(parents=True, exist_ok=True)
    output = {
        "_meta": {
            "generated_at"   : datetime.now().isoformat(),
            "total_komoditas": len(registry),
            "description"    : (
                "Model registry PBL-MarketCast. "
                "Dipakai oleh FastAPI untuk load model saat serving. "
                "Di-generate otomatis oleh train_all.py --mode specialize."
            ),
        },
        "models": registry,
    }
    # Simpan ke disk lokal
    with open(YAML_MODEL_REGISTRY, "w", encoding="utf-8") as f:
        yaml.dump(output, f, allow_unicode=True, sort_keys=False, indent=2)
    log.info(f"Registry disimpan: {YAML_MODEL_REGISTRY}")

    # Upload ke MLflow sebagai artifact — agar semua anggota tim bisa akses
    try:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_yaml = os.path.join(tmpdir, "model_registry_map.yaml")
            with open(tmp_yaml, "w", encoding="utf-8") as f:
                yaml.dump(output, f, allow_unicode=True, sort_keys=False, indent=2)
            mlflow.log_artifact(tmp_yaml, artifact_path="registry")
        log.info("✅ Registry di-upload ke MLflow artifacts")
    except Exception as e:
        log.warning(f"Upload registry ke MLflow gagal (tidak kritis): {e}")

    log.info(f"Total komoditas terdaftar: {len(registry)}")
 
 
# ══════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════
def load_champion_from_registry() -> dict:
    """Baca alias @champion dari MLflow Model Registry."""
    import mlflow
    init_mlflow()   # idempoten — aman dipanggil ulang
    client = mlflow.tracking.MlflowClient()
 
    champion_map = {}
    try:
        for rm in client.search_registered_models():
            try:
                mv      = client.get_model_version_by_alias(rm.name, "champion")
                run     = client.get_run(mv.run_id)
                cluster = run.data.tags.get("cluster", "")
                model   = run.data.tags.get("model", "").lower()
                if cluster and model:
                    champion_map[cluster] = model
                    log.info(f"  Registry @champion: {rm.name} → {cluster}={model}")
            except Exception:
                pass
    except Exception as e:
        log.warning(f"Gagal baca Registry: {e}")
    return champion_map
 
def parse_champion(champion_args: list) -> dict:
    if not champion_args:
        return {}
    result = {}
    for item in champion_args:
        if "=" not in item:
            raise ValueError(f"Format salah: '{item}'. Harus: C0_LabilDatar=xgboost")
        cluster, model = item.split("=", 1)
        cluster = cluster.strip()
        model   = model.strip()
        if model not in MODEL_REGISTRY:
            raise ValueError(
                f"Model '{model}' tidak dikenal. "
                f"Pilihan: {list(MODEL_REGISTRY.keys())}"
            )
        result[cluster] = model
    return result
 
def main():
    parser = argparse.ArgumentParser(description="MarketCast Training Pipeline")
    parser.add_argument("--mode",
                        choices=["tournament", "specialize"],
                        default="tournament")
    parser.add_argument("--model",
                        choices=list(MODEL_REGISTRY.keys()) + ["all"],
                        default="all")
    parser.add_argument("--komoditas", default=None)
    parser.add_argument("--champion",
                        action="append",
                        metavar="CLUSTER=MODEL")
    parser.add_argument("--csv", default=None)
    args = parser.parse_args()
 
    cluster_map   = load_cluster_map()
    centroid_list = load_centroid_list()
 
    log.info(f"Mode        : {args.mode}")
    log.info(f"MLflow URI  : {MLFLOW_TRACKING_URI}")
    log.info(f"Cluster map : {sum(len(v) for v in cluster_map.values())} komoditas "
             f"dalam {len(cluster_map)} cluster")
    log.info(f"Centroid    : {centroid_list}")
 
    if args.mode == "tournament":
        models         = (list(MODEL_REGISTRY.keys())
                          if args.model == "all" else [args.model])
        komoditas_list = ([args.komoditas] if args.komoditas else centroid_list)
 
        df       = load_preprocessed()   # baca dari Neon DB via config DATABASE_URL
        all_data = load_all_series(df, komoditas_list, cluster_map)
 
        results = run_tournament(models, komoditas_list, all_data, cluster_map)
        if not results:
            log.error("Tidak ada run berhasil.")
            sys.exit(1)
 
    elif args.mode == "specialize":
        champion_map = parse_champion(args.champion)
        if not champion_map:
            log.info("--champion tidak diisi → auto-load dari MLflow Registry...")
            champion_map = load_champion_from_registry()
        if not champion_map:
            log.error(
                "Mode specialize butuh --champion. Contoh:\n"
                "  --champion C0_LabilDatar=sarima "
                "--champion C1_LabilInflasi=prophet "
                "--champion C2_StabilMahal=xgboost"
            )
            sys.exit(1)
 
        log.info(f"Champion map: {champion_map}")
 
        df            = load_preprocessed()   # baca dari Neon DB
        all_komoditas = df["komoditas"].unique().tolist()
        all_data      = load_all_series(df, all_komoditas, cluster_map)
 
        registry = run_specialize(champion_map, all_data, cluster_map)
        if not registry:
            log.error("Registry kosong — tidak ada model berhasil ditraining.")
            sys.exit(1)
 
if __name__ == "__main__":
    main()