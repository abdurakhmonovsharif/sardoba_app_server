from fastapi import APIRouter

from . import (
    admin,
    auth,
    cashback,
    catalog,
    files,
    health,
    iiko_integration,
    dashboard,
    news,
    notifications,
    stats,
    user,
    user_delete,
    waiters,
)


def get_api_router() -> APIRouter:
    router = APIRouter()
    router.include_router(health.router)
    router.include_router(auth.router)
    router.include_router(user.router)
    router.include_router(cashback.router)
    router.include_router(files.router)
    router.include_router(news.router)
    router.include_router(dashboard.router)
    router.include_router(catalog.router)
    router.include_router(notifications.router)
    router.include_router(stats.router)
    router.include_router(admin.router)
    router.include_router(iiko_integration.router)
    router.include_router(waiters.router)
    router.include_router(user_delete.router)
    return router
