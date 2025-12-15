from sqlalchemy.orm import Session

from app.models import NotificationDeviceToken


class NotificationTokenService:
    def __init__(self, db: Session):
        self.db = db

    def register_token(
        self,
        *,
        user_id: int,
        device_token: str | None,
        device_type: str,
        language: str = "ru",
    ) -> NotificationDeviceToken:
        query = self.db.query(NotificationDeviceToken)
        token = None
        if device_token:
            token = query.filter(NotificationDeviceToken.device_token == device_token).first()
        if token is None:
            token = (
                query.filter(
                    NotificationDeviceToken.user_id == user_id,
                    NotificationDeviceToken.device_type == device_type,
                )
                .first()
            )
        if token:
            token.user_id = user_id
            token.device_type = device_type
            token.language = language
            token.device_token = device_token
        else:
            token = NotificationDeviceToken(
                user_id=user_id,
                device_token=device_token,
                device_type=device_type,
                language=language,
            )
        self.db.add(token)
        self.db.commit()
        self.db.refresh(token)
        return token

    def tokens_for_user(self, user_id: int) -> list[NotificationDeviceToken]:
        return (
            self.db.query(NotificationDeviceToken)
            .filter(NotificationDeviceToken.user_id == user_id)
            .all()
        )
