from app.models import OTPCode, User


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
    token, user = _register_user(client, db_session, phone="+998901002002")
    user_id = user.id
    response = client.delete(
        "/api/v1/users/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 204
    db_session.expire_all()
    assert db_session.query(User).filter(User.id == user_id).first() is None


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
