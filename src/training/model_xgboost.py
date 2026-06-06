"""
src/training/model_xgboost.py
==============================
  Weighted MAPE decay: [0.10, 0.15, 0.20, 0.25, 0.30]

DUA MODE:
  tournament  → hyperparameter default (konservatif untuk data ~1800 rows)
  specialize  → RandomizedSearch n_iter=30 pada 5-fold CV split
                search space identik dengan Optuna untuk perbandingan fair

FALLBACK DATA PENDEK (< 1095 hari):
  Turunkan ke 3 split proporsional terhadap panjang data aktual.
  Min train = 60% total data, test window = 30 hari.
"""

import warnings
import numpy as np
import pandas as pd
import mlflow
import mlflow.xgboost
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from xgboost import XGBRegressor
from sklearn.model_selection import RandomizedSearchCV, TimeSeriesSplit
from scipy.stats import randint, uniform, loguniform
from typing import List, Dict, Tuple

from config import (
    init_mlflow,
    FORECAST_DAYS,
    get_logger,
    compute_metrics,
    get_cluster_short,
)

warnings.filterwarnings("ignore")
log = get_logger("xgboost")

MODEL_NAME    = "XGBoost"
LAG_MAX       = 30
TEST_WINDOW   = 30
MIN_TRAIN     = 1095
SPLIT_WEIGHTS = [0.10, 0.15, 0.20, 0.25, 0.30]

# RandomizedSearch space — identik dengan Optuna untuk perbandingan fair
RANDOM_SEARCH_SPACE = {
    "n_estimators"      : randint(100, 601),
    "learning_rate"     : loguniform(0.01, 0.3),
    "max_depth"         : randint(3, 8),
    "subsample"         : uniform(0.6, 0.4),       # 0.6 → 1.0
    "colsample_bytree"  : uniform(0.6, 0.4),       # 0.6 → 1.0
    "min_child_weight"  : randint(1, 11),
    "reg_alpha"         : loguniform(1e-8, 1.0),
    "reg_lambda"        : loguniform(1e-8, 10.0),
}


# ═════════════════════════════════════════════════════════════════════════════
# 1. FEATURE ENGINEERING
# ═════════════════════════════════════════════════════════════════════════════
def build_features(series: np.ndarray, dates: pd.DatetimeIndex) -> pd.DataFrame:
    """
    Bangun feature matrix dari time series harga.
    """
    df = pd.DataFrame({"harga": series}, index=dates)
    # fitur yang dipakai
    for lag in range(1, LAG_MAX + 1):
        df[f"lag_{lag}"] = df["harga"].shift(lag)
    df["rolling_mean_7"]  = df["harga"].shift(1).rolling(7).mean()
    df["rolling_mean_30"] = df["harga"].shift(1).rolling(30).mean()
    df["rolling_std_7"]   = df["harga"].shift(1).rolling(7).std()
    df["rolling_std_30"]  = df["harga"].shift(1).rolling(30).std()
    df["month"]            = df.index.month
    df["dayofweek"]        = df.index.dayofweek
    df["days_since_start"] = (df.index - df.index[0]).days

    df["target"] = df["harga"]
    df.dropna(inplace=True)
    return df

def get_feature_cols() -> list:
    lag_cols     = [f"lag_{i}" for i in range(1, LAG_MAX + 1)]
    rolling_cols = ["rolling_mean_7", "rolling_mean_30",
                    "rolling_std_7",  "rolling_std_30"]
    cal_cols     = ["month", "dayofweek", "days_since_start"]
    return lag_cols + rolling_cols + cal_cols


# ═════════════════════════════════════════════════════════════════════════════
# 2. SPLIT GENERATOR — Hybrid Expanding + Sliding
# ═════════════════════════════════════════════════════════════════════════════
def build_splits(
    series: np.ndarray,
    dates: pd.DatetimeIndex,
    n_splits: int = 5,
    test_window: int = TEST_WINDOW,
    min_train: int = MIN_TRAIN,
) -> List[Dict]:
    """
    Generate split indices untuk Hybrid Expanding + Sliding.
    Split 1-3: expanding. Split 4-5: sliding.
    Fallback ke 3 split kalau data < min_train + test_window * n_splits.
    """
    n        = len(series)
    required = min_train + test_window * n_splits

    if n < required:
        log.warning(
            f"Data pendek ({n} hari < {required} required). "
            f"Fallback ke 3 split proporsional."
        )
        n_splits    = 3
        min_train   = int(n * 0.60)
        test_window = min(30, int(n * 0.10))
        log.info(f"  Fallback: n_splits={n_splits}, min_train={min_train}, "
                 f"test_window={test_window}")

    expanding_splits = 3
    splits           = []

    for i in range(1, n_splits + 1):
        if i <= expanding_splits:
            train_start = 0
            train_end   = min_train + (i - 1) * test_window
            mode        = "expanding"
        else:
            slide_step  = i - expanding_splits
            train_start = slide_step * test_window
            train_end   = min_train + (expanding_splits - 1) * test_window \
                          + slide_step * test_window
            mode        = "sliding"

        test_start = train_end
        test_end   = test_start + test_window

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

def compute_weighted_mape(split_metrics: List[Dict]) -> float:
    n       = len(split_metrics)
    weights = SPLIT_WEIGHTS[:n]
    total_w = sum(weights)
    return round(
        sum(w * m["mape"] for w, m in zip(weights, split_metrics)) / total_w,
        4,
    )


# ═════════════════════════════════════════════════════════════════════════════
# 3. FORECAST HELPERS
# ═════════════════════════════════════════════════════════════════════════════

def _direct_forecast(
    model,
    train_series: np.ndarray,
    dates_train: pd.DatetimeIndex,
    test_dates: pd.DatetimeIndex,
    feature_cols: list,
) -> np.ndarray:
    preds     = []
    train_arr = np.array(train_series)

    for i, date in enumerate(test_dates):
        # Pakai train asli + prediksi sebelumnya hanya untuk rolling window
        temp_series = (
            np.concatenate([train_arr, np.array(preds)])
            if preds else train_arr
        )
        temp_dates = pd.date_range(end=date, periods=len(temp_series), freq="D")

        feat_df = build_features(temp_series, temp_dates)
        if len(feat_df) == 0:
            preds.append(float(train_arr[-1]))
            continue
        last_row = feat_df.iloc[[-1]][feature_cols].values
        preds.append(float(model.predict(last_row)[0]))

    return np.array(preds)

def _recursive_forecast(
    model,
    series_full: np.ndarray,
    dates_full: pd.DatetimeIndex,
    n_steps: int,
    feature_cols: list,
) -> np.ndarray:
    history      = list(series_full)
    last_date    = dates_full[-1]
    preds        = []

    for step in range(n_steps):
        temp_series = np.array(history)
        temp_dates  = pd.date_range(
            end=last_date + pd.Timedelta(days=step + 1),
            periods=len(temp_series),
            freq="D",
        )
        feat_df = build_features(temp_series, temp_dates)
        if len(feat_df) == 0:
            preds.append(history[-1])
            continue

        last_row = feat_df.iloc[[-1]][feature_cols].values
        pred     = float(model.predict(last_row)[0])
        preds.append(pred)
        history.append(pred)

    return np.array(preds)


# ═════════════════════════════════════════════════════════════════════════════
# 4. RANDOMIZED SEARCH TUNING
# ═════════════════════════════════════════════════════════════════════════════
def tune_xgboost_randomized(
    X_train: np.ndarray,
    y_train: np.ndarray,
    n_iter: int = 30,
    cv_splits: int = 3,
) -> Tuple[dict, float]:
    base_model = XGBRegressor(random_state=42, n_jobs=-1)
    tscv       = TimeSeriesSplit(n_splits=cv_splits)

    search = RandomizedSearchCV(
        estimator           = base_model,
        param_distributions = RANDOM_SEARCH_SPACE,
        n_iter              = n_iter,
        scoring             = "neg_mean_absolute_percentage_error",
        cv                  = tscv,
        random_state        = 42,
        n_jobs              = -1,
        refit               = True,
        verbose             = 0,
    )
    search.fit(X_train, y_train)

    best_params = search.best_params_
    best_score  = -search.best_score_   # neg → positif = MAPE
    log.info(f"  RandomizedSearch selesai | best MAPE(CV)={best_score:.4f}%")
    log.info(f"  Best params: {best_params}")

    return best_params, best_score


# ═════════════════════════════════════════════════════════════════════════════
# 5. MAIN TRAINING FUNCTION
# ═════════════════════════════════════════════════════════════════════════════
def train_xgboost(
    komoditas: str,
    data: dict,
    mlflow_experiment: str = None,
    mode: str = "tournament",       # "tournament" | "specialize"
    # Default hyperparameters (mode tournament)
    n_estimators     : int   = 300,
    learning_rate    : float = 0.05,
    max_depth        : int   = 4,
    subsample        : float = 0.8,
    colsample_bytree : float = 0.8,
    min_child_weight : int   = 5,
    reg_alpha        : float = 0.1,
    reg_lambda       : float = 1.0,
) -> dict:
    """
    Train XGBoost dengan Hybrid Expanding + Sliding CV.

    mode="tournament":
        - Hyperparameter default
        - 5 split (atau fallback)
        - Direct forecast per split, recursive untuk future

    mode="specialize":
        - RandomizedSearch n_iter=30 pada split pertama (train terbesar)
        - Best params dipakai untuk semua split berikutnya
        - Log tuning sebagai nested runs
    """
    init_mlflow()
    mlflow.set_experiment(mlflow_experiment or "MarketCast-Tournament")

    series_full  = data["series_full"]
    dates_full   = data["dates_full"]
    cluster      = get_cluster_short(komoditas)
    feature_cols = get_feature_cols()

    log.info(f"\n{'='*60}")
    log.info(f"[{MODEL_NAME}] {komoditas} | cluster={cluster} | mode={mode}")
    log.info(f"  Total data: {len(series_full)} hari "
             f"({dates_full[0].date()} → {dates_full[-1].date()})")

    # ── Build splits ──────────────────────────────────────────────────────────
    splits = build_splits(series_full, dates_full)
    if not splits:
        raise ValueError(f"{komoditas}: tidak ada split yang valid.")

    n_splits      = len(splits)
    split_weights = SPLIT_WEIGHTS[:n_splits]
    total_w       = sum(split_weights)
    split_weights = [w / total_w for w in split_weights]
    
    run_id    = ""
    model_uri = ""
 
    with mlflow.start_run(
        run_name=f"{MODEL_NAME}__{komoditas}"
    ) as parent_run:

        mlflow.set_tags({
            "model"     : MODEL_NAME,
            "komoditas" : komoditas,
            "cluster"   : cluster,
            "mode"      : mode,
            "project"   : "PBL-MarketCast",
            "cv_scheme" : "hybrid_expanding_sliding",
            "forecast"  : "direct_eval_recursive_future",
        })

        mlflow.log_params({
            "n_splits"     : n_splits,
            "test_window"  : TEST_WINDOW,
            "min_train"    : MIN_TRAIN,
            "mode"         : mode,
            "lag_max"      : LAG_MAX,
            "split_weights": str(split_weights),
        })

        # ── Mode specialize: tuning pada split pertama ────────────────────────
        best_params = None
        if mode == "specialize":
            log.info("\n  ── RandomizedSearch Tuning (split 1 train set) ──")
            sp0   = splits[0]
            train0 = series_full[sp0["train_start"]:sp0["train_end"]]
            dates0 = dates_full[sp0["train_start"]:sp0["train_end"]]

            feat0 = build_features(train0, dates0)
            X0    = feat0[feature_cols].values
            y0    = feat0["target"].values

            with mlflow.start_run(
                run_name="randomized_search",
                nested=True,
            ):
                best_params, best_cv_mape = tune_xgboost_randomized(
                    X0, y0, n_iter=30, cv_splits=3,
                )
                mlflow.log_params({
                    f"tuned_{k}": v for k, v in best_params.items()
                })
                mlflow.log_metric("best_cv_mape", best_cv_mape)
                mlflow.log_param("tuning_method", "RandomizedSearch_n30")

            log.info(f"  Best params dari tuning: {best_params}")

        # ── Tentukan params final ─────────────────────────────────────────────
        if best_params:
            final_params = {**best_params, "random_state": 42, "n_jobs": -1}
        else:
            final_params = {
                "n_estimators"     : n_estimators,
                "learning_rate"    : learning_rate,
                "max_depth"        : max_depth,
                "subsample"        : subsample,
                "colsample_bytree" : colsample_bytree,
                "min_child_weight" : min_child_weight,
                "reg_alpha"        : reg_alpha,
                "reg_lambda"       : reg_lambda,
                "random_state"     : 42,
                "n_jobs"           : -1,
            }

        mlflow.log_params({f"model_{k}": v for k, v in final_params.items()})

        # ── Per-split training & evaluasi ─────────────────────────────────────
        split_results = []

        for sp in splits:
            i            = sp["split_idx"]
            train_series = series_full[sp["train_start"]:sp["train_end"]]
            test_series  = series_full[sp["test_start"]:sp["test_end"]]
            dates_train  = dates_full[sp["train_start"]:sp["train_end"]]
            dates_test   = dates_full[sp["test_start"]:sp["test_end"]]

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

                # Build features untuk split ini
                feat_train = build_features(train_series, dates_train)
                X_train    = feat_train[feature_cols].values
                y_train    = feat_train["target"].values

                # Fit model
                model = XGBRegressor(**final_params)
                model.fit(X_train, y_train, verbose=False)

                # Direct forecast untuk evaluasi (tidak ada error akumulasi)
                forecast = _direct_forecast(
                    model, train_series, dates_train,
                    dates_test, feature_cols,
                )

                metrics = compute_metrics(test_series, forecast)
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
                    "forecast"   : forecast,
                    "train"      : train_series,
                    "test"       : test_series,
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
                 f"WMAE={wmae:,.0f} | WRMSE={wrmse:,.0f} | "
                 f"WMDA={wmda:.2f}")

        # ── Refit final pada full series ──────────────────────────────────────
        log.info(f"\n  Refit final pada full series ({len(series_full)} hari)")
        feat_full  = build_features(series_full, dates_full)
        X_full     = feat_full[feature_cols].values
        y_full     = feat_full["target"].values
        final_model = XGBRegressor(**final_params)
        final_model.fit(X_full, y_full, verbose=False)

        # ── Future forecast 30 hari (recursive) ──────────────────────────────
        future_forecast = _recursive_forecast(
            final_model, series_full, dates_full,
            FORECAST_DAYS, feature_cols,
        )

        # ── Plots ─────────────────────────────────────────────────────────────
        slug = komoditas.replace(" ", "_").replace("/", "_")

        fig_imp = _plot_importance(final_model, feature_cols, komoditas)
        imp_path = f"/tmp/xgb_importance_{slug}.png"
        fig_imp.savefig(imp_path, dpi=120, bbox_inches="tight")
        plt.close(fig_imp)
        mlflow.log_artifact(imp_path, artifact_path="plots")

        fig = _plot_xgboost_cv(
            komoditas, series_full, dates_full,
            split_results, future_forecast, cluster,
        )
        plot_path = f"/tmp/xgb_{slug}.png"
        fig.savefig(plot_path, dpi=120, bbox_inches="tight")
        plt.close(fig)
        mlflow.log_artifact(plot_path, artifact_path="plots")

        # ── Log model ─────────────────────────────────────────────────────────
        safe_name = komoditas.replace(" ", "_").replace("/", "_")
        mlflow.xgboost.log_model(final_model, name=f"XGBoost_{safe_name}")

        run_id    = parent_run.info.run_id
        model_uri = f"runs:/{run_id}/XGBoost_{safe_name}"

    log.info(f"\n[{MODEL_NAME}] {komoditas} selesai. run_id={run_id[:8]}...")

    return {
        "komoditas"      : komoditas,
        "model"          : final_model,
        "split_results"  : split_results,
        "metrics"        : agg_metrics,
        "future_forecast": future_forecast,
        "run_id"         : run_id,
        "model_uri"      : model_uri,
        "data"           : data,
        "n_splits_used"  : n_splits,
        "tuned_params"   : best_params,
    }


# ═════════════════════════════════════════════════════════════════════════════
# 6. PLOTS
# ═════════════════════════════════════════════════════════════════════════════
def _plot_xgboost_cv(
    komoditas, series_full, dates_full,
    split_results, future_forecast, cluster,
):
    SPLIT_COLORS = ["#E74C3C", "#E67E22", "#F1C40F", "#27AE60", "#2980B9"]
    fig, ax = plt.subplots(figsize=(16, 6))

    ax.plot(dates_full[-90:], series_full[-90:],
            color="#2C3E50", lw=1.5, label="Aktual", zorder=5)

    for i, r in enumerate(split_results):
        color = SPLIT_COLORS[i % len(SPLIT_COLORS)]
        ax.plot(r["dates_test"], r["forecast"],
                color=color, lw=1.8, linestyle="--",
                label=f"Split {r['split_idx']} [{r['mode']}] "
                      f"MAPE={r['mape']:.1f}%",
                alpha=0.85)

    last_date    = dates_full[-1]
    future_dates = pd.date_range(
        last_date + pd.Timedelta(days=1),
        periods=len(future_forecast), freq="D",
    )
    ax.plot(future_dates, future_forecast,
            color="#8E44AD", lw=2.2, linestyle=":",
            label="Future 30d forecast")

    ax.set_title(
        f"XGBoost — {komoditas}  [cluster: {cluster}]\n"
        f"Hybrid Expanding+Sliding | {len(split_results)} splits | "
        f"Direct eval + Recursive future",
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

def _plot_importance(model, feature_cols: list, komoditas: str):
    importances = model.feature_importances_
    pairs       = sorted(
        zip(feature_cols, importances),
        key=lambda x: x[1], reverse=True,
    )[:20]
    names, vals = zip(*pairs)

    fig, ax = plt.subplots(figsize=(8, 6))
    ax.barh(range(len(names)), vals, color="#3498DB", alpha=0.8)
    ax.set_yticks(range(len(names)))
    ax.set_yticklabels(names, fontsize=9)
    ax.invert_yaxis()
    ax.set_xlabel("Feature Importance (gain)")
    ax.set_title(f"XGBoost Feature Importance\n{komoditas}", fontweight="bold")
    ax.grid(axis="x", alpha=0.3)
    plt.tight_layout()
    return fig