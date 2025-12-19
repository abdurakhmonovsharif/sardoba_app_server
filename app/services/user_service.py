import logging
import random
import string
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models import DeletedPhone, User
from app.services.iiko_service import IikoService
from . import exceptions as service_exceptions

logger = logging.getLogger(__name__)


class UserService:
    def __init__(self, db: Session):
        self.db = db
        self._iiko = IikoService()

    def delete_user(
        self, user: User, *, purge_real_phone: bool = True
    ) -> dict[str, bool]:
        if user.deleted:
            return {"success": True}
        fake_phone = self._generate_deleted_phone()
        timestamp = datetime.now(tz=timezone.utc)
        real_phone = user.phone
        user.phone = fake_phone
        user.deleted = True
        user.deleted_at = timestamp
        self.db.add(user)
        if purge_real_phone:
            deleted_phone = DeletedPhone(
                real_phone=real_phone, deleted_at=timestamp, user_id=user.id
            )
            self.db.add(deleted_phone)
        self.db.flush()
        payload = {
            "isDeleted": True,
            "name": user.name or "",
            "phone": fake_phone,
            "comment": user.phone,
            "id": user.iiko_customer_id,
        }
        try:
            self._iiko.create_or_update_customer(
                phone=fake_phone, payload_extra=payload
            )
        except service_exceptions.ServiceError as exc:
            logger.warning(
                "Failed to notify Iiko about deleted user %s: %s", user.id, exc
            )
        self.db.commit()
        return {"success": True}

    def _generate_deleted_phone(self) -> str:
        for _ in range(10):
            candidate = "+999" + "".join(random.choice(string.digits) for _ in range(9))
            exists = self.db.query(User.id).filter(User.phone == candidate).first()
            if not exists:
                conflict = (
                    self.db.query(DeletedPhone.id)
                    .filter(DeletedPhone.real_phone == candidate)
                    .first()
                )
                if not conflict:
                    return candidate
        raise service_exceptions.ServiceError("Unable to generate unique deleted phone")
