from decimal import Decimal
from typing import Optional, List

from pydantic import BaseModel, Field


class CategoryBase(BaseModel):
    name: str = Field(..., max_length=150)
    image_url: Optional[str] = Field(default=None, max_length=500)


class CategoryCreate(CategoryBase):
    pass


class CategoryUpdate(BaseModel):
    name: Optional[str] = Field(default=None, max_length=150)
    image_url: Optional[str] = Field(default=None, max_length=500)


class CategoryRead(CategoryBase):
    id: int

    class Config:
        orm_mode = True


class ProductBase(BaseModel):
    category_id: int
    name: str = Field(..., max_length=255)
    price: Decimal = Field(..., gt=0)
    image_url: Optional[str] = Field(default=None, max_length=500)


class ProductCreate(ProductBase):
    pass


class ProductUpdate(BaseModel):
    category_id: Optional[int] = None
    name: Optional[str] = Field(default=None, max_length=255)
    price: Optional[Decimal] = Field(default=None, gt=0)
    image_url: Optional[str] = Field(default=None, max_length=500)


class ProductRead(ProductBase):
    id: int

    class Config:
        orm_mode = True

class MenuPrice(BaseModel):
    storeId: int
    storeName: str
    price: int
    disabled: bool


class MenuItem(BaseModel):
    id: Optional[str] = None
    name: Optional[str] = None
    prices: List[MenuPrice]
    images: List[str] = Field(default_factory=list)


class MenuCategory(BaseModel):
    id: Optional[str] = None
    name: Optional[str] = None
    slug: Optional[str] = None
    items: List[MenuItem]


class MenuResponse(BaseModel):
    success: bool
    categories: List[MenuCategory]
