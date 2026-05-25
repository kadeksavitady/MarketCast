import mlflow
import os
import numpy as np
import pandas as pd
from sqlalchemy import text
from dotenv import load_dotenv
from src.core.config import logger, engine

# 1. Pastikan variabel lingkungan dari .env terbaca
load_dotenv()

# 2. Setup MLflow
os.environ["MLFLOW_TRACKING_USERNAME"] = "kadeksavitady"
os.environ["MLFLOW_TRACKING_PASSWORD"] = os.getenv("DAGSHUB_TOKEN")
mlflow.set_tracking_uri("https://dagshub.com/kadeksavitady/MarketCast.mlflow")

active_models = {}

# Peta 43 Komoditas ke Registry MLflow
MODEL_REGISTRY_MAP = {
    "Beras Premium": "XGBoost__Beras Premium",
    "Beras Medium": "XGBoost__Beras Medium",
    "Gula Kristal Putih": "XGBoost__Gula Kristal Putih",
    "Minyak Goreng Curah": "XGBoost__Minyak Goreng Curah",
    "Minyak Goreng Kemasan Premium": "XGBoost__Minyak Goreng Kemasan Premium",
    "Minyak Goreng Kemasan Sederhana": "XGBoost__Minyak Goreng Kemasan Sederhana",
    "Minyak Goreng MINYAKITA": "XGBoost__Minyak Goreng MINYAKITA",
    "Daging Sapi Paha Belakang": "SARIMA__Daging Sapi Paha Belakang",
    "Daging Ayam Ras": "XGBoost__Daging Ayam Ras",
    "Daging Ayam Kampung": "SARIMA__Daging Ayam Kampung",
    "Telur Ayam Ras": "XGBoost__Telur Ayam Ras",
    "Telur Ayam Kampung": "XGBoost__Telur Ayam Kampung",
    "Susu Kental Manis Merk Bendera": "XGBoost__Susu Kental Manis Merk Bendera",
    "Susu Kental Manis Merk Indomilk": "XGBoost__Susu Kental Manis Merk Indomilk",
    "Susu Bubuk Merk Bendera (Instant)": "SARIMA__Susu Bubuk Merk Bendera (Instant)",
    "Susu Bubuk Merk Indomilk (Instant)": "SARIMA__Susu Bubuk Merk Indomilk (Instant)",
    "Jagung Pipilan Kering": "XGBoost__Jagung Pipilan Kering",
    "Kedelai Impor": "XGBoost__Kedelai Impor",
    "Kedelai Lokal": "XGBoost__Kedelai Lokal",
    "KACANG HIJAU": "XGBoost__KACANG HIJAU",
    "KACANG TANAH": "XGBoost__KACANG TANAH",
    "KETELA POHON": "XGBoost__KETELA POHON",
    "Bata": "XGBoost__Bata",
    "Halus": "XGBoost__Halus",
    "Terigu Protein Sedang (Kemasan)": "XGBoost__Terigu Protein Sedang (Kemasan)",
    "Indomie Rasa Kari Ayam": "XGBoost__Indomie Rasa Kari Ayam",
    "Cabe Merah Keriting": "SARIMA__Cabe Merah Keriting",
    "Cabe Merah Besar": "SARIMA__Cabe Merah Besar",
    "Cabe Rawit Merah": "SARIMA__Cabe Rawit Merah",
    "Bawang Merah": "XGBoost__Bawang Merah",
    "Bawang Putih Sinco/Honan": "XGBoost__Bawang Putih Sinco/Honan",
    "KOL/KUBIS": "XGBoost__KOL/KUBIS",
    "KENTANG": "XGBoost__KENTANG",
    "Tomat Merah": "SARIMA__Tomat Merah",
    "WORTEL": "XGBoost__WORTEL",
    "BUNCIS": "XGBoost__BUNCIS",
    "Ikan Asin Teri": "SARIMA__Ikan Asin Teri",
    "Ikan Bandeng": "XGBoost__Ikan Bandeng",
    "Ikan Kembung": "XGBoost__Ikan Kembung",
    "Ikan Tuna": "XGBoost__Ikan Tuna",
    "Ikan Tongkol": "XGBoost__Ikan Tongkol",
    "Ikan Cakalang": "XGBoost__Ikan Cakalang",
    "GAS ELPIGI 3 Kg": "XGBoost__GAS ELPIGI 3 Kg"
}

def get_model_on_demand(komoditas_id: str):
    if komoditas_id not in active_models:
        try:
            exact_model_name = MODEL_REGISTRY_MAP.get(komoditas_id)
            if not exact_model_name:
                raise ValueError(f"Komoditas '{komoditas_id}' tidak ditemukan di peta registrasi.")
            
            model_uri = f"models:/{exact_model_name}@production"
            logger.info(f"⏳ Mengunduh model {exact_model_name} dari MLflow...")
            active_models[komoditas_id] = mlflow.pyfunc.load_model(model_uri)
            logger.info(f"✅ Model {komoditas_id} berhasil disimpan di cache memori.")
            
        except Exception as e:
            logger.error(f"❌ Gagal memuat model untuk {komoditas_id}: {e}")
            raise RuntimeError(f"Gagal memuat model {komoditas_id} dari server MLflow.") from e
    return active_models[komoditas_id]

# ==========================================
# FEATURE ENGINEERING DATA HISTORIS (XGBOOST)
# ==========================================

def get_recent_history(komoditas_id: str, days: int = 50) -> pd.DataFrame:
    if not engine: 
        raise RuntimeError("Koneksi database (Engine) tidak aktif.")
    
    with engine.connect() as conn:
        query = text("""
            SELECT tanggal_data, harga_per_kg 
            FROM harga_historis 
            WHERE komoditas = :k AND harga_per_kg > 0
            ORDER BY tanggal_data DESC 
            LIMIT :d
        """)
        result = conn.execute(query, {"k": komoditas_id, "d": days}).fetchall()
        
        if not result:
            raise ValueError(f"Tidak ada data historis di database Neon untuk komoditas: {komoditas_id}")
            
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
    
    start_date = pd.to_datetime("2023-01-01") 
    df["days_since_start"] = (df.index - start_date).days
    
    df.dropna(inplace=True)
    
    feature_cols = [f"lag_{i}" for i in range(1, 31)] + \
                   ["rolling_mean_7", "rolling_mean_30", "rolling_std_7", "rolling_std_30"] + \
                   ["month", "dayofweek", "days_since_start"]
                   
    return df[feature_cols]

def _recursive_forecast_xgb(model, history_prices, history_dates, n_steps=30) -> list:
    history = list(history_prices)
    last_date = history_dates[-1]
    preds = []
    
    for step in range(n_steps):
        temp_series = np.array(history)
        temp_dates  = pd.date_range(end=last_date + pd.Timedelta(days=step + 1), periods=len(temp_series), freq="D")
        
        feat_df = _build_xgboost_features(temp_series, temp_dates)
        if len(feat_df) == 0:
            raise ValueError("Data historis tidak mencukupi untuk menghitung lag/rolling window pada iterasi XGBoost.")
            
        last_row = feat_df.iloc[[-1]].values
        pred = float(model.predict(last_row)[0])
        preds.append(pred)
        history.append(pred)
        
    return preds

# ==========================================
# INTERFASE UTAMA ROUTER API
# ==========================================

def predict_harga_satuan(komoditas_id: str) -> float:
    """Dipanggil oleh routes/belanja.py"""
    exact_model_name = MODEL_REGISTRY_MAP.get(komoditas_id, "")
    model = get_model_on_demand(komoditas_id)

    if "XGBoost" in exact_model_name:
        history_df = get_recent_history(komoditas_id, 40)
        if history_df.empty: return 0.0
        
        history_prices = history_df["harga_per_kg"].values
        history_dates = history_df.index
        
        feat_df = _build_xgboost_features(history_prices, history_dates)
        last_row = feat_df.iloc[[-1]].values
        
        prediksi = model.predict(last_row)
        return float(prediksi[0])
        
    elif "SARIMA" in exact_model_name:
        prediksi = model._model_impl.predict(1)
        return float(prediksi[0])
        
    else:
        raise ValueError(f"Tipe model untuk '{exact_model_name}' tidak dikenal.")

def generate_forecast(komoditas_id: str, last_harga: float) -> list:
    """Dipanggil oleh routes/tren.py"""
    exact_model_name = MODEL_REGISTRY_MAP.get(komoditas_id, "")
    model = get_model_on_demand(komoditas_id)

    if "XGBoost" in exact_model_name:
        history_df = get_recent_history(komoditas_id, 50)
        if history_df.empty: return []
        
        history_prices = history_df["harga_per_kg"].values
        history_dates = history_df.index
        
        return _recursive_forecast_xgb(model, history_prices, history_dates, n_steps=30)
        
    elif "SARIMA" in exact_model_name:
        ramalan = model._model_impl.predict(30)
        return [float(x) for x in ramalan]
        
    else:
        raise ValueError(f"Tipe model untuk '{exact_model_name}' tidak dikenal.")