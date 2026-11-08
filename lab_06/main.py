"""
Лабораторна робота №6: Автоматизоване тестування Python-програм.
Варіант №3: Інтернет-магазин (E-commerce shop).

Повністю автономний виробничий та тестовий модуль без зовнішніх залежностей від інших робіт.
Містить доменні моделі, сервіси, протоколи, імпорт/експорт, фікстури різного scope,
параметризовані unit-тести, інтеграційні тести, використання Mock/MagicMock/AsyncMock,
monkeypatch (env vars, attributes, functions), tmp_path та звітність про покриття коду.
"""

from __future__ import annotations

import asyncio
import csv
import json
import os
import sys
import time
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Protocol
from unittest.mock import AsyncMock, MagicMock, Mock

import pytest


# =====================================================================
# 1. ДОМЕННІ ВИНЯТКИ (DOMAIN EXCEPTIONS)
# =====================================================================

class ShopError(Exception):
    """Базовий виняток предметної області інтернет-магазину."""
    pass


class ValidationError(ShopError):
    """Помилка валідації вхідних даних доменної сутності."""

    def __init__(self, message: str, field_name: str) -> None:
        super().__init__(message)
        self.field_name = field_name


class ProductNotFoundError(ShopError):
    """Виникає при спробі доступу до неіснуючого товару."""
    pass


class DataImportError(ShopError):
    """Виникає при помилках структури або синтаксису імпортованих файлів."""
    pass


class PaymentError(ShopError):
    """Виникає при помилках взаємодії із зовнішнім платіжним шлюзом."""
    pass


class ProviderUnavailableError(ShopError):
    """Виникає при збоях зовнішніх провайдерів валютних курсів або сервісів."""
    pass


# =====================================================================
# 2. VALUE OBJECTS & ENTITIES (ДОМЕННІ МОДЕЛІ)
# =====================================================================

class ProductCategory(str, Enum):
    """Перелік категорій товарів магазину."""
    ELECTRONICS = "Electronics"
    CLOTHING = "Clothing"
    BOOKS = "Books"
    HOME = "Home"
    FOOD = "Food"


@dataclass(frozen=True, slots=True)
class Money:
    """Незмінний об'єкт-значення (Value Object) для грошових операцій."""
    amount: float
    currency: str = "UAH"

    def __post_init__(self) -> None:
        if self.amount < 0.0:
            raise ValueError(f"Грошова сума не може бути від'ємною: {self.amount}")

    def __add__(self, other: Money) -> Money:
        if not isinstance(other, Money):
            return NotImplemented
        if self.currency != other.currency:
            raise ValueError(
                f"Неможливо додати гроші в різних валютах: {self.currency} != {other.currency}"
            )
        return Money(round(self.amount + other.amount, 2), self.currency)

    def __mul__(self, factor: float) -> Money:
        if factor < 0:
            raise ValueError("Множник вартості не може бути від'ємним")
        return Money(round(self.amount * factor, 2), self.currency)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Money):
            return False
        return self.currency == other.currency and abs(self.amount - other.amount) < 1e-6


@dataclass(slots=True)
class Product:
    """Доменна сутність товару в каталозі."""
    product_id: int
    name: str
    category: ProductCategory
    price: Money
    quantity: int

    def __post_init__(self) -> None:
        if self.product_id <= 0:
            raise ValidationError("ID товару повинен бути додатним цілим числом", "product_id")
        if not self.name or not self.name.strip():
            raise ValidationError("Назва товару не може бути порожньою", "name")
        if self.quantity < 0:
            raise ValidationError("Кількість товару не може бути від'ємною", "quantity")

    @property
    def total_stock_value(self) -> Money:
        """Загальна балансова вартість залишку даної позиції."""
        return self.price * self.quantity


# =====================================================================
# 3. ІНТЕРФЕЙСИ (PROTOCOLS)
# =====================================================================

class ProductRepository(Protocol):
    """Контракт сховища товарів."""

    def add(self, product: Product) -> None:
        ...

    def get_by_id(self, product_id: int) -> Optional[Product]:
        ...

    def get_all(self) -> List[Product]:
        ...

    def remove(self, product_id: int) -> bool:
        ...


class DiscountPolicy(Protocol):
    """Контракт розрахунку знижки."""

    def apply(self, total: Money) -> Money:
        ...


class Notifier(Protocol):
    """Контракт каналу сповіщення користувачів."""

    def send_notification(self, recipient: str, message: str) -> None:
        ...


class PaymentGateway(Protocol):
    """Контракт зовнішнього платіжного шлюзу."""

    def process_payment(self, amount: Money) -> str:
        ...


class ExternalPriceProvider(Protocol):
    """Асинхронний інтерфейс зовнішнього постачальника валютних курсів."""

    async def get_exchange_rate(self, target_currency: str) -> float:
        ...


class AuditSession(Protocol):
    """Контракт контекстного менеджера для аудиту замовлень."""

    def __enter__(self) -> AuditSession:
        ...

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        ...

    def record_step(self, step_name: str) -> None:
        ...


# =====================================================================
# 4. РЕПОЗИТОРІЙ ТА БІЗНЕС-СЕРВІСИ (APPLICATION SERVICES)
# =====================================================================

def generate_order_id(prefix: str = "ORD") -> str:
    """Генерує базовий системний код замовлення."""
    timestamp = int(time.time())
    return f"{prefix}-{timestamp}"


class InMemoryProductRepository:
    """In-memory сховище товарів для швидкої та ізольованої роботи."""

    def __init__(self) -> None:
        self._storage: Dict[int, Product] = {}

    def add(self, product: Product) -> None:
        self._storage[product.product_id] = product

    def get_by_id(self, product_id: int) -> Optional[Product]:
        return self._storage.get(product_id)

    def get_all(self) -> List[Product]:
        return list(self._storage.values())

    def remove(self, product_id: int) -> bool:
        return self._storage.pop(product_id, None) is not None

    def __len__(self) -> int:
        return len(self._storage)


class PercentageDiscount:
    """Політика знижки у відсотках [0; 100]."""

    def __init__(self, percent: float) -> None:
        if not (0.0 <= percent <= 100.0):
            raise ValueError(f"Відсоток знижки має знаходитися в межах [0; 100], отримано: {percent}")
        self.percent = percent

    def apply(self, total: Money) -> Money:
        discounted = total.amount * (1.0 - self.percent / 100.0)
        return Money(round(discounted, 2), total.currency)


class CatalogService:
    """Сервіс управління каталогом, аналітики складських запасів і пошуку."""

    def __init__(self, repository: ProductRepository) -> None:
        self.repository = repository

    def add_product(self, product: Product) -> None:
        self.repository.add(product)

    def find_by_id(self, product_id: int) -> Product:
        product = self.repository.get_by_id(product_id)
        if product is None:
            raise ProductNotFoundError(f"Товар з ID {product_id} не знайдено в каталозі")
        return product

    def search_by_name(self, query: str) -> List[Product]:
        normalized = query.strip().lower()
        if not normalized:
            return []
        return [
            prod for prod in self.repository.get_all()
            if normalized in prod.name.lower()
        ]

    def filter_by_category(self, category: ProductCategory) -> List[Product]:
        return [
            prod for prod in self.repository.get_all()
            if prod.category == category
        ]

    def calculate_total_inventory_value(self) -> Money:
        products = self.repository.get_all()
        if not products:
            return Money(0.0)

        total = 0.0
        currency = products[0].price.currency
        for prod in products:
            if prod.price.currency != currency:
                raise ValueError("Товари в каталозі мають різні валюти цін")
            total += prod.total_stock_value.amount
        return Money(round(total, 2), currency)

    def get_most_expensive_product(self) -> Optional[Product]:
        products = self.repository.get_all()
        if not products:
            return None
        return max(products, key=lambda p: p.price.amount)

    def get_low_stock_products(self, threshold: int) -> List[Product]:
        if threshold < 0:
            raise ValueError("Поріг залишку товару не може бути від'ємним")
        return [prod for prod in self.repository.get_all() if prod.quantity <= threshold]


class CheckoutService:
    """Сервіс оформлення покупок з інтеграцією платежів, аудиту та сповіщень."""

    def __init__(
        self,
        repository: ProductRepository,
        payment_gateway: PaymentGateway,
        notifier: Notifier,
        audit_session: Optional[AuditSession] = None,
    ) -> None:
        self.repository = repository
        self.payment_gateway = payment_gateway
        self.notifier = notifier
        self.audit_session = audit_session

    def checkout(
        self,
        customer_email: str,
        product_ids: List[int],
        discount: Optional[DiscountPolicy] = None,
    ) -> str:
        if not product_ids:
            raise ValueError("Список товарів для замовлення не може бути порожнім")

        if self.audit_session:
            with self.audit_session:
                self.audit_session.record_step("start_checkout")

        total_sum = 0.0
        currency = "UAH"

        for pid in product_ids:
            product = self.repository.get_by_id(pid)
            if product is None:
                raise ProductNotFoundError(f"Неможливо оформити замовлення: товар {pid} відсутній")
            if product.quantity <= 0:
                raise ShopError(f"Товар '{product.name}' відсутній на складі")
            total_sum += product.price.amount
            currency = product.price.currency

        order_total = Money(round(total_sum, 2), currency)
        if discount:
            order_total = discount.apply(order_total)

        txn_id = self.payment_gateway.process_payment(order_total)

        if self.audit_session:
            with self.audit_session:
                self.audit_session.record_step("payment_completed")

        self.notifier.send_notification(
            customer_email,
            f"Оплата успішна: {order_total.amount} {order_total.currency}. Транзакція: {txn_id}"
        )
        return txn_id


class AsyncCurrencyConverter:
    """Асинхронний сервіс конвертації цін товарів у цільову валюту."""

    def __init__(self, provider: ExternalPriceProvider) -> None:
        self.provider = provider

    async def convert_product_price(self, product: Product, target_currency: str) -> Money:
        rate = await self.provider.get_exchange_rate(target_currency)
        if rate <= 0.0:
            raise ValueError(f"Некоректний обмінний курс від провайдера: {rate}")
        converted_amount = round(product.price.amount * rate, 2)
        return Money(converted_amount, target_currency)


# =====================================================================
# 5. КОНФІГУРАЦІЯ ТА I/O (CSV / JSON)
# =====================================================================

class AppConfig:
    """Клас конфігурації магазину з підтримкою змінних середовища та констант."""
    DEFAULT_CURRENCY: str = "UAH"
    API_VERSION: str = "v1"

    @classmethod
    def get_min_stock_threshold(cls) -> int:
        raw_val = os.getenv("SHOP_MIN_STOCK_THRESHOLD", "5")
        try:
            val = int(raw_val)
            return 5 if val < 0 else val
        except ValueError:
            return 5

    @classmethod
    def get_environment(cls) -> str:
        return os.getenv("SHOP_ENV", "development")


class ProductIO:
    """Модуль завантаження та вивантаження даних каталогу (CSV/JSON)."""

    @staticmethod
    def import_from_csv(file_path: Path) -> List[Product]:
        if not file_path.exists():
            raise FileNotFoundError(f"Файл не знайдено: {file_path}")

        products: List[Product] = []
        with open(file_path, mode="r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            required_cols = {"product_id", "name", "category", "price", "currency", "quantity"}
            if not reader.fieldnames or not required_cols.issubset(set(reader.fieldnames)):
                raise DataImportError("CSV файл не містить обов'язкових заголовків")

            for row_idx, row in enumerate(reader, start=2):
                try:
                    product = Product(
                        product_id=int(row["product_id"]),
                        name=row["name"],
                        category=ProductCategory(row["category"]),
                        price=Money(float(row["price"]), row["currency"]),
                        quantity=int(row["quantity"]),
                    )
                    products.append(product)
                except (ValueError, KeyError, ValidationError) as err:
                    raise DataImportError(
                        f"Помилка даних у рядку {row_idx}: {err}"
                    ) from err
        return products

    @staticmethod
    def export_to_json(products: List[Product], file_path: Path) -> None:
        records = [
            {
                "product_id": p.product_id,
                "name": p.name,
                "category": p.category.value,
                "price": p.price.amount,
                "currency": p.price.currency,
                "quantity": p.quantity,
                "total_stock_value": p.total_stock_value.amount,
            }
            for p in products
        ]
        file_path.write_text(json.dumps(records, indent=2, ensure_ascii=False), encoding="utf-8")


# =====================================================================
# 6. PYTEST FIXTURES (РІЗНІ SCOPES ТА ФАБРИКИ)
# =====================================================================

@pytest.fixture(scope="session")
def session_currency() -> str:
    """Фікстура рівня сесії: базова валюта для тестування всього набору."""
    return "UAH"


@pytest.fixture(scope="module")
def module_sample_products_data(session_currency: str) -> List[Dict[str, Any]]:
    """Фікстура рівня модуля: початковий набір словників для ініціалізації товарів."""
    return [
        {"product_id": 1, "name": "Ultrabook 14", "category": ProductCategory.ELECTRONICS, "price": 38000.0, "quantity": 4},
        {"product_id": 2, "name": "Wireless Mouse", "category": ProductCategory.ELECTRONICS, "price": 1200.0, "quantity": 25},
        {"product_id": 3, "name": "Architecture Patterns", "category": ProductCategory.BOOKS, "price": 980.0, "quantity": 8},
        {"product_id": 4, "name": "Refactoring Guide", "category": ProductCategory.BOOKS, "price": 1150.0, "quantity": 2},
        {"product_id": 5, "name": "Developer Hoodie", "category": ProductCategory.CLOTHING, "price": 2400.0, "quantity": 1},
    ]


@pytest.fixture(scope="function")
def laptop_product(session_currency: str) -> Product:
    """Фікстура рівня функції: типовий екземпляр продукту."""
    return Product(
        product_id=10,
        name="Dell XPS 15",
        category=ProductCategory.ELECTRONICS,
        price=Money(65000.0, session_currency),
        quantity=3,
    )


@pytest.fixture(scope="function")
def product_repository(module_sample_products_data: List[Dict[str, Any]], session_currency: str) -> InMemoryProductRepository:
    """Фікстура функції: попередньо заповнене сховище."""
    repo = InMemoryProductRepository()
    for item in module_sample_products_data:
        prod = Product(
            product_id=item["product_id"],
            name=item["name"],
            category=item["category"],
            price=Money(item["price"], session_currency),
            quantity=item["quantity"],
        )
        repo.add(prod)
    return repo


@pytest.fixture(scope="function")
def catalog_service(product_repository: InMemoryProductRepository) -> CatalogService:
    """Фікстура сервісу каталогу."""
    return CatalogService(product_repository)


@pytest.fixture(scope="function")
def product_factory() -> Callable[..., Product]:
    """Fixture-фабрика для динамічного створення доменних товарів у тестах."""
    id_sequence = 1000

    def _create(
        name: str = "Test Product",
        category: ProductCategory = ProductCategory.ELECTRONICS,
        price_val: float = 100.0,
        currency: str = "UAH",
        quantity: int = 10,
    ) -> Product:
        nonlocal id_sequence
        id_sequence += 1
        return Product(
            product_id=id_sequence,
            name=name,
            category=category,
            price=Money(price_val, currency),
            quantity=quantity,
        )

    return _create


# =====================================================================
# 7. UNIT TESTS (NORMAL, BOUNDARY, INVALID, EXCEPTIONS, MOCKS, MONKEYPATCH)
# =====================================================================

# --- Перевірка Value Object Money ---

def test_money_creation_and_fields() -> None:
    money = Money(250.50, "USD")
    assert money.amount == 250.50
    assert money.currency == "USD"


def test_money_negative_amount_raises_value_error() -> None:
    with pytest.raises(ValueError, match="не може бути від'ємною"):
        Money(-0.01, "UAH")


def test_money_addition_same_currency() -> None:
    m1 = Money(120.35, "UAH")
    m2 = Money(80.65, "UAH")
    result = m1 + m2
    assert result.amount == pytest.approx(201.00)
    assert result.currency == "UAH"


def test_money_addition_different_currency_raises_value_error() -> None:
    m1 = Money(100.0, "UAH")
    m2 = Money(100.0, "EUR")
    with pytest.raises(ValueError, match="різних валютах"):
        _ = m1 + m2


def test_money_multiplication_and_negative_factor() -> None:
    m = Money(50.0, "UAH")
    assert (m * 3.5).amount == pytest.approx(175.0)

    with pytest.raises(ValueError, match="не може бути від'ємним"):
        _ = m * -1.5


# --- Параметризовані тести Product (Граничні та Некоректні значення) ---

@pytest.mark.parametrize(
    "price,quantity",
    [
        (0.0, 0),             # Нижня гранична межа: подарунок, нуль залишків
        (0.01, 1),            # Мінімальні додатні значення
        (1_000_000.0, 5000),  # Великі нормальні значення
    ],
    ids=["boundary_zero_price_qty", "boundary_minimal_positive", "large_valid_numbers"]
)
def test_product_boundary_values(price: float, quantity: int) -> None:
    p = Product(1, "Boundary Test Item", ProductCategory.HOME, Money(price), quantity)
    assert p.price.amount == pytest.approx(price)
    assert p.quantity == quantity


@pytest.mark.parametrize(
    "p_id,name,quantity,expected_field",
    [
        (0, "Desk Lamp", 5, "product_id"),
        (-1, "Desk Lamp", 5, "product_id"),
        (2, "", 5, "name"),
        (3, "   ", 5, "name"),
        (4, "Desk Lamp", -1, "quantity"),
    ],
    ids=["zero_id", "negative_id", "empty_name", "whitespace_name", "negative_quantity"]
)
def test_product_validation_errors(p_id: int, name: str, quantity: int, expected_field: str) -> None:
    with pytest.raises(ValidationError) as exc_info:
        Product(p_id, name, ProductCategory.HOME, Money(100.0), quantity)
    assert exc_info.value.field_name == expected_field


def test_product_total_stock_value(laptop_product: Product) -> None:
    # 65000 * 3 = 195000
    assert laptop_product.total_stock_value == Money(195000.0, "UAH")


# --- Тести CatalogService ---

def test_catalog_find_by_id_success_and_not_found(catalog_service: CatalogService) -> None:
    prod = catalog_service.find_by_id(1)
    assert prod.name == "Ultrabook 14"

    with pytest.raises(ProductNotFoundError, match="не знайдено в каталозі"):
        catalog_service.find_by_id(99999)


def test_catalog_search_by_name(catalog_service: CatalogService) -> None:
    results = catalog_service.search_by_name("guide")
    assert len(results) == 1
    assert results[0].product_id == 4

    assert catalog_service.search_by_name("") == []
    assert catalog_service.search_by_name("non-existent-token") == []


def test_catalog_filter_by_category(catalog_service: CatalogService) -> None:
    electronics = catalog_service.filter_by_category(ProductCategory.ELECTRONICS)
    assert len(electronics) == 2
    food = catalog_service.filter_by_category(ProductCategory.FOOD)
    assert food == []


def test_catalog_inventory_value_and_empty_state() -> None:
    empty_catalog = CatalogService(InMemoryProductRepository())
    assert empty_catalog.calculate_total_inventory_value() == Money(0.0)
    assert empty_catalog.get_most_expensive_product() is None


def test_catalog_inventory_value_mixed_currency_raises_value_error(
    catalog_service: CatalogService, product_factory: Callable[..., Product]
) -> None:
    foreign_prod = product_factory(name="US Import", price_val=50.0, currency="USD")
    catalog_service.add_product(foreign_prod)

    with pytest.raises(ValueError, match="різні валюти цін"):
        catalog_service.calculate_total_inventory_value()


def test_catalog_get_low_stock_products(catalog_service: CatalogService) -> None:
    low = catalog_service.get_low_stock_products(threshold=2)
    # Refactoring Guide (2) та Developer Hoodie (1)
    assert len(low) == 2
    assert {p.product_id for p in low} == {4, 5}

    with pytest.raises(ValueError, match="не може бути від'ємним"):
        catalog_service.get_low_stock_products(threshold=-1)


# --- Тести знижок (PercentageDiscount) ---

@pytest.mark.parametrize(
    "percent,original,expected",
    [
        (0.0, 500.0, 500.0),
        (15.0, 1000.0, 850.0),
        (33.33, 300.0, 200.01),
        (100.0, 800.0, 0.0),
    ],
    ids=["zero_discount", "fifteen_percent", "fractional_percent", "full_free_100_percent"]
)
def test_percentage_discount_calculation(percent: float, original: float, expected: float) -> None:
    policy = PercentageDiscount(percent)
    result = policy.apply(Money(original, "UAH"))
    assert result.amount == pytest.approx(expected)


@pytest.mark.parametrize("invalid_p", [-1.0, -0.01, 100.01, 150.0])
def test_percentage_discount_invalid_raises_error(invalid_p: float) -> None:
    with pytest.raises(ValueError, match="в межах"):
        PercentageDiscount(invalid_p)


# --- Тести взаємодії об'єктів з Mock ---

def test_checkout_successful_interaction_with_mock(product_repository: InMemoryProductRepository) -> None:
    # 1. Arrange: Мок платіжного шлюзу та нотифікатора
    payment_mock = Mock(spec=PaymentGateway)
    payment_mock.process_payment.return_value = "TXN-TEST-12345"

    notifier_mock = Mock(spec=Notifier)
    service = CheckoutService(product_repository, payment_mock, notifier_mock)

    # 2. Act: Товари 3 (980) та 4 (1150). Сума = 2130 грн. Знижка 10% -> 1917 грн.
    txn = service.checkout("test@example.com", [3, 4], discount=PercentageDiscount(10.0))

    # 3. Assert: Перевірка контрактів взаємодії
    assert txn == "TXN-TEST-12345"
    payment_mock.process_payment.assert_called_once_with(Money(1917.0, "UAH"))
    notifier_mock.send_notification.assert_called_once()
    recipient, msg = notifier_mock.send_notification.call_args[0]
    assert recipient == "test@example.com"
    assert "TXN-TEST-12345" in msg


def test_checkout_payment_gateway_failure_side_effect(product_repository: InMemoryProductRepository) -> None:
    # Arrange
    payment_mock = Mock(spec=PaymentGateway)
    payment_mock.process_payment.side_effect = PaymentError("Сервер платежів відхилив запит")
    notifier_mock = Mock(spec=Notifier)

    service = CheckoutService(product_repository, payment_mock, notifier_mock)

    # Act & Assert: Виняток прокидається нагору
    with pytest.raises(PaymentError, match="Сервер платежів відхилив запит"):
        service.checkout("client@domain.ua", [1])

    # Контроль взаємодії: при збої оплати повідомлення клієнту НЕ надсилається
    notifier_mock.send_notification.assert_not_called()


def test_checkout_empty_items_and_out_of_stock(product_repository: InMemoryProductRepository) -> None:
    service = CheckoutService(product_repository, Mock(spec=PaymentGateway), Mock(spec=Notifier))

    with pytest.raises(ValueError, match="не може бути порожнім"):
        service.checkout("client@domain.ua", [])

    # Моделюємо товар із нульовим залишком
    zero_stock_product = Product(99, "Zero Stock Item", ProductCategory.BOOKS, Money(100.0), 0)
    product_repository.add(zero_stock_product)

    with pytest.raises(ShopError, match="відсутній на складі"):
        service.checkout("client@domain.ua", [99])


# --- Тести з використанням MagicMock (Dunder methods, Context Manager) ---

def test_checkout_with_magic_mock_audit_session_context_manager(
    product_repository: InMemoryProductRepository
) -> None:
    # Arrange: MagicMock для симуляції контекстного менеджера аудиту з методами __enter__ / __exit__
    audit_mock = MagicMock(spec=AuditSession)
    audit_mock.__enter__.return_value = audit_mock

    payment_mock = Mock(spec=PaymentGateway)
    payment_mock.process_payment.return_value = "TXN-AUDIT-77"
    notifier_mock = Mock(spec=Notifier)

    service = CheckoutService(
        repository=product_repository,
        payment_gateway=payment_mock,
        notifier=notifier_mock,
        audit_session=audit_mock,
    )

    # Act
    service.checkout("auditor@company.com", [2])

    # Assert: Перевіряємо вхід/вихід із контекстного менеджера та виклики запису аудиту
    assert audit_mock.__enter__.call_count == 2
    assert audit_mock.__exit__.call_count == 2
    audit_mock.record_step.assert_any_call("start_checkout")
    audit_mock.record_step.assert_any_call("payment_completed")


def test_repository_len_dunder_via_magic_mock() -> None:
    # Arrange: MagicMock автоматично реалізує dunder-методи типу __len__
    repo_mock = MagicMock(spec=InMemoryProductRepository)
    repo_mock.__len__.return_value = 42

    # Assert
    assert len(repo_mock) == 42


# --- Тести з AsyncMock (Асинхронний провайдер валют) ---

def test_async_currency_converter_success(laptop_product: Product) -> None:
    async def _scenario() -> None:
        provider_mock = AsyncMock(spec=ExternalPriceProvider)
        provider_mock.get_exchange_rate.return_value = 0.024  # 1 UAH = 0.024 EUR

        converter = AsyncCurrencyConverter(provider_mock)
        converted = await converter.convert_product_price(laptop_product, "EUR")

        # 65000 * 0.024 = 1560.0 EUR
        assert converted.amount == pytest.approx(1560.0)
        assert converted.currency == "EUR"
        provider_mock.get_exchange_rate.assert_awaited_once_with("EUR")

    asyncio.run(_scenario())


def test_async_currency_converter_provider_exception(laptop_product: Product) -> None:
    async def _scenario() -> None:
        provider_mock = AsyncMock(spec=ExternalPriceProvider)
        provider_mock.get_exchange_rate.side_effect = ProviderUnavailableError("HTTP 504 Gateway Timeout")

        converter = AsyncCurrencyConverter(provider_mock)

        with pytest.raises(ProviderUnavailableError, match="Gateway Timeout"):
            await converter.convert_product_price(laptop_product, "USD")

    asyncio.run(_scenario())


# --- Тести з monkeypatch (Environment Variables, Attributes, Functions) ---

def test_monkeypatch_environment_variables(monkeypatch: pytest.MonkeyPatch) -> None:
    # 1. Підміна через setenv
    monkeypatch.setenv("SHOP_MIN_STOCK_THRESHOLD", "12")
    monkeypatch.setenv("SHOP_ENV", "staging")
    assert AppConfig.get_min_stock_threshold() == 12
    assert AppConfig.get_environment() == "staging"

    # 2. Перевірка fallback при видаленні через delenv
    monkeypatch.delenv("SHOP_MIN_STOCK_THRESHOLD", raising=False)
    assert AppConfig.get_min_stock_threshold() == 5

    # 3. Перевірка невалідного значення
    monkeypatch.setenv("SHOP_MIN_STOCK_THRESHOLD", "not-a-number")
    assert AppConfig.get_min_stock_threshold() == 5


def test_monkeypatch_attributes_and_functions(monkeypatch: pytest.MonkeyPatch) -> None:
    # 1. Підміна атрибута класу через monkeypatch.setattr
    monkeypatch.setattr(AppConfig, "DEFAULT_CURRENCY", "PLN")
    assert AppConfig.DEFAULT_CURRENCY == "PLN"

    # 2. Підміна функції через monkeypatch.setattr
    def fake_order_id(prefix: str = "ORD") -> str:
        return f"{prefix}-MOCKED-ID-999"

    current_module = sys.modules[__name__]
    monkeypatch.setattr(current_module, "generate_order_id", fake_order_id)

    assert generate_order_id("ORDER") == "ORDER-MOCKED-ID-999"


# --- Тести помилок CSV та Exception Chaining ---

def test_csv_import_missing_headers_raises_data_import_error(tmp_path: Path) -> None:
    invalid_csv = tmp_path / "missing_cols.csv"
    invalid_csv.write_text("product_id,name,price\n1,Short Data,100\n", encoding="utf-8")

    with pytest.raises(DataImportError, match="не містить обов'язкових заголовків"):
        ProductIO.import_from_csv(invalid_csv)


def test_csv_import_malformed_record_exception_chaining(tmp_path: Path) -> None:
    corrupted_csv = tmp_path / "corrupted.csv"
    corrupted_csv.write_text(
        "product_id,name,category,price,currency,quantity\n"
        "10,Good Book,Books,120.0,UAH,5\n"
        "11,Bad Price,Books,INVALID_FLOAT,UAH,3\n",
        encoding="utf-8"
    )

    with pytest.raises(DataImportError) as exc_info:
        ProductIO.import_from_csv(corrupted_csv)

    assert "Помилка даних у рядку 3" in str(exc_info.value)
    # Перевірка зв'язку винятків (exception chaining через __cause__)
    assert isinstance(exc_info.value.__cause__, ValueError)


# =====================================================================
# 8. INTEGRATION TESTS (ІНТЕГРАЦІЙНІ ТЕСТИ)
# =====================================================================

@pytest.mark.integration
def test_integration_csv_import_to_repository_and_catalog(tmp_path: Path) -> None:
    """
    Інтеграційний тест 1: Файлова система CSV -> Парсинг ProductIO ->
    Наповнення репозиторію -> Сервіс каталогу -> Розрахунок загальної вартості складу.
    """
    csv_file = tmp_path / "batch_products.csv"
    csv_file.write_text(
        "product_id,name,category,price,currency,quantity\n"
        "501,Smart TV 55,Electronics,18000.0,UAH,2\n"
        "502,Soundbar,Electronics,4500.0,UAH,4\n"
        "503,Coffee Beans 1kg,Food,600.0,UAH,10\n",
        encoding="utf-8"
    )

    # 1. Імпорт
    imported_list = ProductIO.import_from_csv(csv_file)
    assert len(imported_list) == 3

    # 2. Наповнення каталогу
    repo = InMemoryProductRepository()
    catalog = CatalogService(repo)
    for p in imported_list:
        catalog.add_product(p)

    # 3. Аналітика складу: 18000*2 (36000) + 4500*4 (18000) + 600*10 (6000) = 60000.0 UAH
    total_val = catalog.calculate_total_inventory_value()
    assert total_val.amount == pytest.approx(60000.0)
    assert total_val.currency == "UAH"

    # Перевірка найдорожчого товару
    most_exp = catalog.get_most_expensive_product()
    assert most_exp is not None
    assert most_exp.name == "Smart TV 55"


@pytest.mark.integration
def test_integration_catalog_filter_to_json_export_and_file_verification(
    tmp_path: Path, catalog_service: CatalogService
) -> None:
    """
    Інтеграційний тест 2: Сховище -> Каталог -> Фільтрація дефіцитних залишків ->
    Експорт у JSON -> Зчитування та валідація вмісту на файловій системі.
    """
    # 1. Фільтруємо позиції з критичним залишком <= 2
    low_stock = catalog_service.get_low_stock_products(threshold=2)
    assert len(low_stock) == 2

    # 2. Експортуємо у тимчасовий JSON
    target_json = tmp_path / "low_stock_audit.json"
    ProductIO.export_to_json(low_stock, target_json)

    # 3. Перевіряємо створення та коректність серіалізованого вмісту
    assert target_json.exists()
    content = json.loads(target_json.read_text(encoding="utf-8"))
    assert isinstance(content, list)
    assert len(content) == 2

    exported_names = {entry["name"] for entry in content}
    assert exported_names == {"Refactoring Guide", "Developer Hoodie"}
    for entry in content:
        assert "total_stock_value" in entry
        assert entry["quantity"] <= 2


@pytest.mark.integration
def test_integration_full_ecommerce_data_pipeline(tmp_path: Path) -> None:
    """
    Інтеграційний тест 3: Наскрізний потік:
    Імпорт CSV -> Застосування знижки до цін -> Асинхронний перерахунок валюти -> Експорт у JSON.
    """
    input_csv = tmp_path / "incoming_goods.csv"
    input_csv.write_text(
        "product_id,name,category,price,currency,quantity\n"
        "701,Gaming Mouse,Electronics,2000.0,UAH,5\n"
        "702,Mechanical Numpad,Electronics,1000.0,UAH,8\n",
        encoding="utf-8"
    )

    # Mock асинхронного джерела котирувань
    rate_mock = AsyncMock(spec=ExternalPriceProvider)
    rate_mock.get_exchange_rate.return_value = 0.025  # 1 UAH = 0.025 USD
    converter = AsyncCurrencyConverter(rate_mock)
    discount = PercentageDiscount(20.0)  # 20% знижка

    async def _run_pipeline() -> None:
        # Читання
        items = ProductIO.import_from_csv(input_csv)
        processed: List[Product] = []

        for p in items:
            discounted_price = discount.apply(p.price)
            # Конвертація у валюту USD
            usd_price = await converter.convert_product_price(
                Product(p.product_id, p.name, p.category, discounted_price, p.quantity),
                target_currency="USD"
            )
            processed.append(Product(p.product_id, p.name, p.category, usd_price, p.quantity))

        output_file = tmp_path / "processed_usd_catalog.json"
        ProductIO.export_to_json(processed, output_file)

        # Перевірка результату на диску
        assert output_file.exists()
        saved = json.loads(output_file.read_text(encoding="utf-8"))
        assert len(saved) == 2
        # Товар 1: 2000 грн - 20% = 1600 грн * 0.025 = 40.0 USD
        assert saved[0]["price"] == pytest.approx(40.0)
        assert saved[0]["currency"] == "USD"
        # Товар 2: 1000 грн - 20% = 800 грн * 0.025 = 20.0 USD
        assert saved[1]["price"] == pytest.approx(20.0)
        assert saved[1]["currency"] == "USD"

    asyncio.run(_run_pipeline())


# =====================================================================
# 9. ГОЛОВНИЙ ДЕМОНСТРАЦІЙНИЙ СКРИПТ ТА ЗАПУСК PYTEST
# =====================================================================

def main() -> None:
    """Точка входу для перевірки та запуску всього набору тестів із розрахунком coverage."""
    print("=" * 80)
    print("  ЛАБОРАТОРНА РОБОТА №6. ТЕСТУВАННЯ PYTHON (ВАРІАНТ №3: ІНТЕРНЕТ-МАГАЗИН)")
    print("=" * 80)
    print("Демонстрація доменної моделі...")

    repo = InMemoryProductRepository()
    cat = CatalogService(repo)
    p1 = Product(101, "Dell UltraSharp Monitor", ProductCategory.ELECTRONICS, Money(14500.0), 3)
    p2 = Product(102, "Ergonomic Mechanical Keyboard", ProductCategory.ELECTRONICS, Money(3200.0), 10)
    cat.add_product(p1)
    cat.add_product(p2)

    print(f"Кількість товарів у каталозі: {len(cat.repository.get_all())}")
    print(f"Балансова вартість залишків: {cat.calculate_total_inventory_value().amount} UAH")
    print(f"Найдорожчий товар: {cat.get_most_expensive_product().name}")
    print("-" * 80)
    print("Запуск тестів через pytest runner...")
    print("-" * 80)

    pytest_args = [
        __file__,
        "-v",
        "--tb=short",
    ]

    try:
        import pytest_cov  # noqa: F401
        pytest_args.extend(["--cov", "--cov-branch", "--cov-report=term-missing"])
    except ImportError:
        print("[Увага] Модуль pytest-cov не встановлено. Для звіту про покриття виконайте: pip install pytest-cov")

    code = pytest.main(pytest_args)
    if code == 0:
        print("\n[УСПІХ] Усі unit та integration тести виконані успішно!")
    else:
        print(f"\n[ПОМИЛКА] Тестування завершилося з кодом: {code}")
    sys.exit(code)


if __name__ == "__main__":
    main()