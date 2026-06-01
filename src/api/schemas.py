from pydantic import BaseModel
from typing import List, Optional

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
    forecast_trend_percentage: float