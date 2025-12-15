from app.models import User
from app.services import NotificationTokenService, UserNotificationService


def _create_user(session, phone="+998901234599"):
    user = User(name="Client", phone=phone)
    session.add(user)
    session.commit()
    session.refresh(user)
    return user


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
