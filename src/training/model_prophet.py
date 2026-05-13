"""
src/training/model_prophet.py
==============================
Baseline 2: Facebook Prophet
"""

import warnings
import numpy as np
import pandas as pd
import mlflow
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from prophet import Prophet

from config import (MLFLOW_TRACKING_URI, init_mlflow,
                    FORECAST_DAYS, get_logger, compute_metrics,
                    get_cluster_short)

warnings.filterwarnings("ignore")
log = get_logger("prophet")

MODEL_NAME = "Prophet"

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
    "lower_window": [-7, -7, -7, -7, -7, -3, -3, -3, -3, -3, -3, -3, -3, -3, -3],
    "upper_window": [ 3,  3,  3,  3,  3,  1,  1,  1,  1,  1,  1,  1,  1,  1,  1],
})


def train_prophet(komoditas: str, data: dict, 
                  mlflow_experiment: str = None,
                  changepoint_prior_scale: float = None,
                  seasonality_prior_scale: float = 10.0
                  ) -> dict:

    mlflow.set_tracking_uri(MLFLOW_TRACKING_URI)
    mlflow.set_experiment(mlflow_experiment or "MarketCast-Tournament")

    init_mlflow()
    mlflow.set_experiment(mlflow_experiment or "MarketCast-Tournament")

    train       = data["train"]
    test        = data["test"]
    dates_train = data["dates_train"]
    dates_test  = data["dates_test"]
    cluster     = get_cluster_short(komoditas)

    # Validasi test set tidak kosong
    if len(test) == 0:
        raise ValueError(f"{komoditas}: test set kosong setelah split.")

    log.info(f"[{MODEL_NAME}] Training: {komoditas} (cluster: {cluster})")

    df_train = pd.DataFrame({"ds": dates_train, "y": train})

    run_id = ""
    model_uri = ""

    with mlflow.start_run(run_name=f"{MODEL_NAME}__{komoditas}"):

        mlflow.set_tags({
            "model"    : MODEL_NAME,
            "komoditas": komoditas,
            "cluster"  : cluster,
            "project"  : "PBL-MarketCast",
        })

        # FIX: label cluster yang benar adalah "C0_LabilDatar", bukan "high_volatility"
        # Cluster 0 (Labil & Murah →Datar) = cabai, tomat — volatilitas tinggi
        changepoint_scale = 0.3 if cluster == "C0_LabilDatar" else 0.05

        model = Prophet(
            yearly_seasonality      = True,
            weekly_seasonality      = True,
            daily_seasonality       = False,
            holidays                = INDONESIAN_HOLIDAYS,
            changepoint_prior_scale = changepoint_prior_scale,
            seasonality_prior_scale = seasonality_prior_scale,
            interval_width          = 0.95,
            uncertainty_samples     = 100,
        )
        model.add_seasonality(name="monthly", period=30.5, fourier_order=5)
        model.fit(df_train)

        mlflow.log_params({
            "changepoint_prior_scale": changepoint_prior_scale,
            "seasonality_prior_scale": seasonality_prior_scale,
            "yearly_seasonality"     : True,
            "weekly_seasonality"     : True,
            "monthly_seasonality"    : True,
            "fourier_order_monthly"  : 5,
            "holidays"               : "ID_Idul_Fitri,Natal,Tahun_Baru",
            "interval_width"         : 0.95,
            "uncertainty_samples"    : 100,
            "n_train"                : len(train),
            "n_test"                 : len(test),
        })

        future_test = pd.DataFrame({"ds": dates_test})
        forecast_df = model.predict(future_test)
        forecast    = forecast_df["yhat"].values

        last_date    = dates_test[-1]
        future_dates = pd.date_range(last_date + pd.Timedelta(days=1),
                                      periods=FORECAST_DAYS, freq="D")
        future_pred  = model.predict(pd.DataFrame({"ds": future_dates}))

        metrics = compute_metrics(test, forecast)
        mlflow.log_metrics(metrics)
        log.info(f"  Metrics: MAE={metrics['mae']:,.0f} | RMSE={metrics['rmse']:,.0f} "
                 f"| MAPE={metrics['mape']:.2f}% | SMAPE={metrics['smape']:.2f}%")

        fig = _plot_prophet(komoditas, train, test, dates_train, dates_test,
                            forecast_df, future_pred, cluster)
        plot_path = f"/tmp/prophet_{komoditas.replace(' ','_').replace('/','_').replace('/','_')}.png"
        fig.savefig(plot_path, dpi=120, bbox_inches="tight")
        plt.close(fig)
        mlflow.log_artifact(plot_path, artifact_path="plots")

        fig_comp = model.plot_components(
            pd.concat([forecast_df, future_pred], ignore_index=True)
        )
        comp_path = f"/tmp/prophet_components_{komoditas.replace(' ','_').replace('/','_').replace('/','_')}.png"
        fig_comp.savefig(comp_path, dpi=100, bbox_inches="tight")
        plt.close(fig_comp)
        mlflow.log_artifact(comp_path, artifact_path="plots")

        import pickle, tempfile, os
        with tempfile.TemporaryDirectory() as tmpdir:
            pkl_path = os.path.join(tmpdir, "model.pkl")
            with open(pkl_path, "wb") as f:
                pickle.dump(model, f)
            mlflow.log_artifact(pkl_path, artifact_path=f"Prophet_{komoditas.replace(' ', '_')}")
        active_run = mlflow.active_run()
        run_id     = active_run.info.run_id if active_run else ""
        model_uri  = f"runs:/{run_id}/model" if run_id else ""

        if not run_id:
            log.error(f"  run_id kosong untuk {komoditas} — model tidak ter-log!")

    return {
        "komoditas"    : komoditas,
        "model"        : model,
        "forecast_test": forecast,
        "forecast_df"  : forecast_df,
        "future_pred"  : future_pred,
        "run_id"       : run_id,
        "model_uri"    : model_uri,
        "data"         : data,
        "metrics"      : metrics,
    }


def _plot_prophet(komoditas, train, test, dates_train, dates_test,
                  forecast_df, future_pred, cluster):
    fig, ax = plt.subplots(figsize=(14, 5))
    ax.plot(dates_train[-90:], train[-90:], color="#2C3E50", lw=1.5,
            label="Train (90 hari terakhir)")
    ax.plot(dates_test, test, color="#27AE60", lw=2, label="Aktual (test)")
    ax.plot(dates_test, forecast_df["yhat"].values, color="#E67E22",
            lw=2, linestyle="--", label="Forecast Prophet")
    ax.fill_between(dates_test,
                    forecast_df["yhat_lower"].values,
                    forecast_df["yhat_upper"].values,
                    color="#E67E22", alpha=0.15, label="95% CI")
    future_dates_plot = future_pred["ds"].values
    ax.plot(future_dates_plot, future_pred["yhat"].values,
            color="#8E44AD", lw=2, linestyle=":", label="Future forecast")
    ax.fill_between(future_dates_plot,
                    future_pred["yhat_lower"].values,
                    future_pred["yhat_upper"].values,
                    color="#8E44AD", alpha=0.12)
    ax.axvline(dates_test[0], color="gray", lw=1, linestyle="--", alpha=0.7)
    ax.set_title(f"Prophet — {komoditas}  [cluster: {cluster}]",
                 fontsize=13, fontweight="bold")
    ax.set_xlabel("Tanggal"); ax.set_ylabel("Harga/kg (Rp)")
    ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, _: f"Rp{x:,.0f}"))
    ax.legend(fontsize=9); ax.grid(alpha=0.2)
    plt.tight_layout()
    return fig
