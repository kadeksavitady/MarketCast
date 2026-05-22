import os
import logging
import dagshub
from dotenv import load_dotenv
from sqlalchemy import create_engine

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

DAGSHUB_REPO_OWNER = os.getenv("DAGSHUB_USER")
DAGSHUB_REPO_NAME  = os.getenv("DAGSHUB_REPO")
DATABASE_URL       = os.getenv("DATABASE_URL")
MODEL_REGISTRY = {
    "cluster_1": "cluster 1",
    "cluster_2": "cluster 2",
    "cluster_3": "cluster 3"
}

engine = create_engine(
    DATABASE_URL, 
    pool_pre_ping=True,  # 🆕 Selalu tes "Halo?" sebelum mengeksekusi SQL
    pool_recycle=300     # 🆕 Paksa tutup dan buka koneksi baru setiap 300 detik (5 menit)
) if DATABASE_URL else None

try:
    if DAGSHUB_REPO_OWNER and DAGSHUB_REPO_NAME:
        dagshub.init(repo_owner=DAGSHUB_REPO_OWNER, repo_name=DAGSHUB_REPO_NAME, mlflow=True)
except Exception as e:
    logger.warning(f"DagsHub init failed: {e}")