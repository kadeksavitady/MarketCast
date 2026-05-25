from typing import List, Tuple
from src.business_logic.katalog import COMMODITY_CATALOG
from src.business_logic.ml_service import predict_harga_satuan
from src.api.schemas import CartItem, ItemResult, SubstitusiItem

def build_substitution_dynamic(keranjang: List[CartItem], detail: List[ItemResult]) -> Tuple[List[SubstitusiItem], float]:
    subs = []
    total_hemat = 0.0

    for item, result in zip(keranjang, detail):
        current_id = item.komoditas_id
        current_info = COMMODITY_CATALOG.get(current_id)
        if not current_info: continue

        kategori_target = current_info["kategori"]
        best_sub_id, best_sub_harga, max_hemat = None, 0.0, 0.0

        for slug, info in COMMODITY_CATALOG.items():
            if info["kategori"] == kategori_target and slug != current_id:
                sub_harga = predict_harga_satuan(slug)
                hemat = (result.harga_per_satuan - sub_harga) * item.jumlah

                if hemat > max_hemat:
                    max_hemat = hemat
                    best_sub_id = slug
                    best_sub_harga = sub_harga

        if best_sub_id and max_hemat > 0:
            subs.append(SubstitusiItem(
                current_id=current_id, current_nama=result.nama, current_harga=result.harga_per_satuan,
                substitute_id=best_sub_id, substitute_nama=COMMODITY_CATALOG[best_sub_id]["nama"], substitute_harga=best_sub_harga,
                potensi_hemat=round(max_hemat, 2),
            ))
            total_hemat += max_hemat

    return subs, round(total_hemat, 2)  