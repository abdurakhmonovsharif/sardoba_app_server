from __future__ import annotations

from typing import Optional, Tuple

from sqlalchemy import or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core import security
from app.models import Staff, StaffRole

from . import exceptions
from .auth_service import AuthService


class StaffService:
    def __init__(self, db: Session):
        self.db = db

    def list_waiters(self, *, page: int, size: int, search: Optional[str] = None) -> Tuple[int, list[Staff]]:
        query = self.db.query(Staff).filter(Staff.role == StaffRole.WAITER)
        if search:
            pattern = f"%{search}%"
            query = query.filter(or_(Staff.name.ilike(pattern), Staff.phone.ilike(pattern)))
        total = query.count()
        waiters = (
            query.order_by(Staff.created_at.desc())
            .offset((page - 1) * size)
            .limit(size)
            .all()
        )
        return total, waiters

    def get_waiter(self, waiter_id: int) -> Staff:
        waiter = (
            self.db.query(Staff)
            .filter(Staff.id == waiter_id, Staff.role == StaffRole.WAITER)
            .first()
        )
        if not waiter:
            raise exceptions.NotFoundError("Waiter not found")
        return waiter

    def create_waiter(
        self,
        *,
        name: str,
        phone: str,
        password: str,
        branch_id: Optional[int],
        actor: Staff,
    ) -> Staff:
        service = AuthService(self.db)
        return service.create_staff(
            name=name,
            phone=phone,
            password=password,
            role=StaffRole.WAITER,
            branch_id=branch_id,
            actor=actor,
        )

    def update_waiter(
        self,
        *,
        waiter_id: int,
        name: Optional[str] = None,
        phone: Optional[str] = None,
        password: Optional[str] = None,
        branch_id: Optional[int] = None,
        branch_is_set: bool = False,
    ) -> Staff:
        waiter = self.get_waiter(waiter_id)

        if phone and phone != waiter.phone:
            exists = (
                self.db.query(Staff.id)
                .filter(Staff.phone == phone, Staff.id != waiter.id)
                .first()
            )
            if exists:
                raise exceptions.ConflictError("Staff with this phone already exists")
            waiter.phone = phone

        if name is not None:
            waiter.name = name

        if branch_is_set:
            waiter.branch_id = branch_id

        if password:
            waiter.password_hash = security.create_password_hash(password)

        self.db.add(waiter)
        self.db.commit()
        self.db.refresh(waiter)
        return waiter

    def delete_waiter(self, waiter_id: int) -> None:
        waiter = self.get_waiter(waiter_id)
        self.db.delete(waiter)
        try:
            self.db.commit()
        except IntegrityError as exc:
            self.db.rollback()
            raise exceptions.ConflictError("Cannot delete waiter with related records") from exc
