from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import mlflow

# Import dari core & business logic
from src.core.config import MODEL_REGISTRY, logger
from src.business_logic.katalog import load_harga_terkini
from src.business_logic.ml_service import set_model

# Import loket rute
from src.api.routes import katalog, belanja, tren

# Proses saat server baru menyala (Startup)
@asynccontextmanager
async def lifespan(app: FastAPI):
    load_harga_terkini()
    
    for cluster_key, model_name in MODEL_REGISTRY.items():
        try:
            model_uri = f"models:/{model_name}@champion"
            logger.info(f"Mengunduh model {model_name} (Champion) untuk {cluster_key}...")
            
            loaded_model = mlflow.pyfunc.load_model(model_uri)
            set_model(cluster_key, loaded_model)
            
            logger.info(f"✅ Model {cluster_key} berhasil diaktifkan!")
        except Exception as e:
            logger.error(f"❌ Gagal memuat model {cluster_key}: {e}")

    yield
    import src.business_logic.ml_service as ml
    ml.active_models.clear()

# Inisialisasi Aplikasi Utama
app = FastAPI(
    title="MarketCast API",
    lifespan=lifespan
)

# Keamanan agar Frontend bisa mengakses API
app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"]
)

# Mendaftarkan Loket Rute
app.include_router(katalog.router)
app.include_router(belanja.router)
app.include_router(tren.router)

# Mesin Uvicorn untuk menjalankan server
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("src.api.main:app", host="127.0.0.1", port=8000, reload=True)