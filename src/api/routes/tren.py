from fastapi import APIRouter, HTTPException
from typing import List, Optional
import pandas as pd
from sqlalchemy import text
from src.core.config import engine
from src.business_logic.katalog import COMMODITY_CATALOG
from src.business_logic.ml_service import generate_forecast, hitung_tren_forecast, get_clustering_data
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

    # Step 1: Ambil data periode sekarang (termasuk yang 0)
    df = pd.read_sql(text("""
        SELECT tanggal_data, harga_per_kg 
        FROM harga_historis 
        WHERE komoditas = :nama 
        AND tanggal_data >= CURRENT_DATE - INTERVAL '1 day' * :hari
        ORDER BY tanggal_data ASC
    """), engine, params={"nama": info["nama"], "hari": hari})

    # Step 2: Cari harga terakhir yang valid (bisa dari kapan saja)
    last_valid = pd.read_sql(text("""
        SELECT harga_per_kg FROM harga_historis
        WHERE komoditas = :nama AND harga_per_kg > 0
        ORDER BY tanggal_data DESC LIMIT 1
    """), engine, params={"nama": info["nama"]})

    # Step 3: Ganti 0 dengan NaN, isi dari harga terakhir valid
    if not df.empty:
        df["tanggal_data"] = pd.to_datetime(df["tanggal_data"])
        df.loc[df["harga_per_kg"] == 0, "harga_per_kg"] = None
        if not last_valid.empty:
            fill_price = float(last_valid["harga_per_kg"].iloc[0]) if not last_valid.empty else float(info["harga_ref"])
            df["harga_per_kg"] = df["harga_per_kg"].fillna(fill_price).ffill()

    historis = [
        TitikData(
            tanggal=row["tanggal_data"].strftime("%Y-%m-%d"),
            harga=round(float(row["harga_per_kg"]), 2)
        )
        for _, row in df.iterrows()
    ] if not df.empty else []

    last_harga = float(df["harga_per_kg"].iloc[-1]) if not df.empty else float(info["harga_ref"])
    
    # Tangkap error dari MLflow
    try:
        forecast_prices = generate_forecast(info["nama"], last_harga)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Gagal menyusun ramalan: {str(e)}")
    
    # Rakit tanggal kalender untuk angka ramalan
    forecast_models = []
    if historis:
        last_date_obj = pd.to_datetime(historis[-1].tanggal)
    else:
        last_date_obj = pd.Timestamp.today()
        
    for i, price in enumerate(forecast_prices):
        # Tambahkan hari (1 sampai 30) dari tanggal terakhir
        next_date = (last_date_obj + pd.Timedelta(days=i+1)).strftime("%Y-%m-%d")
        forecast_models.append(TitikData(tanggal=next_date, harga=round(price, 2)))

    persentase_ramalan = hitung_tren_forecast(forecast_prices)
    
    return TrenResponse(
        komoditas_id=komoditas_id,
        nama_komoditas=info["nama"], 
        data_historis=historis, 
        forecast_30_hari=forecast_models,
        forecast_trend_percentage=persentase_ramalan
    )

@router.get("/funfact/{komoditas_id}")
def get_fun_fact(komoditas_id: str):
    # BACA KATALOG DULU UNTUK MENGUBAH SLUG (beras-premium) MENJADI NAMA ASLI (Beras Premium)
    info = COMMODITY_CATALOG.get(komoditas_id)
    if not info:
        return {"pesan": "Komoditas tidak ditemukan di katalog."}
        
    nama_asli = info["nama"]
    satuan_barang = info.get("satuan", "satuan")
    
    # Panggil data CSV menggunakan NAMA ASLI
    data_cluster = get_clustering_data()
    info_komoditas = data_cluster.get(nama_asli)
    
    if not info_komoditas:
        return {"pesan": "Data informasi pasar belum tersedia untuk komoditas ini."}
        
    # Ambil nilai spesifik untuk komoditas yang sedang dicari
    cv_value = float(info_komoditas['cv'])
    trend_slope = float(info_komoditas['trend_slope'])
    mean_harga = float(info_komoditas['mean'])
    
    # A. Menerjemahkan Tingkat Fluktuasi (CV)
    if cv_value < 0.1:
        karakter_cv = "sangat stabil dan jarang mengalami perubahan harga yang drastis"
    elif cv_value <= 0.25:
        karakter_cv = "cukup stabil, meskipun terkadang ada sedikit penyesuaian harga yang wajar"
    else:
        karakter_cv = "memiliki tingkat fluktuasi tinggi, di mana harga bisa naik atau turun dengan cepat"
        
    # B. Menerjemahkan Arah Tren (Trend Slope)
    if trend_slope > 0.01:
        arah_tren = "menunjukkan tren kenaikan secara perlahan"
    elif trend_slope < -0.01:
        arah_tren = "menunjukkan tren penurunan harga"
    else:
        arah_tren = "cenderung datar tanpa pergerakan yang berarti"
    
    kalimat_fun_fact = (
        f"Saat ini, rata-rata harga wajar untuk {nama_asli} berada di kisaran Rp{mean_harga:,.0f} per {satuan_barang}. "
        f"Berdasarkan catatan historis, harga komoditas ini {karakter_cv}. Untuk saat ini, pergerakannya di pasar {arah_tren}."
    )
    
    return {
        "komoditas": nama_asli,
        "label_cerdas_ml": info_komoditas.get("cluster_label", ""),
        "detail_cluster": info_komoditas,
        "teks_fun_fact": kalimat_fun_fact
    }