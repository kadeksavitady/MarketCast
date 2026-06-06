import mlflow
import os
import numpy as np
import pandas as pd
from sqlalchemy import text
from src.core.config import logger, engine
from mlflow.tracking import MlflowClient

os.environ["MLFLOW_TRACKING_USERNAME"] = "kadeksavitady"
os.environ["MLFLOW_TRACKING_PASSWORD"] = os.getenv("DAGSHUB_TOKEN")
mlflow.set_tracking_uri("https://dagshub.com/kadeksavitady/MarketCast.mlflow")

active_models: dict = {}
active_model_names: dict = {}
clustering_data_cache: dict = {}

MODEL_TYPE_PREFIXES = ["XGBoost__", "SARIMA__", "Prophet__"]

def get_clustering_data() -> dict:
    """Load CSV clustering dari MLflow, cache in-memory setelah pertama kali."""
    global clustering_data_cache

    if clustering_data_cache:
        return clustering_data_cache

    try:
        client = MlflowClient()
        model_version = client.get_model_version_by_alias(name="Metadata__Clustering", alias="production")
        lokasi_file = client.download_artifacts(
            model_version.run_id,
            "clustering_results/model_artifacts/cluster_assignments.csv",
        )
        df_cluster = pd.read_csv(lokasi_file)

        for _, row in df_cluster.iterrows():
            clustering_data_cache[row["komoditas"]] = {
                "cluster":       row.get("cluster", "Tidak Diketahui"),
                "cluster_label": row.get("cluster_label", ""),
                "is_centroid":   row.get("is_centroid", False),
                "cv":            row["cv"],
                "trend_slope":   row["trend_slope"],
                "mean":          row["mean_harga"],
            }

        logger.info("Clustering CSV loaded and cached.")
        return clustering_data_cache

    except Exception as e:
        logger.error(f"Failed to load clustering CSV from MLflow: {e}")
        return {}

def resolve_model_name(komoditas_id: str) -> str:
    """Cari nama model MLflow production yang aktif untuk komoditas, dengan caching."""
    if komoditas_id in active_model_names:
        return active_model_names[komoditas_id]

    client = MlflowClient()

    # Slash dalam nama komoditas tidak valid sebagai nama model MLflow
    sanitized_name = komoditas_id
    slash_replacements = {
        "Bawang Putih Sinco/Honan": "Bawang Putih SincoHonan",
        "KOL/KUBIS": "KOLKUBIS",
    }
    if komoditas_id in slash_replacements:
        sanitized_name = slash_replacements[komoditas_id]
        logger.info(f"Model name sanitized: {komoditas_id} -> {sanitized_name}")

    for prefix in MODEL_TYPE_PREFIXES:
        candidate_name = f"{prefix}{sanitized_name}"
        try:
            client.get_model_version_by_alias(name=candidate_name, alias="production")
            active_model_names[komoditas_id] = candidate_name
            logger.info(f"Production model found: {candidate_name}")
            return candidate_name
        except Exception:
            continue

    raise ValueError(f"No production model set for '{komoditas_id}' in MLflow.")

def get_model_on_demand(komoditas_id: str):
    if komoditas_id not in active_models:
        try:
            exact_model_name = resolve_model_name(komoditas_id)
            model_uri = f"models:/{exact_model_name}@production"
            logger.info(f"Downloading model {exact_model_name} from MLflow...")
            active_models[komoditas_id] = mlflow.pyfunc.load_model(model_uri)
            logger.info(f"Model {komoditas_id} cached in memory.")
        except Exception as e:
            logger.error(f"Failed to load model for {komoditas_id}: {e}")
            raise RuntimeError(f"Failed to load model {komoditas_id} from MLflow.") from e
    return active_models[komoditas_id]

def get_recent_history(komoditas_id: str, days: int = 50) -> pd.DataFrame:
    if not engine:
        raise RuntimeError("Database engine is not active.")

    with engine.connect() as conn:
        result = conn.execute(text("""
            SELECT tanggal_data, harga_per_kg
            FROM harga_historis
            WHERE komoditas = :k AND harga_per_kg > 0
            ORDER BY tanggal_data DESC
            LIMIT :limit
        """), {"k": komoditas_id, "limit": days}).fetchall()

        if not result:
            raise ValueError(f"No historical data in database for: {komoditas_id}")

        df = pd.DataFrame(result, columns=["tanggal_data", "harga_per_kg"])
        df["tanggal_data"] = pd.to_datetime(df["tanggal_data"])
        df = df.sort_values("tanggal_data").set_index("tanggal_data")
        return df

def _build_xgboost_features(series: np.ndarray, dates: pd.DatetimeIndex) -> pd.DataFrame:
    df = pd.DataFrame({"harga": series}, index=dates)

    for lag in range(1, 31):
        df[f"lag_{lag}"] = df["harga"].shift(lag)

    df["rolling_mean_7"]  = df["harga"].shift(1).rolling(7).mean()
    df["rolling_mean_30"] = df["harga"].shift(1).rolling(30).mean()
    df["rolling_std_7"]   = df["harga"].shift(1).rolling(7).std()
    df["rolling_std_30"]  = df["harga"].shift(1).rolling(30).std()
    df["month"]           = df.index.month
    df["dayofweek"]       = df.index.dayofweek
    df["days_since_start"] = (df.index - pd.to_datetime("2023-01-01")).days

    df.dropna(inplace=True)

    feature_cols = (
        [f"lag_{i}" for i in range(1, 31)]
        + ["rolling_mean_7", "rolling_mean_30", "rolling_std_7", "rolling_std_30"]
        + ["month", "dayofweek", "days_since_start"]
    )
    return df[feature_cols]

def _recursive_forecast_xgb(model, history_prices, history_dates, n_steps=30) -> list:
    history = list(history_prices)
    last_date = history_dates[-1]
    preds = []

    for step in range(n_steps):
        temp_series = np.array(history)
        temp_dates = pd.date_range(
            end=last_date + pd.Timedelta(days=step + 1),
            periods=len(temp_series),
            freq="D",
        )
        feat_df = _build_xgboost_features(temp_series, temp_dates)
        if len(feat_df) == 0:
            raise ValueError("Insufficient history for XGBoost lag/rolling features.")
        pred = float(model.predict(feat_df.iloc[[-1]].values)[0])
        preds.append(pred)
        history.append(pred)

    return preds

def predict_harga_satuan(komoditas_id: str) -> float:
    """Prediksi harga satuan untuk hari berikutnya. Dipanggil oleh routes/belanja.py."""
    exact_model_name = resolve_model_name(komoditas_id)
    model = get_model_on_demand(komoditas_id)

    if "XGBoost" in exact_model_name:
        history_df = get_recent_history(komoditas_id, 40)
        if history_df.empty:
            return 0.0
        feat_df = _build_xgboost_features(
            history_df["harga_per_kg"].values, history_df.index
        )
        return float(model.predict(feat_df.iloc[[-1]].values)[0])

    elif "SARIMA" in exact_model_name:
        return float(model._model_impl.predict(1)[0])

    elif "Prophet" in exact_model_name:
        # Prophet requires a DataFrame with column 'ds'
        history_df = get_recent_history(komoditas_id, 1)
        last_date = history_df.index[-1] if not history_df.empty else pd.Timestamp.today()
        future_df = pd.DataFrame({"ds": [last_date + pd.Timedelta(days=1)]})
        return float(model.predict(future_df)["yhat"].iloc[0])

    raise ValueError(f"Unknown model type for '{exact_model_name}'.")

def generate_forecast(komoditas_id: str) -> list:
    """Hasilkan 30-hari forecast. Dipanggil oleh routes/tren.py."""
    exact_model_name = resolve_model_name(komoditas_id)
    model = get_model_on_demand(komoditas_id)

    if "XGBoost" in exact_model_name:
        history_df = get_recent_history(komoditas_id, 50)
        if history_df.empty:
            return []
        return _recursive_forecast_xgb(
            model,
            history_df["harga_per_kg"].values,
            history_df.index,
            n_steps=30,
        )

    elif "SARIMA" in exact_model_name:
        return [float(x) for x in model._model_impl.predict(30)]

    elif "Prophet" in exact_model_name:
        history_df = get_recent_history(komoditas_id, 1)
        last_date = history_df.index[-1] if not history_df.empty else pd.Timestamp.today()
        future_df = pd.DataFrame({
            "ds": pd.date_range(start=last_date + pd.Timedelta(days=1), periods=30, freq="D")
        })
        return [float(x) for x in model.predict(future_df)["yhat"]]

    raise ValueError(f"Unknown model type for '{exact_model_name}'.")

def calculate_forecast_pct(forecast_prices: list) -> float:
    """Persentase perubahan harga dari hari pertama ke hari ke-30 forecast."""
    if not forecast_prices or len(forecast_prices) < 2:
        return 0.0
    harga_awal = float(forecast_prices[0])
    if harga_awal == 0:
        return 0.0
    return round(((float(forecast_prices[-1]) - harga_awal) / harga_awal) * 100, 2)