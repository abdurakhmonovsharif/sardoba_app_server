import httpx

from app.models import OTPCode, User
from app.services import exceptions as service_exceptions


def _register_user(client, db_session, phone: str = "+998901112233") -> tuple[str, User]:
    client.post(
        "/api/v1/auth/client/request-otp",
        json={"phone": phone, "purpose": "register"},
    )
    otp = (
        db_session.query(OTPCode)
        .filter(OTPCode.phone == phone)
        .order_by(OTPCode.id.desc())
        .first()
    )
    assert otp is not None
    verify_response = client.post(
        "/api/v1/auth/client/verify-otp",
        json={"phone": phone, "code": otp.code, "purpose": "register"},
    )
    assert verify_response.status_code == 200
    access_token = verify_response.json()["tokens"]["access_token"]
    user = db_session.query(User).filter(User.phone == phone).first()
    assert user is not None
    return access_token, user


def test_user_can_update_profile(client, db_session):
    token, user = _register_user(client, db_session, phone="+998901001001")
    response = client.put(
        "/api/v1/users/me",
        json={"name": "Updated User", "date_of_birth": "02.02.1990"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "Updated User"
    assert data["date_of_birth"] == "02.02.1990"

    db_session.expire_all()
    updated = db_session.query(User).filter(User.id == user.id).first()
    assert updated.name == "Updated User"
    assert updated.date_of_birth.strftime("%d.%m.%Y") == "02.02.1990"


def test_user_can_delete_account(client, db_session):
    phone = "+998901002002"
    token, user = _register_user(client, db_session, phone=phone)
    user_id = user.id
    response = client.delete(
        "/api/v1/users/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 204
    db_session.expire_all()
    deleted = db_session.query(User).filter(User.id == user_id).first()
    assert deleted is None


def test_deleted_user_can_reregister(client, db_session):
    phone = "+998901004004"
    token, user = _register_user(client, db_session, phone=phone)
    user_id = user.id
    delete_response = client.delete(
        "/api/v1/users/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert delete_response.status_code == 204
    db_session.expire_all()
    deleted = db_session.query(User).filter(User.id == user_id).first()
    assert deleted is None

    request_response = client.post(
        "/api/v1/auth/client/request-otp",
        json={"phone": phone, "purpose": "register"},
    )
    assert request_response.status_code == 204
    otp = (
        db_session.query(OTPCode)
        .filter(OTPCode.phone == phone)
        .order_by(OTPCode.id.desc())
        .first()
    )
    assert otp is not None
    verify_response = client.post(
        "/api/v1/auth/client/verify-otp",
        json={
            "phone": phone,
            "code": otp.code,
            "purpose": "register",
            "name": "Reactivated",
            "date_of_birth": "01.01.1991",
        },
    )
    assert verify_response.status_code == 200

    db_session.expire_all()
    reactivated = db_session.query(User).filter(User.phone == phone).first()
    assert reactivated is not None
    assert reactivated.is_deleted is False
    assert reactivated.deleted_at is None
    assert reactivated.name == "Reactivated"
    assert reactivated.date_of_birth.strftime("%d.%m.%Y") == "01.01.1991"


def test_delete_user_notifies_iiko_with_real_phone(db_session, monkeypatch):
    phone = "+998901020202"
    user = User(name="Notify Real", phone=phone)
    db_session.add(user)
    db_session.commit()

    class FakeIikoService:
        def __init__(self):
            self.calls: list[dict[str, object]] = []

        def create_or_update_customer(
            self, *, phone: str, payload_extra: dict[str, object] | None = None
        ) -> dict[str, object]:
            self.calls.append(
                {
                    "phone": phone,
                    "payload": dict(payload_extra) if payload_extra else {},
                }
            )
            return {}

    fake_service = FakeIikoService()
    monkeypatch.setattr("app.services.user_service.IikoService", lambda: fake_service)

    from app.services.user_service import UserService

    UserService(db_session).delete_user(user)
    assert len(fake_service.calls) == 1
    recorded = fake_service.calls[0]
    assert recorded["phone"] == phone
    assert recorded["payload"].get("isDeleted") is True
    assert recorded["payload"].get("phone") == phone


def test_register_aborts_on_iiko_bad_request(client, db_session, monkeypatch):
    phone = "+998901005005"

    def fake_create_or_update_customer(self, *, phone: str, payload_extra: dict | None = None):
        request = httpx.Request("POST", "https://api-ru.iiko.services/api/1/loyalty/iiko/customer/create_or_update")
        response = httpx.Response(status_code=400)
        raise service_exceptions.ServiceError("Iiko rejected the payload") from httpx.HTTPStatusError(
            "Bad Request", request=request, response=response
        )

    monkeypatch.setattr(
        "app.services.auth_service.IikoService.create_or_update_customer", fake_create_or_update_customer
    )
    client.post(
        "/api/v1/auth/client/request-otp",
        json={"phone": phone, "purpose": "register"},
    )
    otp = (
        db_session.query(OTPCode)
        .filter(OTPCode.phone == phone)
        .order_by(OTPCode.id.desc())
        .first()
    )
    assert otp is not None
    response = client.post(
        "/api/v1/auth/client/verify-otp",
        json={"phone": phone, "code": otp.code, "purpose": "register"},
    )
    assert response.status_code == 400
    db_session.rollback()
    assert db_session.query(User).filter(User.phone == phone).first() is None


def test_user_can_upload_profile_photo(client, db_session):
    token, user = _register_user(client, db_session, phone="+998901003003")
    files = {"file": ("avatar.png", b"fake-image-bytes", "image/png")}
    response = client.post(
        "/api/v1/files/profile-photo",
        headers={"Authorization": f"Bearer {token}"},
        files=files,
    )
    assert response.status_code == 201
    data = response.json()
    assert data["profile_photo_url"].endswith(".png")

    photo_url = data["profile_photo_url"]
    get_response = client.get(photo_url)
    assert get_response.status_code == 200

    db_session.expire_all()
    stored = db_session.query(User).filter(User.id == user.id).first()
    assert stored.profile_photo_url == photo_url
