"""
src/training/model_xgboost.py
==============================
Baseline 3: XGBoost
-----------------------------------------
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
from sklearn.preprocessing import MinMaxScaler

from config import (MLFLOW_TRACKING_URI, init_mlflow,
                    FORECAST_DAYS, get_logger, compute_metrics, get_cluster_short)

warnings.filterwarnings("ignore")
log = get_logger("xgboost")

MODEL_NAME = "XGBoost"
LAG_MAX    = 30   # hari ke belakang yang dijadikan fitur


# ══════════════════════════════════════════════════════════════
# FEATURE ENGINEERING
# ══════════════════════════════════════════════════════════════

def build_features(series: np.ndarray, dates: pd.DatetimeIndex) -> pd.DataFrame:
    """
    Bangun feature matrix dari time series harga.

    Fitur:
        lag_1 .. lag_LAG_MAX   : harga LAG hari lalu
        rolling_mean_7/30      : rata-rata harga 7 dan 30 hari terakhir
        rolling_std_7/30       : std harga 7 dan 30 hari terakhir
        month                  : bulan (1–12), encode musiman tahunan
        dayofweek              : hari dalam minggu (0=Senin)
        days_since_start       : counter linear, encode tren global
    """
    df = pd.DataFrame({"harga": series}, index=dates)

    # Lag features
    for lag in range(1, LAG_MAX + 1):
        df[f"lag_{lag}"] = df["harga"].shift(lag)

    # Rolling features
    df["rolling_mean_7"]  = df["harga"].shift(1).rolling(7).mean()
    df["rolling_mean_30"] = df["harga"].shift(1).rolling(30).mean()
    df["rolling_std_7"]   = df["harga"].shift(1).rolling(7).std()
    df["rolling_std_30"]  = df["harga"].shift(1).rolling(30).std()

    # Kalender features
    df["month"]           = df.index.month
    df["dayofweek"]       = df.index.dayofweek
    df["days_since_start"] = (df.index - df.index[0]).days

    # Target: harga hari ini
    df["target"] = df["harga"]

    # Drop baris dengan NaN (akibat lag & rolling di awal)
    df.dropna(inplace=True)
    return df


def get_feature_cols() -> list:
    """Return daftar nama kolom fitur (tanpa 'harga' dan 'target')."""
    lag_cols     = [f"lag_{i}" for i in range(1, LAG_MAX + 1)]
    rolling_cols = ["rolling_mean_7", "rolling_mean_30",
                    "rolling_std_7",  "rolling_std_30"]
    cal_cols     = ["month", "dayofweek", "days_since_start"]
    return lag_cols + rolling_cols + cal_cols


# ══════════════════════════════════════════════════════════════
# TRAIN
# ══════════════════════════════════════════════════════════════

def train_xgboost(komoditas: str, 
                  data: dict, 
                  mlflow_experiment: str = None,
                  # ── Hyperparameters — semua eksplisit untuk tuning ──────
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
    Train XGBoost untuk satu komoditas dan log ke MLflow.

    Flow:
        1. Build feature matrix dari seluruh series
        2. Split train/test sesuai indeks (bukan rolling window)
        3. Fit XGBRegressor
        4. Iterative forecast untuk test set (recursive)
        5. Iterative forecast 30 hari ke depan
        6. Hitung metrics & log ke MLflow
    """
    init_mlflow()
    mlflow.set_experiment(mlflow_experiment or "MarketCast-Tournament")

    series_full  = data["series_full"]
    dates_full   = data["dates_full"]
    train        = data["train"]
    test         = data["test"]
    dates_train  = data["dates_train"]
    dates_test   = data["dates_test"]
    cluster      = get_cluster_short(komoditas)

    log.info(f"[{MODEL_NAME}] Training: {komoditas} (cluster: {cluster})")

    # ── Feature matrix dari full series ──────────────────────
    feat_df      = build_features(series_full, dates_full)
    feature_cols = get_feature_cols()

    # Pisah train/test berdasarkan tanggal
    train_feat = feat_df[feat_df.index < dates_test[0]]
    test_feat  = feat_df[feat_df.index >= dates_test[0]]

    X_train = train_feat[feature_cols].values
    y_train = train_feat["target"].values
    X_test  = test_feat[feature_cols].values
    y_test  = test_feat["target"].values

    run_id = ''
    model_uri = ''

    with mlflow.start_run(run_name=f"{MODEL_NAME}__{komoditas}"):

        mlflow.set_tags({
            "model"    : MODEL_NAME,
            "komoditas": komoditas,
            "cluster"  : cluster,
            "project"  : "PBL-MarketCast",
        })

        # ── Hyperparameters ───────────────────────────────────
        params = {
            "n_estimators"      : n_estimators,
            "learning_rate"     : learning_rate,
            "max_depth"         : max_depth,
            "subsample"         : subsample,
            "colsample_bytree"  : colsample_bytree,
            "min_child_weight"  : min_child_weight,
            "reg_alpha"         : reg_alpha,   # L1 regularization
            "reg_lambda"        : reg_lambda,   # L2 regularization
            "random_state"      : 42,
            "n_jobs"            : -1,
        }

        model = XGBRegressor(**params)
        model.fit(
            X_train, y_train,
            eval_set=[(X_test, y_test)],
            verbose=False,
        )

        mlflow.log_params({**params,
                           "lag_max"  : LAG_MAX,
                           "n_train"  : len(X_train),
                           "n_test"   : len(X_test),
                           "strategy" : "recursive_forecast"})

        # ── Forecast test set (recursive) ────────────────────
        forecast_test = _recursive_forecast(
            model, series_full, dates_full,
            n_steps=len(test), feature_cols=feature_cols
        )

        # ── Metrics ───────────────────────────────────────────
        metrics = compute_metrics(y_test, forecast_test)
        mlflow.log_metrics(metrics)
        log.info(f"  Metrics: MAE={metrics['mae']:,.0f} | RMSE={metrics['rmse']:,.0f} "
                 f"| MAPE={metrics['mape']:.2f}% | SMAPE={metrics['smape']:.2f}%")

        # ── Future forecast 30 hari ke depan ─────────────────
        future_forecast = _recursive_forecast(
            model, series_full, dates_full,
            n_steps=FORECAST_DAYS, feature_cols=feature_cols
        )

        # ── Feature importance plot ───────────────────────────
        fig_imp = _plot_importance(model, feature_cols, komoditas)
        imp_path = f"/tmp/xgb_importance_{komoditas.replace(' ','_').replace('/','_').replace('/','_')}.png"
        fig_imp.savefig(imp_path, dpi=120, bbox_inches="tight")
        plt.close(fig_imp)
        mlflow.log_artifact(imp_path, artifact_path="plots")

        # ── Forecast plot ─────────────────────────────────────
        fig = _plot_xgboost(
            komoditas, train, test, dates_train, dates_test,
            forecast_test, future_forecast, cluster
        )
        plot_path = f"/tmp/xgb_{komoditas.replace(' ','_').replace('/','_').replace('/','_')}.png"
        fig.savefig(plot_path, dpi=120, bbox_inches="tight")
        plt.close(fig)
        mlflow.log_artifact(plot_path, artifact_path="plots")

        # ── Log model ─────────────────────────────────────────
        import pickle, tempfile, os
        with tempfile.TemporaryDirectory() as tmpdir:
            pkl_path = os.path.join(tmpdir, "model.pkl")
            with open(pkl_path, "wb") as f:
                pickle.dump(model, f)
            mlflow.log_artifact(pkl_path, artifact_path=f"XGBoost_{komoditas.replace(' ', '_')}")
        # Capture run info untuk model_registry_map.yaml
        active_run = mlflow.active_run()
        run_id     = active_run.info.run_id if active_run else ""
        model_uri  = f"runs:/{run_id}/model" if run_id else ""

        if not run_id:
            log.error(f"  run_id kosong untuk {komoditas} — model tidak ter-log!")
            
    return {
        "komoditas"      : komoditas,
        "model"          : model,
        "forecast_test"  : forecast_test,
        "future_forecast": future_forecast,
        "run_id"         : run_id,
        "model_uri"      : model_uri,
        "data"           : data,
        "metrics"        : metrics,
    }

def tune_xgboost_optuna(
    komoditas: str,
    data: dict,
    n_trials: int = 30,
    mlflow_experiment: str = "MarketCast-XGBoost-Tuning",
) -> dict:
    """
    Bayesian hyperparameter search via Optuna untuk XGBoost.
 
    Returns:
        dict dengan best_params, best_mape, best_run_id
    """
    try:
        import optuna
        optuna.logging.set_verbosity(optuna.logging.WARNING)
    except ImportError:
        raise ImportError("Optuna belum terinstall. Jalankan: pip install optuna")
 
    init_mlflow()
    mlflow.set_experiment(mlflow_experiment)
 
    series_full  = data["series_full"]
    dates_full   = data["dates_full"]
    test         = data["test"]
    dates_test   = data["dates_test"]
 
    feat_df      = build_features(series_full, dates_full)
    feature_cols = get_feature_cols()
 
    train_feat = feat_df[feat_df.index < dates_test[0]]
    test_feat  = feat_df[feat_df.index >= dates_test[0]]
    X_train = train_feat[feature_cols].values
    y_train = train_feat["target"].values
    y_test  = test_feat["target"].values
 
    log.info(f"[XGBoost-Optuna] Tuning: {komoditas} | {n_trials} trials")
 
    best_params  = {}
    best_mape    = float("inf")
    best_run_id  = ""
 
    # Parent MLflow run untuk tuning session
    with mlflow.start_run(run_name=f"XGBoost_Tuning__{komoditas}") as parent_run:
        mlflow.set_tags({
            "model"    : "XGBoost-Optuna",
            "komoditas": komoditas,
            "cluster"  : get_cluster_short(komoditas),
            "project"  : "PBL-MarketCast",
            "tuning"   : "optuna_tpe",
        })
 
        def objective(trial):
            """
            Optuna objective function.
            Setiap pemanggilan = 1 trial = 1 child MLflow run.
            Return: MAPE (minimized by Optuna).
            """
            trial_params = {
                "n_estimators"    : trial.suggest_int("n_estimators", 100, 600),
                "learning_rate"   : trial.suggest_float("learning_rate",
                                                         0.01, 0.3, log=True),
                "max_depth"       : trial.suggest_int("max_depth", 3, 7),
                "subsample"       : trial.suggest_float("subsample", 0.6, 1.0),
                "colsample_bytree": trial.suggest_float("colsample_bytree", 0.6, 1.0),
                "min_child_weight": trial.suggest_int("min_child_weight", 1, 10),
                "reg_alpha"       : trial.suggest_float("reg_alpha",
                                                         1e-8, 1.0, log=True),
                "reg_lambda"      : trial.suggest_float("reg_lambda",
                                                         1e-8, 10.0, log=True),
                "random_state"    : 42,
                "n_jobs"          : -1,
            }
 
            # Child run nested di dalam parent
            with mlflow.start_run(
                run_name=f"trial_{trial.number:03d}",
                nested=True
            ):
                mlflow.log_params(trial_params)
 
                m = XGBRegressor(**trial_params)
                m.fit(X_train, y_train, verbose=False)
 
                # Eval langsung pada X_test (bukan recursive) untuk kecepatan
                y_pred  = m.predict(test_feat[feature_cols].values)
                metrics = compute_metrics(y_test, y_pred)
                mlflow.log_metrics(metrics)
 
            return metrics["mape"]
 
        # Jalankan Optuna study
        study = optuna.create_study(
            direction="minimize",
            sampler=optuna.samplers.TPESampler(seed=42),
        )
        study.optimize(objective, n_trials=n_trials, show_progress_bar=False)
 
        best_params = study.best_params
        best_mape   = study.best_value
 
        # Log best result ke parent run
        mlflow.log_params({f"best_{k}": v for k, v in best_params.items()})
        mlflow.log_metric("best_mape", best_mape)
        mlflow.log_metric("n_trials", n_trials)
        best_run_id = parent_run.info.run_id
 
        log.info(f"  Best MAPE: {best_mape:.4f}%")
        log.info(f"  Best params: {best_params}")
 
    return {
        "komoditas"  : komoditas,
        "best_params": best_params,
        "best_mape"  : best_mape,
        "best_run_id": best_run_id,
    }

def _recursive_forecast(model, series_full, dates_full,
                         n_steps: int, feature_cols: list) -> np.ndarray:
    """
    Recursive multi-step forecast:
        1. Bangun history dari series aktual
        2. Predict 1 langkah ke depan
        3. Append prediksi ke history
        4. Ulangi n_steps kali

    Error akumulasi tidak terhindarkan di sini.
    Untuk volatile commodity (cabai), interval konfidensnya lebar —
    ini harus disampaikan ke user sebagai ketidakpastian prediksi.
    """
    history      = list(series_full)
    last_date    = dates_full[-1]
    future_dates = pd.date_range(last_date + pd.Timedelta(days=1),
                                  periods=n_steps, freq="D")
    preds = []

    for step in range(n_steps):
        # Bangun series sementara dari history
        temp_series = np.array(history)
        temp_dates  = pd.date_range(
            end=last_date + pd.Timedelta(days=step + 1),
            periods=len(temp_series),
            freq="D"
        )

        feat_df = build_features(temp_series, temp_dates)
        if len(feat_df) == 0:
            preds.append(history[-1])  # fallback: ulang nilai terakhir
            continue

        last_row = feat_df.iloc[[-1]][feature_cols].values
        pred     = float(model.predict(last_row)[0])
        preds.append(pred)
        history.append(pred)

    return np.array(preds)


# ══════════════════════════════════════════════════════════════
# PLOTS
# ══════════════════════════════════════════════════════════════

def _plot_xgboost(komoditas, train, test, dates_train, dates_test,
                  forecast_test, future_forecast, cluster):
    fig, ax = plt.subplots(figsize=(14, 5))

    ax.plot(dates_train[-90:], train[-90:],
            color="#2C3E50", lw=1.5, label="Train (90 hari terakhir)")
    ax.plot(dates_test, test,
            color="#27AE60", lw=2, label="Aktual (test)")
    ax.plot(dates_test, forecast_test,
            color="#3498DB", lw=2, linestyle="--", label="Forecast XGBoost")

    last_date    = dates_test[-1]
    future_dates = pd.date_range(last_date + pd.Timedelta(days=1),
                                  periods=len(future_forecast), freq="D")
    ax.plot(future_dates, future_forecast,
            color="#8E44AD", lw=2, linestyle=":", label="Future forecast")

    ax.axvline(dates_test[0], color="gray", lw=1, linestyle="--", alpha=0.7)
    ax.set_title(f"XGBoost — {komoditas}  [cluster: {cluster}]",
                 fontsize=13, fontweight="bold")
    ax.set_xlabel("Tanggal"); ax.set_ylabel("Harga/kg (Rp)")
    ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, _: f"Rp{x:,.0f}"))
    ax.legend(fontsize=9); ax.grid(alpha=0.2)
    plt.tight_layout()
    return fig


def _plot_importance(model, feature_cols: list, komoditas: str):
    """Top 20 feature importance untuk interpretabilitas model."""
    importances = model.feature_importances_
    pairs       = sorted(zip(feature_cols, importances),
                          key=lambda x: x[1], reverse=True)[:20]
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
