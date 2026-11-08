import asyncio
import csv
import json
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Protocol, runtime_checkable
from unittest.mock import AsyncMock, Mock

import pytest


# =====================================================================
# 1. СИСТЕМА ДОМЕННИХ ВИНЯТКІВ (CUSTOM EXCEPTIONS)
# =====================================================================

class StoreError(Exception):
    """Базовий клас винятків для підсистеми інтернет-магазину."""
    pass


class StoreValidationError(StoreError):
    """Виняток, що сигналізує про помилку валідації сутності чи поля."""

    def __init__(self, field_name: str, message: str) -> None:
        super().__init__(f"Validation error for field '{field_name}': {message}")
        self.field_name = field_name
        self.message = message


class ProductNotFoundError(StoreError):
    """Виняток, що сигналізує про відсутність товару з вказаним ідентифікатором."""

    def __init__(self, product_id: int) -> None:
        super().__init__(f"Product with ID {product_id} was not found in the catalog.")
        self.product_id = product_id


class ExternalProviderError(StoreError):
    """Виняток, що сигналізує про помилку зовнішнього асинхронного постачальника."""
    pass


class ExportError(StoreError):
    """Виняток, що сигналізує про збій під час експорту даних."""
    pass


# =====================================================================
# 2. VALUE OBJECTS & DOMAIN ENTITIES
# =====================================================================

@dataclass(frozen=True, slots=True)
class Money:
    """
    Незмінний Value Object для представлення грошової суми та валюти.
    
    Забезпечує захист інваріантів: сума не може бути від'ємною,
    операції додавання можливі лише для однакових валют.
    """
    amount: float
    currency: str = "UAH"

    def __post_init__(self) -> None:
        if self.amount < 0.0:
            raise StoreValidationError("amount", f"Money amount cannot be negative: {self.amount}")

    def __add__(self, other: "Money") -> "Money":
        if not isinstance(other, Money):
            return NotImplemented
        if self.currency != other.currency:
            raise StoreValidationError(
                "currency",
                f"Currency mismatch: cannot add {self.currency} and {other.currency}"
            )
        return Money(round(self.amount + other.amount, 2), self.currency)

    def __sub__(self, other: "Money") -> "Money":
        if not isinstance(other, Money):
            return NotImplemented
        if self.currency != other.currency:
            raise StoreValidationError(
                "currency",
                f"Currency mismatch: cannot subtract {self.currency} and {other.currency}"
            )
        if self.amount < other.amount:
            raise StoreValidationError(
                "amount",
                f"Resulting money amount cannot be negative: {self.amount} - {other.amount}"
            )
        return Money(round(self.amount - other.amount, 2), self.currency)

    def multiply(self, factor: float) -> "Money":
        """Множення суми на числовий коефіцієнт (наприклад, кількість)."""
        if factor < 0:
            raise StoreValidationError("factor", f"Multiplication factor cannot be negative: {factor}")
        return Money(round(self.amount * factor, 2), self.currency)


@dataclass(slots=True)
class Product:
    """
    Доменна сутність товару в інтернет-магазині.
    
    Включає валідацію назви, категорії, вартості та складської кількості.
    """
    product_id: int
    name: str
    category: str
    price: Money
    quantity: int

    def __post_init__(self) -> None:
        if self.product_id <= 0:
            raise StoreValidationError("product_id", f"Product ID must be positive: {self.product_id}")
        if not self.name or not self.name.strip():
            raise StoreValidationError("name", "Product name cannot be empty.")
        if not self.category or not self.category.strip():
            raise StoreValidationError("category", "Product category cannot be empty.")
        if self.quantity < 0:
            raise StoreValidationError("quantity", f"Quantity cannot be negative: {self.quantity}")

    @property
    def inventory_value(self) -> Money:
        """Розрахунок повної вартості складського залишку для даного товару."""
        return self.price.multiply(self.quantity)


# =====================================================================
# 3. PROTOCOLS & INTERFACES (DEPENDENCY INVERSION)
# =====================================================================

@runtime_checkable
class ProductRepositoryProtocol(Protocol):
    """Контракт репозиторію для зберігання та отримання сутностей Product."""

    def add(self, product: Product) -> None:
        ...

    def get_by_id(self, product_id: int) -> Product | None:
        ...

    def get_all(self) -> list[Product]:
        ...

    def delete(self, product_id: int) -> bool:
        ...


@runtime_checkable
class NotifierProtocol(Protocol):
    """Контракт сервісу сповіщень."""

    def send_notification(self, recipient: str, message: str) -> bool:
        ...


@runtime_checkable
class AsyncSupplierClientProtocol(Protocol):
    """Контракт зовнішнього асинхронного API постачальника."""

    async def fetch_supplier_data(self, product_id: int) -> dict[str, Any]:
        ...


# =====================================================================
# 4. REPOSITORIES & REPOSITORY IMPLEMENTATIONS
# =====================================================================

class InMemoryProductRepository:
    """In-memory імплементація сховища товарів для каталогів та тестів."""

    def __init__(self, initial_products: list[Product] | None = None) -> None:
        self._storage: dict[int, Product] = {}
        if initial_products:
            for p in initial_products:
                self.add(p)

    def add(self, product: Product) -> None:
        self._storage[product.product_id] = product

    def get_by_id(self, product_id: int) -> Product | None:
        return self._storage.get(product_id)

    def get_all(self) -> list[Product]:
        return list(self._storage.values())

    def delete(self, product_id: int) -> bool:
        return self._storage.pop(product_id, None) is not None

    def clear(self) -> None:
        self._storage.clear()


# =====================================================================
# 5. CONFIGURATION & POLICIES
# =====================================================================

def get_min_stock_threshold() -> int:
    """Отримання порогового значення мінімального залишку зі змінних оточення."""
    raw_val = os.getenv("MIN_STOCK_THRESHOLD", "5")
    try:
        val = int(raw_val)
        if val < 0:
            return 5
        return val
    except ValueError:
        return 5


def get_default_currency() -> str:
    """Отримання робочої валюти магазину з environment variables."""
    return os.getenv("STORE_CURRENCY", "UAH").upper().strip()


class PercentageDiscount:
    """Політика розрахунку відсоткової знижки."""

    def __init__(self, percent: float) -> None:
        if not (0.0 <= percent <= 100.0):
            raise StoreValidationError("percent", f"Discount percent must be between 0 and 100: {percent}")
        self.percent = percent

    def apply(self, price: Money) -> Money:
        """Застосувати знижку до вартості."""
        discounted = price.amount * (1.0 - (self.percent / 100.0))
        return Money(round(discounted, 2), price.currency)


# =====================================================================
# 6. BUSINESS SERVICES
# =====================================================================

class StoreCatalogService:
    """
    Основний сервіс каталогу товарів інтернет-магазину.
    
    Забезпечує керування каталогом, фільтрацію, пошук, складські метрики
    та сповіщення адміністратора/клієнтів.
    """

    def __init__(
        self,
        repository: ProductRepositoryProtocol,
        notifier: NotifierProtocol | None = None,
    ) -> None:
        self._repository = repository
        self._notifier = notifier

    def add_product(self, product: Product) -> None:
        """Додати товар до каталогу зі збереженням у репозиторій."""
        self._repository.add(product)
        if self._notifier:
            self._notifier.send_notification(
                "admin@store.ua",
                f"New product added: {product.name} (ID: {product.product_id})"
            )

    def find_product_by_id(self, product_id: int) -> Product:
        """Пошук товару за ID або викидання ProductNotFoundError."""
        product = self._repository.get_by_id(product_id)
        if product is None:
            raise ProductNotFoundError(product_id)
        return product

    def search_by_name(self, query: str) -> list[Product]:
        """Пошук товарів за підрядком у назві (case-insensitive)."""
        clean_query = query.strip().lower()
        if not clean_query:
            return []
        return [p for p in self._repository.get_all() if clean_query in p.name.lower()]

    def filter_by_category(self, category: str) -> list[Product]:
        """Фільтрація списку товарів за відповідною категорією."""
        target = category.strip().lower()
        return [p for p in self._repository.get_all() if p.category.lower() == target]

    def calculate_total_inventory_value(self) -> Money:
        """Розрахунок загальної вартості всіх складських залишків каталогу."""
        products = self._repository.get_all()
        if not products:
            return Money(0.0, get_default_currency())

        currency = products[0].price.currency
        total_amount = sum(p.inventory_value.amount for p in products)
        return Money(round(total_amount, 2), currency)

    def get_most_expensive_product(self) -> Product | None:
        """Визначення найдорожчого товару за одиничною ціною."""
        products = self._repository.get_all()
        if not products:
            return None
        return max(products, key=lambda p: p.price.amount)

    def get_low_stock_products(self, threshold: int | None = None) -> list[Product]:
        """Визначення товарів, запас яких нижче або дорівнює встановленому порогу."""
        limit = threshold if threshold is not None else get_min_stock_threshold()
        return [p for p in self._repository.get_all() if p.quantity <= limit]


class AsyncProductSyncService:
    """
    Асинхронний сервіс інтеграції зі складом постачальника через AsyncSupplierClient.
    """

    def __init__(
        self,
        repository: ProductRepositoryProtocol,
        supplier_client: AsyncSupplierClientProtocol,
    ) -> None:
        self._repository = repository
        self._client = supplier_client

    async def sync_product_from_supplier(self, product_id: int) -> Product:
        """
        Отримує актуальну інформацію від постачальника та синхронізує ціну/залишок.
        """
        try:
            data = await self._client.fetch_supplier_data(product_id)
        except Exception as exc:
            raise ExternalProviderError(f"Failed to fetch data for product {product_id}: {exc}") from exc

        if "price" not in data or "quantity" not in data:
            raise ExternalProviderError(f"Malformed response from supplier for product {product_id}")

        existing = self._repository.get_by_id(product_id)
        if existing:
            updated = Product(
                product_id=existing.product_id,
                name=existing.name,
                category=existing.category,
                price=Money(float(data["price"]), existing.price.currency),
                quantity=int(data["quantity"]),
            )
        else:
            updated = Product(
                product_id=product_id,
                name=str(data.get("name", f"Supplier Item {product_id}")),
                category=str(data.get("category", "General")),
                price=Money(float(data["price"]), get_default_currency()),
                quantity=int(data["quantity"]),
            )

        self._repository.add(updated)
        return updated


# =====================================================================
# 7. IMPORT / EXPORT UTILITIES (FILESYSTEM I/O)
# =====================================================================

def export_catalog_to_json(products: list[Product], target_path: Path) -> None:
    """Експорт списку товарів у формат JSON."""
    data = [
        {
            "product_id": p.product_id,
            "name": p.name,
            "category": p.category,
            "price": p.price.amount,
            "currency": p.price.currency,
            "quantity": p.quantity,
            "inventory_value": p.inventory_value.amount,
        }
        for p in products
    ]
    try:
        target_path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    except Exception as exc:
        raise ExportError(f"Could not export catalog to {target_path}: {exc}") from exc


def import_catalog_from_csv(source_path: Path) -> list[Product]:
    """
    Імпорт товарів із CSV-файлу.
    
    Очікувані стовпчики: product_id,name,category,price,currency,quantity
    Викидає StoreValidationError при некоректних даних або відсутніх колонках.
    """
    if not source_path.exists():
        raise FileNotFoundError(f"Source CSV not found: {source_path}")

    products: list[Product] = []
    content = source_path.read_text(encoding="utf-8").strip()
    if not content:
        return []

    reader = csv.DictReader(content.splitlines())
    required_fields = {"product_id", "name", "category", "price", "currency", "quantity"}

    if reader.fieldnames is None or not required_fields.issubset(set(reader.fieldnames)):
        raise StoreValidationError("csv_header", f"CSV file missing required columns: {required_fields}")

    for line_num, row in enumerate(reader, start=2):
        try:
            p_id = int(row["product_id"])
            name = row["name"].strip()
            category = row["category"].strip()
            price_val = float(row["price"])
            currency = row["currency"].strip()
            quantity = int(row["quantity"])

            product = Product(
                product_id=p_id,
                name=name,
                category=category,
                price=Money(price_val, currency),
                quantity=quantity,
            )
            products.append(product)
        except (ValueError, TypeError, KeyError) as err:
            raise StoreValidationError(
                f"csv_line_{line_num}",
                f"Malformed CSV record at line {line_num}: {err}"
            ) from err

    return products


# =====================================================================
# 8. PYTEST FIXTURES (REUSABLE TEST SETUP)
# =====================================================================

@pytest.fixture
def base_currency() -> str:
    """Фікстура повертає стандартну валюту тестів."""
    return "UAH"


@pytest.fixture
def laptop(base_currency: str) -> Product:
    """Фікстура тестового товару 'Ноутбук'."""
    return Product(
        product_id=101,
        name="Ноутбук Pro",
        category="Електроніка",
        price=Money(30000.0, base_currency),
        quantity=4,
    )


@pytest.fixture
def mouse(base_currency: str) -> Product:
    """Фікстура тестового товару 'Мишка'."""
    return Product(
        product_id=102,
        name="Оптична мишка",
        category="Електроніка",
        price=Money(600.0, base_currency),
        quantity=15,
    )


@pytest.fixture
def coffee_maker(base_currency: str) -> Product:
    """Фікстура тестового товару 'Кавомашина'."""
    return Product(
        product_id=201,
        name="Кавомашина Еспресо",
        category="Побутова техніка",
        price=Money(12500.0, base_currency),
        quantity=2,
    )


@pytest.fixture
def sample_catalog(laptop: Product, mouse: Product, coffee_maker: Product) -> list[Product]:
    """Фікстура попередньо заповненого списку товарів."""
    return [laptop, mouse, coffee_maker]


@pytest.fixture
def memory_repo(sample_catalog: list[Product]) -> InMemoryProductRepository:
    """Фікстура репозиторію з початковими даними."""
    return InMemoryProductRepository(sample_catalog)


@pytest.fixture
def catalog_service(memory_repo: InMemoryProductRepository) -> StoreCatalogService:
    """Фікстура готового до роботи сервісу каталогу."""
    return StoreCatalogService(repository=memory_repo)


# =====================================================================
# 9. UNIT TESTS (>= 18 TESTS, ISOLATED, DETERMINISTIC)
# =====================================================================

def test_money_creation_valid() -> None:
    """Перевірка успішного створення Money та відповідності полів."""
    # Arrange & Act
    m = Money(150.5, "USD")

    # Assert
    assert m.amount == pytest.approx(150.5)
    assert m.currency == "USD"


def test_money_negative_amount_raises() -> None:
    """Перевірка відхилення від'ємної суми у Money з викиданням StoreValidationError."""
    with pytest.raises(StoreValidationError, match="cannot be negative") as exc_info:
        Money(-10.0, "UAH")
    assert exc_info.value.field_name == "amount"


def test_money_addition_same_currency() -> None:
    """Перевірка коректного додавання Money з однаковою валютою."""
    m1 = Money(100.25, "UAH")
    m2 = Money(49.75, "UAH")
    total = m1 + m2
    assert total.amount == pytest.approx(150.0)
    assert total.currency == "UAH"


def test_money_addition_currency_mismatch_raises() -> None:
    """Перевірка неможливості додавання грошових сум у різних валютах."""
    m1 = Money(100.0, "UAH")
    m2 = Money(50.0, "EUR")
    with pytest.raises(StoreValidationError, match="Currency mismatch"):
        _ = m1 + m2


def test_product_creation_and_inventory_value(laptop: Product) -> None:
    """Перевірка розрахунку складської вартості товару (price * quantity)."""
    # 30000.0 * 4 = 120000.0
    assert laptop.inventory_value.amount == pytest.approx(120000.0)
    assert laptop.inventory_value.currency == "UAH"


def test_product_negative_quantity_raises() -> None:
    """Перевірка заборони від'ємної кількості товару."""
    with pytest.raises(StoreValidationError, match="Quantity cannot be negative") as exc:
        Product(
            product_id=1,
            name="Товар",
            category="Тест",
            price=Money(10.0),
            quantity=-1,
        )
    assert exc.value.field_name == "quantity"


@pytest.mark.parametrize(
    "name,category,expected_field",
    [
        ("", "Електроніка", "name"),
        ("   ", "Електроніка", "name"),
        ("Ноутбук", "", "category"),
        ("Ноутбук", "   ", "category"),
    ],
    ids=["empty-name", "whitespace-name", "empty-category", "whitespace-category"]
)
def test_product_invalid_strings_raise(name: str, category: str, expected_field: str) -> None:
    """Параметризований тест на відхилення порожніх назв або категорій товару."""
    with pytest.raises(StoreValidationError) as exc:
        Product(
            product_id=5,
            name=name,
            category=category,
            price=Money(100.0),
            quantity=1,
        )
    assert exc.value.field_name == expected_field


@pytest.mark.parametrize(
    "price_val,qty,expected_total",
    [
        (0.0, 10, 0.0),          # Граничний випадок: безкоштовний товар
        (100.0, 0, 0.0),         # Граничний випадок: товар закінчився (qty=0)
        (0.01, 1, 0.01),         # Мінімальна вартість
        (999.99, 3, 2999.97),    # Дробові числа з плаваючою комою
    ],
    ids=["zero-price", "zero-qty", "min-price", "fractional-calc"]
)
def test_product_boundary_inventory_calculation(price_val: float, qty: int, expected_total: float) -> None:
    """Параметризована перевірка граничних значень для розрахунку вартості залишків."""
    p = Product(
        product_id=99,
        name="Тестовий товар",
        category="Тест",
        price=Money(price_val, "UAH"),
        quantity=qty,
    )
    assert p.inventory_value.amount == pytest.approx(expected_total, abs=1e-2)


def test_add_and_find_product(catalog_service: StoreCatalogService) -> None:
    """Перевірка додавання товару в каталог та подальшого пошуку за ID."""
    new_product = Product(
        product_id=301,
        name="Клавіатура",
        category="Електроніка",
        price=Money(1500.0, "UAH"),
        quantity=8,
    )
    catalog_service.add_product(new_product)

    found = catalog_service.find_product_by_id(301)
    assert found == new_product
    assert found.name == "Клавіатура"


def test_find_product_not_found_raises(catalog_service: StoreCatalogService) -> None:
    """Перевірка викидання ProductNotFoundError при пошуку неіснуючого товару."""
    with pytest.raises(ProductNotFoundError, match="Product with ID 9999 was not found") as exc:
        catalog_service.find_product_by_id(9999)
    assert exc.value.product_id == 9999


def test_search_by_name(catalog_service: StoreCatalogService) -> None:
    """Перевірка пошуку за частковим збігом назви без урахування регістру."""
    results = catalog_service.search_by_name("мишка")
    assert len(results) == 1
    assert results[0].name == "Оптична мишка"

    empty_res = catalog_service.search_by_name("неіснуюче")
    assert empty_res == []


def test_filter_by_category(catalog_service: StoreCatalogService) -> None:
    """Перевірка фільтрації каталогу за категорією."""
    electronics = catalog_service.filter_by_category("Електроніка")
    assert len(electronics) == 2
    assert all(p.category == "Електроніка" for p in electronics)

    appliances = catalog_service.filter_by_category("Побутова техніка")
    assert len(appliances) == 1
    assert appliances[0].name == "Кавомашина Еспресо"


def test_calculate_total_inventory_value(catalog_service: StoreCatalogService) -> None:
    """
    Перевірка обчислення повної вартості складських залишків усіх товарів.
    Ноутбук: 30000 * 4 = 120000
    Мишка: 600 * 15 = 9000
    Кавомашина: 12500 * 2 = 25000
    Разом = 154000.0 UAH
    """
    total = catalog_service.calculate_total_inventory_value()
    assert total.amount == pytest.approx(154000.0)
    assert total.currency == "UAH"


def test_get_most_expensive_product(catalog_service: StoreCatalogService, laptop: Product) -> None:
    """Перевірка визначення найдорожчого товару в каталозі."""
    expensive = catalog_service.get_most_expensive_product()
    assert expensive is not None
    assert expensive.product_id == laptop.product_id
    assert expensive.price.amount == pytest.approx(30000.0)


def test_empty_catalog_metrics() -> None:
    """Перевірка поведінки метрик для повністю порожнього каталогу (Boundary Case)."""
    empty_service = StoreCatalogService(repository=InMemoryProductRepository([]))

    assert empty_service.calculate_total_inventory_value().amount == pytest.approx(0.0)
    assert empty_service.get_most_expensive_product() is None
    assert empty_service.search_by_name("будь-що") == []
    assert empty_service.filter_by_category("Електроніка") == []


@pytest.mark.parametrize(
    "percent,original_price,expected_discounted",
    [
        (0.0, 1000.0, 1000.0),    # 0% знижки
        (10.0, 1000.0, 900.0),    # 10%
        (50.0, 500.0, 250.0),     # 50%
        (100.0, 1200.0, 0.0),     # 100% знижки
        (33.33, 100.0, 66.67),    # Дробовий відсоток
    ],
    ids=["0-percent", "10-percent", "50-percent", "100-percent", "fractional-percent"]
)
def test_percentage_discount_policy(percent: float, original_price: float, expected_discounted: float) -> None:
    """Параметризована перевірка політики знижок з використанням pytest.approx."""
    policy = PercentageDiscount(percent)
    initial_money = Money(original_price, "UAH")
    discounted_money = policy.apply(initial_money)
    assert discounted_money.amount == pytest.approx(expected_discounted, abs=1e-2)


def test_percentage_discount_invalid_raises() -> None:
    """Перевірка заборони від'ємної знижки та знижки більше 100%."""
    with pytest.raises(StoreValidationError, match="between 0 and 100"):
        PercentageDiscount(-5.0)

    with pytest.raises(StoreValidationError, match="between 0 and 100"):
        PercentageDiscount(105.0)


def test_get_min_stock_threshold_with_monkeypatch(monkeypatch: pytest.MonkeyPatch) -> None:
    """Тестування зчитування конфігурації мінімального залишку через monkeypatch."""
    # Тест зміненого значення у змінній оточення
    monkeypatch.setenv("MIN_STOCK_THRESHOLD", "10")
    assert get_min_stock_threshold() == 10

    # Тест некоректного значення (повинен повернути fallback=5)
    monkeypatch.setenv("MIN_STOCK_THRESHOLD", "not_a_number")
    assert get_min_stock_threshold() == 5

    # Тест видалення змінної оточення
    monkeypatch.delenv("MIN_STOCK_THRESHOLD", raising=False)
    assert get_min_stock_threshold() == 5


def test_low_stock_filtering_with_config(
    catalog_service: StoreCatalogService,
    monkeypatch: pytest.MonkeyPatch
) -> None:
    """Перевірка пошуку товарів із низьким запасом на основі конфігурації оточення."""
    # Встановлюємо поріг залишку = 4
    monkeypatch.setenv("MIN_STOCK_THRESHOLD", "4")
    # У каталозі: Ноутбук (4 шт), Кавомашина (2 шт), Мишка (15 шт)
    low_stock = catalog_service.get_low_stock_products()
    assert len(low_stock) == 2
    names = {p.name for p in low_stock}
    assert names == {"Ноутбук Pro", "Кавомашина Еспресо"}


def test_notifier_mock_interaction_and_return_value() -> None:
    """
    Тестування взаємодії з залежністю Notifier через Mock.
    Перевіряється передача аргументів та interaction assertion.
    """
    mock_notifier = Mock(spec=NotifierProtocol)
    mock_notifier.send_notification.return_value = True

    repo = InMemoryProductRepository()
    service = StoreCatalogService(repository=repo, notifier=mock_notifier)

    product = Product(
        product_id=55,
        name="Монітор",
        category="Електроніка",
        price=Money(8000.0),
        quantity=3,
    )
    service.add_product(product)

    # Assert interaction
    mock_notifier.send_notification.assert_called_once()
    mock_notifier.send_notification.assert_called_once_with(
        "admin@store.ua",
        "New product added: Монітор (ID: 55)"
    )


def test_notifier_mock_failure_side_effect() -> None:
    """
    Тестування обробки збою залежності через Mock.side_effect.
    """
    mock_notifier = Mock(spec=NotifierProtocol)
    mock_notifier.send_notification.side_effect = RuntimeError("SMTP connection timeout")

    repo = InMemoryProductRepository()
    service = StoreCatalogService(repository=repo, notifier=mock_notifier)

    product = Product(
        product_id=56,
        name="Планшет",
        category="Електроніка",
        price=Money(9500.0),
        quantity=5,
    )

    with pytest.raises(RuntimeError, match="SMTP connection timeout"):
        service.add_product(product)

    # Перевіряємо, що виклик відбувся перед винятком
    mock_notifier.send_notification.assert_called_once()


def test_async_product_sync_service_success() -> None:
    """
    Тестування асинхронного сервісу з використанням AsyncMock,
    перевірка return_value та assert_awaited_once_with.
    """
    async def run_test() -> None:
        mock_client = AsyncMock(spec=AsyncSupplierClientProtocol)
        mock_client.fetch_supplier_data.return_value = {
            "name": "Серверний SSD",
            "category": "Комплектуючі",
            "price": 4500.0,
            "quantity": 12,
        }

        repo = InMemoryProductRepository()
        async_service = AsyncProductSyncService(repo, mock_client)

        synced = await async_service.sync_product_from_supplier(777)

        assert synced.product_id == 777
        assert synced.name == "Серверний SSD"
        assert synced.price.amount == pytest.approx(4500.0)
        assert synced.quantity == 12

        mock_client.fetch_supplier_data.assert_awaited_once_with(777)
        assert repo.get_by_id(777) == synced

    asyncio.run(run_test())


def test_async_product_sync_service_failure_side_effect() -> None:
    """
    Тестування негативного сценарію асинхронного клієнта за допомогою side_effect.
    Перевіряється загортання у доменний виняток ExternalProviderError (exception chaining).
    """
    async def run_test() -> None:
        mock_client = AsyncMock(spec=AsyncSupplierClientProtocol)
        mock_client.fetch_supplier_data.side_effect = TimeoutError("Remote API unreachable")

        repo = InMemoryProductRepository()
        async_service = AsyncProductSyncService(repo, mock_client)

        with pytest.raises(ExternalProviderError, match="Failed to fetch data") as exc_info:
            await async_service.sync_product_from_supplier(888)

        # Перевірка exception chaining (__cause__)
        assert isinstance(exc_info.value.__cause__, TimeoutError)
        mock_client.fetch_supplier_data.assert_awaited_once_with(888)

    asyncio.run(run_test())


def test_csv_import_malformed_record_raises(tmp_path: Path) -> None:
    """
    Перевірка виявлення пошкоджених записів у CSV з викиданням StoreValidationError.
    Використовує ізольовану директорію tmp_path.
    """
    bad_csv = tmp_path / "corrupted.csv"
    bad_csv.write_text(
        "product_id,name,category,price,currency,quantity\n"
        "10,Valid,Category,100,UAH,5\n"
        "not_an_int,BadItem,Category,200,UAH,2\n",
        encoding="utf-8"
    )

    with pytest.raises(StoreValidationError, match="Malformed CSV record at line 3") as exc:
        import_catalog_from_csv(bad_csv)
    assert exc.value.field_name == "csv_line_3"


# =====================================================================
# 10. INTEGRATION TESTS (FILESYSTEM, PIPELINES, MULTI-COMPONENT FLOW)
# =====================================================================

def test_integration_csv_import_pipeline(tmp_path: Path) -> None:
    """
    Integration Test 1: Створення тимчасового CSV, парсинг у доменні моделі,
    завантаження у сервіс та перевірка цілісності бізнес-метрик.
    """
    csv_file = tmp_path / "incoming_catalog.csv"
    csv_file.write_text(
        "product_id,name,category,price,currency,quantity\n"
        "501,Смартфон X,Смартфони,22000.0,UAH,10\n"
        "502,Захисне скло,Аксесуари,350.0,UAH,50\n"
        "503,Чохол силіконовий,Аксесуари,250.0,UAH,20\n",
        encoding="utf-8"
    )

    # Act: імпорт даних
    imported_products = import_catalog_from_csv(csv_file)

    # Завантаження у сховище та сервіс
    repo = InMemoryProductRepository()
    service = StoreCatalogService(repo)
    for p in imported_products:
        service.add_product(p)

    # Assert: перевірка загального стану та метрик
    assert len(repo.get_all()) == 3
    # Розрахунок: 22000*10 (220000) + 350*50 (17500) + 250*20 (5000) = 242500 UAH
    total_val = service.calculate_total_inventory_value()
    assert total_val.amount == pytest.approx(242500.0)

    accessories = service.filter_by_category("Аксесуари")
    assert len(accessories) == 2


def test_integration_json_export_pipeline(tmp_path: Path, sample_catalog: list[Product]) -> None:
    """
    Integration Test 2: Експорт каталогу у JSON-файл через tmp_path,
    подальше зчитування файлу та валідація збереженої схеми даних.
    """
    export_file = tmp_path / "catalog_dump.json"

    # Act
    export_catalog_to_json(sample_catalog, export_file)

    # Assert
    assert export_file.exists()
    raw_content = export_file.read_text(encoding="utf-8")
    loaded_data = json.loads(raw_content)

    assert isinstance(loaded_data, list)
    assert len(loaded_data) == 3

    # Перевіряємо першу позицію
    first_item = loaded_data[0]
    assert first_item["product_id"] == 101
    assert first_item["name"] == "Ноутбук Pro"
    assert first_item["inventory_value"] == pytest.approx(120000.0)


def test_integration_full_ecommerce_flow(tmp_path: Path) -> None:
    """
    Integration Test 3: Наскрізний потік (E2E-like Integration):
    1. Імпорт товарів із CSV.
    2. Фільтрація та застосування політики знижок.
    3. Синхронізація позиції через зовнішній сервіс постачальника.
    4. Експорт фінального звіту в JSON та перевірка коректності.
    """
    async def run_pipeline() -> None:
        # Крок 1: Тимчасовий вхідний CSV
        input_csv = tmp_path / "batch.csv"
        input_csv.write_text(
            "product_id,name,category,price,currency,quantity\n"
            "601,Навушники Wireless,Аудіо,3000.0,UAH,5\n"
            "602,Колонка Bluetooth,Аудіо,1500.0,UAH,2\n",
            encoding="utf-8"
        )
        products = import_catalog_from_csv(input_csv)

        repo = InMemoryProductRepository()
        catalog_svc = StoreCatalogService(repo)
        for p in products:
            catalog_svc.add_product(p)

        # Крок 2: Застосування акційної знижки 20% на категорію 'Аудіо'
        discount = PercentageDiscount(20.0)
        audio_items = catalog_svc.filter_by_category("Аудіо")
        discounted_products: list[Product] = []

        for item in audio_items:
            new_price = discount.apply(item.price)
            updated_p = Product(
                item.product_id,
                item.name,
                item.category,
                new_price,
                item.quantity
            )
            catalog_svc.add_product(updated_p)
            discounted_products.append(updated_p)

        # Крок 3: Синхронізація нового товару через асинхронного постачальника
        mock_supplier = AsyncMock(spec=AsyncSupplierClientProtocol)
        mock_supplier.fetch_supplier_data.return_value = {
            "name": "Мікрофон Студійний",
            "category": "Аудіо",
            "price": 5000.0,
            "quantity": 3,
        }
        sync_svc = AsyncProductSyncService(repo, mock_supplier)
        await sync_svc.sync_product_from_supplier(603)

        # Крок 4: Фінальний експорт усього оновленого каталогу
        final_json = tmp_path / "final_report.json"
        all_final_items = repo.get_all()
        export_catalog_to_json(all_final_items, final_json)

        # Перевірка файлу звіту
        data = json.loads(final_json.read_text(encoding="utf-8"))
        assert len(data) == 3

        # Перевіряємо товар зі знижкою 20%: 3000 - 20% = 2400.0 UAH
        headphones = next(x for x in data if x["product_id"] == 601)
        assert headphones["price"] == pytest.approx(2400.0)
        assert headphones["inventory_value"] == pytest.approx(2400.0 * 5)

        # Перевіряємо синхронізований мікрофон
        mic = next(x for x in data if x["product_id"] == 603)
        assert mic["price"] == pytest.approx(5000.0)
        assert mic["quantity"] == 3

    asyncio.run(run_pipeline())


# =====================================================================
# 11. DEMONSTRATION & CLI ENTRYPOINT (MAIN)
# =====================================================================

def run_manual_demonstration() -> None:
    """Демонстрація виконання ключових сценаріїв предметної області."""
    print("=" * 70)
    print("ДЕМОНСТРАЦІЯ МОДУЛЯ 'ІНТЕРНЕТ-МАГАЗИН' (ВА PIANT №3)")
    print("=" * 70)

    # 1. Створення товарів
    p1 = Product(1, "Ігровий ПК Ultra", "Комп'ютери", Money(45000.0), 3)
    p2 = Product(2, "Монітор 27' 144Hz", "Монітори", Money(9500.0), 7)
    p3 = Product(3, "Ігрова миша", "Периферія", Money(1800.0), 12)

    repo = InMemoryProductRepository([p1, p2, p3])
    service = StoreCatalogService(repo)

    print("\n1. Товари в каталозі:")
    for p in repo.get_all():
        print(f"  - [{p.product_id}] {p.name} ({p.category}): {p.price.amount} {p.price.currency} | Залишок: {p.quantity}")

    # 2. Метрики
    total_val = service.calculate_total_inventory_value()
    most_expensive = service.get_most_expensive_product()
    print(f"\n2. Загальна вартість залишків на складі: {total_val.amount:.2f} {total_val.currency}")
    if most_expensive:
        print(f"   Найдорожчий товар: {most_expensive.name} ({most_expensive.price.amount:.2f} {most_expensive.price.currency})")

    # 3. Знижка
    discount = PercentageDiscount(15.0)
    new_price = discount.apply(p1.price)
    print(f"\n3. Застосування знижки 15% до '{p1.name}':")
    print(f"   Початкова: {p1.price.amount} -> Нова ціна: {new_price.amount:.2f} {new_price.currency}")

    # 4. Пошук та фільтрація
    found = service.search_by_name("миша")
    print(f"\n4. Результат пошуку за запитом 'миша': {[p.name for p in found]}")
    print("=" * 70)


def main() -> None:
    """
    Головна точка входу:
    1. Виконує демонстрацію доменного функціоналу.
    2. Автоматично запускає повний набір unit та integration тестів через pytest.
    """
    run_manual_demonstration()

    print("\n[INFO] Запуск автоматизованого pytest suite...")
    # Запускаємо pytest безпосередньо для поточного файлу
    test_args = [
        "-v",
        "-s",
        "--tb=short",
        __file__,
    ]

    # Додаємо підтримку виводу coverage, якщо встановлено бібліотеку pytest-cov
    try:
        import pytest_cov  # noqa: F401
        test_args.extend(["--cov", "--cov-report=term-missing"])
    except ImportError:
        pass

    exit_code = pytest.main(test_args)
    if exit_code == 0:
        print("\n[SUCCESS] Усі тести завершилися успішно (Exit code 0).")
    else:
        print(f"\n[FAILURE] Тестовий набір завершився з кодом: {exit_code}")


if __name__ == "__main__":
    main()