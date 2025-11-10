from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.core.cache import invalidate_cache
from app.models import News, Staff, StaffRole

from . import exceptions

NEWS_CACHE_NAMESPACE = "news"


class NewsService:
    def __init__(self, db: Session):
        self.db = db

    def list_public(self) -> list[News]:
        now = datetime.now(tz=timezone.utc)
        return (
            self.db.query(News)
            .filter(
                (News.starts_at.is_(None) | (News.starts_at <= now)),
                (News.ends_at.is_(None) | (News.ends_at >= now)),
            )
            .order_by(News.priority.desc(), News.created_at.desc())
            .all()
        )

    def create(self, *, actor: Staff, data: dict) -> News:
        self._ensure_manager(actor)
        news = News(**data)
        self.db.add(news)
        self.db.commit()
        self.db.refresh(news)
        invalidate_cache(NEWS_CACHE_NAMESPACE)
        return news

    def update(self, *, actor: Staff, news_id: int, data: dict) -> News:
        self._ensure_manager(actor)
        news = self._get(news_id)
        for key, value in data.items():
            setattr(news, key, value)
        self.db.add(news)
        self.db.commit()
        self.db.refresh(news)
        invalidate_cache(NEWS_CACHE_NAMESPACE)
        return news

    def delete(self, *, actor: Staff, news_id: int) -> None:
        self._ensure_manager(actor)
        news = self._get(news_id)
        self.db.delete(news)
        self.db.commit()
        invalidate_cache(NEWS_CACHE_NAMESPACE)

    def _get(self, news_id: int) -> News:
        news = self.db.query(News).filter(News.id == news_id).first()
        if not news:
            raise exceptions.NotFoundError("News not found")
        return news

    @staticmethod
    def _ensure_manager(actor: Staff) -> None:
        if actor.role != StaffRole.MANAGER:
            raise exceptions.AuthorizationError("Only managers can perform this action")
