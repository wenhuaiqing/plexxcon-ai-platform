"""FastAPI application entry."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.app.routers import bids, finance, msr, orb, platform, trades
from src.app.services import db
from src.settings import settings

app = FastAPI(
    title="plexxcon-ai-platform",
    description=("A construction operations platform demo: three workflow systems, finance reporting and a data "
                 "agent. Built for a job application; not affiliated with or endorsed by Plexxcon. All data is synthetic."),
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

for module in (platform, finance, bids, trades, msr, orb):
    app.include_router(module.router)


@app.get("/health")
def health() -> dict[str, str]:
    db.connection()
    return {"status": "ok"}
