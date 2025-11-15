from app.core.config import get_settings
from app.core.security import create_password_hash
from app.models import OTPCode, Staff, StaffRole, User


def test_client_otp_flow(client, db_session):
    phone = "+998901234567"
    existing = User(name="Existing", phone=phone)
    db_session.add(existing)
    db_session.commit()

    response = client.post(
        "/api/v1/auth/client/request-otp",
        json={"phone": phone, "purpose": "login"},
    )
    assert response.status_code == 204

    otp = (
        db_session.query(OTPCode)
        .filter(OTPCode.phone == phone)
        .order_by(OTPCode.id.desc())
        .first()
    )
    assert otp is not None
    settings = get_settings()
    assert len(otp.code) == settings.OTP_LENGTH

    verify_response = client.post(
        "/api/v1/auth/client/verify-otp",
        json={"phone": phone, "code": otp.code, "name": "Test User", "purpose": "login"},
    )
    assert verify_response.status_code == 200
    data = verify_response.json()
    assert "user" not in data
    access_token = data["tokens"]["access_token"]
    refresh_token = data["tokens"]["refresh_token"]
    assert access_token and refresh_token

    me_response = client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {access_token}"},
    )
    assert me_response.status_code == 200
    profile = me_response.json()
    assert profile["type"] == "CLIENT"
    assert profile["profile"]["phone"] == phone
    assert profile["cashback"]["balance"] == "0.00"
    assert profile["cashback"]["currency"] == "UZS"
    assert profile["cashback"]["transactions"] == []
    assert profile["profile"]["date_of_birth"] is None


def test_login_requires_existing_user(client, db_session):
    phone = "+998908080808"

    response = client.post(
        "/api/v1/auth/client/request-otp",
        json={"phone": phone, "purpose": "login"},
    )
    assert response.status_code == 204

    otp = (
        db_session.query(OTPCode)
        .filter(OTPCode.phone == phone)
        .order_by(OTPCode.id.desc())
        .first()
    )
    assert otp is not None

    verify_response = client.post(
        "/api/v1/auth/client/verify-otp",
        json={"phone": phone, "code": otp.code, "purpose": "login"},
    )
    assert verify_response.status_code == 404
    assert verify_response.json()["detail"] == "User not found. Please register first."


def test_client_registers_with_waiter_referral(client, db_session):
    waiter = Staff(
        name="Waiter One",
        phone="+998900000050",
        password_hash=create_password_hash("secret123"),
        role=StaffRole.WAITER,
        referral_code="WAITER1",
    )
    db_session.add(waiter)
    db_session.commit()

    phone = "+998909876543"
    request_resp = client.post(
        "/api/v1/auth/client/request-otp",
        json={"phone": phone, "purpose": "register"},
    )
    assert request_resp.status_code == 204

    otp = (
        db_session.query(OTPCode)
        .filter(OTPCode.phone == phone)
        .order_by(OTPCode.id.desc())
        .first()
    )
    assert otp is not None

    dob = "05.08.1995"

    verify_response = client.post(
        "/api/v1/auth/client/verify-otp",
        json={
            "phone": phone,
            "code": otp.code,
            "name": "Referral User",
            "waiter_referral_code": "WAITER1",
            "purpose": "register",
            "date_of_birth": dob,
        },
    )
    assert verify_response.status_code == 200
    data = verify_response.json()
    assert "user" not in data
    access_token = data["tokens"]["access_token"]
    assert access_token

    me_response = client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {access_token}"},
    )
    assert me_response.status_code == 200
    profile = me_response.json()
    assert profile["profile"]["phone"] == phone
    assert profile["profile"]["waiter_id"] == waiter.id
    assert profile["cashback"]["balance"] == "0.00"
    assert profile["cashback"]["currency"] == "UZS"
    assert profile["profile"]["date_of_birth"] == dob


def test_staff_login_and_refresh(client, session_factory):
    session = session_factory()
    manager = Staff(
        name="Manager",
        phone="+998900000001",
        password_hash=create_password_hash("secret123"),
        role=StaffRole.MANAGER,
    )
    session.add(manager)
    session.commit()
    session.close()

    response = client.post(
        "/api/v1/auth/staff/login",
        json={"phone": manager.phone, "password": "secret123"},
    )
    assert response.status_code == 200
    payload = response.json()
    access = payload["tokens"]["access_token"]
    refresh = payload["tokens"]["refresh_token"]
    assert access and refresh

    refresh_resp = client.post("/api/v1/auth/refresh", json={"refresh_token": refresh})
    assert refresh_resp.status_code == 200
    refreshed = refresh_resp.json()
    assert refreshed["access_token"]


def test_refresh_requires_token_value(client):
    response = client.post("/api/v1/auth/refresh", json={"refresh_token": ""})
    assert response.status_code == 400
    assert response.json()["detail"] == "refresh_token is required"


def test_refresh_invalid_token_returns_unauthorized(client):
    response = client.post("/api/v1/auth/refresh", json={"refresh_token": "invalid"})
    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid refresh token"
