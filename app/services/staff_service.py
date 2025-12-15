from __future__ import annotations

from typing import Optional, Tuple

from sqlalchemy import func, or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core import security
from app.models import Staff, StaffRole, User

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
        if waiters:
            waiter_ids = [waiter.id for waiter in waiters]
            counts = (
                self.db.query(User.waiter_id, func.count(User.id).label("client_count"))
                .filter(User.waiter_id.in_(waiter_ids))
                .group_by(User.waiter_id)
                .all()
            )
            count_map = {waiter_id: client_count for waiter_id, client_count in counts}
            for waiter in waiters:
                setattr(waiter, "clients_count", count_map.get(waiter.id, 0))
        return total, waiters

    def list_staff(self, *, page: int, size: int, search: Optional[str] = None) -> Tuple[int, list[Staff]]:
        query = self.db.query(Staff)
        if search:
            pattern = f"%{search}%"
            query = query.filter(or_(Staff.name.ilike(pattern), Staff.phone.ilike(pattern)))
        total = query.count()
        staff_members = (
            query.order_by(Staff.created_at.desc())
            .offset((page - 1) * size)
            .limit(size)
            .all()
        )
        return total, staff_members

    def get_waiter(self, waiter_id: int) -> Staff:
        waiter = (
            self.db.query(Staff)
            .filter(Staff.id == waiter_id, Staff.role == StaffRole.WAITER)
            .first()
        )
        if not waiter:
            raise exceptions.NotFoundError("Waiter not found")
        client_count = (
            self.db.query(func.count(User.id))
            .filter(User.waiter_id == waiter.id)
            .scalar()
            or 0
        )
        setattr(waiter, "clients_count", client_count)
        return waiter

    def create_waiter(
        self,
        *,
        name: str,
        phone: str,
        password: str,
        branch_id: Optional[int],
        referring_code: str | None,
        actor: Staff,
    ) -> Staff:
        service = AuthService(self.db)
        return service.create_staff(
            name=name,
            phone=phone,
            password=password,
            role=StaffRole.WAITER,
            branch_id=branch_id,
            referral_code=referring_code,
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
        referral_code: Optional[str] = None,
        referral_code_is_set: bool = False,
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

        if referral_code_is_set:
            normalized_ref = referral_code.strip() if referral_code else None
            if normalized_ref:
                ref_conflict = (
                    self.db.query(Staff.id)
                    .filter(Staff.referral_code == normalized_ref, Staff.id != waiter.id)
                    .first()
                )
                if ref_conflict:
                    raise exceptions.ConflictError("Referral code already in use")
            waiter.referral_code = normalized_ref

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
