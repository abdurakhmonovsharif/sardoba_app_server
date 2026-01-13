from app.core.security import create_password_hash
from app.models import AuthActorType, Staff, StaffRole, User, UserNotification
from app.services import (
    AuthService,
    NotificationService,
    NotificationTokenService,
    UserNotificationService,
)


def _create_user(session, phone="+998901234599"):
    user = User(name="Client", phone=phone)
    session.add(user)
    session.commit()
    session.refresh(user)
    return user


def _create_manager(session, phone="+998900000006"):
    manager = Staff(
        name="Manager",
        phone=phone,
        password_hash=create_password_hash("secret123"),
        role=StaffRole.MANAGER,
    )
    session.add(manager)
    session.commit()
    session.refresh(manager)
    return manager


def test_user_notification_service_records_notifications(session_factory):
    session = session_factory()
    user = _create_user(session, phone="+998901234590")
    session.close()

    session = session_factory()
    service = UserNotificationService(session)
    notification = service.create_notification(
        user_id=user.id,
        title="Cashback added",
        description="+50 000 UZS cashback has been added to your balance.",
        notification_type="cashback_accrual",
        payload={"amount": "50000"},
    )
    listed = service.list_for_user(user_id=user.id)
    assert listed
    assert listed[0].id == notification.id
    session.close()


def test_user_notification_service_honors_limit(session_factory):
    session = session_factory()
    user = _create_user(session, phone="+998901234591")
    session.close()

    session = session_factory()
    service = UserNotificationService(session)
    for index in range(3):
        service.create_notification(
            user_id=user.id,
            title=f"Notification {index}",
            description="Test",
            notification_type="test",
        )
    limited = service.list_for_user(user_id=user.id, limit=2)
    assert len(limited) == 2
    session.close()


def test_notification_token_service_handles_ios_without_token(session_factory):
    session = session_factory()
    user = _create_user(session, phone="+998901234592")
    session.close()

    session = session_factory()
    service = NotificationTokenService(session)
    token = service.register_token(
        user_id=user.id,
        device_token=None,
        device_type="ios",
        language="uz",
    )
    updated = service.register_token(
        user_id=user.id,
        device_token="ios-token",
        device_type="ios",
        language="uz",
    )
    assert updated.device_token == "ios-token"
    session.close()


def test_user_notifications_pending_and_mark_sent(session_factory):
    session = session_factory()
    user = _create_user(session, phone="+998901234593")
    session.close()

    session = session_factory()
    service = UserNotificationService(session)
    notification = service.create_notification(
        user_id=user.id,
        title="Pending",
        description="Pending delivery",
        notification_type="test",
    )
    pending = service.list_pending_for_user(user.id)
    assert any(item.id == notification.id for item in pending)
    service.mark_as_sent(notification.id)
    pending_after = service.list_pending_for_user(user.id)
    assert not any(item.id == notification.id for item in pending_after)
    session.close()


def test_notifications_clients_lists_global_notifications(client, db_session):
    user = _create_user(db_session, phone="+998901234594")
    notification = UserNotificationService(db_session).create_notification(
        user_id=user.id,
        title="Hello user",
        description="World",
        notification_type="test",
    )

    tokens = AuthService(db_session).issue_tokens(
        actor_type=AuthActorType.CLIENT,
        subject_id=user.id,
    )

    response = client.get(
        "/api/v1/notifications/clients",
        headers={"Authorization": f"Bearer {tokens['access']}"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["items"]
    assert payload["unread_count"] == 1
    assert payload["items"][0]["title"] == notification.title


def test_mark_notification_read(client, db_session):
    user = _create_user(db_session, phone="+998901234595")
    service = UserNotificationService(db_session)
    notification = service.create_notification(
        user_id=user.id,
        title="Mark me",
        description="Read me",
        notification_type="test",
    )

    tokens = AuthService(db_session).issue_tokens(
        actor_type=AuthActorType.CLIENT,
        subject_id=user.id,
    )

    read_resp = client.post(
        f"/api/v1/notifications/clients/{notification.id}/read",
        headers={"Authorization": f"Bearer {tokens['access']}"},
    )
    assert read_resp.status_code == 204

    list_resp = client.get(
        "/api/v1/notifications/clients",
        headers={"Authorization": f"Bearer {tokens['access']}"},
    )
    assert list_resp.status_code == 200
    data = list_resp.json()
    assert data["unread_count"] == 0
    assert data["items"][0]["is_read"] is True


def test_deleting_notification_removes_user_notifications(session_factory):
    session = session_factory()
    manager = _create_manager(session)
    _ = _create_user(session, phone="+998901234596")
    service = NotificationService(session)
    notification = service.create_notification(
        actor=manager,
        data={"title": "Broadcast", "description": "Hello user"},
    )
    # ensure the fan-out created per-user records for this notification
    assert session.query(UserNotification).filter(
        UserNotification.notification_id == notification.id
    ).count() > 0

    service.delete_notification(actor=manager, notification_id=notification.id)
    remaining = session.query(UserNotification).filter(
        UserNotification.notification_id == notification.id
    ).count()
    assert remaining == 0
    session.close()
