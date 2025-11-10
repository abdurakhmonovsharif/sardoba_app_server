from sqlalchemy.orm import Session, selectinload

from app.core.cache import cache, invalidate_cache
from app.models import Category, Product, Staff, StaffRole

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
        return [self._serialize_category(cat) for cat in categories]

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

    def _invalidate(self) -> None:
        invalidate_cache(CATEGORY_NAMESPACE)
        self._invalidate_products()

    @staticmethod
    def _invalidate_products() -> None:
        invalidate_cache(PRODUCT_NAMESPACE)
        invalidate_cache(CATALOG_FULL_NAMESPACE)

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
    def _serialize_category(category: Category) -> dict:
        return {
            "id": category.id,
            "name": category.name,
            "image_url": category.image_url,
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
