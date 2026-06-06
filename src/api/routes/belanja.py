from fastapi import APIRouter, HTTPException
from src.business_logic.katalog import COMMODITY_CATALOG
from src.business_logic.ml_service import predict_harga_satuan
from src.business_logic.substitusi import build_substitution_dynamic
from src.api.schemas import PredictRequest, BudgetResponse, ItemResult
from src.core.config import logger

router = APIRouter()

@router.post("/belanja/predict", response_model=BudgetResponse)
def predict_budget(payload: PredictRequest):
    detail = []
    total = 0.0
    for item in payload.keranjang:
        if item.komoditas_id not in COMMODITY_CATALOG: 
            continue
            
        info = COMMODITY_CATALOG[item.komoditas_id]
        
        try:
            harga_satuan = predict_harga_satuan(info["nama"])
        except Exception as e:
            logger.error(f"Prediction error for {info['nama']}: {e}")
            raise HTTPException(status_code=400, detail=f"Gagal memprediksi harga {info['nama']}: {str(e)}")
            
        subtotal = harga_satuan * item.jumlah
        total += subtotal
        detail.append(ItemResult(
            komoditas_id=item.komoditas_id, nama=info["nama"], jumlah=item.jumlah, 
            satuan=info["satuan"], harga_per_satuan=round(harga_satuan, 2), subtotal=round(subtotal, 2)
        ))
    
    sisa = round(payload.budget - total, 2)
    persen = round((total / payload.budget) * 100, 2) if payload.budget > 0 else 0
    status = "aman" if persen <= 80 else "perhatian" if persen <= 100 else "over_budget"
    
    subs, hemat = build_substitution_dynamic(payload.keranjang, detail)

    return BudgetResponse(
        budget_user=payload.budget, total_prediksi=round(total, 2), sisa_budget=sisa, 
        persentase_penggunaan=persen, status=status, detail_keranjang=detail, 
        smart_substitution=subs, potensi_hemat_total=hemat
    )