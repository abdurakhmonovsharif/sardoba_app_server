import logging

from sqlalchemy.exc import IntegrityError
from passlib.exc import UnknownHashError

from app.core import security
from app.core.config import get_settings
from app.core.db import session_scope
from app.models import Staff, StaffRole

logger = logging.getLogger(__name__)


def ensure_default_admin() -> None:
    """Create or update the default admin user defined via environment variables."""

    settings = get_settings()
    phone = (settings.DEFAULT_ADMIN_PHONE or "").strip()
    password = settings.DEFAULT_ADMIN_PASSWORD
    name = (settings.DEFAULT_ADMIN_NAME or "Admin").strip() or "Admin"

    if not phone or not password:
        logger.warning("Default admin bootstrap skipped: phone or password not configured")
        return

    with session_scope() as db:
        admin = db.query(Staff).filter(Staff.phone == phone).first()
        if admin:
            updated = False
            if admin.role != StaffRole.MANAGER:
                admin.role = StaffRole.MANAGER
                updated = True
            if admin.name != name:
                admin.name = name
                updated = True
            needs_password_update = False
            if not admin.password_hash:
                needs_password_update = True
            else:
                try:
                    if not security.verify_password(password, admin.password_hash):
                        needs_password_update = True
                except (ValueError, UnknownHashError):
                    needs_password_update = True
            if needs_password_update:
                admin.password_hash = security.create_password_hash(password)
                updated = True
            if updated:
                logger.info("Default admin '%s' updated", phone)
            return

        admin = Staff(
            name=name,
            phone=phone,
            password_hash=security.create_password_hash(password),
            role=StaffRole.MANAGER,
        )
        db.add(admin)
        try:
            db.flush()
        except IntegrityError:
            logger.warning(
                "Default admin bootstrap encountered integrity error (phone=%s). Another process may have created it.",
                phone,
            )
            db.rollback()
        else:
            logger.info("Default admin '%s' created", phone)
