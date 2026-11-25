"""Servicio acortador: crea, lista y elimina enlaces cortos.

Es el dueño de los datos de los enlaces (base de datos propia).
"""
import os
import re
import secrets
import string
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import Depends, FastAPI, HTTPException, Query, status
from pydantic import BaseModel, Field, HttpUrl
from sqlalchemy import DateTime, String, Text, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

DATABASE_URL = os.environ["DATABASE_URL"]
PUBLIC_BASE_URL = os.getenv("PUBLIC_BASE_URL", "http://localhost:8000").rstrip("/")
REDIS_URL = os.getenv("REDIS_URL", "")
CODE_LENGTH = int(os.getenv("CODE_LENGTH", "7"))

ALPHABET = string.ascii_letters + string.digits
CUSTOM_CODE_RE = re.compile(r"[A-Za-z0-9_-]{3,32}")
RESERVED_CODES = {"api", "health", "static", "docs", "redoc", "openapi.json", "favicon.ico"}

engine = create_async_engine(DATABASE_URL, pool_pre_ping=True)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


class Link(Base):
    __tablename__ = "links"

    code: Mapped[str] = mapped_column(String(32), primary_key=True)
    url: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )


class LinkCreate(BaseModel):
    url: HttpUrl
    custom_code: str | None = Field(default=None, description="Alias opcional (3-32 caracteres)")


class LinkOut(BaseModel):
    code: str
    url: str
    short_url: str
    created_at: datetime


def to_out(link: Link) -> LinkOut:
    return LinkOut(
        code=link.code,
        url=link.url,
        short_url=f"{PUBLIC_BASE_URL}/{link.code}",
        created_at=link.created_at,
    )


redis_client = None


@asynccontextmanager
async def lifespan(_: FastAPI):
    global redis_client
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    if REDIS_URL:
        import redis.asyncio as redis

        redis_client = redis.from_url(REDIS_URL, decode_responses=True)
    yield
    if redis_client is not None:
        await redis_client.aclose()
    await engine.dispose()


app = FastAPI(title="Shortener service", lifespan=lifespan)


async def get_session():
    async with SessionLocal() as session:
        yield session


def random_code() -> str:
    return "".join(secrets.choice(ALPHABET) for _ in range(CODE_LENGTH))


@app.get("/health")
async def health():
    return {"status": "ok", "service": "shortener"}


@app.post("/links", response_model=LinkOut, status_code=status.HTTP_201_CREATED)
async def create_link(payload: LinkCreate, session: AsyncSession = Depends(get_session)):
    url = str(payload.url)

    if payload.custom_code is not None:
        code = payload.custom_code
        if not CUSTOM_CODE_RE.fullmatch(code) or code.lower() in RESERVED_CODES:
            raise HTTPException(422, "Alias inválido: usa 3-32 letras, números, '-' o '_'")
        candidates = [code]
    else:
        candidates = [random_code() for _ in range(5)]

    for code in candidates:
        link = Link(code=code, url=url)
        session.add(link)
        try:
            await session.commit()
            return to_out(link)
        except IntegrityError:
            await session.rollback()

    if payload.custom_code is not None:
        raise HTTPException(409, "Ese alias ya está en uso")
    raise HTTPException(500, "No se pudo generar un código único")


@app.get("/links", response_model=list[LinkOut])
async def list_links(
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    session: AsyncSession = Depends(get_session),
):
    result = await session.execute(
        select(Link).order_by(Link.created_at.desc()).limit(limit).offset(offset)
    )
    return [to_out(link) for link in result.scalars()]


@app.get("/links/{code}", response_model=LinkOut)
async def get_link(code: str, session: AsyncSession = Depends(get_session)):
    link = await session.get(Link, code)
    if link is None:
        raise HTTPException(404, "Enlace no encontrado")
    return to_out(link)


@app.delete("/links/{code}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_link(code: str, session: AsyncSession = Depends(get_session)):
    link = await session.get(Link, code)
    if link is None:
        raise HTTPException(404, "Enlace no encontrado")
    await session.delete(link)
    await session.commit()
    # Invalida la caché del servicio de redirección para que deje de resolver.
    if redis_client is not None:
        try:
            await redis_client.delete(f"link:{code}")
        except Exception:
            pass
