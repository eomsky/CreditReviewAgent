"""API v1 router composition."""

from fastapi import APIRouter

from app.api.v1.endpoints import chat, health, poc


api_router = APIRouter()
api_router.include_router(health.router, prefix="/health", tags=["health"])
api_router.include_router(chat.router, prefix="/chat", tags=["chat"])
api_router.include_router(poc.router, prefix="/poc", tags=["poc"])
