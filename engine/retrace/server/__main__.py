"""python -m retrace.server : 엔진 서버 기동 (ENGINE_PORT)"""
import argparse

import uvicorn

from .. import config
from .app import create_app


def main() -> None:
    p = argparse.ArgumentParser(prog="retrace.server")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=config.ENGINE_PORT)
    args = p.parse_args()
    uvicorn.run(create_app(), host=args.host, port=args.port)


if __name__ == "__main__":
    main()
