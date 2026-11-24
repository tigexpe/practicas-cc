"""Servicio de redirección: resuelve un código corto y redirige.

Ruta caliente del sistema: cachea los enlaces (Redis) y publica un evento
de clic por cada visita, sin bloquear la respuesta.
"""
import json
import os
import time
from contextlib import asynccontextmanager
from datetime import datetime, timezone

import httpx
from fastapi import BackgroundTasks, FastAPI, HTTPException, Request
from fastapi.responses import RedirectResponse

SHORTENER_URL = os.getenv("SHORTENER_URL", "http://localhost:8001").rstrip("/")
ANALYTICS_URL = os.getenv("ANALYTICS_URL", "http://localhost:8003").rstrip("/")
REDIS_URL = os.getenv("REDIS_URL", "")
CACHE_TTL = int(os.getenv("CACHE_TTL_SECONDS", "3600"))
CLICK_STREAM = os.getenv("CLICK_STREAM", "clicks")

state: dict = {}


class MemoryCache:
    """Caché de respaldo para ejecutar sin Redis."""

    def __init__(self):
        self._data: dict[str, tuple[float, str]] = {}

    async def get(self, key):
        item = self._data.get(key)
        if item and item[0] > time.monotonic():
            return item[1]
        self._data.pop(key, None)
        return None

    async def set(self, key, value, ex):
        self._data[key] = (time.monotonic() + ex, value)

    async def delete(self, key):
        self._data.pop(key, None)


@asynccontextmanager
async def lifespan(_: FastAPI):
    state["http"] = httpx.AsyncClient(timeout=3.0)
    if REDIS_URL:
        import redis.asyncio as redis

        state["redis"] = redis.from_url(REDIS_URL, decode_responses=True)
        state["cache"] = state["redis"]
    else:
        state["redis"] = None
        state["cache"] = MemoryCache()
    yield
    await state["http"].aclose()
    if state["redis"] is not None:
        await state["redis"].aclose()


app = FastAPI(title="Redirect service", lifespan=lifespan)


async def resolve(code: str) -> str | None:
    cache = state["cache"]
    key = f"link:{code}"
    url = await cache.get(key)
    if url:
        return url
    try:
        resp = await state["http"].get(f"{SHORTENER_URL}/links/{code}")
    except httpx.HTTPError:
        raise HTTPException(503, "Servicio acortador no disponible")
    if resp.status_code == 404:
        return None
    resp.raise_for_status()
    url = resp.json()["url"]
    await cache.set(key, url, ex=CACHE_TTL)
    return url


async def publish_click(event: dict):
    """Publica el clic en Redis Streams; sin Redis, lo envía por HTTP."""
    try:
        if state["redis"] is not None:
            await state["redis"].xadd(CLICK_STREAM, {"data": json.dumps(event)}, maxlen=100_000)
        else:
            await state["http"].post(f"{ANALYTICS_URL}/events", json=event)
    except Exception:
        # Las analíticas nunca deben romper una redirección.
        pass


@app.get("/health")
async def health():
    return {"status": "ok", "service": "redirect", "cache": "redis" if REDIS_URL else "memory"}


@app.get("/{code}")
async def redirect(code: str, request: Request, background: BackgroundTasks):
    url = await resolve(code)
    if url is None:
        raise HTTPException(404, "Enlace no encontrado")
    background.add_task(
        publish_click,
        {
            "code": code,
            "ts": datetime.now(timezone.utc).isoformat(),
            "referrer": request.headers.get("referer"),
            "user_agent": request.headers.get("user-agent"),
        },
    )
    return RedirectResponse(url, status_code=307, headers={"Cache-Control": "no-store"})
