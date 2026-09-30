"""FastAPI 앱 : API + 정적 화면"""
import time
from pathlib import Path

from fastapi import Cookie, FastAPI, Header, Request
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import config
from .store import PRODUCTS, PRODUCTS_DELAY, ApiError, store

STATIC_DIR = Path(__file__).parent / "static"

app = FastAPI(title="Retrace Demo Shop")


@app.exception_handler(ApiError)
def api_error_handler(_: Request, exc: ApiError):
    return JSONResponse({"detail": exc.message}, status_code=exc.status)


@app.middleware("http")
async def no_store(request: Request, call_next):
    # 뒤로가기 시 bfcache 대신 페이지 재로드
    response = await call_next(request)
    response.headers["Cache-Control"] = "no-store"
    return response


class LoginBody(BaseModel):
    grade: str


class CartBody(BaseModel):
    product_id: int
    delta: int = 1


class CouponBody(BaseModel):
    code: str


@app.get("/")
def index():
    return RedirectResponse("/login.html")


@app.get("/api/config")
def get_config():
    return {"bug_mode": config.BUG_MODE}


@app.post("/api/login")
def login(body: LoginBody):
    token = store.login(body.grade)
    res = JSONResponse(store.me(body.grade))
    res.set_cookie("session", token, httponly=True, samesite="lax")
    return res


@app.get("/api/me")
def me(session: str | None = Cookie(None)):
    return store.me(store.user_of(session))


@app.get("/api/products")
def products():
    time.sleep(PRODUCTS_DELAY)
    return PRODUCTS


@app.get("/api/cart")
def get_cart(session: str | None = Cookie(None)):
    return store.cart_view(store.user_of(session))


@app.post("/api/cart")
def post_cart(body: CartBody, session: str | None = Cookie(None)):
    return store.update_cart(store.user_of(session), body.product_id, body.delta)


@app.post("/api/coupons/apply")
def apply_coupon(body: CouponBody, session: str | None = Cookie(None)):
    return store.apply_coupon(store.user_of(session), body.code)


@app.post("/api/orders")
def post_order(
    session: str | None = Cookie(None),
    idempotency_key: str | None = Header(None),
):
    return store.create_order(store.user_of(session), idempotency_key)


@app.get("/api/orders")
def get_orders(session: str | None = Cookie(None)):
    return store.list_orders(store.user_of(session))


@app.post("/api/reset")
def reset():
    store.reset()
    return {"ok": True}


app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")
