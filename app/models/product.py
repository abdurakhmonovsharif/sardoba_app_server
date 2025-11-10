from decimal import Decimal

from sqlalchemy import DECIMAL, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base


class Product(Base):
    __tablename__ = "products"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    category_id: Mapped[int] = mapped_column(ForeignKey("categories.id"), index=True)
    name: Mapped[str] = mapped_column(String(255))
    price: Mapped[Decimal] = mapped_column(DECIMAL(10, 2))
    image_url: Mapped[str | None] = mapped_column(String(500), nullable=True)

    category: Mapped["Category"] = relationship("Category", back_populates="products")
