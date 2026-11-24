"""Servicio de analíticas: consume eventos de clic y expone estadísticas.

Con Redis, consume el stream `clicks` como grupo de consumidores (escalable a
varias réplicas). Sin Redis, acepta los eventos por POST /events.
"""
import asyncio
import json
import logging
import os
import socket
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import Depends, FastAPI, Query, status
from pydantic import BaseModel
from sqlalchemy import DateTime, Integer, String, Text, func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./analytics.db")
REDIS_URL = os.getenv("REDIS_URL", "")
CLICK_STREAM = os.getenv("CLICK_STREAM", "clicks")
CONSUMER_GROUP = os.getenv("CONSUMER_GROUP", "analytics")
CONSUMER_NAME = os.getenv("CONSUMER_NAME", socket.gethostname())

log = logging.getLogger("analytics")
engine = create_async_engine(DATABASE_URL, pool_pre_ping=True)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


class Click(Base):
    __tablename__ = "clicks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(32), index=True)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    referrer: Mapped[str | None] = mapped_column(Text, nullable=True)
    user_agent: Mapped[str | None] = mapped_column(Text, nullable=True)


class ClickEvent(BaseModel):
    code: str
    ts: datetime
    referrer: str | None = None
    user_agent: str | None = None


class DayCount(BaseModel):
    day: str
    clicks: int


class LinkStats(BaseModel):
    code: str
    total_clicks: int
    last_click: datetime | None
    by_day: list[DayCount]
    top_referrers: list[dict]


async def save_events(events: list[ClickEvent]):
    async with SessionLocal() as session:
        session.add_all(Click(**e.model_dump()) for e in events)
        await session.commit()


async def consume_stream(redis):
    try:
        await redis.xgroup_create(CLICK_STREAM, CONSUMER_GROUP, id="0", mkstream=True)
    except Exception as exc:  # BUSYGROUP: el grupo ya existe
        if "BUSYGROUP" not in str(exc):
            raise
    # Primero reprocesa mensajes pendientes de una caída anterior ("0"), luego nuevos (">").
    last_id = "0"
    while True:
        try:
            resp = await redis.xreadgroup(
                CONSUMER_GROUP, CONSUMER_NAME, {CLICK_STREAM: last_id}, count=100, block=5000
            )
            if not resp or not resp[0][1]:
                last_id = ">"
                continue
            _, messages = resp[0]
            events, ids = [], []
            for msg_id, fields in messages:
                ids.append(msg_id)
                try:
                    events.append(ClickEvent(**json.loads(fields["data"])))
                except Exception:
                    log.warning("Evento inválido descartado: %s", fields)
            if events:
                await save_events(events)
            await redis.xack(CLICK_STREAM, CONSUMER_GROUP, *ids)
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("Error consumiendo el stream; reintentando")
            await asyncio.sleep(2)


@asynccontextmanager
async def lifespan(_: FastAPI):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    task, redis = None, None
    if REDIS_URL:
        import redis.asyncio as aioredis

        redis = aioredis.from_url(REDIS_URL, decode_responses=True)
        task = asyncio.create_task(consume_stream(redis))
    yield
    if task:
        task.cancel()
    if redis is not None:
        await redis.aclose()
    await engine.dispose()


app = FastAPI(title="Analytics service", lifespan=lifespan)


async def get_session():
    async with SessionLocal() as session:
        yield session


@app.get("/health")
async def health():
    return {"status": "ok", "service": "analytics", "ingest": "redis-stream" if REDIS_URL else "http"}


@app.post("/events", status_code=status.HTTP_202_ACCEPTED)
async def ingest(event: ClickEvent):
    await save_events([event])
    return {"accepted": True}


@app.get("/stats")
async def top_links(limit: int = Query(10, ge=1, le=100), session: AsyncSession = Depends(get_session)):
    total = func.count(Click.id).label("clicks")
    result = await session.execute(
        select(Click.code, total).group_by(Click.code).order_by(total.desc()).limit(limit)
    )
    return [{"code": code, "clicks": clicks} for code, clicks in result.all()]


@app.get("/stats/{code}", response_model=LinkStats)
async def link_stats(code: str, session: AsyncSession = Depends(get_session)):
    total, last = (
        await session.execute(
            select(func.count(Click.id), func.max(Click.ts)).where(Click.code == code)
        )
    ).one()

    day = func.date(Click.ts).label("day")
    by_day = await session.execute(
        select(day, func.count(Click.id)).where(Click.code == code).group_by(day).order_by(day)
    )

    ref_count = func.count(Click.id).label("n")
    refs = await session.execute(
        select(Click.referrer, ref_count)
        .where(Click.code == code, Click.referrer.is_not(None))
        .group_by(Click.referrer)
        .order_by(ref_count.desc())
        .limit(5)
    )

    if isinstance(last, str):  # SQLite devuelve texto en agregados
        last = datetime.fromisoformat(last)
    if last is not None and last.tzinfo is None:
        last = last.replace(tzinfo=timezone.utc)

    return LinkStats(
        code=code,
        total_clicks=total,
        last_click=last,
        by_day=[DayCount(day=str(d), clicks=c) for d, c in by_day.all()],
        top_referrers=[{"referrer": r, "clicks": n} for r, n in refs.all()],
    )
