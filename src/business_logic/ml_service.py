import mlflow
import os
import numpy as np
import pandas as pd
from sqlalchemy import text
from dotenv import load_dotenv
from src.core.config import logger, engine
from mlflow.tracking import MlflowClient

# 1. Pastikan variabel lingkungan dari .env terbaca
load_dotenv()

# 2. Setup MLflow
os.environ["MLFLOW_TRACKING_USERNAME"] = "kadeksavitady"
os.environ["MLFLOW_TRACKING_PASSWORD"] = os.getenv("DAGSHUB_TOKEN")
mlflow.set_tracking_uri("https://dagshub.com/kadeksavitady/MarketCast.mlflow")

active_models = {}

# 1. Tempat menyimpan model dan namanya secara otomatis (Cache)
active_models = {}
active_model_names = {}

# 2. Tiga awalan nama model
KANDIDAT_MODEL = ["XGBoost__", "SARIMA__", "Prophet__"]

def dapatkan_nama_model_otomatis(komoditas_id: str) -> str:
    """Fungsi Resepsionis: Mencari tahu apa model terbaik saat ini di DagsHub"""
    
    # Kalau namanya sudah pernah dicari, langsung ambil dari cache
    if komoditas_id in active_model_names:
        return active_model_names[komoditas_id]
        
    client = MlflowClient()
    
    # Cek satu-satu (XGBoost, SARIMA, Prophet)
    for tipe in KANDIDAT_MODEL:
        nama_coba_coba = f"{tipe}{komoditas_id}"
        try:
            # Cari model yang statusnya production
            client.get_model_version_by_alias(name=nama_coba_coba, alias="production")
            
            active_model_names[komoditas_id] = nama_coba_coba # Simpan nama model yang ditemukan ke cache
            logger.info(f"Menemukan model production: {nama_coba_coba}")
            return nama_coba_coba
            
        except Exception:
            # Kalau Resepsionis bilang "Nggak ada!", lanjut coba pintu berikutnya
            continue
            
    # Kalau ketiga tipe sudah dicoba dan tidak ada satupun yang 'production'
    raise ValueError(f"Waduh, Laila belum nge-set model production untuk {komoditas_id} di MLflow!")

def get_model_on_demand(komoditas_id: str):
    if komoditas_id not in active_models:
        try:
            exact_model_name = dapatkan_nama_model_otomatis(komoditas_id)
            
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
    exact_model_name = dapatkan_nama_model_otomatis(komoditas_id)
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

    elif "Prophet" in exact_model_name:
        # Prophet butuh tanggal esok hari di dalam DataFrame bernama 'ds'
        history_df = get_recent_history(komoditas_id, 1)
        last_date = history_df.index[-1] if not history_df.empty else pd.Timestamp.today()
        
        future_df = pd.DataFrame({'ds': [last_date + pd.Timedelta(days=1)]})
        prediksi = model.predict(future_df)
        
        # Prophet mengembalikan dataframe, hasil prediksi ada di kolom 'yhat'
        return float(prediksi['yhat'].iloc[0])
        
    else:
        raise ValueError(f"Tipe model untuk '{exact_model_name}' tidak dikenal.")

def generate_forecast(komoditas_id: str, last_harga: float) -> list:
    """Dipanggil oleh routes/tren.py"""
    exact_model_name = dapatkan_nama_model_otomatis(komoditas_id)
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
    
    elif "Prophet" in exact_model_name:
        # Prophet butuh rentang tanggal (30 hari ke depan) di kolom 'ds'
        history_df = get_recent_history(komoditas_id, 1)
        last_date = history_df.index[-1] if not history_df.empty else pd.Timestamp.today()
        
        future_dates = pd.date_range(start=last_date + pd.Timedelta(days=1), periods=30, freq="D")
        future_df = pd.DataFrame({'ds': future_dates})
        
        prediksi = model.predict(future_df)
        
        # Ekstrak seluruh nilai dari kolom 'yhat' menjadi list
        return [float(x) for x in prediksi['yhat']]
        
    else:
        raise ValueError(f"Tipe model untuk '{exact_model_name}' tidak dikenal.")

def hitung_tren_forecast(list_harga_prediksi: list) -> float:
    """Menghitung persentase kenaikan/penurunan harga dari hari 1 ke hari 30"""
    if not list_harga_prediksi or len(list_harga_prediksi) < 2:
        return 0.0
    
    harga_awal = float(list_harga_prediksi[0])
    harga_akhir = float(list_harga_prediksi[-1])
    
    if harga_awal == 0:
        return 0.0
        
    persentase = ((harga_akhir - harga_awal) / harga_awal) * 100
    return round(persentase, 2)