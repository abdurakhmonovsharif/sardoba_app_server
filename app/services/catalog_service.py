from decimal import Decimal

from sqlalchemy.orm import Session, selectinload

from app.core.cache import cache, invalidate_cache
from app.models import Category, Product, Staff, StaffRole

from .ikko_myresto_menu import get_simplified_menu
from . import exceptions

CATEGORY_NAMESPACE = "categories"
PRODUCT_NAMESPACE = "products"
CATALOG_FULL_NAMESPACE = "catalog_full"


class CatalogService:
    def __init__(self, db: Session):
        self.db = db

    @cache(ttl=60, namespace=CATEGORY_NAMESPACE, key_builder=lambda self: "all")
    def get_cached_categories(self) -> list[dict]:
        categories = self.db.query(Category).order_by(Category.name).all()
        result: list[dict] = []
        for cat in categories:
            first_product_image = (
                self.db.query(Product.image_url)
                .filter(Product.category_id == cat.id, Product.image_url.isnot(None))
                .order_by(Product.id)
                .first()
            )
            fallback_image = first_product_image[0] if first_product_image else None
            result.append(self._serialize_category(cat, fallback_image))
        return result

    @cache(ttl=60, namespace=PRODUCT_NAMESPACE, key_builder=lambda self, category_id=None: f"category:{category_id or 'all'}")
    def get_cached_products(self, category_id: int | None = None) -> list[dict]:
        query = self.db.query(Product)
        if category_id:
            query = query.filter(Product.category_id == category_id)
        products = query.order_by(Product.name).all()
        return [self._serialize_product(prod) for prod in products]

    @cache(ttl=60, namespace=CATALOG_FULL_NAMESPACE, key_builder=lambda self: "full")
    def get_categories_with_products_cached(self) -> list[dict]:
        categories = (
            self.db.query(Category)
            .options(selectinload(Category.products))
            .order_by(Category.name)
            .all()
        )
        result = []
        for category in categories:
            result.append(
                {
                    "id": category.id,
                    "name": category.name,
                    "image_url": category.image_url,
                    "products": [self._serialize_product(product) for product in category.products],
                }
            )
        return result

    def create_category(self, *, actor: Staff, data: dict) -> Category:
        self._ensure_manager(actor)
        category = Category(**data)
        self.db.add(category)
        self.db.commit()
        self.db.refresh(category)
        self._invalidate()
        return category

    def update_category(self, *, actor: Staff, category_id: int, data: dict) -> Category:
        self._ensure_manager(actor)
        category = self._get_category(category_id)
        for key, value in data.items():
            setattr(category, key, value)
        self.db.add(category)
        self.db.commit()
        self.db.refresh(category)
        self._invalidate()
        return category

    def delete_category(self, *, actor: Staff, category_id: int) -> None:
        self._ensure_manager(actor)
        category = self._get_category(category_id)
        self.db.delete(category)
        self.db.commit()
        self._invalidate()

    def create_product(self, *, actor: Staff, data: dict) -> Product:
        self._ensure_manager(actor)
        self._get_category(data["category_id"])
        product = Product(**data)
        self.db.add(product)
        self.db.commit()
        self.db.refresh(product)
        self._invalidate_products()
        return product

    def update_product(self, *, actor: Staff, product_id: int, data: dict) -> Product:
        self._ensure_manager(actor)
        product = self._get_product(product_id)
        if "category_id" in data and data["category_id"] is not None:
            self._get_category(data["category_id"])
        for key, value in data.items():
            setattr(product, key, value)
        self.db.add(product)
        self.db.commit()
        self._invalidate_products()
        self.db.refresh(product)
        return product

    def delete_product(self, *, actor: Staff, product_id: int) -> None:
        self._ensure_manager(actor)
        product = self._get_product(product_id)
        self.db.delete(product)
        self.db.commit()
        self._invalidate_products()

    def sync_from_iiko(self, *, actor: Staff) -> dict:
        """Synchronize categories and products from iiko/MyResto menu payload."""
        self._ensure_manager(actor)
        menu = get_simplified_menu()
        categories_payload = menu.get("categories") or []

        existing_categories = {
            cat.name: cat
            for cat in self.db.query(Category).options(selectinload(Category.products)).all()
        }

        created_categories = updated_categories = 0
        created_products = updated_products = removed_products = 0

        for category_data in categories_payload:
            cat_name = (category_data.get("name") or "").strip()
            if not cat_name:
                continue
            cat_image = None

            category = existing_categories.get(cat_name)
            if category is None:
                category = Category(name=cat_name, image_url=cat_image)
                self.db.add(category)
                self.db.flush()
                created_categories += 1
            else:
                if cat_image is not None and category.image_url != cat_image:
                    category.image_url = cat_image
                    updated_categories += 1

            existing_products = {prod.name: prod for prod in (category.products or [])}
            seen_products: set[int] = set()

            for item in category_data.get("items") or []:
                prod_name = (item.get("name") or "").strip()
                if not prod_name:
                    continue
                prices = item.get("prices") or []
                price_values = [
                    p.get("price")
                    for p in prices
                    if isinstance(p, dict) and p.get("price") is not None
                ]
                if not price_values:
                    continue
                price_value = Decimal(str(price_values[0]))
                image_url = None
                images = item.get("images") or []
                if images:
                    image_url = images[0]

                product = existing_products.get(prod_name)
                if product is None:
                    product = Product(
                        name=prod_name,
                        category_id=category.id,
                        price=price_value,
                        image_url=image_url,
                    )
                    self.db.add(product)
                    self.db.flush()
                    created_products += 1
                else:
                    changed = False
                    if product.price != price_value:
                        product.price = price_value
                        changed = True
                    if image_url is not None and product.image_url != image_url:
                        product.image_url = image_url
                        changed = True
                    if product.category_id != category.id:
                        product.category_id = category.id
                        changed = True
                    if changed:
                        updated_products += 1
                    self.db.add(product)
                seen_products.add(product.id)

            for prod in list(category.products or []):
                if prod.id not in seen_products:
                    self.db.delete(prod)
                    removed_products += 1

        self.db.commit()
        self._invalidate()
        return {
            "status": "ok",
            "categories_created": created_categories,
            "categories_updated": updated_categories,
            "products_created": created_products,
            "products_updated": updated_products,
            "products_removed": removed_products,
        }

    def _invalidate(self) -> None:
        invalidate_cache(CATEGORY_NAMESPACE)
        self._invalidate_products()

    @staticmethod
    def _invalidate_products() -> None:
        invalidate_cache(PRODUCT_NAMESPACE)
        invalidate_cache(CATALOG_FULL_NAMESPACE)
        invalidate_cache(CATEGORY_NAMESPACE)

    def _get_category(self, category_id: int) -> Category:
        category = self.db.query(Category).filter(Category.id == category_id).first()
        if not category:
            raise exceptions.NotFoundError("Category not found")
        return category

    def _get_product(self, product_id: int) -> Product:
        product = self.db.query(Product).filter(Product.id == product_id).first()
        if not product:
            raise exceptions.NotFoundError("Product not found")
        return product

    @staticmethod
    def _ensure_manager(actor: Staff) -> None:
        if actor.role != StaffRole.MANAGER:
            raise exceptions.AuthorizationError("Only managers can perform this action")

    @staticmethod
    def _serialize_category(category: Category, fallback_image: str | None = None) -> dict:
        return {
            "id": category.id,
            "name": category.name,
            "image_url": category.image_url or fallback_image,
        }

    @staticmethod
    def _serialize_product(product: Product) -> dict:
        return {
            "id": product.id,
            "category_id": product.category_id,
            "name": product.name,
            "price": str(product.price),
            "image_url": product.image_url,
        }
