"""환경변수 기반 엔진 설정"""
import os
from pathlib import Path

from dotenv import load_dotenv

ROOT_DIR = Path(__file__).resolve().parents[2]

# 루트 .env 로드 (이미 설정된 환경변수 우선)
load_dotenv(ROOT_DIR / ".env")

DEMO_SHOP_PORT = int(os.getenv("DEMO_SHOP_PORT", "5100"))
BASE_URL = os.getenv("RETRACE_BASE_URL", f"http://127.0.0.1:{DEMO_SHOP_PORT}").rstrip("/")
REPORTS_DIR = Path(os.getenv("RETRACE_REPORTS_DIR", ROOT_DIR / "reports"))
HEADLESS = os.getenv("RETRACE_HEADLESS", "1").strip() != "0"
