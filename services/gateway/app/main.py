"""API Gateway: único punto de entrada público.

Enruta /api/links -> shortener, /api/stats -> analytics, /{code} -> redirect
y sirve el frontend estático.
"""
import asyncio
import os
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse, Response

SERVICES = {
    "shortener": os.getenv("SHORTENER_URL", "http://localhost:8001").rstrip("/"),
    "redirect": os.getenv("REDIRECT_URL", "http://localhost:8002").rstrip("/"),
    "analytics": os.getenv("ANALYTICS_URL", "http://localhost:8003").rstrip("/"),
}
STATIC_DIR = Path(__file__).parent / "static"
HOP_HEADERS = {"connection", "keep-alive", "transfer-encoding", "content-encoding", "content-length", "host"}

state: dict = {}


@asynccontextmanager
async def lifespan(_: FastAPI):
    state["http"] = httpx.AsyncClient(timeout=5.0, follow_redirects=False)
    yield
    await state["http"].aclose()


app = FastAPI(title="URL Shortener - Gateway", lifespan=lifespan)


async def proxy(request: Request, service: str, path: str) -> Response:
    url = f"{SERVICES[service]}{path}"
    headers = {k: v for k, v in request.headers.items() if k.lower() not in HOP_HEADERS}
    headers["x-forwarded-for"] = request.client.host if request.client else ""
    try:
        upstream = await state["http"].request(
            request.method,
            url,
            params=request.query_params,
            content=await request.body(),
            headers=headers,
        )
    except httpx.HTTPError:
        return JSONResponse({"detail": f"Servicio '{service}' no disponible"}, status_code=503)
    resp_headers = {k: v for k, v in upstream.headers.items() if k.lower() not in HOP_HEADERS}
    return Response(upstream.content, status_code=upstream.status_code, headers=resp_headers)


@app.get("/", include_in_schema=False)
async def index():
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/health")
async def health():
    async def check(name, base):
        try:
            r = await state["http"].get(f"{base}/health", timeout=2.0)
            return name, "ok" if r.status_code == 200 else f"http {r.status_code}"
        except httpx.HTTPError:
            return name, "down"

    results = dict(await asyncio.gather(*(check(n, u) for n, u in SERVICES.items())))
    ok = all(v == "ok" for v in results.values())
    return JSONResponse({"status": "ok" if ok else "degraded", "services": results}, status_code=200 if ok else 503)


@app.api_route("/api/links", methods=["GET", "POST"])
@app.api_route("/api/links/{rest:path}", methods=["GET", "DELETE"])
async def links(request: Request, rest: str = ""):
    return await proxy(request, "shortener", f"/links/{rest}" if rest else "/links")


@app.get("/api/stats")
@app.get("/api/stats/{rest:path}")
async def stats(request: Request, rest: str = ""):
    return await proxy(request, "analytics", f"/stats/{rest}" if rest else "/stats")


@app.get("/{code}", include_in_schema=False)
async def follow(request: Request, code: str):
    return await proxy(request, "redirect", f"/{code}")
