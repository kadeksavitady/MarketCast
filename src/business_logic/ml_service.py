import pandas as pd
import numpy as np
from datetime import date, timedelta
from src.business_logic.katalog import COMMODITY_CATALOG

# Global variable untuk menyimpan model yang sudah di-load
active_model = None

def set_model(model):
    global active_model
    active_model = model

def predict_harga_satuan(komoditas_id: str) -> float:
    info = COMMODITY_CATALOG.get(komoditas_id)
    if not info: return 0.0
    if active_model:
        try:
            X = pd.DataFrame([{"komoditas": info["nama"]}])
            pred = active_model.predict(X)
            res = pred[0]
            return float(res) if not isinstance(res, np.ndarray) else float(res[0])
        except: pass
    return float(info["harga_ref"])

def generate_forecast(nama_komoditas: str, last_harga: float, days: int = 30) -> list:
    today = date.today()
    forecast = []
    if active_model:
        try:
            X = pd.DataFrame([{"komoditas": nama_komoditas, "hari_ke": i + 1} for i in range(days)])
            preds = active_model.predict(X)
            return [{"tanggal": (today + timedelta(days=i+1)).strftime("%Y-%m-%d"), "harga": round(float(p), 2)} for i, p in enumerate(preds)]
        except: pass
    
    harga = last_harga
    rng = np.random.default_rng(seed=42)
    for i in range(days):
        harga = harga * (1 + rng.uniform(-0.02, 0.02))
        forecast.append({"tanggal": (today + timedelta(days=i + 1)).strftime("%Y-%m-%d"), "harga": round(harga, 2)})
    return forecast