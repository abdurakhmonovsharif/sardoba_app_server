from app.models import User


def test_webhook_sets_giftget_flag_on_35k_refill(client, db_session):
    user = User(
        phone="+998931434413",
        name="Gift Recipient",
        iiko_customer_id="gift-customer-id",
    )
    db_session.add(user)
    db_session.commit()
    payload = {
        "sum": "35000",
        "balance": "35000",
        "walletId": "gift-wallet",
        "customerId": user.iiko_customer_id,
        "id": "event-123",
        "uocId": "uoc-123",
        "transactionType": "RefillWallet",
        "phone": user.phone,
    }

    response = client.post("/api/v1/iiko/webhook", json=payload)
    assert response.status_code == 200
    db_session.refresh(user)
    assert user.giftget is True


def test_webhook_sets_giftget_flag_on_35k_pay_from_wallet(client, db_session):
    user = User(
        phone="+998931434414",
        name="Gift Spender",
        iiko_customer_id="gift-spender-customer-id",
    )
    db_session.add(user)
    db_session.commit()
    payload = {
        "sum": "35000",
        "balance": "0",
        "walletId": "gift-wallet-2",
        "customerId": user.iiko_customer_id,
        "id": "event-456",
        "uocId": "uoc-456",
        "transactionType": "PayFromWallet",
        "phone": user.phone,
    }

    response = client.post("/api/v1/iiko/webhook", json=payload)
    assert response.status_code == 200
    db_session.refresh(user)
    assert user.giftget is True
