"""FastAPI entrypoint. Phase 8 exposes /chat and /health."""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.api.routes import router
from backend.database import init_schema


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_schema()
    yield


app = FastAPI(title="AI Patient Appointment Scheduling Agent", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(router)
