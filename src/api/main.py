from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import mlflow

from src.core.config import MODEL_NAME, logger
from src.business_logic.katalog import load_harga_terkini
from src.business_logic.ml_service import set_model

from src.api.routes import katalog, belanja, tren

@asynccontextmanager
async def lifespan(app: FastAPI):
    load_harga_terkini()
    try:
        model_uri = f"models:/{MODEL_NAME}/latest"
        logger.info(f"Memuat model {MODEL_NAME} dari DagsHub...")
        loaded_model = mlflow.pyfunc.load_model(model_uri)
        set_model(loaded_model)
        logger.info("Model berhasil dimuat!")
    except Exception as e:
        logger.error(f"Gagal memuat model: {e}")
    yield
    set_model(None)

app = FastAPI(
    title="MarketCast API",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"]
)

app.include_router(katalog.router)
app.include_router(belanja.router)
app.include_router(tren.router)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("src.api.main:app", host="127.0.0.1", port=8000, reload=True)