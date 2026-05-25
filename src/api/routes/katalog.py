from fastapi import APIRouter
from typing import List, Optional
from sqlalchemy import text
from src.core.config import engine
from src.business_logic.katalog import COMMODITY_CATALOG
from src.business_logic.ml_service import active_models
from src.api.schemas import CategoryInfo, CommodityInfo

router = APIRouter()

@router.get("/health")
def health():
    db_ok = False
    if engine:
        try:
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            db_ok = True
        except: pass
    return {"status": "ok", "model_loaded": len(active_models) > 0, "database_connected": db_ok}

@router.get("/katalog/categories", response_model=List[CategoryInfo])
def list_categories():
    cats = {}
    for info in COMMODITY_CATALOG.values(): cats[info["kategori"]] = cats.get(info["kategori"], 0) + 1
    return [CategoryInfo(kategori=k, jumlah_komoditas=v) for k, v in cats.items()]

@router.get("/katalog/commodities", response_model=List[CommodityInfo])
def list_commodities(kategori: Optional[str] = None):
    hasil_filter = []
    
    for slug, info in COMMODITY_CATALOG.items():
        # Jika harga masih 0 (data kosong), jangan dikirim ke frontend
        if info["harga_ref"] <= 0:
            continue
            
        # Filter Kategori (kalau diklik dari frontend)
        if kategori and info["kategori"].upper() != kategori.upper():
            continue
            
        # Harga per satuan dikali faktor
        harga_tampil = info["harga_ref"] * info["faktor_konversi"]
        
        hasil_filter.append(CommodityInfo(
            id=slug, 
            nama=info["nama"], 
            kategori=info["kategori"], 
            satuan=info["satuan"], 
            harga_ref=int(harga_tampil) # Kirim harga yang sudah dikonversi
        ))
        
    return hasil_filter