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
import numpy as np
import pandas as pd
import mlflow
import mlflow.pyfunc
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from pathlib import Path

import pmdarima as pm
from pmdarima.arima import auto_arima

from config import (MLFLOW_TRACKING_URI, init_mlflow,
                    FORECAST_DAYS, get_logger, compute_metrics,
                    get_cluster_short)

warnings.filterwarnings("ignore")
log = get_logger("sarima")

MODEL_NAME = "SARIMA"


def train_sarima(komoditas: str, data: dict, 
                 mlflow_experiment: str = None,
                 max_p: int = 3, max_q: int = 3,
                 max_P: int = 2, max_Q: int = 2
                 ) -> dict:
    """
    Train SARIMA untuk satu komoditas dan log ke MLflow.

    Flow:
        1. auto_arima → pilih order optimal via AIC
        2. Refit model final di full train set
        3. Prediksi 30 hari ke depan (test set)
        4. Hitung metrics
        5. Log semua ke MLflow (params, metrics, artifacts)

    Returns:
        dict dengan model, metrics, forecast
    """
    init_mlflow()
    mlflow.set_experiment(mlflow_experiment or "MarketCast-Tournament")

    mlflow.set_tracking_uri(MLFLOW_TRACKING_URI)
    mlflow.set_experiment(mlflow_experiment or "MarketCast-Tournament")

    train       = data["train"]
    test        = data["test"]
    dates_test  = data["dates_test"]
    dates_train = data["dates_train"]
    cluster     = get_cluster_short(komoditas)

    log.info(f"[{MODEL_NAME}] Training: {komoditas} (cluster: {cluster})")

    run_id = ""
    model_uri = ""

    with mlflow.start_run(run_name=f"{MODEL_NAME}__{komoditas}"):

        # ── Tags ──────────────────────────────────────────
        mlflow.set_tags({
            "model"     : MODEL_NAME,
            "komoditas" : komoditas,
            "cluster"   : cluster,
            "project"   : "PBL-MarketCast",
        })

        # ── Step 1: auto_arima ────────────────────────────
        log.info(f"  auto_arima fitting (m=7, stepwise) max_p={max_p} max_q={max_q} ...")
        try:
            auto_model = auto_arima(
                train,
                start_p=0, max_p=3,
                start_q=0, max_q=3,
                d=None,              # auto-detect differencing
                start_P=0, max_P=2,
                start_Q=0, max_Q=2,
                D=None,
                m=7,                 # seasonality mingguan
                seasonal=True,
                information_criterion="aic",
                stepwise=True,       # stepwise=True lebih cepat, cukup untuk jurnal
                suppress_warnings=True,
                error_action="ignore",
                trace=False,
            )
            order         = auto_model.order
            seasonal_order = (auto_model.seasonal_order)
            log.info(f"  Best order: SARIMA{order}x{seasonal_order}")

        except Exception as e:
            log.warning(f"  SARIMA m=7 gagal ({e}), fallback ke ARIMA (m=1)")
            auto_model = auto_arima(
                train,
                seasonal=False,
                information_criterion="aic",
                stepwise=True,
                suppress_warnings=True,
                error_action="ignore",
            )
            order          = auto_model.order
            seasonal_order = (0, 0, 0, 0)

        # ── Step 2: Log params ────────────────────────────
        mlflow.log_params({
            "p"       : order[0],
            "d"       : order[1],
            "q"       : order[2],
            "P"       : seasonal_order[0],
            "D"       : seasonal_order[1],
            "Q"       : seasonal_order[2],
            "m"       : seasonal_order[3],
            "aic"     : round(auto_model.aic(), 4),
            # Search space — dicatat agar bisa dibandingkan antar run di MLflow
            "max_p"  : max_p,
            "max_q"  : max_q,
            "max_P"  : max_P,
            "max_Q"  : max_Q,
            "n_train": len(train),
            "n_test" : len(test),
        })

        # ── Step 3: Forecast test set ─────────────────────
        forecast, conf_int = auto_model.predict(
            n_periods=len(test),
            return_conf_int=True,
            alpha=0.05   # 95% confidence interval
        )

        # ── Step 4: Metrics ───────────────────────────────
        metrics = compute_metrics(test, forecast)
        mlflow.log_metrics(metrics)
        log.info(f"  Metrics: MAE={metrics['mae']:,.0f} | RMSE={metrics['rmse']:,.0f} "
                 f"| MAPE={metrics['mape']:.2f}% | SMAPE={metrics['smape']:.2f}%")

        # ── Step 5: Forecast 30 hari ke depan ─────────────
        future_forecast, future_ci = auto_model.predict(
            n_periods=FORECAST_DAYS,
            return_conf_int=True,
            alpha=0.05
        )

        # ── Step 6: Artifacts — plot ──────────────────────
        fig = _plot_sarima(
            komoditas, train, test, dates_train, dates_test,
            forecast, conf_int, future_forecast, future_ci
        )
        plot_path = f"/tmp/sarima_{komoditas.replace(' ','_').replace('/','_').replace('/','_')}.png"
        fig.savefig(plot_path, dpi=120, bbox_inches="tight")
        plt.close(fig)
        mlflow.log_artifact(plot_path, artifact_path="plots")

        # ── Step 7: Log model ─────────────────────────────
        import pickle, tempfile, os
        with tempfile.TemporaryDirectory() as tmpdir:
            pkl_path = os.path.join(tmpdir, "model.pkl")
            with open(pkl_path, "wb") as f:
                pickle.dump(auto_model, f)
            mlflow.log_artifact(pkl_path, artifact_path=f"SARIMA_{komoditas.replace(' ', '_')}")
        active_run = mlflow.active_run()
        run_id     = active_run.info.run_id if active_run else ""
        model_uri  = f"runs:/{run_id}/model" if run_id else ""

        if not run_id:
            log.error(f"  run_id kosong untuk {komoditas} — model tidak ter-log!")

    return {
        "komoditas"      : komoditas,
        "model"          : auto_model,
        "order"          : order,
        "seasonal_order" : seasonal_order,
        "forecast_test"  : forecast,
        "conf_int_test"  : conf_int,
        "run_id"         : run_id,
        "model_uri"      : model_uri,
        "data"           : data,
        "future_forecast": future_forecast,
        "future_ci"      : future_ci,
        "metrics"        : metrics,
    }


def _plot_sarima(komoditas, train, test, dates_train, dates_test,
                 forecast, conf_int, future_forecast, future_ci):
    fig, ax = plt.subplots(figsize=(14, 5))

    # Plot train (last 90 days only untuk readability)
    ax.plot(dates_train[-90:], train[-90:],
            color="#2C3E50", lw=1.5, label="Train (90 hari terakhir)")

    # Plot test actual
    ax.plot(dates_test, test,
            color="#27AE60", lw=2, label="Aktual (test)")

    # Plot forecast test
    ax.plot(dates_test, forecast,
            color="#E74C3C", lw=2, linestyle="--", label="Forecast SARIMA")

    # Confidence interval test
    ax.fill_between(dates_test,
                    conf_int[:, 0], conf_int[:, 1],
                    color="#E74C3C", alpha=0.15, label="95% CI")

    # Future forecast
    last_date    = dates_test[-1]
    future_dates = pd.date_range(last_date + pd.Timedelta(days=1),
                                  periods=len(future_forecast), freq="D")
    ax.plot(future_dates, future_forecast,
            color="#8E44AD", lw=2, linestyle=":", label="Future forecast")
    ax.fill_between(future_dates,
                    future_ci[:, 0], future_ci[:, 1],
                    color="#8E44AD", alpha=0.12)

    ax.axvline(dates_test[0], color="gray", lw=1, linestyle="--", alpha=0.7)
    ax.set_title(f"SARIMA — {komoditas}", fontsize=13, fontweight="bold")
    ax.set_xlabel("Tanggal"); ax.set_ylabel("Harga/kg (Rp)")
    ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, _: f"Rp{x:,.0f}"))
    ax.legend(fontsize=9); ax.grid(alpha=0.2)
    plt.tight_layout()
    return fig
