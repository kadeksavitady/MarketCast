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
        Fase 2.5: Validasi Tuning pada Centroid (Default vs Tuned) [CHAMPION vs CHALLENGER]
        Fase 3.0: SEMUA komoditas di-training menggunakan mode pemenang 
                  dari Fase 2.5 (mencegah degradasi performa/overfitting).
        Experiment: MarketCast-Specialization
        Output: model_registry_map.yaml → dipakai FastAPI & business logic

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
    YAML_MODEL_REGISTRY,
    load_cluster_map, load_centroid_list,
    get_logger,
)

# DIR_REGISTRY didefinisikan lokal — tidak perlu dari config
DIR_REGISTRY = YAML_MODEL_REGISTRY.parent
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
# HELPER: Pendaftaran Model ke MLflow Registry
# ══════════════════════════════════════════════════════════════
def _register_to_mlflow_registry(model_uri: str, reg_name: str, alias_name: str, client) -> tuple:
    """
    Register model ke MLflow Model Registry.
    Pakai create_registered_model + create_model_version (API lama)
    karena DagHub tidak support MLflow 3.x logged-models API.
    """
    import mlflow
    log.info(f"  Mendaftarkan ke DagsHub Registry sebagai '{reg_name}@{alias_name}'...")
    
    # 1. Pastikan registered model sudah ada (buat kalau belum)
    try:
        client.create_registered_model(reg_name)
        log.info(f"  Registered model '{reg_name}' dibuat baru.")
    except Exception:
        log.info(f"  Registered model '{reg_name}' sudah ada, skip create.")
    
    # 2. Buat versi baru langsung dari source artifact yang sesuai dengan source dalam format DagsHub
    run_id        = model_uri.split("/")[1]
    artifact_path = "/".join(model_uri.split("/")[2:])
    run_info   = client.get_run(run_id)
    artifact_uri = run_info.info.artifact_uri
    source       = f"{artifact_uri}/{artifact_path}"
    
    mv = client.create_model_version(
        name   = reg_name,
        source = source,
        run_id = run_id,
    )
    log.info(f"  Model version {mv.version} dibuat dari source: {source}")
    
    # 3. Set alias
    if alias_name:
        client.set_registered_model_alias(
            name    = reg_name,
            alias   = alias_name,
            version = mv.version,
        )
        log.info(f"  ✓ Alias @{alias_name} di-set ke version {mv.version}")
    return reg_name, mv.version

# ══════════════════════════════════════════════════════════════
# HELPER: Pemanggilan Model dengan Arsitektur Unified Interface
# ══════════════════════════════════════════════════════════════
def _call_model(model_name: str, komoditas: str, data: dict,
                mlflow_experiment: str, training_mode: str, 
                tuned_params: dict = None) -> dict:
    """
    Wrapper pemanggilan model yang meneruskan training_mode.
    """
    fn = MODEL_REGISTRY[model_name]
    kwargs = {"mlflow_experiment": mlflow_experiment}

    if model_name in ["sarima", "xgboost"]:
        kwargs["mode"] = training_mode

    if model_name == "sarima":
        return fn(komoditas, data,
                  mlflow_experiment=mlflow_experiment,
                  mode=training_mode)
    
    if tuned_params and model_name == "xgboost":
        kwargs["tuned_params"] = tuned_params

    else:
        # Prophet & XGBoost: tidak ada parameter mode
        return fn(komoditas, data, **kwargs)

def _select_champion_ranksum(df_res: pd.DataFrame) -> pd.DataFrame:
    """
    Rank-Sum Method untuk memilih champion per cluster.
    """
    results = []
    for cluster, group in df_res.groupby("cluster"):
        g = group.copy()  
        # Rank per metrik (method='min' = ties dapat rank sama)
        g["rank_mape"] = g["metric_mape"].rank(ascending=True,  method="min")
        g["rank_mda"]  = g["metric_mda"].rank( ascending=False, method="min")
        g["rank_rmse"] = g["metric_rmse"].rank(ascending=True,  method="min")
        # Total rank — semakin kecil semakin baik
        g["rank_total"] = g["rank_mape"] + g["rank_mda"] + g["rank_rmse"]
        results.append(g)   
    return pd.concat(results)
 
# ══════════════════════════════════════════════════════════════
# HELPER: Evaluasi Komposit Hibrida (Validasi Tuning)
# ══════════════════════════════════════════════════════════════
def _calculate_hybrid_score(metrics: dict) -> float:
    """
    Menghitung skor gabungan MAPE dan MDA. SEMAKIN TINGGI SEMAKIN BAIK.
    Formula: Skor = (0.60 * Akurasi_Nominal) + (0.40 * MDA)
    """
    mape = metrics.get("mape", 100)
    mda = metrics.get("mda", 0.0)
    akurasi_nominal = max(0, 100 - mape)
    return (0.60 * akurasi_nominal) + (0.40 * mda)

# ══════════════════════════════════════════════════════════════
# TAHAP 2 — training_mode="tournament"
# ══════════════════════════════════════════════════════════════
def run_tournament(models: list, komoditas_list: list,
                   all_data: dict, cluster_map: dict) -> list:
    """ 3 centroid × 3 model = 9 runs """
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
                    f"  ✓ MAPE={m['mape']:>6.2f}%  "
                    f"MDA={m.get('mda', 0):>6.2f}%  "
                    f"RMSE={m['rmse']:>8,.0f}  "
                    f"MAE={m['mae']:>8,.0f}"
                )
            except Exception as e:
                n_failed += 1
                log.error(f"  ✗ GAGAL: {e}")
                log.debug(traceback.format_exc())
 
    _print_tournament_leaderboard(results)
    
    # ══════════════════════════════════════════════════════════════
    # LOGIKA AUTO-REGISTRY — SEMUA MODEL + @champion untuk juara
    # ══════════════════════════════════════════════════════════════
    from mlflow.tracking import MlflowClient
    client = MlflowClient()

    log.info(f"\n  ── AUTO-REGISTER SEMUA MODEL + CHAMPION ──")
    df_res = pd.DataFrame([
        {
            "cluster"    : r["data"]["cluster"],
            "model_name" : r["model_name"],
            "model_uri"  : r.get("model_uri", ""),
            "metric_mape": r["metrics"]["mape"],
            "metric_mda" : r["metrics"].get("mda", 0.0),
            "metric_rmse": r["metrics"]["rmse"],
        } for r in results
    ])
    if "model_uri" in df_res.columns:
        df_res = df_res[df_res["model_uri"].str.len() > 0]

    if df_res.empty:
        log.error("Semua model_uri kosong — tidak ada yang bisa diregister.")
    else:
        df_ranked_list = []
        for cluster, group in df_res.groupby("cluster"):
            g = group.copy()
            g["rank_mape"] = g["metric_mape"].rank(ascending=True,  method="min")
            g["rank_mda"]  = g["metric_mda"].rank( ascending=False, method="min")
            g["rank_rmse"] = g["metric_rmse"].rank(ascending=True,  method="min")
            g["rank_total"] = g["rank_mape"] + g["rank_mda"] + g["rank_rmse"]
            df_ranked_list.append(g)
        df_ranked = pd.concat(df_ranked_list)

        # Log rank-sum leaderboard per cluster
        log.info("\n  ── RANK-SUM LEADERBOARD ──")
        for cluster, group in df_ranked.groupby("cluster"):
            group_sorted = group.sort_values("rank_total")
            min_rank     = group_sorted["rank_total"].min()
            log.info(f"\n  {cluster}:")
            for _, row in group_sorted.iterrows():
                log.info(
                    f"    {row['model_name'].upper():10s} | "
                    f"MAPE={row['metric_mape']:6.2f}% (r{int(row['rank_mape'])}) | "
                    f"MDA={row['metric_mda']:5.1f}% (r{int(row['rank_mda'])}) | "
                    f"RMSE={row['metric_rmse']:8.0f} (r{int(row['rank_rmse'])}) | "
                    f"Total={int(row['rank_total'])}"
                    + (" ← @champion" if row["rank_total"] == min_rank else "")
                )

        # Tentukan champion per cluster (rank_total terkecil)
        best_idx = df_ranked.groupby("cluster")["rank_total"].idxmin()

        # Mapping cluster string → nama registry
        def cluster_to_reg_name(cluster_str: str) -> str:
            import re
            # Coba parse format C{N}_... → "cluster N+1"
            m = re.match(r"C(\d+)_?", cluster_str)
            if m:
                num = int(m.group(1))
                return f"cluster {num + 1}"
            # Fallback: cari angka pertama di string
            m = re.search(r"\d+", cluster_str)
            if m:
                return f"cluster {int(m.group())+1}"
            return cluster_str

        # Register SEMUA model — juara dapat @champion, lainnya tidak
        for idx, row in df_ranked.iterrows():
            cluster_str = row["cluster"]
            model_name  = row["model_name"]
            model_uri   = row["model_uri"]
            is_champion = idx in best_idx.values

            reg_name = cluster_to_reg_name(cluster_str)
            alias    = "champion" if is_champion else None

            log.info(
                f"  Register: {model_name.upper()} → '{reg_name}' "
                f"(rank_total={int(row['rank_total'])} | "
                f"MAPE={row['metric_mape']:.2f}% | "
                f"MDA={row['metric_mda']:.1f}% | "
                f"RMSE={row['metric_rmse']:.0f})"
                + (" ← @champion" if is_champion else "")
            )

            try:
                reg_n, version = _register_to_mlflow_registry(
                    model_uri  = model_uri,
                    reg_name   = reg_name,
                    alias_name = alias,
                    client     = client,
                )
                log.info(
                    f"  ✓ Registry: {reg_n} v{version}"
                    + (f" @champion" if alias else "")
                )
            except Exception as e:
                log.error(f"  ✗ Gagal register {model_name} ke {reg_name}: {e}")
        
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
    log.info("  LEADERBOARD TURNAMEN (sorted per cluster)")
    log.info("=" * 65)
    log.info(f"\n{lb.to_string(index=False)}")
    log.info("\n── Best model per cluster ────────────────────────────────")
    best = lb.loc[lb.groupby("cluster")["mape"].idxmin()]
    cols = [c for c in ['cluster','model','mape','mda','rmse','mae'] if c in best.columns]
    log.info(f"\n{best[cols].to_string(index=False)}")
 
 
# ══════════════════════════════════════════════════════════════
# TAHAP 3a — training_mode="specialize"
# ══════════════════════════════════════════════════════════════
def run_specialize(champion_map: dict, all_data: dict,
                   cluster_map: dict) -> dict:
    """
    Training SEMUA komoditas (centroid + non-centroid) dengan model champion.
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
    log.info(f"  Champion map: {champion_map}")
    log.info(f"  Experiment  : {MLFLOW_EXP_SPECIALIZE}")
    log.info("=" * 65)

    # ──────────────────────────────────────────────────────────────
    # FASE 2.5: ARENA VALIDASI (Mengadu Default vs Tuned pada Centroid)
    # ──────────────────────────────────────────────────────────────
    log.info("\n  ── FASE 2.5: ARENA VALIDASI (DEFAULT vs TUNED) ──")
    cluster_best_mode = {}
    
    for cluster_short, model_name in champion_map.items():
        # Cari nama komoditas centroid untuk klaster ini
        centroid_name = [k for k, v in all_data.items() if v["cluster"] == cluster_short and k in centroid_list]
        if not centroid_name:
            cluster_best_mode[cluster_short] = "specialize" # Fallback
            continue
            
        centroid_name = centroid_name[0]
        data_centroid = all_data[centroid_name]

        log.info(f"\n  > Validasi Klaster {cluster_short} ({model_name.upper()} pada {centroid_name})")
        
        try:
            # 1. Jalankan mode Default (Champion)
            res_def = _call_model(model_name, centroid_name, data_centroid, MLFLOW_EXP_SPECIALIZE, "tournament")
            score_def = _calculate_hybrid_score(res_def["metrics"])
            
            # 2. Jalankan mode Tuned (Challenger)
            res_tun = _call_model(model_name, centroid_name, data_centroid, MLFLOW_EXP_SPECIALIZE, "specialize")
            score_tun = _calculate_hybrid_score(res_tun["metrics"])
            
            log.info(f"    - Skor Default : {score_def:.2f} (MAPE: {res_def['metrics']['mape']:.2f}%, MDA: {res_def['metrics'].get('mda',0):.1f}%)")
            log.info(f"    - Skor Tuned   : {score_tun:.2f} (MAPE: {res_tun['metrics']['mape']:.2f}%, MDA: {res_tun['metrics'].get('mda',0):.1f}%)")
            
            # 3. Pengambilan Keputusan (Skor lebih tinggi = lebih baik)
            if score_tun > score_def:
                log.info(f"    ✓ TUNED MENANG! Klaster {cluster_short} akan dilatih menggunakan Hyperparameter Tuning.")
                cluster_best_mode[cluster_short] = "specialize"
            else:
                log.info(f"    ✗ DEFAULT LEBIH BAIK/SERI. Klaster {cluster_short} akan dikunci pada parameter Default (mencegah overfitting).")
                cluster_best_mode[cluster_short] = "tournament"
                
        except Exception as e:
            log.error(f"    ✗ Validasi gagal ({e}), fallback ke mode specialize.")
            cluster_best_mode[cluster_short] = "specialize"

    log.info("\n  ── FASE 3.0: EKSEKUSI KOMODITAS KESELURUHAN ──")
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
        applied_mode  = cluster_best_mode.get(cluster_short, "specialize")

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
        mode_label = "[TUNED]" if applied_mode == "specialize" else "[DEFAULT]"
        log.info(f"[{n_done}/{n_total}] {model_name.upper()} × {komoditas} "
                 f"[{cluster_short}] {label}")
 
        try:
            # training_mode="specialize" diteruskan ke model
            result = _call_model(
                model_name, komoditas, data,
                mlflow_experiment=MLFLOW_EXP_SPECIALIZE,
                training_mode=applied_mode,
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
            log.info(f"  ✓ MAPE={result['metrics']['mape']:.2f}%  uri={model_uri} | Registry: {reg_name}@production (v{mv_version})")
 
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
    log.info(f"  SPESIALISASI SELESAI ")
    log.info(f"  Berhasil : {len(registry)}/{n_total}")
    log.info(f"  Gagal    : {n_failed}")
    log.info(f"  Coverage : {len([k for k, v in registry.items() if v.get('model_uri')])} "
             f"komoditas punya model_uri valid")
    log.info(f"  Registry : {YAML_MODEL_REGISTRY}")
    log.info(f"{'='*65}")
    return registry

def _save_registry(registry: dict):
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
        import mlflow, tempfile, os
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
        result[cluster.strip()] = model.strip()
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
                "Mode specialize butuh mapping champion dari tournament!"
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