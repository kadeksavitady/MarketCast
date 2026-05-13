from contextlib import asynccontextmanager    
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import Dict, List, Optional
import pickle
import numpy as np
import os
import logging

# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ── Katalog Komoditas ─────────────────────────────────────────────────────────
COMMODITY_CATALOG: Dict[str, dict] = {
    # Beras
    "beras_premium":  {"nama": "Beras Premium",  "kategori": "Beras",         "satuan": "kg",    "harga_ref": 15_600,  "emoji": "🌾"},
    "beras_medium":   {"nama": "Beras Medium",   "kategori": "Beras",         "satuan": "kg",    "harga_ref": 12_000,  "emoji": "🌾"},
    "jagung":         {"nama": "Jagung",          "kategori": "Beras",         "satuan": "kg",    "harga_ref":  8_500,  "emoji": "🌽"},
    # Daging
    "daging_sapi":    {"nama": "Daging Sapi",    "kategori": "Daging",        "satuan": "kg",    "harga_ref": 124_000, "emoji": "🥩"},
    "daging_ayam":    {"nama": "Daging Ayam",    "kategori": "Daging",        "satuan": "kg",    "harga_ref":  35_000, "emoji": "🍗"},
    "daging_kambing": {"nama": "Daging Kambing", "kategori": "Daging",        "satuan": "kg",    "harga_ref":  85_000, "emoji": "🐑"},
    # Minyak Goreng
    "minyak_goreng":  {"nama": "Minyak Goreng",  "kategori": "Minyak Goreng", "satuan": "liter", "harga_ref":  18_000, "emoji": "🫙"},
    "minyak_kelapa":  {"nama": "Minyak Kelapa",  "kategori": "Minyak Goreng", "satuan": "liter", "harga_ref":  22_000, "emoji": "🥥"},
    # Telur
    "telur_ayam":     {"nama": "Telur Ayam",     "kategori": "Telur",         "satuan": "kg",    "harga_ref":  28_000, "emoji": "🥚"},
    "telur_bebek":    {"nama": "Telur Bebek",    "kategori": "Telur",         "satuan": "kg",    "harga_ref":  35_000, "emoji": "🥚"},
    # Bumbu
    "gula":           {"nama": "Gula Pasir",     "kategori": "Bumbu",         "satuan": "kg",    "harga_ref":  16_000, "emoji": "🍬"},
    "garam":          {"nama": "Garam",           "kategori": "Bumbu",         "satuan": "kg",    "harga_ref":   5_000, "emoji": "🧂"},
    "tepung":         {"nama": "Tepung Terigu",  "kategori": "Bumbu",         "satuan": "kg",    "harga_ref":  12_000, "emoji": "🌾"},
    # Ikan
    "ikan_lele":      {"nama": "Ikan Lele",      "kategori": "Ikan",          "satuan": "kg",    "harga_ref":  20_000, "emoji": "🐟"},
    "ikan_tongkol":   {"nama": "Ikan Tongkol",   "kategori": "Ikan",          "satuan": "kg",    "harga_ref":  25_000, "emoji": "🐟"},
    "ikan_salmon":    {"nama": "Ikan Salmon",    "kategori": "Ikan",          "satuan": "kg",    "harga_ref":  85_000, "emoji": "🐠"},
    "udang":          {"nama": "Udang",           "kategori": "Ikan",          "satuan": "kg",    "harga_ref":  60_000, "emoji": "🦐"},
}

SUBSTITUTION_MAP: Dict[str, str] = {
    "beras_premium":  "beras_medium",
    "beras_medium":   "jagung",
    "daging_sapi":    "daging_ayam",
    "daging_kambing": "daging_ayam",
    "minyak_kelapa":  "minyak_goreng",
    "telur_bebek":    "telur_ayam",
    "ikan_salmon":    "ikan_tongkol",
    "ikan_tongkol":   "ikan_lele",
    "udang":          "ikan_tongkol",
}

# ── Model ─────────────────────────────────────────────────────────────────────
MODEL_PATH = os.getenv("MODEL_PATH", "models/model.pkl")
model = None

# ── Lifespan (load & unload model) ───────────────────────────────────────────
# Harus didefinisikan SEBELUM FastAPI() dipanggil
@asynccontextmanager
async def lifespan(app: FastAPI):
    # STARTUP
    global model
    if os.path.exists(MODEL_PATH):
        with open(MODEL_PATH, "rb") as f:
            model = pickle.load(f)
        logger.info(f"✅ Model loaded from {MODEL_PATH}")
    else:
        logger.warning("⚠️  Model not found. Using harga_ref fallback.")

    yield  # server berjalan di sini

    # SHUTDOWN
    model = None
    logger.info("🛑 Model unloaded.")

# ── App (pakai lifespan yang sudah didefinisikan di atas) ─────────────────────
app = FastAPI(
    title="Budget Belanja API",
    description="Prediksi total belanja bahan pokok dan rekomendasi substitusi cerdas",
    version="1.0.0",
    lifespan=lifespan,              # ← aman karena lifespan sudah ada di atas
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Schemas ───────────────────────────────────────────────────────────────────
class CartItem(BaseModel):
    komoditas_id: str = Field(..., description="Slug komoditas, e.g. 'beras_premium'")
    jumlah: float     = Field(..., gt=0, description="Jumlah dalam satuan (kg / liter)")

class PredictRequest(BaseModel):
    budget: float             = Field(..., gt=0, description="Total budget dalam rupiah")
    keranjang: List[CartItem] = Field(..., min_length=1)

class ItemResult(BaseModel):
    komoditas_id: str
    nama: str
    kategori: str
    satuan: str
    jumlah: float
    harga_per_satuan: float
    subtotal: float

class SubstitusiItem(BaseModel):
    current_id: str
    current_nama: str
    current_harga: float    # per satuan
    substitute_id: str
    substitute_nama: str
    substitute_harga: float # per satuan
    potensi_hemat: float    # total hemat jika diganti

class PredictResponse(BaseModel):
    budget: float
    total_prediksi: float
    sisa_budget: float
    persentase_penggunaan: float
    status: str                         # "aman" | "perhatian" | "over_budget"
    detail_keranjang: List[ItemResult]
    smart_substitution: List[SubstitusiItem]
    potensi_hemat_total: float

class CommodityInfo(BaseModel):
    id: str
    nama: str
    kategori: str
    satuan: str
    harga_ref: float
    emoji: str

# ── Helpers ───────────────────────────────────────────────────────────────────
def predict_harga_satuan(komoditas_id: str) -> float:
    """
    Prediksi harga per satuan.
    Jika model ada → pakai model.
    Jika tidak → fallback ke harga_ref.
    ⚠️  Sesuaikan feature vector dengan waktu training!
    """
    info = COMMODITY_CATALOG[komoditas_id]
    if model is not None:
        X = np.array([[info["harga_ref"]]])   # ganti sesuai fitur training
        return float(model.predict(X)[0])
    return float(info["harga_ref"])


def build_substitution(
    keranjang: List[CartItem],
    detail: List[ItemResult],
) -> tuple[List[SubstitusiItem], float]:
    subs: List[SubstitusiItem] = []
    total_hemat = 0.0
    for item, result in zip(keranjang, detail):
        sub_id = SUBSTITUTION_MAP.get(item.komoditas_id)
        if not sub_id or sub_id not in COMMODITY_CATALOG:
            continue
        sub_harga = predict_harga_satuan(sub_id)
        hemat = (result.harga_per_satuan - sub_harga) * item.jumlah
        if hemat > 0:
            subs.append(SubstitusiItem(
                current_id=item.komoditas_id,
                current_nama=result.nama,
                current_harga=result.harga_per_satuan,
                substitute_id=sub_id,
                substitute_nama=COMMODITY_CATALOG[sub_id]["nama"],
                substitute_harga=sub_harga,
                potensi_hemat=round(hemat, 2),
            ))
            total_hemat += hemat
    return subs, round(total_hemat, 2)

# ── Endpoints ─────────────────────────────────────────────────────────────────
@app.get("/", tags=["Root"])
def root():
    return {"message": "Budget Belanja API 🚀"}


@app.get("/health", tags=["Health"])
def health():
    return {"status": "ok", "model_loaded": model is not None}


@app.get("/categories", tags=["Katalog"])
def list_categories():
    """Daftar kategori unik beserta jumlah komoditas."""
    cats: Dict[str, int] = {}
    for info in COMMODITY_CATALOG.values():
        cats[info["kategori"]] = cats.get(info["kategori"], 0) + 1
    return [{"kategori": k, "jumlah_komoditas": v} for k, v in cats.items()]


@app.get("/commodities", response_model=List[CommodityInfo], tags=["Katalog"])
def list_commodities(kategori: Optional[str] = None):
    """
    Semua komoditas tersedia.
    Filter opsional: ?kategori=Daging
    """
    return [
        CommodityInfo(id=slug, **info)
        for slug, info in COMMODITY_CATALOG.items()
        if not kategori or info["kategori"].lower() == kategori.lower()
    ]


@app.post("/predict", response_model=PredictResponse, tags=["Prediksi"])
def predict(payload: PredictRequest):
    # Validasi komoditas dikenal
    unknown = [i.komoditas_id for i in payload.keranjang
               if i.komoditas_id not in COMMODITY_CATALOG]
    if unknown:
        raise HTTPException(422, detail=f"Komoditas tidak dikenal: {unknown}")

    # Hitung per item
    detail: List[ItemResult] = []
    for item in payload.keranjang:
        info         = COMMODITY_CATALOG[item.komoditas_id]
        harga_satuan = predict_harga_satuan(item.komoditas_id)
        subtotal     = harga_satuan * item.jumlah
        detail.append(ItemResult(
            komoditas_id=item.komoditas_id,
            nama=info["nama"],
            kategori=info["kategori"],
            satuan=info["satuan"],
            jumlah=item.jumlah,
            harga_per_satuan=round(harga_satuan, 2),
            subtotal=round(subtotal, 2),
        ))

    total  = round(sum(d.subtotal for d in detail), 2)
    sisa   = round(payload.budget - total, 2)
    persen = round((total / payload.budget) * 100, 2)

    if persen <= 80:
        status = "aman"
    elif persen <= 100:
        status = "perhatian"
    else:
        status = "over_budget"

    subs, hemat = build_substitution(payload.keranjang, detail)

    return PredictResponse(
        budget=payload.budget,
        total_prediksi=total,
        sisa_budget=sisa,
        persentase_penggunaan=persen,
        status=status,
        detail_keranjang=detail,
        smart_substitution=subs,
        potensi_hemat_total=hemat,
    )

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=True)