"""
src/business_logic/substitution_engine.py
==========================================
Engine substitusi komoditas PBL-MarketCast.

LOGIKA UTAMA:
    1. Cari komoditas lain dalam kategori yang sama (WHITELIST_MAP)
    2. Load forecast 30 hari ke depan dari MLflow via model_registry_map.yaml
    3. Hitung weighted mean forecast (bobot linear — hari terdekat lebih berat)
       → atasi bias akibat distribusi harga skewed / spike di awal/akhir periode
    4. Filter kandidat yang weighted_price ≤ budget user
    5. Kalau semua kandidat > budget → return notifikasi "tidak ada saran substitusi"

INPUT:
    - komoditas : str   — nama komoditas yang ingin disubstitusi
    - budget    : float — batas harga per kg yang sanggup dibayar user (Rp)

OUTPUT:
    dict {
        "komoditas_asal"    : str,
        "kategori"          : str,
        "budget"            : float,
        "forecast_asal"     : float,   weighted mean forecast komoditas asal
        "status_inflasi"    : bool,    True kalau forecast > harga historis
        "saran"             : list[dict] | [],
        "pesan"             : str,
    }

CARA PAKAI:
    from substitution_engine import SubstitutionEngine
    engine = SubstitutionEngine()
    result = engine.get_substitusi("Beras Premium", budget=14000)
    print(result)
"""

import yaml
import logging
import numpy as np
import pandas as pd
from pathlib import Path

import mlflow
from mlflow.tracking import MlflowClient

log = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s | %(levelname)s | %(message)s")

# ─────────────────────────────────────────────────────────────────────────────
# KONSTANTA
# ─────────────────────────────────────────────────────────────────────────────

# Mapping komoditas → kategori (dari daily_scraper.py)
WHITELIST_MAP = {
    'Beras Premium': 'BERAS', 'Beras Medium': 'BERAS',
    'Gula Kristal Putih': 'GULA',
    'Minyak Goreng Curah': 'MINYAK GORENG',
    'Minyak Goreng Kemasan Premium': 'MINYAK GORENG',
    'Minyak Goreng Kemasan Sederhana': 'MINYAK GORENG',
    'Minyak Goreng MINYAKITA': 'MINYAK GORENG',
    'Daging Sapi Paha Belakang': 'DAGING',
    'Daging Ayam Ras': 'DAGING',
    'Daging Ayam Kampung': 'DAGING',
    'Telur Ayam Ras': 'TELUR',
    'Telur Ayam Kampung': 'TELUR',
    'Susu Kental Manis Merk Bendera': 'SUSU',
    'Susu Kental Manis Merk Indomilk': 'SUSU',
    'Susu Bubuk Merk Bendera (Instant)': 'SUSU',
    'Susu Bubuk Merk Indomilk (Instant)': 'SUSU',
    'Jagung Pipilan Kering': 'PALAWIJA',
    'Kedelai Impor': 'PALAWIJA',
    'Kedelai Lokal': 'PALAWIJA',
    'Terigu Protein Sedang (Kemasan)': 'TEPUNG',
    'Indomie Rasa Kari Ayam': 'MIE INSTAN',
    'Cabe Merah Keriting': 'CABE',
    'Cabe Merah Besar': 'CABE',
    'Cabe Rawit Merah': 'CABE',
    'Bawang Merah': 'BAWANG',
    'Bawang Putih Sinco/Honan': 'BAWANG',
    'Ikan Asin Teri': 'IKAN ASIN',
    'Tomat Merah': 'SAYUR MAYUR',
    'Ikan Bandeng': 'IKAN SEGAR',
    'Ikan Kembung': 'IKAN SEGAR',
    'Ikan Tuna': 'IKAN SEGAR',
    'Ikan Tongkol': 'IKAN SEGAR',
    'Ikan Cakalang': 'IKAN SEGAR',
}

# Path default
DIR_ROOT        = Path(__file__).resolve().parent.parent.parent
YAML_REGISTRY   = DIR_ROOT / "outputs" / "registry" / "model_registry_map.yaml"
CSV_PREPROCESSED = DIR_ROOT / "outputs" / "clustering" / "data_preprocessed.csv"
MLFLOW_URI      = "http://localhost:5000"
FORECAST_DAYS   = 30


# ─────────────────────────────────────────────────────────────────────────────
# SUBSTITUTION ENGINE
# ─────────────────────────────────────────────────────────────────────────────

class SubstitutionEngine:
    """
    Engine substitusi komoditas berbasis kategori + weighted forecast.

    Inisialisasi sekali, pakai berkali-kali (cache registry & data historis).
    """

    def __init__(self,
                 registry_path: Path = YAML_REGISTRY,
                 csv_path: Path = CSV_PREPROCESSED,
                 mlflow_uri: str = MLFLOW_URI):

        self.mlflow_uri    = mlflow_uri
        self.registry      = self._load_registry(registry_path)
        self.df_historis   = self._load_historis(csv_path)
        self._forecast_cache: dict = {}  # cache forecast per komoditas

        mlflow.set_tracking_uri(mlflow_uri)
        self.client = MlflowClient()

        log.info(f"SubstitutionEngine ready — "
                 f"{len(self.registry)} komoditas di registry")

    # ── Loaders ──────────────────────────────────────────────────────────────

    def _load_registry(self, path: Path) -> dict:
        if not path.exists():
            raise FileNotFoundError(
                f"Registry tidak ditemukan: {path}\n"
                "Jalankan train_all.py --mode specialize terlebih dahulu."
            )
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        return data.get("models", {})

    def _load_historis(self, path: Path) -> pd.DataFrame:
        if not path.exists():
            log.warning(f"Data historis tidak ditemukan: {path}")
            return pd.DataFrame()
        df = pd.read_csv(path)
        df["tanggal"] = pd.to_datetime(df["tanggal"])
        return df

    # ── Forecast ─────────────────────────────────────────────────────────────

    def get_forecast(self, komoditas: str) -> np.ndarray | None:
        """
        Load model dari MLflow dan generate forecast 30 hari ke depan.
        Hasil di-cache supaya tidak load ulang model yang sama.
        """
        if komoditas in self._forecast_cache:
            return self._forecast_cache[komoditas]

        if komoditas not in self.registry:
            log.warning(f"{komoditas} tidak ada di registry")
            return None

        info      = self.registry[komoditas]
        model_uri = info.get("model_uri", "")
        model_name = info.get("model", "")

        if not model_uri:
            log.warning(f"{komoditas}: model_uri kosong di registry")
            return None

        try:
            if model_name == "prophet":
                forecast = self._forecast_prophet(model_uri, komoditas)
            elif model_name == "sarima":
                forecast = self._forecast_sarima(model_uri, komoditas)
            elif model_name == "xgboost":
                forecast = self._forecast_xgboost(model_uri, komoditas)
            else:
                log.warning(f"{komoditas}: model '{model_name}' tidak dikenal")
                return None

            self._forecast_cache[komoditas] = forecast
            return forecast

        except Exception as e:
            log.error(f"Gagal load/forecast {komoditas}: {e}")
            return None

    def _get_last_series(self, komoditas: str) -> np.ndarray:
        """Ambil series historis terakhir untuk input model."""
        if self.df_historis.empty:
            return np.array([])
        sub = (self.df_historis[self.df_historis["komoditas"] == komoditas]
               .sort_values("tanggal")["harga_per_kg"]
               .values)
        return sub

    def _forecast_prophet(self, model_uri: str, komoditas: str) -> np.ndarray:
        import mlflow.prophet
        model    = mlflow.prophet.load_model(model_uri)
        last_date = (self.df_historis[self.df_historis["komoditas"] == komoditas]
                     ["tanggal"].max())
        future_dates = pd.date_range(
            last_date + pd.Timedelta(days=1),
            periods=FORECAST_DAYS, freq="D"
        )
        future_df = pd.DataFrame({"ds": future_dates})
        pred      = model.predict(future_df)
        return pred["yhat"].values

    def _forecast_sarima(self, model_uri: str, komoditas: str) -> np.ndarray:
        import mlflow.sklearn
        model    = mlflow.sklearn.load_model(model_uri)
        forecast = model.predict(n_periods=FORECAST_DAYS)
        return np.array(forecast)

    def _forecast_xgboost(self, model_uri: str, komoditas: str) -> np.ndarray:
        import mlflow.xgboost
        import sys
        sys.path.insert(0, str(DIR_ROOT / "src" / "training"))
        from model_xgboost import build_features, get_feature_cols, _recursive_forecast

        model       = mlflow.xgboost.load_model(model_uri)
        series      = self._get_last_series(komoditas)
        last_date   = (self.df_historis[self.df_historis["komoditas"] == komoditas]
                       ["tanggal"].max())
        dates       = pd.date_range(
            end=last_date, periods=len(series), freq="D"
        )
        feature_cols = get_feature_cols()
        forecast     = _recursive_forecast(
            model, series, dates, FORECAST_DAYS, feature_cols
        )
        return forecast

    # ── Weighted Mean ─────────────────────────────────────────────────────────

    def weighted_mean_forecast(self, forecast: np.ndarray) -> float:
        """
        Weighted mean dengan bobot linear — hari terdekat ke sekarang
        (hari ke-1) bobotnya lebih kecil, hari ke-30 bobotnya lebih besar.

        Alasan: user lebih terpengaruh harga yang akan dia hadapi dalam
        waktu dekat. Bobot linear lebih intuitif dan mudah dijelaskan
        di laporan dibanding exponential weighting.

        Contoh untuk 5 hari: weights = [1,2,3,4,5]
        → hari ke-5 bobotnya 5x lebih besar dari hari ke-1
        """
        n       = len(forecast)
        weights = np.arange(1, n + 1, dtype=float)
        return float(np.average(forecast, weights=weights))

    # ── Harga historis rata-rata (baseline) ───────────────────────────────────

    def get_mean_historis(self, komoditas: str, last_n_days: int = 30) -> float:
        """
        Rata-rata harga historis N hari terakhir.
        Dipakai sebagai baseline untuk deteksi inflasi:
        kalau weighted_forecast > mean_historis → sedang inflasi.
        """
        if self.df_historis.empty:
            return 0.0
        sub = (self.df_historis[self.df_historis["komoditas"] == komoditas]
               .sort_values("tanggal")
               .tail(last_n_days)["harga_per_kg"])
        return float(sub.mean()) if len(sub) > 0 else 0.0

    # ── Main API ──────────────────────────────────────────────────────────────

    def get_substitusi(self, komoditas: str, budget: float) -> dict:
        """
        Cari saran substitusi untuk komoditas tertentu dengan budget user.

        Returns:
            dict dengan keys:
                komoditas_asal, kategori, budget,
                forecast_asal, status_inflasi,
                saran (list), pesan (str)
        """
        # ── Validasi komoditas ada di whitelist ───────────────────────────────
        if komoditas not in WHITELIST_MAP:
            return {
                "komoditas_asal" : komoditas,
                "kategori"       : None,
                "budget"         : budget,
                "forecast_asal"  : None,
                "status_inflasi" : None,
                "saran"          : [],
                "pesan"          : f"'{komoditas}' tidak ada dalam daftar komoditas yang dipantau.",
            }

        kategori = WHITELIST_MAP[komoditas]

        # ── Forecast komoditas asal ───────────────────────────────────────────
        forecast_asal = self.get_forecast(komoditas)
        if forecast_asal is None:
            weighted_asal = self.get_mean_historis(komoditas)
        else:
            weighted_asal = self.weighted_mean_forecast(forecast_asal)

        mean_historis_asal = self.get_mean_historis(komoditas)
        status_inflasi     = weighted_asal > mean_historis_asal

        # ── Cari kandidat substitusi (kategori sama, bukan diri sendiri) ──────
        kandidat = [k for k, v in WHITELIST_MAP.items()
                    if v == kategori and k != komoditas]

        if not kandidat:
            return {
                "komoditas_asal" : komoditas,
                "kategori"       : kategori,
                "budget"         : budget,
                "forecast_asal"  : round(weighted_asal, 2),
                "status_inflasi" : status_inflasi,
                "saran"          : [],
                "pesan"          : f"Tidak ada komoditas lain dalam kategori '{kategori}'.",
            }

        # ── Hitung weighted forecast tiap kandidat ────────────────────────────
        saran = []
        for k in kandidat:
            fc = self.get_forecast(k)
            if fc is None:
                weighted_k = self.get_mean_historis(k)
            else:
                weighted_k = self.weighted_mean_forecast(fc)

            mean_historis_k = self.get_mean_historis(k)
            inflasi_k       = weighted_k > mean_historis_k

            saran.append({
                "komoditas"      : k,
                "forecast_harga" : round(weighted_k, 2),
                "mean_historis"  : round(mean_historis_k, 2),
                "status_inflasi" : inflasi_k,
                "dalam_budget"   : weighted_k <= budget,
                "selisih_budget" : round(budget - weighted_k, 2),
            })

        # ── Filter: dalam budget ──────────────────────────────────────────────
        dalam_budget = [s for s in saran if s["dalam_budget"]]

        # ── Sort: harga termurah yang masih dalam budget ──────────────────────
        dalam_budget_sorted = sorted(dalam_budget,
                                     key=lambda x: x["forecast_harga"])

        # ── Susun pesan ───────────────────────────────────────────────────────
        if dalam_budget_sorted:
            pesan = (
                f"Ditemukan {len(dalam_budget_sorted)} saran substitusi "
                f"untuk '{komoditas}' dalam budget Rp{budget:,.0f}/kg."
            )
        else:
            pesan = (
                f"Tidak tersedia saran substitusi untuk '{komoditas}' "
                f"dalam kategori '{kategori}' yang sesuai budget "
                f"Rp{budget:,.0f}/kg. Semua alternatif melebihi budget."
            )

        return {
            "komoditas_asal" : komoditas,
            "kategori"       : kategori,
            "budget"         : budget,
            "forecast_asal"  : round(weighted_asal, 2),
            "status_inflasi" : status_inflasi,
            "saran"          : dalam_budget_sorted,
            "semua_kandidat" : saran,   # untuk debug / UI tambahan
            "pesan"          : pesan,
        }


# ─────────────────────────────────────────────────────────────────────────────
# CLI TEST
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import json

    engine = SubstitutionEngine()

    # Test 1: Beras Premium dengan budget terbatas
    print("\n" + "="*60)
    print("TEST 1: Beras Premium, budget Rp14.000/kg")
    print("="*60)
    result = engine.get_substitusi("Beras Premium", budget=14_000)
    print(json.dumps(result, indent=2, ensure_ascii=False,
                     default=lambda x: float(x) if isinstance(x, np.floating) else x))

    # Test 2: Minyak Goreng Curah dengan budget lebih longgar
    print("\n" + "="*60)
    print("TEST 2: Minyak Goreng Curah, budget Rp18.000/kg")
    print("="*60)
    result2 = engine.get_substitusi("Minyak Goreng Curah", budget=18_000)
    print(json.dumps(result2, indent=2, ensure_ascii=False,
                     default=lambda x: float(x) if isinstance(x, np.floating) else x))

    # Test 3: Komoditas tanpa alternatif (kategori tunggal)
    print("\n" + "="*60)
    print("TEST 3: Indomie Rasa Kari Ayam, budget Rp3.000/bungkus")
    print("="*60)
    result3 = engine.get_substitusi("Indomie Rasa Kari Ayam", budget=3_000)
    print(json.dumps(result3, indent=2, ensure_ascii=False,
                     default=lambda x: float(x) if isinstance(x, np.floating) else x))