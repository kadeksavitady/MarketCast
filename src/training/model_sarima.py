"""
src/training/model_sarima.py
=============================
Baseline 1: SARIMA via auto_arima (pmdarima)
---------------------------------------------
Seasonality period (m=7):
    Dipilih 7 (mingguan) karena:
    1. Data siskaperbapo: harga bergerak dalam siklus mingguan
       (pasar tradisional ramai di hari tertentu)
    2. Periode bulanan (m=30) butuh jauh lebih banyak data untuk stabil
    3. m=52 (tahunan) bisa dicoba tapi butuh >3 tahun data penuh
    Kalau auto_arima tidak konvergen dengan m=7, fallback ke m=1 (ARIMA).
"""

import warnings
import itertools
import logging
import numpy as np
import pandas as pd
import mlflow
import mlflow.sklearn
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from pathlib import Path
from typing import List, Tuple, Dict, Optional
 
import pmdarima as pm
from pmdarima.arima import auto_arima, ARIMA
 
from config import (
    init_mlflow,
    FORECAST_DAYS,
    get_logger,
    compute_metrics,
    get_cluster_short,
)
 
warnings.filterwarnings("ignore")
log = get_logger("sarima")
 
MODEL_NAME   = "SARIMA"
TEST_WINDOW  = 30       # hari — sesuai tujuan prediksi
MIN_TRAIN    = 1095     # 3 tahun — minimum untuk 5 split penuh
SPLIT_WEIGHTS = [0.10, 0.15, 0.20, 0.25, 0.30]   # decay, total = 1.0
 
# ─── Prior Knowledge dari clustering ─────────────────────────────────────────
# Basis: karakteristik tiap cluster menentukan kompleksitas AR/MA yang wajar.
# C0 (volatile) → AR lebih tinggi untuk tangkap autokorelasi spike.
# C1 (inflasi moderat) → AR(1) cukup, tren linear.
# C2 (stabil) → MA(1) dominan, sedikit autokorelasi.
PRIOR_ORDER = {
    "C0_LabilDatar"  : (2, 1, 1),
    "C1_LabilInflasi": (1, 1, 1),
    "C2_StabilMahal" : (0, 1, 1),
}
 
# GridSearch space di sekitar prior (mode specialize)
PARAM_GRID = {
    "p": [0, 1, 2],
    "d": [1],          # fixed — harga hampir selalu butuh 1x differencing
    "q": [0, 1, 2],
    "P": [0, 1],
    "D": [0],          # fixed — seasonal differencing jarang perlu untuk m=7
    "Q": [0, 1],
    # m=7 fixed — mingguan
}   # Total: 3×1×3×2×1×2 = 36 kombinasi
 
 
# ═════════════════════════════════════════════════════════════════════════════
# 1. SPLIT GENERATOR — Hybrid Expanding + Sliding
# ═════════════════════════════════════════════════════════════════════════════
def build_splits(
    series: np.ndarray,
    dates: pd.DatetimeIndex,
    n_splits: int = 5,
    test_window: int = TEST_WINDOW,
    min_train: int = MIN_TRAIN,
) -> List[Dict]:
    n = len(series)
    required = min_train + test_window * n_splits
 
    # ── Fallback: data pendek ─────────────────────────────────────────────────
    if n < required:
        log.warning(
            f"Data pendek ({n} hari < {required} required). "
            f"Fallback ke 3 split proporsional."
        )
        n_splits   = 3
        min_train  = int(n * 0.60)
        test_window = min(30, int(n * 0.10))
        log.info(f"  Fallback: n_splits={n_splits}, min_train={min_train}, "
                 f"test_window={test_window}")
 
    # ── Expanding boundary ────────────────────────────────────────────────────
    expanding_splits = 3
    sliding_splits   = n_splits - expanding_splits
    splits       = []
    train_start  = 0
    for i in range(1, n_splits + 1):
        if i <= expanding_splits:
            # Expanding: train start tetap, train end gerak maju
            train_end   = min_train + (i - 1) * test_window
            test_start  = train_end
            test_end    = test_start + test_window
            mode        = "expanding"
        else:
            # Sliding: geser window
            slide_step  = (i - expanding_splits)
            train_end   = min_train + (expanding_splits - 1) * test_window \
                          + slide_step * test_window
            train_start = slide_step * test_window      # geser start
            test_start  = train_end
            test_end    = test_start + test_window
            mode        = "sliding"
 
        # Guard: jangan overflow
        if test_end > n:
            log.warning(f"Split {i}: test_end={test_end} > n={n}, skip.")
            break
 
        splits.append({
            "split_idx"  : i,
            "mode"       : mode,
            "train_start": train_start,
            "train_end"  : train_end,
            "test_start" : test_start,
            "test_end"   : test_end,
            "n_train"    : train_end - train_start,
            "n_test"     : test_end - test_start,
            "date_train_start": dates[train_start],
            "date_train_end"  : dates[train_end - 1],
            "date_test_start" : dates[test_start],
            "date_test_end"   : dates[test_end - 1],
        })
 
        log.info(
            f"  Split {i} [{mode:9s}]: "
            f"train [{dates[train_start].date()} → {dates[train_end-1].date()}] "
            f"({train_end - train_start}d) | "
            f"test [{dates[test_start].date()} → {dates[test_end-1].date()}]"
        )
 
    return splits
 
def compute_weighted_mape(split_metrics: List[Dict]) -> float:
    """
    Weighted MAPE dengan bobot decay [0.10, 0.15, 0.20, 0.25, 0.30].
    Split terbaru (index terbesar) mendapat bobot lebih besar.
    """
    n      = len(split_metrics)
    weights = SPLIT_WEIGHTS[:n]
    # Normalize kalau jumlah split < 5 (fallback)
    total_w = sum(weights)
    mapes   = [m["mape"] for m in split_metrics]
    wmape   = sum(w * m for w, m in zip(weights, mapes)) / total_w
    return round(wmape, 4)
 
 
# ═════════════════════════════════════════════════════════════════════════════
# 2. SARIMA FITTING HELPERS
# ═════════════════════════════════════════════════════════════════════════════
def fit_auto_arima(train: np.ndarray) -> Tuple[object, tuple, tuple]:
    """
    auto_arima untuk mode tournament.
    Fallback ke ARIMA(1,1,1) kalau tidak konvergen.
    """
    try:
        model = auto_arima(
            train,
            start_p=0, max_p=3,
            start_q=0, max_q=3,
            d=None,
            start_P=0, max_P=2,
            start_Q=0, max_Q=2,
            D=None,
            m=7,
            seasonal=True,
            information_criterion="aic",
            stepwise=True,
            suppress_warnings=True,
            error_action="ignore",
            trace=False,
        )
        return model, model.order, model.seasonal_order
    except Exception as e:
        log.warning(f"auto_arima gagal ({e}), fallback ke ARIMA(1,1,1)")
        model = ARIMA(order=(1, 1, 1))
        model.fit(train)
        return model, (1, 1, 1), (0, 0, 0, 0)
 
 
def fit_prior_with_gridsearch(
    train: np.ndarray,
    cluster: str,
) -> Tuple[object, tuple, tuple, float]:
    """
    Mode specialize: GridSearch 36 kombinasi di sekitar prior knowledge.
    """
    prior_pdq = PRIOR_ORDER.get(cluster, (1, 1, 1))
    log.info(f"  Prior order untuk {cluster}: {prior_pdq}")
 
    combinations = list(itertools.product(
        PARAM_GRID["p"],
        PARAM_GRID["d"],
        PARAM_GRID["q"],
        PARAM_GRID["P"],
        PARAM_GRID["D"],
        PARAM_GRID["Q"],
    ))
 
    best_model   = None
    best_order   = prior_pdq
    best_seas    = (0, 0, 0, 7)
    best_aic     = np.inf
    n_success    = 0
 
    for p, d, q, P, D, Q in combinations:
        try:
            model = ARIMA(order=(p, d, q), seasonal_order=(P, D, Q, 7))
            model.fit(train)
            aic = model.aic()
            n_success += 1
            if aic < best_aic:
                best_aic   = aic
                best_model = model
                best_order = (p, d, q)
                best_seas  = (P, D, Q, 7)
        except Exception:
            continue
 
    log.info(f"  GridSearch: {n_success}/{len(combinations)} berhasil | "
             f"Best: SARIMA{best_order}x{best_seas} AIC={best_aic:.2f}")
 
    # Fallback: pakai prior kalau semua gagal
    if best_model is None:
        log.warning("  GridSearch semua gagal, fallback ke prior order.")
        try:
            p, d, q = prior_pdq
            model = ARIMA(order=(p, d, q), seasonal_order=(0, 0, 0, 7))
            model.fit(train)
            best_model = model
            best_order = prior_pdq
            best_seas  = (0, 0, 0, 7)
            best_aic   = model.aic()
        except Exception as e:
            log.error(f"  Prior fallback juga gagal: {e}")
            raise
    return best_model, best_order, best_seas, best_aic
 

# ═════════════════════════════════════════════════════════════════════════════
# 3. EVALUASI PER SPLIT
# ═════════════════════════════════════════════════════════════════════════════
def evaluate_split(
    model,
    train: np.ndarray,
    test: np.ndarray,
) -> Dict:
    """Forecast test window dan hitung metrics untuk satu split."""
    try:
        forecast, conf_int = model.predict(
            n_periods=len(test),
            return_conf_int=True,
            alpha=0.05,
        )
    except Exception as e:
        log.warning(f"  Forecast gagal ({e}), pakai last value.")
        forecast  = np.full(len(test), train[-1])
        conf_int  = np.column_stack([forecast * 0.9, forecast * 1.1])
    metrics = compute_metrics(test, forecast)
    return {
        **metrics,
        "forecast" : forecast,
        "conf_int" : conf_int,
        "n_test"   : len(test),
    }
 
 
# ═════════════════════════════════════════════════════════════════════════════
# 4. MAIN TRAINING FUNCTION
# ═════════════════════════════════════════════════════════════════════════════
def train_sarima(
    komoditas: str,
    data: dict,
    mlflow_experiment: str = None,
    mode: str = "tournament",  # "tournament" | "specialize"
    tuned_params: dict = None,  
) -> dict:
    """
    mode="tournament":
        - auto_arima untuk pilih order
        - 5 split (atau fallback)
        - Log semua split sebagai nested runs
    mode="specialize":
        - GridSearch 36 kombinasi dengan prior knowledge
        - 5 split (atau fallback)
        - Log best order + tuning summary
    """
    init_mlflow()
    mlflow.set_experiment(mlflow_experiment or "MarketCast-Tournament")
 
    series_full  = data["series_full"]
    dates_full   = data["dates_full"]
    cluster      = data.get("cluster") or get_cluster_short(komoditas)
 
    log.info(f"\n{'='*60}")
    log.info(f"[{MODEL_NAME}] {komoditas} | cluster={cluster} | mode={mode}")
    log.info(f"  Total data: {len(series_full)} hari "
             f"({dates_full[0].date()} → {dates_full[-1].date()})")
 
    # ── Build splits ──────────────────────────────────────────────────────────
    splits = build_splits(series_full, dates_full)
    if not splits:
        raise ValueError(f"{komoditas}: tidak ada split yang valid.")
 
    # Sesuaikan SPLIT_WEIGHTS dengan jumlah split aktual
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
            "n_splits"    : n_splits,
            "test_window" : TEST_WINDOW,
            "min_train"   : MIN_TRAIN,
            "mode"        : mode,
            "seasonality" : 7,
            "split_weights": str(split_weights),
        })
 
        # ── Per-split training ────────────────────────────────────────────────
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
                    "split"       : i,
                    "mode"        : sp["mode"],
                    "n_train"     : sp["n_train"],
                    "n_test"      : sp["n_test"],
                    "train_start" : str(sp["date_train_start"].date()),
                    "train_end"   : str(sp["date_train_end"].date()),
                    "test_start"  : str(sp["date_test_start"].date()),
                    "test_end"    : str(sp["date_test_end"].date()),
                })
 
                # ── Fit model ─────────────────────────────────────────────────
                if mode == "tournament":
                    model, order, seas_order = fit_auto_arima(train)
                    best_aic = round(model.aic(), 4)
                else:   # specialize
                    if tuned_params is not None:
                        # ── JIKA ADA CONTEKAN, LANGSUNG PAKAI! ──
                        order = tuned_params["order"]
                        seas_order = tuned_params["seasonal_order"]
                        model = ARIMA(order=order, seasonal_order=seas_order)
                        model.fit(train)
                        best_aic = round(model.aic(), 4)
                        log.info("  Menggunakan Orde TUNED warisan dari Centroid!")
                    else:
                        # ── JIKA TIDAK ADA, CARI SENDIRI (Khusus Centroid) ──
                        model, order, seas_order, best_aic = \
                            fit_prior_with_gridsearch(train, cluster)
                log.info(f"  Order: SARIMA{order}x{seas_order} | AIC={best_aic:.2f}")
 
                mlflow.log_params({
                    "p": order[0], "d": order[1], "q": order[2],
                    "P": seas_order[0], "D": seas_order[1],
                    "Q": seas_order[2], "m": seas_order[3],
                    "aic": best_aic,
                })
 
                # ── Evaluate ──────────────────────────────────────────────────
                metrics = evaluate_split(model, train, test)
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
 
                # CI coverage per split
                ci_cov = compute_ci_coverage(test, metrics["conf_int"])
                mlflow.log_metric(f"split_{i}_ci_coverage", ci_cov)

                # Horizon error per split
                horizon_err = compute_horizon_error(model, train, test)
                mlflow.log_metrics({f"split_{i}_{k}": v
                                    for k, v in horizon_err.items()})

                split_results.append({
                    **metrics,
                    "split_idx"  : i,
                    "mode"       : sp["mode"],
                    "order"      : order,
                    "seas_order" : seas_order,
                    "aic"        : best_aic,
                    "ci_coverage": ci_cov,
                    "train"      : train,
                    "test"       : test,
                    "dates_train": dates_train,
                    "dates_test" : dates_test,
                    "model"      : model,
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
 
        # ── Refit model final di full series ──────────────────────────────────
        # Pakai order dari split terakhir (paling representatif data terkini)
        best_split  = split_results[-1]
        best_order  = best_split["order"]
        best_seas   = best_split["seas_order"]
 
        log.info(f"\n  Refit final: SARIMA{best_order}x{best_seas} "
                 f"pada full series ({len(series_full)} hari)")
 
        try:
            final_model = ARIMA(
                order=best_order,
                seasonal_order=best_seas,
            )
            final_model.fit(series_full)
        except Exception as e:
            log.warning(f"  Refit final gagal ({e}), pakai model split terakhir.")
            final_model = best_split["model"]
 
        # ── Future forecast 30 hari ke depan ─────────────────────────────────
        future_forecast, future_ci = final_model.predict(
            n_periods=FORECAST_DAYS,
            return_conf_int=True,
            alpha=0.05,
        )

        # ── Step 3: Diagnostik Residual ──────────────────────────────────────
        diag_metrics, diag_plots = compute_diagnostics(
            final_model, series_full, komoditas
        )
        if diag_metrics:
            mlflow.log_metrics(diag_metrics)
        for dp in diag_plots:
            mlflow.log_artifact(dp, artifact_path="diagnostics")

        # Weighted CI coverage
        wci_cov = sum(
            w * r.get("ci_coverage", 0.0)
            for w, r in zip(split_weights, split_results)
        )
        agg_metrics["ci_coverage"] = round(wci_cov, 2)
        mlflow.log_metric("ci_coverage_weighted", wci_cov)

        # ── Plot ──────────────────────────────────────────────────────────────
        fig = _plot_sarima_cv(
            komoditas, series_full, dates_full,
            split_results, future_forecast, future_ci, cluster,
        )
        plot_path = f"/tmp/sarima_{komoditas.replace(' ','_').replace('/','_')}.png"
        fig.savefig(plot_path, dpi=120, bbox_inches="tight")
        plt.close(fig)
        mlflow.log_artifact(plot_path, artifact_path="plots")
 
        # ── Log model ─────────────────────────────────────────────────────────
        # Retry logic untuk upload artifact ke DagHub (antisipasi timeout)
        import pickle, tempfile, os, time

        class SARIMAWrapper(mlflow.pyfunc.PythonModel):
            """Wrapper pmdarima → MLflow pyfunc agar bisa di-register."""
            def load_context(self, context):
                import pickle
                with open(context.artifacts["sarima_pkl"], "rb") as f:
                    self.model = pickle.load(f)

            def predict(self, context, model_input):
                import pandas as pd
                n = int(model_input["n_periods"].iloc[0])
                forecast, ci = self.model.predict(
                    n_periods=n, return_conf_int=True, alpha=0.05)
                return pd.DataFrame({
                    "forecast" : forecast,
                    "lower_ci" : ci[:, 0],
                    "upper_ci" : ci[:, 1],
                })

        safe_name = komoditas.replace(" ", "_").replace("/", "_")
        for attempt in range(3):
            try:
                with tempfile.TemporaryDirectory() as tmpdir:
                    pkl_path = os.path.join(tmpdir, "model.pkl")
                    with open(pkl_path, "wb") as f:
                        pickle.dump(final_model, f)
                    mlflow.pyfunc.log_model(
                        artifact_path=f"SARIMA_{safe_name}",
                        python_model=SARIMAWrapper(),
                        artifacts={"sarima_pkl": pkl_path},
                        pip_requirements=["pmdarima", "pandas", "numpy"],
                    )
                log.info(f"  Model artifact ter-upload (attempt {attempt+1})")
                break
            except Exception as e:
                if attempt < 2:
                    log.warning(f"  Upload gagal attempt {attempt+1}: {e} — retry 5 detik")
                    time.sleep(5)
                else:
                    log.error(f"  Upload gagal setelah 3 attempt: {e}")

        run_id    = parent_run.info.run_id
        model_uri = f"runs:/{run_id}/SARIMA_{safe_name}"
 
        mlflow.log_params({
            "final_order"      : str(best_order),
            "final_seas_order" : str(best_seas),
        })
 
    log.info(f"\n[{MODEL_NAME}] {komoditas} selesai. run_id={run_id[:8]}...")
 
    return {
        "komoditas"      : komoditas,
        "model"          : final_model,
        "order"          : best_order,
        "seasonal_order" : best_seas,
        "split_results"  : split_results,
        "metrics"        : agg_metrics,
        "future_forecast": future_forecast,
        "future_ci"      : future_ci,
        "run_id"         : run_id,
        "model_uri"      : model_uri,
        "data"           : data,
        "n_splits_used"  : n_splits,
        "tuned_params"   : {"order": best_order, "seasonal_order": best_seas},
    }
 
 
# ═════════════════════════════════════════════════════════════════════════════
# 5. STEP 3 — EVALUASI DIAGNOSTIK
# ═════════════════════════════════════════════════════════════════════════════
def compute_horizon_error(
    model, train: np.ndarray, test: np.ndarray
) -> dict:
    """
    Evaluasi error per horizon (1, 7, 14, 30 hari ke depan).
    Model di-fit pada train, lalu dievaluasi di tiap horizon.
    Menunjukkan apakah error membesar seiring horizon prediksi.
    """
    results = {}
    for h in [1, 7, 14, min(30, len(test))]:
        if h > len(test):
            continue
        try:
            pred = model.predict(n_periods=h)
            actual = test[:h]
            nonzero = actual != 0
            mape_h = float(np.mean(
                np.abs((actual[nonzero] - pred[nonzero]) / actual[nonzero])
            ) * 100) if nonzero.any() else 0.0
            results[f"horizon_{h}d_mape"] = round(mape_h, 4)
        except Exception:
            results[f"horizon_{h}d_mape"] = -1.0
    return results


def compute_diagnostics(
    model, train: np.ndarray, komoditas: str
) -> tuple:
    """
    Diagnostik residual:
    - Ljung-Box test (uji autokorelasi residual)
    - Plot ACF/PACF residual
    - Plot residual vs waktu

    Return: (metrics_dict, plot_paths_list)
    """
    import tempfile, os
    import matplotlib.pyplot as plt
    from statsmodels.stats.diagnostic import acorr_ljungbox
    from statsmodels.graphics.tsaplots import plot_acf, plot_pacf

    metrics  = {}
    plots    = []
    safe     = komoditas.replace(" ", "_").replace("/", "_")

    try:
        residuals = model.resid()
    except Exception:
        return metrics, plots

    # ── Ljung-Box test ────────────────────────────────────────
    try:
        lb = acorr_ljungbox(residuals, lags=[10, 20], return_df=True)
        metrics["ljungbox_lag10_pval"] = round(float(lb["lb_pvalue"].iloc[0]), 4)
        metrics["ljungbox_lag20_pval"] = round(float(lb["lb_pvalue"].iloc[1]), 4)
        # p > 0.05 → residual tidak ada autokorelasi → model fit baik
        metrics["ljungbox_pass"] = int(lb["lb_pvalue"].iloc[0] > 0.05)
    except Exception as e:
        log.warning(f"  Ljung-Box gagal: {e}")

    # ── Plot residual vs waktu ────────────────────────────────
    try:
        fig, ax = plt.subplots(figsize=(12, 3))
        ax.plot(residuals, color="#E74C3C", lw=0.8)
        ax.axhline(0, color="gray", linestyle="--", lw=0.8)
        ax.set_title(f"Residual vs Waktu — {komoditas}", fontsize=10)
        ax.set_ylabel("Residual (Rp)")
        plt.tight_layout()
        p = f"/tmp/sarima_resid_{safe}.png"
        fig.savefig(p, dpi=100)
        plt.close(fig)
        plots.append(p)
    except Exception:
        pass

    # ── ACF & PACF residual ───────────────────────────────────
    try:
        fig, axes = plt.subplots(1, 2, figsize=(12, 4))
        plot_acf(residuals,  ax=axes[0], lags=40, title=f"ACF Residual — {komoditas}")
        plot_pacf(residuals, ax=axes[1], lags=40, title=f"PACF Residual — {komoditas}")
        plt.tight_layout()
        p = f"/tmp/sarima_acf_{safe}.png"
        fig.savefig(p, dpi=100)
        plt.close(fig)
        plots.append(p)
    except Exception:
        pass

    return metrics, plots


def compute_ci_coverage(
    test: np.ndarray, conf_int: np.ndarray
) -> float:
    """
    Coverage interval prediksi 95%:
    Persentase nilai aktual yang jatuh dalam CI prediksi.
    Idealnya mendekati 95%.
    """
    lower, upper = conf_int[:, 0], conf_int[:, 1]
    covered = np.sum((test >= lower) & (test <= upper))
    return round(float(covered / len(test) * 100), 2)


# ═════════════════════════════════════════════════════════════════════════════
# 6. PLOT
# ═════════════════════════════════════════════════════════════════════════════
def _plot_sarima_cv(
    komoditas, series_full, dates_full,
    split_results, future_forecast, future_ci, cluster,
):
    """Plot gabungan semua split CV + future forecast."""
    SPLIT_COLORS = ["#E74C3C", "#E67E22", "#F1C40F", "#27AE60", "#2980B9"]
    fig, ax = plt.subplots(figsize=(16, 6))
 
    # Aktual full series (90 hari terakhir untuk readability)
    ax.plot(dates_full[-90:], series_full[-90:],
            color="#2C3E50", lw=1.5, label="Aktual", zorder=5)
    # Tiap split forecast
    for i, r in enumerate(split_results):
        color = SPLIT_COLORS[i % len(SPLIT_COLORS)]
        ax.plot(r["dates_test"], r["forecast"],
                color=color, lw=1.8, linestyle="--",
                label=f"Split {r['split_idx']} [{r['mode']}] "
                      f"MAPE={r['mape']:.1f}%",
                alpha=0.85)
        ax.fill_between(r["dates_test"],
                        r["conf_int"][:, 0], r["conf_int"][:, 1],
                        color=color, alpha=0.08)
    # Future forecast
    last_date    = dates_full[-1]
    future_dates = pd.date_range(
        last_date + pd.Timedelta(days=1),
        periods=len(future_forecast), freq="D",
    )
    ax.plot(future_dates, future_forecast,
            color="#8E44AD", lw=2.2, linestyle=":",
            label=f"Future 30d forecast")
    ax.fill_between(future_dates,
                    future_ci[:, 0], future_ci[:, 1],
                    color="#8E44AD", alpha=0.12)
    ax.set_title(
        f"SARIMA — {komoditas}  [cluster: {cluster}]\n"
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