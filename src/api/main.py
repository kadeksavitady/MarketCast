from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.core.config import logger
from src.business_logic.katalog import load_harga_terkini
from src.api.routes import katalog, belanja, tren

@asynccontextmanager
async def lifespan(app: FastAPI):
    load_harga_terkini()
    logger.info("MarketCast API ready. Models are lazy-loaded on first request.")
    yield
    import src.business_logic.ml_service as ml
    ml.active_models.clear()

app = FastAPI(title="MarketCast API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"]
)

app.include_router(katalog.router)
app.include_router(belanja.router)
app.include_router(tren.router)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("src.api.main:app", host="127.0.0.1", port=8000, reload=True)