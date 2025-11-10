from decimal import Decimal

from app.core.security import create_password_hash
from app.models import Staff, StaffRole, User
from app.models.enums import SardobaBranch


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
    assert len(history) == 1
    assert Decimal(str(history[0]["amount"])) == Decimal("15.50")
    assert Decimal(str(history[0]["balance_after"])) == Decimal("15.50")
    assert history[0]["branch_id"] == SardobaBranch.SARDOBA_GEOFIZIKA.value

    session = session_factory()
    user_db = session.query(User).filter(User.id == user.id).one()
    assert Decimal(user_db.cashback_balance) == Decimal("15.50")
    session.close()
