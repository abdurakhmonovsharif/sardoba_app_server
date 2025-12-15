from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.cache import cache
from app.core.dependencies import get_current_manager, get_db
from app.core.localization import localize_message
from app.models import Staff
from app.schemas import NewsCreate, NewsRead, NewsUpdate
from app.services import NewsService
from app.services import exceptions as service_exceptions

router = APIRouter(prefix="/news", tags=["news"])


@cache(ttl=60, namespace="news", key_builder=lambda db: "public")
def _cached_news(db: Session) -> list[dict]:
    service = NewsService(db)
    items = service.list_public()
    return [NewsRead.from_orm(item).dict() for item in items]


@router.get("", response_model=list[NewsRead])
def list_news(db: Session = Depends(get_db)):
    cached = _cached_news(db)
    return [NewsRead(**item) for item in cached]


@router.post("", response_model=NewsRead)
def create_news(
    payload: NewsCreate,
    manager: Staff = Depends(get_current_manager),
    db: Session = Depends(get_db),
):
    service = NewsService(db)
    news = service.create(actor=manager, data=payload.dict())
    return NewsRead.from_orm(news)


@router.put("/{news_id}", response_model=NewsRead)
def update_news(
    news_id: int,
    payload: NewsUpdate,
    manager: Staff = Depends(get_current_manager),
    db: Session = Depends(get_db),
):
    data = {k: v for k, v in payload.dict().items() if v is not None}
    service = NewsService(db)
    try:
        news = service.update(actor=manager, news_id=news_id, data=data)
    except service_exceptions.NotFoundError as exc:
        raise HTTPException(status_code=404, detail=localize_message(str(exc))) from exc
    return NewsRead.from_orm(news)


@router.delete("/{news_id}", status_code=204)
def delete_news(
    news_id: int,
    manager: Staff = Depends(get_current_manager),
    db: Session = Depends(get_db),
):
    service = NewsService(db)
    try:
        service.delete(actor=manager, news_id=news_id)
    except service_exceptions.NotFoundError as exc:
        raise HTTPException(status_code=404, detail=localize_message(str(exc))) from exc
