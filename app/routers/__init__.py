from fastapi import APIRouter

from . import admin, auth, cashback, catalog, files, health, news, notifications, stats, user, waiters


def get_api_router() -> APIRouter:
    router = APIRouter()
    router.include_router(health.router)
    router.include_router(auth.router)
    router.include_router(user.router)
    router.include_router(cashback.router)
    router.include_router(files.router)
    router.include_router(news.router)
    router.include_router(catalog.router)
    router.include_router(notifications.router)
    router.include_router(stats.router)
    router.include_router(admin.router)
    router.include_router(waiters.router)
    return router
