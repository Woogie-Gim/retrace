"""python -m demo_shop 진입점"""
import uvicorn

from .app import app
from .config import BUG_MODE, BUG_SEED, PORT

if __name__ == "__main__":
    print(f"[demo-shop] BUG_MODE={'on' if BUG_MODE else 'off'} BUG_SEED={BUG_SEED}")
    uvicorn.run(app, host="127.0.0.1", port=PORT)
