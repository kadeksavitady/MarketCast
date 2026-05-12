"""
src/training/train_all.py
==========================
Orchestrator pipeline training PBL-MarketCast.

POSISI DALAM PIPELINE KESELURUHAN:
    ← Input : outputs/clustering/data_preprocessed.csv   (Tahap 0)
              outputs/clustering/cluster_assignments.csv  (Tahap 0)
              outputs/clustering/centroid_representatives.csv (Tahap 0)
    → Output: MLflow runs (Tahap 2 & 3a)
              outputs/registry/model_registry_map.yaml   (→ Tahap 3b)

DUA MODE EKSEKUSI:
    --mode tournament  (Tahap 2)
        3 centroid × 3 model = 9 runs
        Experiment: MarketCast-Tournament
        Hasilnya: leaderboard → pilih 1 juara per cluster

    --mode specialize  (Tahap 3a)
        30 komoditas non-centroid × model juara cluster masing-masing
        Experiment: MarketCast-Specialization
        Hasilnya: model_registry_map.yaml → dipakai FastAPI & business logic

CARA PAKAI:
    # Tahap 2 — turnamen baseline (jalankan dari root repo)
    python src/training/train_all.py --mode tournament

    # Tahap 3a — setelah pilih juara di MLflow UI
    python src/training/train_all.py --mode specialize \
        --champion C0_LabilDatar=xgboost \
        --champion C1_LabilInflasi=sarima \
        --champion C2_StabilMahal=prophet

    # Satu komoditas / satu model (debugging)
    python src/training/train_all.py --mode tournament \
        --model prophet --komoditas "Telur Ayam Ras"
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
    YAML_MODEL_REGISTRY, DIR_REGISTRY, CSV_PREPROCESSED,
    load_cluster_map, load_centroid_list,
    CLUSTER_SHORT_TO_FULL, get_logger,
)
from data_loader import load_preprocessed, load_all_series
from model_sarima   import train_sarima
from model_prophet  import train_prophet
from model_xgboost  import train_xgboost
import dagshub
# Ini akan otomatis mengatur autentikasi MLflow ke repo temanmu
dagshub.init(repo_owner='kadeksavitady', repo_name='MarketCast', mlflow=True)

log = get_logger("train_all")

MODEL_REGISTRY = {
    "sarima"  : train_sarima,
    "prophet" : train_prophet,
    "xgboost" : train_xgboost,
}


# ══════════════════════════════════════════════════════════════
# TAHAP 2 — TURNAMEN BASELINE
# ══════════════════════════════════════════════════════════════

def run_tournament(models: list, komoditas_list: list,
                   all_data: dict, cluster_map: dict) -> list:
    """
    3 centroid × 3 model = 9 runs.
    MLflow experiment: MarketCast-Tournament
    """
    import mlflow
    mlflow.set_tracking_uri(MLFLOW_TRACKING_URI)

    results  = []
    n_total  = len(models) * len(komoditas_list)
    n_done   = 0
    n_failed = 0

    log.info("=" * 65)
    log.info("  TAHAP 2 — TURNAMEN BASELINE MODEL")
    log.info(f"  {len(models)} model × {len(komoditas_list)} centroid = {n_total} runs")
    log.info(f"  Experiment: {MLFLOW_EXP_TOURNAMENT}")
    log.info(f"  MLflow   : {MLFLOW_TRACKING_URI}")
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
                result = MODEL_REGISTRY[model_name](
                    komoditas, data,
                    mlflow_experiment=MLFLOW_EXP_TOURNAMENT
                )
                result["model_name"] = model_name
                results.append(result)
                m = result["metrics"]
                log.info(
                    f"  ✓ MAE={m['mae']:>10,.0f}  "
                    f"MAPE={m['mape']:>6.2f}%  "
                    f"SMAPE={m['smape']:>6.2f}%"
                )
            except Exception as e:
                n_failed += 1
                log.error(f"  ✗ GAGAL: {e}")
                log.debug(traceback.format_exc())

    _print_tournament_leaderboard(results)
    log.info(f"\n✓ Tournament: {len(results)}/{n_total} runs | {n_failed} gagal")
    log.info(f"  → Buka MLflow UI: {MLFLOW_TRACKING_URI}")
    log.info(f"  → Pilih juara per cluster, lalu jalankan --mode specialize")
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
    log.info(f"\n{best[['cluster','model','mape','smape']].to_string(index=False)}")


# ══════════════════════════════════════════════════════════════
# TAHAP 3a — SPESIALISASI
# ══════════════════════════════════════════════════════════════

def run_specialize(champion_map: dict, all_data: dict,
                   cluster_map: dict) -> dict:
    """
    Training semua komoditas non-centroid dengan model juara
    cluster masing-masing.

    champion_map: {cluster_short: model_name}
        Contoh: {"C0_LabilDatar": "xgboost",
                 "C1_LabilInflasi": "sarima",
                 "C2_StabilMahal": "prophet"}
    """
    import mlflow
    mlflow.set_tracking_uri(MLFLOW_TRACKING_URI)

    centroid_list   = load_centroid_list()
    all_komoditas   = list(all_data.keys())
    specialize_list = [k for k in all_komoditas if k not in centroid_list]

    log.info("=" * 65)
    log.info("  TAHAP 3a — SPESIALISASI")
    log.info(f"  {len(specialize_list)} komoditas non-centroid")
    log.info(f"  Champion map: {champion_map}")
    log.info(f"  Experiment: {MLFLOW_EXP_SPECIALIZE}")
    log.info("=" * 65)

    registry  = {}
    n_done    = 0
    n_failed  = 0
    n_total   = len(specialize_list)

    for komoditas in specialize_list:
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
                f"'{cluster_short}'. Pastikan --champion sudah diisi semua."
            )
            n_failed += 1
            continue

        n_done += 1
        log.info(f"[{n_done}/{n_total}] {model_name.upper()} × {komoditas} [{cluster_short}]")

        try:
            result = MODEL_REGISTRY[model_name](
                komoditas, data,
                mlflow_experiment=MLFLOW_EXP_SPECIALIZE
            )
            registry[komoditas] = {
                "cluster"      : cluster_short,
                "model"        : model_name,
                "mlflow_run_id": result.get("run_id", ""),
                "model_uri"    : result.get("model_uri", ""),
                "mape"         : result["metrics"]["mape"],
                "mae"          : result["metrics"]["mae"],
            }
            log.info(f"  ✓ MAPE={result['metrics']['mape']:.2f}%")

        except Exception as e:
            n_failed += 1
            log.error(f"  ✗ GAGAL: {e}")
            log.debug(traceback.format_exc())

    # Tambahkan centroid ke registry juga
    for komoditas in centroid_list:
        data = all_data.get(komoditas)
        if data:
            cluster_short = data["cluster"]
            model_name    = champion_map.get(cluster_short, "unknown")
            registry[komoditas] = {
                "cluster"      : cluster_short,
                "model"        : model_name,
                "mlflow_run_id": "",
                "model_uri"    : "",
                "mape"         : None,
                "mae"          : None,
                "note"         : "centroid — run_id dari Tournament experiment",
            }

    _save_registry(registry)
    log.info(f"\n✓ Spesialisasi: {n_done}/{n_total} berhasil | {n_failed} gagal")
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
    with open(YAML_MODEL_REGISTRY, "w", encoding="utf-8") as f:
        yaml.dump(output, f, allow_unicode=True, sort_keys=False, indent=2)
    log.info(f"Registry disimpan: {YAML_MODEL_REGISTRY}")
    log.info(f"Total komoditas terdaftar: {len(registry)}")


# ══════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════

def parse_champion(champion_args: list) -> dict:
    if not champion_args:
        return {}
    result = {}
    for item in champion_args:
        if "=" not in item:
            raise ValueError(
                f"Format --champion salah: '{item}'. "
                "Harus: --champion C0_LabilDatar=xgboost"
            )
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
    parser = argparse.ArgumentParser(
        description="MarketCast Training Pipeline",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
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

    # ── Resolve path CSV — selalu dari root repo ──────────────
    csv_path    = CSV_PREPROCESSED
    cluster_map = load_cluster_map()
    centroid_list = load_centroid_list()

    log.info(f"Mode        : {args.mode}")
    log.info(f"MLflow URI  : {MLFLOW_TRACKING_URI}")
    log.info(f"Cluster map : {sum(len(v) for v in cluster_map.values())} komoditas "
             f"dalam {len(cluster_map)} cluster")
    log.info(f"Centroid    : {centroid_list}")

    if args.mode == "tournament":
        models         = (list(MODEL_REGISTRY.keys())
                          if args.model == "all" else [args.model])
        komoditas_list = ([args.komoditas] if args.komoditas
                          else centroid_list)

        df       = load_preprocessed(csv_path)
        # FIX: panggil load_all_series langsung, bukan via __import__
        all_data = load_all_series(df, komoditas_list, cluster_map)

        results = run_tournament(models, komoditas_list, all_data, cluster_map)

        if not results:
            log.error("Tidak ada run berhasil.")
            sys.exit(1)

    elif args.mode == "specialize":
        champion_map = parse_champion(args.champion)
        if not champion_map:
            log.error(
                "Mode specialize butuh --champion. Contoh:\n"
                "  --champion C0_LabilDatar=xgboost "
                "--champion C1_LabilInflasi=sarima "
                "--champion C2_StabilMahal=prophet"
            )
            sys.exit(1)

        log.info(f"Champion map: {champion_map}")

        df            = load_preprocessed(csv_path)
        all_komoditas = df["komoditas"].unique().tolist()
        # FIX: panggil load_all_series langsung, bukan via __import__
        all_data      = load_all_series(df, all_komoditas, cluster_map)

        registry = run_specialize(champion_map, all_data, cluster_map)

        if not registry:
            log.error("Registry kosong — tidak ada model berhasil ditraining.")
            sys.exit(1)


if __name__ == "__main__":
    main()
