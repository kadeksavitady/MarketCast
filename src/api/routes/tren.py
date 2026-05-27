from fastapi import APIRouter, HTTPException
from typing import List, Optional
import pandas as pd
from sqlalchemy import text
from src.core.config import engine
from src.business_logic.katalog import COMMODITY_CATALOG
from src.business_logic.ml_service import generate_forecast
from src.api.schemas import TrenResponse, CommodityInfo, TitikData

router = APIRouter()

@router.get("/tren/komoditas", response_model=List[CommodityInfo])
def tren_komoditas_list(kategori: Optional[str] = None):
    return [CommodityInfo(id=slug, **info) for slug, info in COMMODITY_CATALOG.items() if not kategori or info["kategori"].upper() == kategori.upper()]

@router.get("/tren/{komoditas_id}", response_model=TrenResponse)
def get_tren(komoditas_id: str, hari: int = 90):
    info = COMMODITY_CATALOG.get(komoditas_id)
    if not info: raise HTTPException(404, detail="Komoditas tidak ditemukan")
    if not engine: raise HTTPException(503, detail="Database tidak terhubung")

    # Ambil data dalam rentang hari yang diminta
    df = pd.read_sql(
        text("""
            SELECT tanggal_data, harga_per_kg 
            FROM harga_historis 
            WHERE komoditas = :nama 
            AND tanggal_data >= CURRENT_DATE - INTERVAL '1 day' * :hari
            AND harga_per_kg > 0
            ORDER BY tanggal_data ASC
        """),
        engine, params={"nama": info["nama"], "hari": hari}
    )

    # Fallback: kalau rentang hari kosong, ambil N data terbaru yang valid
    if df.empty:
        df = pd.read_sql(
            text("""
                SELECT tanggal_data, harga_per_kg
                FROM harga_historis
                WHERE komoditas = :nama
                AND harga_per_kg > 0
                ORDER BY tanggal_data DESC
                LIMIT :hari
            """),
            engine, params={"nama": info["nama"], "hari": hari}
        ).sort_values("tanggal_data")

    # Bangun rentang tanggal penuh lalu forward-fill harga yang kosong
    if not df.empty:
        df["tanggal_data"] = pd.to_datetime(df["tanggal_data"])
        df = df.set_index("tanggal_data")

        # Buat index tanggal lengkap dari tanggal pertama sampai terakhir
        full_range = pd.date_range(start=df.index.min(), end=df.index.max(), freq="D")
        df = df.reindex(full_range)

        # Forward-fill: hari tanpa data pakai harga hari sebelumnya
        df["harga_per_kg"] = df["harga_per_kg"].ffill()
        df = df.reset_index().rename(columns={"index": "tanggal_data"})

    historis = [
        TitikData(
            tanggal=row["tanggal_data"].strftime("%Y-%m-%d"),
            harga=round(float(row["harga_per_kg"]), 2)
        )
        for _, row in df.iterrows()
    ] if not df.empty else []

    last_harga = float(df["harga_per_kg"].iloc[-1]) if not df.empty else float(info["harga_ref"])
    
    # 🚨 PERBAIKAN 1: Tangkap error dari MLflow
    try:
        forecast_prices = generate_forecast(info["nama"], last_harga)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Gagal menyusun ramalan: {str(e)}")
    
    # 🚨 PERBAIKAN 2: Rakit tanggal kalender untuk angka ramalan
    forecast_models = []
    if historis:
        last_date_obj = pd.to_datetime(historis[-1].tanggal)
    else:
        last_date_obj = pd.Timestamp.today()
        
    for i, price in enumerate(forecast_prices):
        # Tambahkan hari (1 sampai 30) dari tanggal terakhir
        next_date = (last_date_obj + pd.Timedelta(days=i+1)).strftime("%Y-%m-%d")
        forecast_models.append(TitikData(tanggal=next_date, harga=round(price, 2)))
    
    return TrenResponse(
        komoditas_id=komoditas_id, nama_komoditas=info["nama"], 
        data_historis=historis, forecast_30_hari=forecast_models
    )