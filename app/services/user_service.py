import random
import string
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models import User
from . import exceptions as service_exceptions
from .iiko_sync_job_service import IikoSyncJobService

class UserService:
    def __init__(self, db: Session):
        self.db = db

    def delete_user(self, user: User, *, notify_iiko: bool = True) -> dict[str, bool]:
        if user.deleted:
            self.db.delete(user)
            self.db.commit()
            return {"success": True}
        timestamp = datetime.now(tz=timezone.utc)
        fake_phone = self._generate_deleted_phone()
        real_phone = user.phone
        user.phone = fake_phone
        user.deleted = True
        user.deleted_at = timestamp
        self.db.add(user)
        self.db.flush()
        if notify_iiko:
            IikoSyncJobService(self.db).enqueue_delete_sync(
                user_id=user.id,
                phone=real_phone,
                customer_id=user.iiko_customer_id,
                full_name=user.name,
                source="user_delete",
                auto_commit=False,
            )
        self.db.delete(user)
        self.db.commit()
        return {"success": True}

    def _generate_deleted_phone(self) -> str:
        for _ in range(10):
            candidate = "+999" + "".join(random.choice(string.digits) for _ in range(9))
            exists = self.db.query(User.id).filter(User.phone == candidate).first()
            if not exists:
                return candidate
        raise service_exceptions.ServiceError("Unable to generate unique deleted phone")
