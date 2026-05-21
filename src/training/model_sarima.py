<<<<<<< HEAD
from contextlib import asynccontextmanager
from sqlalchemy import create_engine
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import Dict, List, Optional
=======
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
>>>>>>> e5c8a0de5b1b05976f1c386cf9a5c5da8aa66e8a
import pandas as pd
import numpy as np
import os
import logging
import mlflow
import dagshub
from dotenv import load_dotenv

# Ambil data dari file .env
load_dotenv()

<<<<<<< HEAD
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
=======
from config import (MLFLOW_TRACKING_URI, init_mlflow,
                    FORECAST_DAYS, get_logger, compute_metrics,
                    get_cluster_short)
>>>>>>> e5c8a0de5b1b05976f1c386cf9a5c5da8aa66e8a

# --- CONFIG ---
DAGSHUB_REPO_OWNER = os.getenv("DAGSHUB_USER")
DAGSHUB_REPO_NAME = os.getenv("DAGSHUB_REPO")
DATABASE_URL = os.getenv("DATABASE_URL")
MODEL_NAME = "cluster 1" 

# Inisialisasi Database Neon
engine = create_engine(DATABASE_URL) if DATABASE_URL else None

# Inisialisasi DagsHub & MLflow
try:
    dagshub.init(repo_owner=DAGSHUB_REPO_OWNER, repo_name=DAGSHUB_REPO_NAME, mlflow=True)
except Exception as e:
    logger.warning(f"⚠️ DagsHub Connection Issue: {e}")

<<<<<<< HEAD
model = None
=======
def train_sarima(komoditas: str, data: dict, 
                 mlflow_experiment: str = None,
                 max_p: int = 3, max_q: int = 3,
                 max_P: int = 2, max_Q: int = 2
                 ) -> dict:
    """
    Train SARIMA untuk satu komoditas dan log ke MLflow.
>>>>>>> e5c8a0de5b1b05976f1c386cf9a5c5da8aa66e8a

# --- KATALOG OTOMATIS (Sesuai Whitelist-mu) ---
RAW_WHITELIST = {
    'Beras Premium': 'BERAS', 'Beras Medium': 'BERAS', 'Gula Kristal Putih': 'GULA',
    'Minyak Goreng Curah': 'MINYAK GORENG', 'Minyak Goreng Kemasan Premium': 'MINYAK GORENG',
    'Minyak Goreng Kemasan Sederhana': 'MINYAK GORENG', 'Minyak Goreng MINYAKITA': 'MINYAK GORENG',
    'Daging Sapi Paha Belakang': 'DAGING', 'Daging Ayam Ras': 'DAGING', 'Daging Ayam Kampung': 'DAGING',
    'Telur Ayam Ras': 'TELUR', 'Telur Ayam Kampung': 'TELUR',
    'Susu Kental Manis Merk Bendera': 'SUSU', 'Susu Kental Manis Merk Indomilk': 'SUSU',
    'Susu Bubuk Merk Bendera (Instant)': 'SUSU', 'Susu Bubuk Merk Indomilk (Instant)': 'SUSU',
    'Jagung Pipilan Kering': 'PALAWIJA', 'Kedelai Impor': 'PALAWIJA', 'Kedelai Lokal': 'PALAWIJA',
    'KACANG HIJAU': 'PALAWIJA', 'KACANG TANAH': 'PALAWIJA', 'KETELA POHON': 'PALAWIJA',
    'Bata': 'GARAM', 'Halus': 'GARAM', 'Terigu Protein Sedang (Kemasan)': 'TEPUNG',
    'Indomie Rasa Kari Ayam': 'MIE INSTAN', 'Cabe Merah Keriting': 'CABE',
    'Cabe Merah Besar': 'CABE', 'Cabe Rawit Merah': 'CABE', 'Bawang Merah': 'BAWANG',
    'Bawang Putih Sinco/Honan': 'BAWANG', 'Ikan Asin Teri': 'IKAN ASIN',
    'KOL/KUBIS': 'SAYUR MAYUR', 'KENTANG': 'SAYUR MAYUR', 'Tomat Merah': 'SAYUR MAYUR',
    'WORTEL': 'SAYUR MAYUR', 'BUNCIS': 'SAYUR MAYUR', 'Ikan Bandeng': 'IKAN SEGAR',
    'Ikan Kembung': 'IKAN SEGAR', 'Ikan Tuna': 'IKAN SEGAR', 'Ikan Tongkol': 'IKAN SEGAR',
    'Ikan Cakalang': 'IKAN SEGAR', 'GAS ELPIGI 3 Kg': 'BARANG PENTING LAINNYA'
}

<<<<<<< HEAD
COMMODITY_CATALOG = {}
for nama, kategori in RAW_WHITELIST.items():
    slug = nama.lower().replace(" ", "_").replace("/", "_").replace("(", "").replace(")", "")
    COMMODITY_CATALOG[slug] = {
        "nama": nama, 
        "kategori": kategori, 
        "satuan": "kg" if kategori != "BARANG PENTING LAINNYA" else "tabung", 
        "harga_ref": 15000
=======
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
>>>>>>> e5c8a0de5b1b05976f1c386cf9a5c5da8aa66e8a
    }

# ── Lifespan (Startup/Shutdown) ──
@asynccontextmanager
async def lifespan(app: FastAPI):
    global model
    try:
        model_uri = f"models:/{MODEL_NAME}/latest"
        logger.info(f"🚚 Memuat model {MODEL_NAME} dari Registry...")
        model = mlflow.pyfunc.load_model(model_uri)
        logger.info("✅ Model Berhasil Dimuat!")
    except Exception as e:
        logger.error(f"❌ Error saat memuat model: {e}")
    yield
    model = None

app = FastAPI(
    title="MarketCast API - Swagger Mode", 
    description="Dokumentasi API untuk Prediksi Harga Bahan Pokok",
    version="1.0.0",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Pydantic Schemas (Agar Swagger Cantik) ──
class TitikGrafik(BaseModel):
    tanggal: str
    harga: float

class GrafikResponse(BaseModel):
    komoditas_id: str
    nama_komoditas: str
    data_historis: List[TitikGrafik]

class CartItem(BaseModel):
    komoditas_id: str = Field(..., example="beras_premium")
    jumlah: float = Field(..., example=2.5)

class PredictRequest(BaseModel):
    budget: float = Field(..., example=100000)
    keranjang: List[CartItem]

class ItemResult(BaseModel):
    komoditas_id: str
    nama: str
    jumlah: float
    harga_per_satuan: float
    subtotal: float

class PredictResponse(BaseModel):
    budget_user: float
    total_prediksi: float
    sisa_budget: float
    status: str # "aman" | "perhatian" | "over_budget"
    detail_keranjang: List[ItemResult]

# --- HELPERS ---
def predict_harga_satuan(komoditas_id: str) -> float:
    info = COMMODITY_CATALOG.get(komoditas_id)
    if model and info:
        try:
            X_input = pd.DataFrame([{"komoditas": info["nama"]}])
            pred = model.predict(X_input)
            res = pred[0]
            return float(res) if not isinstance(res, np.ndarray) else float(res[0])
        except Exception as e:
            logger.error(f"Prediction error: {e}")
    return float(info["harga_ref"]) if info else 0.0

# --- ENDPOINTS ---

@app.get("/commodities", tags=["Katalog"])
def get_commodities():
    """Mengambil daftar seluruh ID komoditas untuk input di Frontend/Swagger."""
    return [{"id": k, **v} for k, v in COMMODITY_CATALOG.items()]

@app.get("/grafik/{komoditas_id}", response_model=GrafikResponse, tags=["Visualisasi"])
def get_grafik(komoditas_id: str):
    """Menarik data historis 30 hari terakhir dari Neon Cloud."""
    info = COMMODITY_CATALOG.get(komoditas_id)
    if not info or not engine: 
        raise HTTPException(status_code=404, detail="Komoditas tidak ditemukan atau DB offline")
    
    query = f"SELECT tanggal_data, harga_per_kg FROM harga_historis WHERE komoditas = '{info['nama']}' ORDER BY tanggal_data DESC LIMIT 30"
    df = pd.read_sql(query, engine).sort_values('tanggal_data')
    
    pts = [TitikGrafik(tanggal=r['tanggal_data'].strftime("%Y-%m-%d"), harga=r['harga_per_kg']) for _, r in df.iterrows()]
    return GrafikResponse(komoditas_id=komoditas_id, nama_komoditas=info['nama'], data_historis=pts)

@app.post("/predict", response_model=PredictResponse, tags=["Analisis"])
def predict_budget(payload: PredictRequest):
    """Menerima budget dan daftar belanja, lalu memberikan estimasi harga model."""
    detail_keranjang = []
    total_estimasi = 0.0
    
    for item in payload.keranjang:
        if item.komoditas_id not in COMMODITY_CATALOG:
            continue
            
        harga = predict_harga_satuan(item.komoditas_id)
        subtotal = harga * item.jumlah
        total_estimasi += subtotal
        
        detail_keranjang.append(ItemResult(
            komoditas_id=item.komoditas_id,
            nama=COMMODITY_CATALOG[item.komoditas_id]["nama"],
            jumlah=item.jumlah,
            harga_per_satuan=round(harga, 2),
            subtotal=round(subtotal, 2)
        ))
    
    sisa = payload.budget - total_estimasi
    persen = (total_estimasi / payload.budget) * 100 if payload.budget > 0 else 0
    
    if persen <= 80: status = "aman"
    elif persen <= 100: status = "perhatian"
    else: status = "over_budget"
    
    return PredictResponse(
        budget_user=payload.budget,
        total_prediksi=round(total_estimasi, 2),
        sisa_budget=round(sisa, 2),
        status=status,
        detail_keranjang=detail_keranjang
    )