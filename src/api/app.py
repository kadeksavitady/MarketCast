from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Dict, List, Optional
from sqlalchemy import create_engine, text
import pandas as pd
import numpy as np
import os
import logging
import mlflow
import dagshub
from dotenv import load_dotenv

# Load kredensial dari file .env
load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ── Config ──
DAGSHUB_REPO_OWNER = os.getenv("DAGSHUB_USER")
DAGSHUB_REPO_NAME  = os.getenv("DAGSHUB_REPO")
DATABASE_URL       = os.getenv("DATABASE_URL")
MODEL_NAME         = "cluster 1"

engine = create_engine(DATABASE_URL) if DATABASE_URL else None

try:
    dagshub.init(repo_owner=DAGSHUB_REPO_OWNER, repo_name=DAGSHUB_REPO_NAME, mlflow=True)
except Exception as e:
    logger.warning(f"DagsHub init failed: {e}")

# ── Katalog Komoditas ──
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
    'Ikan Cakalang': 'IKAN SEGAR', 'GAS ELPIGI 3 Kg': 'BARANG PENTING LAINNYA',
}

COMMODITY_CATALOG: Dict[str, dict] = {}
for nama, kategori in RAW_WHITELIST.items():
    slug = nama.lower().replace(" ", "_").replace("/", "_").replace("(", "").replace(")", "")
    COMMODITY_CATALOG[slug] = {
        "nama": nama,
        "kategori": kategori,
        "satuan": "tabung" if kategori == "BARANG PENTING LAINNYA" else "kg",
        "harga_ref": 15000,
    }

SUBSTITUTION_MAP: Dict[str, str] = {
    "beras_premium": "beras_medium", "minyak_goreng_kemasan_premium": "minyak_goreng_kemasan_sederhana",
    "minyak_goreng_kemasan_sederhana": "minyak_goreng_curah", "daging_sapi_paha_belakang": "daging_ayam_ras",
    "daging_ayam_kampung": "daging_ayam_ras", "telur_ayam_kampung": "telur_ayam_ras",
    "susu_kental_manis_merk_bendera": "susu_kental_manis_merk_indomilk",
    "susu_bubuk_merk_bendera_instant": "susu_bubuk_merk_indomilk_instant",
    "ikan_tuna": "ikan_tongkol", "ikan_tongkol": "ikan_kembung", "ikan_kembung": "ikan_bandeng",
}

# ── Lifespan & Model ──
model = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    global model
    try:
        model_uri = f"models:/{MODEL_NAME}/latest"
        logger.info(f"🚚 Memuat model {MODEL_NAME} dari DagsHub...")
        model = mlflow.pyfunc.load_model(model_uri)
        logger.info("✅ Model berhasil dimuat!")
    except Exception as e:
        logger.error(f"Gagal memuat model: {e}")
    yield
    model = None

app = FastAPI(lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

# ── Schemas ──
class CategoryInfo(BaseModel):
    kategori: str
    jumlah_komoditas: int

class CommodityInfo(BaseModel):
    id: str
    nama: str
    kategori: str
    satuan: str
    harga_ref: int

class CartItem(BaseModel):
    komoditas_id: str
    jumlah: float

class PredictRequest(BaseModel):
    budget: float
    keranjang: List[CartItem]

class ItemResult(BaseModel):
    komoditas_id: str
    nama: str
    jumlah: float
    satuan: str
    harga_per_satuan: float
    subtotal: float

class SubstitusiItem(BaseModel):
    current_id: str
    current_nama: str
    current_harga: float
    substitute_id: str
    substitute_nama: str
    substitute_harga: float
    potensi_hemat: float

class BudgetResponse(BaseModel):
    budget_user: float
    total_prediksi: float
    sisa_budget: float
    persentase_penggunaan: float
    status: str
    detail_keranjang: List[ItemResult]
    smart_substitution: List[SubstitusiItem]
    potensi_hemat_total: float

class TitikData(BaseModel):
    tanggal: str
    harga: float

class TrenResponse(BaseModel):
    komoditas_id: str
    nama_komoditas: str
    data_historis: List[TitikData]
    forecast_30_hari: List[TitikData]

# ── Helpers ──
def predict_harga_satuan(komoditas_id: str) -> float:
    info = COMMODITY_CATALOG.get(komoditas_id)
    if not info: return 0.0
    if model:
        try:
            X = pd.DataFrame([{"komoditas": info["nama"]}])
            pred = model.predict(X)
            res = pred[0]
            return float(res) if not isinstance(res, np.ndarray) else float(res[0])
        except: pass
    return float(info["harga_ref"])

def build_substitution(keranjang: List[CartItem], detail: List[ItemResult]):
    subs = []
    total_hemat = 0.0
    for item, result in zip(keranjang, detail):
        sub_id = SUBSTITUTION_MAP.get(item.komoditas_id)
        if not sub_id or sub_id not in COMMODITY_CATALOG: continue
        sub_harga = predict_harga_satuan(sub_id)
        hemat = (result.harga_per_satuan - sub_harga) * item.jumlah
        if hemat > 0:
            subs.append(SubstitusiItem(
                current_id=item.komoditas_id, current_nama=result.nama, current_harga=result.harga_per_satuan,
                substitute_id=sub_id, substitute_nama=COMMODITY_CATALOG[sub_id]["nama"], substitute_harga=sub_harga,
                potensi_hemat=round(hemat, 2),
            ))
            total_hemat += hemat
    return subs, round(total_hemat, 2)

def generate_forecast(nama_komoditas: str, last_harga: float, days: int = 30) -> List[TitikData]:
    from datetime import date, timedelta
    today = date.today()
    forecast = []
    if model:
        try:
            X = pd.DataFrame([{"komoditas": nama_komoditas, "hari_ke": i + 1} for i in range(days)])
            preds = model.predict(X)
            return [TitikData(tanggal=(today + timedelta(days=i+1)).strftime("%Y-%m-%d"), harga=round(float(p), 2)) for i, p in enumerate(preds)]
        except: pass
    
    harga = last_harga
    rng = np.random.default_rng(seed=42)
    for i in range(days):
        harga = harga * (1 + rng.uniform(-0.02, 0.02))
        forecast.append(TitikData(tanggal=(today + timedelta(days=i + 1)).strftime("%Y-%m-%d"), harga=round(harga, 2)))
    return forecast

# ── Endpoints ──
@app.get("/health")
def health():
    db_ok = False
    if engine:
        try:
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            db_ok = True
        except: pass
    return {"status": "ok", "model_loaded": model is not None, "database_connected": db_ok}

@app.get("/katalog/categories", response_model=List[CategoryInfo])
def list_categories():
    cats = {}
    for info in COMMODITY_CATALOG.values(): cats[info["kategori"]] = cats.get(info["kategori"], 0) + 1
    return [CategoryInfo(kategori=k, jumlah_komoditas=v) for k, v in cats.items()]

@app.get("/katalog/commodities", response_model=List[CommodityInfo])
def list_commodities(kategori: Optional[str] = None):
    return [CommodityInfo(id=slug, **info) for slug, info in COMMODITY_CATALOG.items() if not kategori or info["kategori"].upper() == kategori.upper()]

@app.post("/belanja/predict", response_model=BudgetResponse)
def predict_budget(payload: PredictRequest):
    detail = []
    total = 0.0
    for item in payload.keranjang:
        if item.komoditas_id not in COMMODITY_CATALOG: continue
        info = COMMODITY_CATALOG[item.komoditas_id]
        harga_satuan = predict_harga_satuan(item.komoditas_id)
        subtotal = harga_satuan * item.jumlah
        total += subtotal
        detail.append(ItemResult(komoditas_id=item.komoditas_id, nama=info["nama"], jumlah=item.jumlah, satuan=info["satuan"], harga_per_satuan=round(harga_satuan, 2), subtotal=round(subtotal, 2)))
    
    sisa = round(payload.budget - total, 2)
    persen = round((total / payload.budget) * 100, 2) if payload.budget > 0 else 0
    status = "aman" if persen <= 80 else "perhatian" if persen <= 100 else "over_budget"
    subs, hemat = build_substitution(payload.keranjang, detail)

    return BudgetResponse(budget_user=payload.budget, total_prediksi=round(total, 2), sisa_budget=sisa, persentase_penggunaan=persen, status=status, detail_keranjang=detail, smart_substitution=subs, potensi_hemat_total=hemat)

@app.get("/tren/komoditas", response_model=List[CommodityInfo])
def tren_komoditas_list(kategori: Optional[str] = None):
    return list_commodities(kategori)

@app.get("/tren/{komoditas_id}", response_model=TrenResponse)
def get_tren(komoditas_id: str):
    info = COMMODITY_CATALOG.get(komoditas_id)
    if not info: raise HTTPException(404, detail="Komoditas tidak ditemukan")
    if not engine: raise HTTPException(503, detail="Database tidak terhubung")

    df = pd.read_sql(text("SELECT tanggal_data, harga_per_kg FROM harga_historis WHERE komoditas = :nama ORDER BY tanggal_data DESC LIMIT 30"), engine, params={"nama": info["nama"]}).sort_values("tanggal_data")
    historis = [TitikData(tanggal=row["tanggal_data"].strftime("%Y-%m-%d"), harga=round(float(row["harga_per_kg"]), 2)) for _, row in df.iterrows()]
    last_harga = float(df["harga_per_kg"].iloc[-1]) if not df.empty else float(info["harga_ref"])
    
    return TrenResponse(komoditas_id=komoditas_id, nama_komoditas=info["nama"], data_historis=historis, forecast_30_hari=generate_forecast(info["nama"], last_harga))

# ── Eksekusi VS Code ──
if __name__ == "__main__":
    import uvicorn
    # Dengan memasukkan variabel 'app' langsung (bukan string "app:app"), 
    # kode ini bisa kamu jalankan dari folder mana pun tanpa error ModuleNotFound!
    uvicorn.run(app, host="127.0.0.1", port=8000)