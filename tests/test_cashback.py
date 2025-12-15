from decimal import Decimal

from app.core.security import create_password_hash
from app.models import Staff, StaffRole, User
from app.models.enums import SardobaBranch, UserLevel


def _create_manager(session, phone="+998900000002"):
    manager = Staff(
        name="Manager",
        phone=phone,
        password_hash=create_password_hash("secret123"),
        role=StaffRole.MANAGER,
    )
    session.add(manager)
    session.commit()
    return manager


def _create_user(session, phone="+998901234568"):
    user = User(name="Client", phone=phone)
    session.add(user)
    session.commit()
    session.refresh(user)
    return user


def test_add_cashback_and_history(client, session_factory):
    session = session_factory()
    manager = _create_manager(session)
    user = _create_user(session)
    session.close()

    login_resp = client.post(
        "/api/v1/auth/staff/login",
        json={"phone": manager.phone, "password": "secret123"},
    )
    assert login_resp.status_code == 200
    token = login_resp.json()["tokens"]["access_token"]

    add_resp = client.post(
        "/api/v1/cashback/add",
        json={
            "user_id": user.id,
            "amount": "15.50",
            "branch_id": SardobaBranch.SARDOBA_GEOFIZIKA.value,
            "source": "MANUAL",
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert add_resp.status_code == 200
    data = add_resp.json()
    assert Decimal(str(data["amount"])) == Decimal("15.50")

    history_resp = client.get(
        f"/api/v1/cashback/user/{user.id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert history_resp.status_code == 200
    history = history_resp.json()
    transactions = history["transactions"]
    assert len(transactions) == 1
    assert Decimal(str(transactions[0]["amount"])) == Decimal("15.50")
    assert Decimal(str(transactions[0]["balance_after"])) == Decimal("15.50")
    assert transactions[0]["branch_id"] == SardobaBranch.SARDOBA_GEOFIZIKA.value
    loyalty = history["loyalty"]
    assert loyalty["level"] == "SILVER"
    assert Decimal(str(loyalty["cashback_balance"])) == Decimal("15.50")
    assert Decimal(str(loyalty["points_total"])) == Decimal("7")
    assert Decimal(str(loyalty["current_level_points"])) == Decimal("7")
    assert Decimal(str(loyalty["current_level_min_points"])) == Decimal("0")
    assert Decimal(str(loyalty["current_level_max_points"])) == Decimal("10000")
    assert loyalty["next_level"] == "GOLD"
    assert Decimal(str(loyalty["next_level_required_points"])) == Decimal("10000")
    assert Decimal(str(loyalty["points_to_next_level"])) == Decimal("9993")
    assert loyalty["is_max_level"] is False
    assert Decimal(str(loyalty["cashback_percent"])) == Decimal("2.00")
    assert Decimal(str(loyalty["next_level_cashback_percent"])) == Decimal("2.50")

    session = session_factory()
    user_db = session.query(User).filter(User.id == user.id).one()
    assert Decimal(user_db.cashback_balance) == Decimal("15.50")
    session.close()


def test_add_cashback_awards_loyalty_points(client, session_factory):
    session = session_factory()
    manager = _create_manager(session, phone="+998900000003")
    user = _create_user(session, phone="+998901234569")
    session.close()

    login_resp = client.post(
        "/api/v1/auth/staff/login",
        json={"phone": manager.phone, "password": "secret123"},
    )
    token = login_resp.json()["tokens"]["access_token"]

    add_resp = client.post(
        "/api/v1/cashback/add",
        json={
            "user_id": user.id,
            "amount": "250000",
            "branch_id": SardobaBranch.SARDOBA_GEOFIZIKA.value,
            "source": "MANUAL",
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert add_resp.status_code == 200
    session = session_factory()
    user_db = session.query(User).filter(User.id == user.id).one()
    assert user_db.cashback_wallet is not None
    assert Decimal(user_db.cashback_wallet.points) == Decimal("125000")
    assert user_db.level == UserLevel.VIP
    session.close()


def test_cashback_use_requires_minimums(client, session_factory):
    session = session_factory()
    manager = _create_manager(session, phone="+998900000004")
    user = _create_user(session, phone="+998901234570")
    session.close()

    login_resp = client.post(
        "/api/v1/auth/staff/login",
        json={"phone": manager.phone, "password": "secret123"},
    )
    token = login_resp.json()["tokens"]["access_token"]

    client.post(
        "/api/v1/cashback/add",
        json={
            "user_id": user.id,
            "amount": "60000",
            "branch_id": SardobaBranch.SARDOBA_GEOFIZIKA.value,
            "source": "MANUAL",
        },
        headers={"Authorization": f"Bearer {token}"},
    )

    use_resp = client.post(
        "/api/v1/cashback/use",
        json={"user_id": user.id, "amount": "40000"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert use_resp.status_code == 400
    assert use_resp.json()["detail"]["uz"] == "Keshbek bilan to'lash uchun summa kamida 50 000 so'm bo'lishi kerak."

    use_resp = client.post(
        "/api/v1/cashback/use",
        json={"user_id": user.id, "amount": "70000"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert use_resp.status_code == 400
    assert use_resp.json()["detail"]["uz"] == "Keshbek balansi yetarli emas."

    session = session_factory()
    user_db = session.query(User).filter(User.id == user.id).one()
    assert Decimal(user_db.cashback_balance) == Decimal("60000")
    session.close()


def test_cashback_use_succeeds(client, session_factory):
    session = session_factory()
    manager = _create_manager(session, phone="+998900000005")
    user = _create_user(session, phone="+998901234571")
    session.close()

    login_resp = client.post(
        "/api/v1/auth/staff/login",
        json={"phone": manager.phone, "password": "secret123"},
    )
    token = login_resp.json()["tokens"]["access_token"]

    client.post(
        "/api/v1/cashback/add",
        json={
            "user_id": user.id,
            "amount": "60000",
            "branch_id": SardobaBranch.SARDOBA_GEOFIZIKA.value,
            "source": "MANUAL",
        },
        headers={"Authorization": f"Bearer {token}"},
    )

    use_resp = client.post(
        "/api/v1/cashback/use",
        json={"user_id": user.id, "amount": "50000"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert use_resp.status_code == 200
    resp_data = use_resp.json()
    assert resp_data["can_use_cashback"] is True
    assert Decimal(resp_data["balance"]) == Decimal("60000")
    assert resp_data["message"]["uz"] == "Keshbek bilan to'lovga ruxsat beriladi."
