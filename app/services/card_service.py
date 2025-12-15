import secrets
from sqlalchemy.orm import Session

from app.models import Card, User


class CardService:
    CARD_NUMBER_PREFIX = "8600"
    CARD_NUMBER_LENGTH = 16
    CARD_TRACK_LENGTH = 32

    def __init__(self, db: Session):
        self.db = db

    def _generate_card_number(self) -> str:
        suffix_length = self.CARD_NUMBER_LENGTH - len(self.CARD_NUMBER_PREFIX)
        while True:
            suffix = "".join(secrets.choice("0123456789") for _ in range(suffix_length))
            candidate = f"{self.CARD_NUMBER_PREFIX}{suffix}"
            exists = (
                self.db.query(Card.id).filter(Card.card_number == candidate).first()
            )
            if not exists:
                return candidate

    def _generate_card_track(self) -> str:
        while True:
            track = "".join(secrets.choice("0123456789") for _ in range(20))  # 20-digit
            exists = self.db.query(Card.id).filter(Card.card_track == track).first()
            if not exists:
                return track

    def create_card_for_user(self, user: User, iiko_card_id: str | None = None) -> Card:
        card = Card(
            user_id=user.id,
            card_number=self._generate_card_number(),
            card_track=self._generate_card_track(),
            iiko_card_id=iiko_card_id,
        )
        self.db.add(card)
        self.db.flush()
        return card

    def _normalize_card_number(self, value: str) -> str:
        return "".join(ch for ch in value if ch.isdigit())

    def _normalize_card_track(self, value: str) -> str:
        return value.strip()

    def ensure_card_from_iiko(
        self, user: User, card_payload: dict[str, str]
    ) -> Card | None:
        card_number_raw = card_payload.get("cardNumber") or card_payload.get("number")
        card_track_raw = card_payload.get("cardTrack") or card_payload.get("track")
        if not card_number_raw or not card_track_raw:
            return None
        card_number = self._normalize_card_number(card_number_raw)
        card_track = self._normalize_card_track(card_track_raw)
        if not card_number or not card_track:
            return None
        existing = self.db.query(Card).filter(Card.card_number == card_number).first()
        iiko_card_id = card_payload.get("id") or card_payload.get("cardId")
        if existing:
            if card_track:
                existing.card_track = card_track
            if iiko_card_id:
                existing.iiko_card_id = iiko_card_id
            self.db.add(existing)
            return existing
        card = Card(
            user_id=user.id,
            card_number=card_number,
            card_track=card_track,
            iiko_card_id=iiko_card_id,
        )
        self.db.add(card)
        self.db.flush()
        return card
