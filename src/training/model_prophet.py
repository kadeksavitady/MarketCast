"""
src/training/model_prophet.py
==============================
Baseline 2: Prophet — Hybrid Expanding+Sliding CV
────────────────────────────────────────────────────────────
"""
import warnings
import logging
import numpy as np
import pandas as pd
import mlflow
import mlflow.prophet
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from typing import List, Dict, Optional, Tuple
 
from prophet import Prophet
 
from config import (
    FORECAST_DAYS, get_logger, compute_metrics,
    get_cluster_short, init_mlflow,
)
 
warnings.filterwarnings("ignore")
log = get_logger("prophet")
 
MODEL_NAME    = "Prophet"
TEST_WINDOW   = 30
MIN_TRAIN     = 1095    # 3 tahun
SPLIT_WEIGHTS = [0.10, 0.15, 0.20, 0.25, 0.30]
 
# Default changepoint_prior_scale per cluster
CLUSTER_CPS_DEFAULT = {
    "C0_LabilDatar"  : 0.30, # tren boleh berubah tajam (volatile, spike tinggi)
    "C1_LabilInflasi": 0.05, # tren smooth, inflasi konsisten (inflasi moderat) 
    "C2_StabilMahal" : 0.05, # tren sangat smooth (stabil, harga tinggi)
}

# Kalender hari besar Indonesia
# Dampak ke harga pangan terdokumentasi (BPS Jatim 2021-2025)
INDONESIAN_HOLIDAYS = pd.DataFrame({
    "holiday": [
        "Idul_Fitri", "Idul_Fitri", "Idul_Fitri", "Idul_Fitri", "Idul_Fitri",
        "Natal",      "Natal",      "Natal",      "Natal",      "Natal",
        "Tahun_Baru", "Tahun_Baru", "Tahun_Baru", "Tahun_Baru", "Tahun_Baru",
    ],
    "ds": pd.to_datetime([
        "2021-05-13", "2022-05-02", "2023-04-21", "2024-04-10", "2025-03-31",
        "2021-12-25", "2022-12-25", "2023-12-25", "2024-12-25", "2025-12-25",
        "2021-01-01", "2022-01-01", "2023-01-01", "2024-01-01", "2025-01-01",
    ]),
    "lower_window": [-7,-7,-7,-7,-7, -3,-3,-3,-3,-3, -3,-3,-3,-3,-3],
    "upper_window": [ 3, 3, 3, 3, 3,  1, 1, 1, 1, 1,  1, 1, 1, 1, 1],
})
 
# ══════════════════════════════════════════════════════════════
# 1. SPLIT GENERATOR — sama persis dengan model_sarima.py
#    agar CV scheme konsisten antar semua baseline model
# ══════════════════════════════════════════════════════════════
def build_splits(
    series: np.ndarray,
    dates: pd.DatetimeIndex,
    n_splits: int = 5,
    test_window: int = TEST_WINDOW,
    min_train: int = MIN_TRAIN,
) -> List[Dict]:
    n        = len(series)
    required = min_train + test_window * n_splits
 
    if n < required:
        log.warning(
            f"Data pendek ({n} hari < {required} required). "
            "Fallback ke 3 split proporsional."
        )
        n_splits    = 3
        min_train   = int(n * 0.60)
        test_window = min(30, int(n * 0.10))
        log.info(f"  Fallback: n_splits={n_splits}, min_train={min_train}, "
                 f"test_window={test_window}")
 
    expanding_splits = 3
    splits           = []
    train_start      = 0
 
    for i in range(1, n_splits + 1):
        if i <= expanding_splits:
            train_end  = min_train + (i - 1) * test_window
            test_start = train_end
            test_end   = test_start + test_window
            mode       = "expanding"
        else:
            slide_step  = i - expanding_splits
            train_end   = min_train + (expanding_splits - 1) * test_window \
                          + slide_step * test_window
            train_start = slide_step * test_window
            test_start  = train_end
            test_end    = test_start + test_window
            mode        = "sliding"
 
        if test_end > n:
            log.warning(f"Split {i}: test_end={test_end} > n={n}, skip.")
            break
 
        splits.append({
            "split_idx"        : i,
            "mode"             : mode,
            "train_start"      : train_start,
            "train_end"        : train_end,
            "test_start"       : test_start,
            "test_end"         : test_end,
            "n_train"          : train_end - train_start,
            "n_test"           : test_end - test_start,
            "date_train_start" : dates[train_start],
            "date_train_end"   : dates[train_end - 1],
            "date_test_start"  : dates[test_start],
            "date_test_end"    : dates[test_end - 1],
        })
 
        log.info(
            f"  Split {i} [{mode:9s}]: "
            f"train [{dates[train_start].date()} → {dates[train_end-1].date()}] "
            f"({train_end - train_start}d) | "
            f"test [{dates[test_start].date()} → {dates[test_end-1].date()}]"
        )
 
    return splits
 
 
# ══════════════════════════════════════════════════════════════
# 2. PROPHET FITTING HELPERS
# ══════════════════════════════════════════════════════════════
def _build_prophet_model(
    cps: float,
    sps: float,
    fourier_order: int = 5,
) -> Prophet:
    """
    Inisialisasi Prophet dengan parameter yang diberikan.
    Dipakai oleh fit_prophet() dan Optuna objective.
    """
    model = Prophet(
        yearly_seasonality      = True,
        weekly_seasonality      = True,
        daily_seasonality       = False,
        holidays                = INDONESIAN_HOLIDAYS,
        changepoint_prior_scale = cps,
        seasonality_prior_scale = sps,
        interval_width          = 0.95,
        uncertainty_samples     = 100,
    )
    model.add_seasonality(name="monthly", period=30.5,
                          fourier_order=fourier_order)
    return model

def fit_prophet_default(
    train: np.ndarray,
    dates_train: pd.DatetimeIndex,
    cluster: str,
    cps_override: Optional[float] = None,
    sps_override: Optional[float] = None,
) -> Tuple[Prophet, float, float, int]:
    """
    Fit Prophet dengan parameter default per cluster.

    Returns: (model, cps_used, sps_used, fourier_order_used)
    """
    cps = cps_override if cps_override is not None \
          else CLUSTER_CPS_DEFAULT.get(cluster, 0.05)
    sps = sps_override if sps_override is not None else 10.0
    fo  = 5
 
    df_train = pd.DataFrame({"ds": dates_train, "y": train})
    model    = _build_prophet_model(cps, sps, fo)
    model.fit(df_train)
    return model, cps, sps, fo
 
def fit_prophet_optuna(
    train: np.ndarray,
    dates_train: pd.DatetimeIndex,
    test: np.ndarray,
    dates_test: pd.DatetimeIndex,
    cluster: str,
    n_trials: int = 15,
    patience: int = 5,
) -> Tuple[Prophet, dict, float]:
    """
    Mode tunning memakai optuna

    Returns: (best_model, best_params, best_mape)
    """
    try:
        import optuna
        optuna.logging.set_verbosity(optuna.logging.WARNING)
    except ImportError:
        raise ImportError(
            "Optuna belum terinstall. Jalankan: pip install optuna\n"
            "Optuna dibutuhkan untuk mode=specialize Prophet."
        )
 
    df_train = pd.DataFrame({"ds": dates_train, "y": train})
    df_test  = pd.DataFrame({"ds": dates_test})
 
    best_mape        = float("inf")
    best_params      = {}
    no_improve_count = 0
 
    def objective(trial) -> float:
        nonlocal best_mape, no_improve_count
 
        # Early stopping manual (Optuna tidak punya callback di semua versi)
        if no_improve_count >= patience:
            raise optuna.exceptions.TrialPruned()
 
        cps = trial.suggest_float("changepoint_prior_scale",
                                   0.001, 0.5, log=True)
        sps = trial.suggest_float("seasonality_prior_scale",
                                   1.0, 50.0, log=True)
        fo  = trial.suggest_int("fourier_order_monthly", 3, 10)
 
        try:
            m = _build_prophet_model(cps, sps, fo)
            m.fit(df_train)
            pred    = m.predict(df_test)["yhat"].values
            metrics = compute_metrics(test, pred)
            mape    = metrics["mape"]
 
            if mape < best_mape:
                best_mape        = mape
                no_improve_count = 0
            else:
                no_improve_count += 1
 
            return mape
 
        except Exception:
            no_improve_count += 1
            return 999.0
 
    study = optuna.create_study(
        direction="minimize",
        sampler=optuna.samplers.TPESampler(seed=42),
    )
    study.optimize(objective, n_trials=n_trials, show_progress_bar=False)
 
    bp      = study.best_params
    best_cps = bp["changepoint_prior_scale"]
    best_sps = bp["seasonality_prior_scale"]
    best_fo  = bp["fourier_order_monthly"]
 
    log.info(f"  Optuna best: cps={best_cps:.4f} sps={best_sps:.2f} "
             f"fo={best_fo} MAPE={study.best_value:.2f}%  "
             f"(trials={len(study.trials)})")
 
    # Refit dengan best params
    best_model = _build_prophet_model(best_cps, best_sps, best_fo)
    best_model.fit(df_train)
 
    return best_model, {
        "changepoint_prior_scale": best_cps,
        "seasonality_prior_scale": best_sps,
        "fourier_order_monthly"  : best_fo,
        "optuna_best_mape"       : round(study.best_value, 4),
        "optuna_n_trials"        : len(study.trials),
    }, study.best_value
 
 
# ══════════════════════════════════════════════════════════════
# 3. EVALUASI PER SPLIT
# ══════════════════════════════════════════════════════════════
def evaluate_split_prophet(
    model: Prophet,
    dates_test: pd.DatetimeIndex,
    test: np.ndarray,
) -> Dict:
    """Forecast test window dan hitung metrics untuk satu split."""
    try:
        df_test  = pd.DataFrame({"ds": dates_test})
        pred_df  = model.predict(df_test)
        forecast = pred_df["yhat"].values
        ci_lower = pred_df["yhat_lower"].values
        ci_upper = pred_df["yhat_upper"].values
    except Exception as e:
        log.warning(f"  Forecast gagal ({e}), pakai last value.")
        last_val = float(model.history["y"].iloc[-1])
        forecast = np.full(len(test), last_val)
        ci_lower = forecast * 0.9
        ci_upper = forecast * 1.1
 
    metrics = compute_metrics(test, forecast)
    return {
        **metrics,
        "forecast" : forecast,
        "ci_lower" : ci_lower,
        "ci_upper" : ci_upper,
        "n_test"   : len(test),
    }
 
 
# ══════════════════════════════════════════════════════════════
# 4. MAIN TRAINING FUNCTION
# ══════════════════════════════════════════════════════════════
def train_prophet(
    komoditas: str,
    data: dict,
    mlflow_experiment: str = None,
    mode: str = "tournament",     # "tournament" | "specialize"
    changepoint_prior_scale: float = None,
    seasonality_prior_scale: float = None,
) -> dict:
    """
    Train Prophet dengan Hybrid Expanding+Sliding CV.
 
    mode="tournament":
        Fit Prophet dengan parameter default per cluster.
        5 split (atau fallback 3). Semua split di-log sebagai nested runs.
        Weighted MAPE sebagai metrik agregat untuk leaderboard.
 
    mode="specialize":
        Optuna tuning pada split terakhir (paling representatif).
        Best params dipakai untuk refit di semua split → weighted MAPE.
        Refit final di full series dengan best params.
 
    Parameters:
        changepoint_prior_scale : opsional override (untuk manual experiment)
        seasonality_prior_scale : opsional override (untuk manual experiment)
        mode                    : dikontrol dari train_all._call_model()
 
    Returns dict: model, metrics, forecast, run_id, model_uri, data
    """
    init_mlflow()
    mlflow.set_experiment(mlflow_experiment or "MarketCast-Tournament")
 
    series_full  = data["series_full"]
    dates_full   = data["dates_full"]
    cluster      = get_cluster_short(komoditas)
 
    if len(data.get("test", [])) == 0:
        raise ValueError(f"{komoditas}: test set kosong setelah split.")
 
    log.info(f"\n{'='*60}")
    log.info(f"[{MODEL_NAME}] {komoditas} | cluster={cluster} | mode={mode}")
    log.info(f"  Total data: {len(series_full)} hari "
             f"({dates_full[0].date()} → {dates_full[-1].date()})")
 
    # ── Build splits ──────────────────────────────────────────
    splits = build_splits(series_full, dates_full)
    if not splits:
        raise ValueError(f"{komoditas}: tidak ada split yang valid.")
 
    n_splits      = len(splits)
    split_weights = SPLIT_WEIGHTS[:n_splits]
    total_w       = sum(split_weights)
    split_weights = [w / total_w for w in split_weights]
 
    run_id    = ""
    model_uri = ""
 
    with mlflow.start_run(run_name=f"{MODEL_NAME}__{komoditas}") as parent_run:
 
        mlflow.set_tags({
            "model"     : MODEL_NAME,
            "komoditas" : komoditas,
            "cluster"   : cluster,
            "mode"      : mode,
            "project"   : "PBL-MarketCast",
            "cv_scheme" : "hybrid_expanding_sliding",
        })
 
        mlflow.log_params({
            "n_splits"     : n_splits,
            "test_window"  : TEST_WINDOW,
            "min_train"    : MIN_TRAIN,
            "mode"         : mode,
            "split_weights": str(split_weights),
        })
 
        # ── Optuna tuning pada split terakhir (mode=specialize) ──
        # Dilakukan SEBELUM loop split agar best_params dipakai
        # konsisten di semua split (bukan hanya split terakhir)
        # Resolve None ke nilai default cluster — agar log tidak tampil None
        best_cps    = changepoint_prior_scale or CLUSTER_CPS_DEFAULT.get(cluster, 0.05)
        best_sps    = seasonality_prior_scale or 10.0
        best_fo     = 5
        tune_params = {}
 
        if mode == "specialize":
            last_sp     = splits[-1]
            train_last  = series_full[last_sp["train_start"]:last_sp["train_end"]]
            test_last   = series_full[last_sp["test_start"]:last_sp["test_end"]]
            dates_tr    = dates_full[last_sp["train_start"]:last_sp["train_end"]]
            dates_te    = dates_full[last_sp["test_start"]:last_sp["test_end"]]
 
            log.info(f"\n  ── Optuna Tuning (split {last_sp['split_idx']}) ──")
 
            with mlflow.start_run(
                run_name="optuna_tuning",
                nested=True,
            ):
                _, tune_params, best_tune_mape = fit_prophet_optuna(
                    train_last, dates_tr, test_last, dates_te, cluster,
                    n_trials=15, patience=5,
                )
                best_cps = tune_params["changepoint_prior_scale"]
                best_sps = tune_params["seasonality_prior_scale"]
                best_fo  = tune_params["fourier_order_monthly"]
                mlflow.log_params(tune_params)
                mlflow.log_metric("tuning_best_mape", best_tune_mape)
 
            log.info(f"  Best params: cps={best_cps:.4f} sps={best_sps:.2f} "
                     f"fo={best_fo}")
 
        # ── Per-split training ────────────────────────────────
        split_results = []
 
        for sp in splits:
            i           = sp["split_idx"]
            train       = series_full[sp["train_start"]:sp["train_end"]]
            test        = series_full[sp["test_start"]:sp["test_end"]]
            dates_train = dates_full[sp["train_start"]:sp["train_end"]]
            dates_test  = dates_full[sp["test_start"]:sp["test_end"]]
 
            log.info(f"\n  ── Split {i}/{n_splits} [{sp['mode']}] "
                     f"n_train={sp['n_train']} ──")
 
            with mlflow.start_run(
                run_name=f"split_{i}_{sp['mode']}",
                nested=True,
            ):
                mlflow.log_params({
                    "split"      : i,
                    "mode"       : sp["mode"],
                    "n_train"    : sp["n_train"],
                    "n_test"     : sp["n_test"],
                    "train_start": str(sp["date_train_start"].date()),
                    "train_end"  : str(sp["date_train_end"].date()),
                    "test_start" : str(sp["date_test_start"].date()),
                    "test_end"   : str(sp["date_test_end"].date()),
                })
 
                # Fit dengan params terbaik (dari tuning atau default)
                model_split, cps_used, sps_used, fo_used = fit_prophet_default(
                    train, dates_train, cluster,
                    cps_override=best_cps,
                    sps_override=best_sps,
                )
 
                mlflow.log_params({
                    "changepoint_prior_scale": cps_used,
                    "seasonality_prior_scale": sps_used,
                    "fourier_order_monthly"  : fo_used,
                })
 
                metrics = evaluate_split_prophet(model_split, dates_test, test)
                mlflow.log_metrics({
                    f"split_{i}_mae"  : metrics["mae"],
                    f"split_{i}_rmse" : metrics["rmse"],
                    f"split_{i}_mape" : metrics["mape"],
                    f"split_{i}_smape": metrics["smape"],
                    f"split_{i}_mda": metrics["mda"]
                })
 
                log.info(
                    f"MAPE={metrics['mape']:>6.2f}% | "
                    f"RMSE={metrics['rmse']:>6.2f} | "
                    f"MDA: {metrics['mda']:>6.2f}"
                )
 
                split_results.append({
                    **metrics,
                    "split_idx"  : i,
                    "mode"       : sp["mode"],
                    "cps"        : cps_used,
                    "sps"        : sps_used,
                    "fo"         : fo_used,
                    "train"      : train,
                    "test"       : test,
                    "dates_train": dates_train,
                    "dates_test" : dates_test,
                    "model"      : model_split,
                })
 
        # ── Weighted MAPE agregat ─────────────────────────────────────────────
        wmape  = sum(w * r["mape"]  for w, r in zip(split_weights, split_results))
        wsmape = sum(w * r["smape"] for w, r in zip(split_weights, split_results))
        wmae   = sum(w * r["mae"]   for w, r in zip(split_weights, split_results))
        wrmse  = sum(w * r["rmse"]  for w, r in zip(split_weights, split_results))
        wmda   = sum(w * r["mda"]   for w, r in zip(split_weights, split_results))

        agg_metrics = {
            "wmape" : round(wmape,  4),
            "wsmape": round(wsmape, 4),
            "wmae"  : round(wmae,   2),
            "wrmse" : round(wrmse,  2),
            "wmda"  : round(wmda,   2),
            "mape"  : round(wmape,  4),   # alias untuk train_all.py leaderboard
            "smape" : round(wsmape, 4),
            "mae"   : round(wmae,   2),
            "rmse"  : round(wrmse,  2),
            "mda"   : round(wmda, 2)
        }
        mlflow.log_metrics(agg_metrics)
 
        log.info(f"\n  ── Agregat Weighted ──")
        log.info(f"  WMAPE={wmape:.2f}% | WSMAPE={wsmape:.2f}% | "
                 f" WMAE={wmae:,.0f} | WRMSE={wrmse:,.0f} | "
                 f"WMDA={wmda:.2f}")
 
        # ── Refit model final di full series ──────────────────
        log.info(f"\n  Refit final di full series ({len(series_full)} hari) "
                 f"cps={best_cps} sps={best_sps} fo={best_fo}")
 
        final_model, _, _, _ = fit_prophet_default(
            series_full, dates_full, cluster,
            cps_override=best_cps,
            sps_override=best_sps,
        )
 
        # ── Future forecast 30 hari ke depan ─────────────────
        last_date    = dates_full[-1]
        future_dates = pd.date_range(
            last_date + pd.Timedelta(days=1),
            periods=FORECAST_DAYS, freq="D",
        )
        future_pred = final_model.predict(pd.DataFrame({"ds": future_dates}))
 
        # ── Plot ──────────────────────────────────────────────
        fig = _plot_prophet_cv(
            komoditas, series_full, dates_full,
            split_results, future_pred, cluster,
        )
        safe_name = komoditas.replace(" ", "_").replace("/", "_")
        plot_path = f"/tmp/prophet_{safe_name}.png"
        fig.savefig(plot_path, dpi=120, bbox_inches="tight")
        plt.close(fig)
        mlflow.log_artifact(plot_path, artifact_path="plots")
 
        # Component plot (dekomposisi trend + seasonality)
        comp_df  = future_pred
        fig_comp = final_model.plot_components(comp_df)
        comp_path = f"/tmp/prophet_components_{safe_name}.png"
        fig_comp.savefig(comp_path, dpi=100, bbox_inches="tight")
        plt.close(fig_comp)
        mlflow.log_artifact(comp_path, artifact_path="plots")
        
        safe_name = komoditas.replace(" ", "_").replace("/", "_")
        mlflow.prophet.log_model(final_model, name=f"Prophet_{safe_name}")

        run_id    = parent_run.info.run_id
        model_uri = f"runs:/{run_id}/Prophet_{safe_name}"

        mlflow.log_params({
            "final_cps"           : best_cps,
            "final_sps"           : best_sps,
            "final_fourier_order" : best_fo,
        })
        if tune_params:
            mlflow.log_params({f"tuning_{k}": v for k, v in tune_params.items()})
 
    log.info(f"\n[{MODEL_NAME}] {komoditas} selesai. run_id={run_id[:8] if run_id else 'N/A'}...")
    
    return {
        "komoditas"      : komoditas,
        "model"          : final_model,
        "split_results"  : split_results,
        "metrics"        : agg_metrics,
        "future_pred"    : future_pred,
        "tune_params"    : tune_params,
        "run_id"         : run_id,
        "model_uri"      : model_uri,
        "data"           : data,
        "n_splits_used"  : n_splits,
    }
 
 
# ══════════════════════════════════════════════════════════════
# 5. PLOT
# ══════════════════════════════════════════════════════════════
def _plot_prophet_cv(
    komoditas, series_full, dates_full,
    split_results, future_pred, cluster,
):
    """
    Plot gabungan semua split CV + future forecast.
    Tiap split ditampilkan dengan warna berbeda.
    CI band dari Prophet (yhat_lower/upper) per split.
    """
    SPLIT_COLORS = ["#E74C3C", "#E67E22", "#F1C40F", "#27AE60", "#2980B9"]
    fig, ax = plt.subplots(figsize=(16, 6))
 
    # Aktual full series (90 hari terakhir)
    ax.plot(dates_full[-90:], series_full[-90:],
            color="#2C3E50", lw=1.5, label="Aktual", zorder=5)
 
    # Tiap split
    for i, r in enumerate(split_results):
        color = SPLIT_COLORS[i % len(SPLIT_COLORS)]
        ax.plot(r["dates_test"], r["forecast"],
                color=color, lw=1.8, linestyle="--",
                label=f"Split {r['split_idx']} [{r['mode']}] "
                      f"MAPE={r['mape']:.1f}%",
                alpha=0.85)
        ax.fill_between(r["dates_test"],
                        r["ci_lower"], r["ci_upper"],
                        color=color, alpha=0.08)
 
    # Future forecast
    ax.plot(future_pred["ds"].values, future_pred["yhat"].values,
            color="#8E44AD", lw=2.2, linestyle=":",
            label="Future 30d forecast")
    ax.fill_between(
        future_pred["ds"].values,
        future_pred["yhat_lower"].values,
        future_pred["yhat_upper"].values,
        color="#8E44AD", alpha=0.12,
    )
 
    ax.set_title(
        f"Prophet — {komoditas}  [cluster: {cluster}]\n"
        f"Hybrid Expanding+Sliding | {len(split_results)} splits",
        fontsize=12, fontweight="bold",
    )
    ax.set_xlabel("Tanggal")
    ax.set_ylabel("Harga/kg (Rp)")
    ax.yaxis.set_major_formatter(
        plt.FuncFormatter(lambda x, _: f"Rp{x:,.0f}")
    )
    ax.legend(fontsize=8, loc="upper left")
    ax.grid(alpha=0.2)
    plt.tight_layout()
    return fig