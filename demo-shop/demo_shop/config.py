"""환경변수 기반 설정"""
import os
import random
from pathlib import Path

from dotenv import load_dotenv

# 루트 .env 로드 (이미 설정된 환경변수 우선)
load_dotenv(Path(__file__).resolve().parents[2] / ".env")

PORT = int(os.getenv("DEMO_SHOP_PORT", "5100"))
BUG_MODE = os.getenv("BUG_MODE", "on").strip().lower() != "off"
BUG_SEED = os.getenv("BUG_SEED")

# 확률 버그용 난수 (시드는 기동 시 1회만 고정)
rng = random.Random(int(BUG_SEED)) if BUG_SEED else random.Random()
