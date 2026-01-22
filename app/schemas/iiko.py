from __future__ import annotations

from decimal import Decimal
from enum import Enum

from pydantic import BaseModel


class IikoTransactionType(str, Enum):
    ACCRUAL = "Accrual"                    # bonus qo‘shish
    PAY_FROM_WALLET = "PayFromWallet"      # bonus yechish
    CORRECTION = "Correction"              # tuzatish
    REFILL_WALLET = "RefillWallet"         # bonus/hisob to‘ldirish ← yangi!
    REFILL_WALLET_FROM_ORDER = "RefillWalletFromOrder"
    SIMPLE_PUSH = "SimplePush"
    WELCOMEBONUS = "WelcomeBonus"


class IikoWebhookPayload(BaseModel):
    sum: Decimal | None = None
    balance: Decimal | None = None
    walletId: str | None = None
    id: str | None = None
    customerId: str | None = None
    uocId: str | None = None
    transactionType: IikoTransactionType
    notificationType: int | None = None
    orderId: str | None = None
    orderNumber: str | None = None
    isDelivery: bool | None = None
    terminalGroupId: str | None = None
    subscriptionPassword: str | None = None
    changedOn: str | None = None
    phone: str | None = None


class IikoUserLookup(BaseModel):
    walletId: str | None = None
    customerId: str | None = None
    phone: str | None = None
