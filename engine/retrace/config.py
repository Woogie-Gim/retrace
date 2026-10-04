"""환경변수 기반 엔진 설정"""
import os
import sys
from pathlib import Path

from dotenv import load_dotenv


def _root_dir() -> Path:
    # RETRACE_ROOT 우선 → 빌드 exe면 exe 폴더 → 저장소 루트
    if os.getenv("RETRACE_ROOT"):
        return Path(os.environ["RETRACE_ROOT"]).resolve()
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[2]


ROOT_DIR = _root_dir()

# 루트 .env 로드 (이미 설정된 환경변수 우선)
load_dotenv(ROOT_DIR / ".env")

DEMO_SHOP_PORT = int(os.getenv("DEMO_SHOP_PORT", "5100"))
ENGINE_PORT = int(os.getenv("ENGINE_PORT", "5200"))
BASE_URL = os.getenv("RETRACE_BASE_URL", f"http://127.0.0.1:{DEMO_SHOP_PORT}").rstrip("/")
REPORTS_DIR = Path(os.getenv("RETRACE_REPORTS_DIR", ROOT_DIR / "reports"))
HEADLESS = os.getenv("RETRACE_HEADLESS", "1").strip() != "0"
