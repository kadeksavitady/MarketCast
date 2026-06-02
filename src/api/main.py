from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# Import dari core & business logic
from src.core.config import logger
from src.business_logic.katalog import load_harga_terkini

# Import loket rute
from src.api.routes import katalog, belanja, tren

# Proses saat server baru menyala (Startup)
@asynccontextmanager
async def lifespan(app: FastAPI):
    # 1. Tetap muat harga terkini ke memori katalog
    load_harga_terkini()
    
    # 2. Server langsung menyala tanpa mendownload 43 model di awal
    logger.info("🚀 Server MarketCast API siap. Model MLflow dimuat secara dinamis (Lazy Loading).")

    yield
    
    # 3. Pembersihan memori (cache model) saat server dimatikan
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