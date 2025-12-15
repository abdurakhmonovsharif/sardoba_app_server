from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.dependencies import get_current_manager, get_db
from app.core.localization import localize_message
from app.models import Staff
from app.schemas import (
    CategoryCreate,
    CategoryRead,
    CategoryUpdate,
    MenuResponse,
    ProductCreate,
    ProductRead,
    ProductUpdate,
)
from app.services import CatalogService
from app.services.ikko_myresto_menu import get_simplified_menu
from app.services import exceptions as service_exceptions

router = APIRouter(prefix="/catalog", tags=["catalog"])


@router.get("/categories", response_model=list[CategoryRead])
def list_categories(db: Session = Depends(get_db)):
    service = CatalogService(db)
    data = service.get_cached_categories()
    return [CategoryRead(**item) for item in data]



@router.get("/live", response_model=MenuResponse)
def list_live_menu():
    data = get_simplified_menu()
    return MenuResponse(**data)


@router.post("/categories", response_model=CategoryRead)
def create_category(
    payload: CategoryCreate,
    manager: Staff = Depends(get_current_manager),
    db: Session = Depends(get_db),
):
    service = CatalogService(db)
    category = service.create_category(actor=manager, data=payload.dict())
    return CategoryRead.from_orm(category)


@router.put("/categories/{category_id}", response_model=CategoryRead)
def update_category(
    category_id: int,
    payload: CategoryUpdate,
    manager: Staff = Depends(get_current_manager),
    db: Session = Depends(get_db),
):
    updates = {k: v for k, v in payload.dict().items() if v is not None}
    service = CatalogService(db)
    try:
        category = service.update_category(actor=manager, category_id=category_id, data=updates)
    except service_exceptions.NotFoundError as exc:
        raise HTTPException(status_code=404, detail=localize_message(str(exc))) from exc
    return CategoryRead.from_orm(category)


@router.delete("/categories/{category_id}", status_code=204)
def delete_category(
    category_id: int,
    manager: Staff = Depends(get_current_manager),
    db: Session = Depends(get_db),
):
    service = CatalogService(db)
    try:
        service.delete_category(actor=manager, category_id=category_id)
    except service_exceptions.NotFoundError as exc:
        raise HTTPException(status_code=404, detail=localize_message(str(exc))) from exc


@router.get("/products", response_model=list[ProductRead])
def list_products(
    category_id: Optional[int] = Query(default=None),
    db: Session = Depends(get_db),
):
    service = CatalogService(db)
    data = service.get_cached_products(category_id=category_id)
    return [ProductRead(**{**item, "price": Decimal(item["price"])}) for item in data]


@router.post("/products", response_model=ProductRead)
def create_product(
    payload: ProductCreate,
    manager: Staff = Depends(get_current_manager),
    db: Session = Depends(get_db),
):
    service = CatalogService(db)
    try:
        product = service.create_product(actor=manager, data=payload.dict())
    except service_exceptions.NotFoundError as exc:
        raise HTTPException(status_code=404, detail=localize_message(str(exc))) from exc
    return ProductRead.from_orm(product)


@router.put("/products/{product_id}", response_model=ProductRead)
def update_product(
    product_id: int,
    payload: ProductUpdate,
    manager: Staff = Depends(get_current_manager),
    db: Session = Depends(get_db),
):
    updates = {k: v for k, v in payload.dict().items() if v is not None}
    service = CatalogService(db)
    try:
        product = service.update_product(actor=manager, product_id=product_id, data=updates)
    except service_exceptions.NotFoundError as exc:
        raise HTTPException(status_code=404, detail=localize_message(str(exc))) from exc
    return ProductRead.from_orm(product)


@router.delete("/products/{product_id}", status_code=204)
def delete_product(
    product_id: int,
    manager: Staff = Depends(get_current_manager),
    db: Session = Depends(get_db),
):
    service = CatalogService(db)
    try:
        service.delete_product(actor=manager, product_id=product_id)
    except service_exceptions.NotFoundError as exc:
        raise HTTPException(status_code=404, detail=localize_message(str(exc))) from exc


@router.post("/sync", response_model=dict)
def sync_catalog_with_iiko(
    manager: Staff = Depends(get_current_manager),
    db: Session = Depends(get_db),
):
    service = CatalogService(db)
    result = service.sync_from_iiko(actor=manager)
    return result
