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
MODEL_NAME         = "cluster 1"

engine = create_engine(DATABASE_URL) if DATABASE_URL else None

try:
    if DAGSHUB_REPO_OWNER and DAGSHUB_REPO_NAME:
        dagshub.init(repo_owner=DAGSHUB_REPO_OWNER, repo_name=DAGSHUB_REPO_NAME, mlflow=True)
except Exception as e:
    logger.warning(f"DagsHub init failed: {e}")