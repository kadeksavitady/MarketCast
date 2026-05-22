import pandas as pd
import numpy as np
from datetime import date, timedelta
from src.business_logic.katalog import COMMODITY_CATALOG

active_models = {}

def set_model(cluster_key: str, model):
    active_models[cluster_key] = model

def predict_harga_satuan(komoditas_id: str) -> float:
    info = COMMODITY_CATALOG.get(komoditas_id)
    if not info: return 0.0

    target_cluster = info["cluster"]               # 1. Cek komoditas ini masuk cluster mana?
    model_spesifik = active_models.get(target_cluster) # 2. Ambil model khusus untuk cluster tersebut

    if model_spesifik:
        try:
            X = pd.DataFrame([{"komoditas": info["nama"]}])
            pred = model_spesifik.predict(X)
            res = pred[0]
            return float(res) if not isinstance(res, np.ndarray) else float(res[0])
        except: pass
    
    return float(info["harga_ref"])

def generate_forecast(nama_komoditas: str, last_harga: float, days: int = 30) -> list:
    today = date.today()
    forecast = []

    # Cari slug/ID dari nama komoditas
    slug = nama_komoditas.lower().replace(" ", "_").replace("/", "_").replace("(", "").replace(")", "")
    info = COMMODITY_CATALOG.get(slug, {})
    target_cluster = info.get("cluster", "cluster_1")
    
    model_spesifik = active_models.get(target_cluster)
    
    if model_spesifik:
        try:
            X = pd.DataFrame([{"komoditas": nama_komoditas, "hari_ke": i + 1} for i in range(days)])
            preds = model_spesifik.predict(X)
            return [{"tanggal": (today + timedelta(days=i+1)).strftime("%Y-%m-%d"), "harga": round(float(p), 2)} for i, p in enumerate(preds)]
        except: pass
    
    # Fallback Randomizer
    harga = last_harga
    rng = np.random.default_rng(seed=42)
    for i in range(days):
        harga = harga * (1 + rng.uniform(-0.02, 0.02))
        forecast.append({"tanggal": (today + timedelta(days=i + 1)).strftime("%Y-%m-%d"), "harga": round(harga, 2)})
    return forecast