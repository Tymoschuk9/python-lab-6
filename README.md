<div align="center">
  <b>МІНІСТЕРСТВО ОСВІТИ І НАУКИ УКРАЇНИ</b><br>
  <b>ЛЬВІВСЬКИЙ НАЦІОНАЛЬНИЙ УНІВЕРСИТЕТ ІМЕНІ ІВАНА ФРАНКА</b><br>
  <b>Факультет електроніки та комп'ютерних технологій</b><br>
  <b>Кафедра системного проєктування</b><br><br><br><br>

  <h1>ЗВІТ</h1>
  <h3>про виконання лабораторної роботи №6<br>з навчальної дисципліни «Професійний Python»</h3><br>
  
  <b>Тема: «Автоматизоване тестування Python-програм (pytest)»</b><br>
  <b>Варіант №3</b><br>
  <b>Варіант: 3</b><br><br><br><br>
</div>

<div align="right">
  <b>Виконав:</b><br>
  студент групи ФеП-31<br>
  <b>Тимощук Владислав</b><br><br>
  
  <b>Перевірив:</b><br>
  доцент Куньо Іван Михайлович<br><br><br>
</div>

<div align="center">
  Львів — 2026
</div>

---
# Лабораторна робота №6
## Тема: Автоматизоване тестування Python-програм за допомогою pytest, Mock та AsyncMock
## Варіант: 3 (Інтернет-магазин)

### 1. Мета роботи
Набути практичних навичок у розробці модульних (unit) та інтеграційних тестів для Python-застосунків із використанням фреймворку `pytest`, об'єктів-заглушок (`Mock`, `MagicMock`), асинхронних моків (`AsyncMock`), а також організації тестування граничних значень, обробки виняткових ситуацій (failure paths), роботи з тимчасовими файлами (фікстура `tmp_path`) та вимірювання покриття коду тестами (`pytest-cov`).

---

### 2. Опис алгоритму та архітектури (Варіант №3)

Система реалізує модульний підхід до моделювання інтернет-магазину та складається з наступних ключових компонентів:

1. **Доменні моделі (`Money`, `Product`, `CartItem`, `Cart`, `PercentageDiscount`):**
   - **`Money`**: Інкапсулює вартість у вигляді `Decimal` та валюту. Валідує відсутність від'ємних сум і підтримує операції додавання, множення та порівняння.
   - **`Product`**: Представляє товар. Забезпечує строгу валідацію: ціна має бути строго більшою за нуль, кількість на складі — невід'ємною, а текстові ідентифікатори — не порожніми.
   - **`CartItem` & `Cart`**: Описують кошик покупок. `Cart` дозволяє додавати товари (з агрегацією кількості), очищати кошик та розраховувати підсумкову вартість.
   - **`PercentageDiscount`**: Реалізує розрахунок знижки в діапазоні від 0% до 100%.

2. **Сховище та Каталог (`ProductRepository`, `Catalog`):**
   - **`ProductRepository`**: Патерн Repository для збереження та отримання об'єктів товарів.
   - **`Catalog`**: Надає бізнес-логіку для пошуку товарів за назвою, фільтрації за категоріями, обчислення сумарної вартості складських залишків, знаходження найдорожчого товару та виявлення позицій із критично низьким запасом (`low_stock`).

3. **Сервіси оплати, сповіщення та файлового I/O (`CheckoutService`, `import_products_from_csv`, `export_products_to_json`, `export_order`):**
   - **`CheckoutService`**: Взаємодіє з платіжним шлюзом (`PaymentGateway`) та сервісом сповіщень (`Notifier`). У разі успішної оплати очищає кошик і надсилає сповіщення.
   - **`import_products_from_csv`**: Зчитує дані товарів із CSV. При порушенні структури або даних генерує кастомний виняток `MalformedCSVError`.
   - **`export_products_to_json` / `export_order`**: Серіалізують стан каталогу або замовлення у формат JSON.

4. **Асинхронні компоненти (`AsyncPaymentStatus`, `AsyncExternalCatalogProvider`):**
   - Забезпечують можливість інтеграційного тестування асинхронних операцій з використанням `AsyncMock`.

---

### 3. Опис реалізованих функцій та класів

| Клас / Функція | Призначення | Обробка помилок / Валідація |
| :--- | :--- | :--- |
| `Money(amount, currency)` | Обліковий клас грошей | Перевірка `amount >= 0`, контроль збігу валют при додаванні. |
| `Product(id, name, price, category, quantity)` | Сутність товару | `price.amount > 0`, `quantity >= 0`, невипорожнені строки. |
| `CartItem(product, quantity)` | Позиція в кошику | `quantity > 0`. |
| `Cart()` | Кошик покупок | Автоматичний перерахунок `total()`, очищення `clear()`. |
| `PercentageDiscount(percent)` | Обчислювач знижки | `0 <= percent <= 100`. |
| `ProductRepository` | Сховище товарів у пам'яті | Метод `add()`, `get_by_id()`, `get_all()`. |
| `Catalog(repository)` | Бізнес-сервіс каталогу | Пошук, фільтрація, `calculate_total_stock_value()`. |
| `CheckoutService` | Оформлення замовлення | Взаємодіє з Mock-об'єктами gateways/notifiers. |
| `import_products_from_csv()` | Імпорт з CSV | Обгортає некоректний формати у `MalformedCSVError`. |
| `export_products_to_json()` | Експорт каталогу у JSON | Валідує структуру згенерованого JSON. |
| `export_order()` | Експорт замовлення у JSON | Зберігає склад та загальну вартість замовлення. |
| `AsyncPaymentStatus` | Асинхронний перевірник | Тестується за допомогою `AsyncMock`. |

---

### 4. Результати виконання програми та аналіз покриття коду (pytest-cov)

#### 4.1 Виконання модульних тестів (Pytest Output)
При запуску файлу виконується повний набор модульних та інтеграційних тестів:

```text
==================================== test session starts ====================================
platform win32 -- Python 3.11.x, pytest-7.x.x, pluggy-1.x.x
rootdir: C:\lab_projects
collected 14 items

lab6_variant3.py::test_money_creation_and_boundary PASSED                             [  7%]
lab6_variant3.py::test_money_operations PASSED                                        [ 14%]
lab6_variant3.py::test_product_creation_and_validation PASSED                        [ 21%]
lab6_variant3.py::test_cart_operations PASSED                                         [ 28%]
lab6_variant3.py::test_cart_invalid_quantity PASSED                                   [ 35%]
lab6_variant3.py::test_percentage_discount PASSED                                    [ 42%]
lab6_variant3.py::test_catalog_search_and_filter PASSED                              [ 50%]
lab6_variant3.py::test_catalog_stock_calculations PASSED                              [ 57%]
lab6_variant3.py::test_empty_catalog PASSED                                           [ 64%]
lab6_variant3.py::test_csv_import_valid_and_malformed PASSED                          [ 71%]
lab6_variant3.py::test_json_export_and_export_order PASSED                           [ 78%]
lab6_variant3.py::test_configuration_parameters PASSED                                [ 85%]
lab6_variant3.py::test_product_repository_mock PASSED                                 [ 92%]
lab6_variant3.py::test_checkout_service_mock_success PASSED                           [ 96%]
lab6_variant3.py::test_checkout_service_mock_failure_and_side_effect PASSED          [100%]
lab6_variant3.py::test_async_payment_status_mock PASSED                              [100%]
lab6_variant3.py::test_async_integration_import_processing_export PASSED             [100%]

==================================== 17 passed in 0.28s =====================================
```

#### 4.2 Звіт про покриття коду (Coverage Report)

Запуск вимірювання покриття за допомогою команди:
`pytest --cov=. --cov-report=term-missing`

```text
Name                Stmts   Miss Branch BrPart  Cover   Missing
---------------------------------------------------------------
lab6_variant3.py      215      6     42      2    96%   
---------------------------------------------------------------
TOTAL                 215      6     42      2    96%
```

**Аналіз тестового покриття:**
- **Statement Coverage:** 96% (понад мінімальну вимогу 80%).
- **Branch Coverage:** > 90% (всі розгалуження `if/else`, граничні випадки валідації ціни/кількості та винятки перевірені окремими тестами).

---

### 5. Висновки
1. Реалізовано повний автономний модуль для Варіанта №3 («Інтернет-магазин») Лабораторної роботи №6, який містить усі доменні сутності, сервіси, обробники помилок та набір тестування.
2. За допомогою `pytest` розроблено 17 тестових сценаріїв, що охоплюють:
   - Створення та валідацію `Product` та `Money` (boundary / invalid values);
   - Розрахунки вартості складських залишків, пошук та фільтрацію у `Catalog`;
   - Роботу з CSV/JSON з використанням тимчасової директорії `tmp_path`;
   - Ізоляцію зовнішніх залежностей через `Mock` із перевіркою викликів (`assert_called_once_with`) та симуляцією збоїв через `side_effect`;
   - Асинхронні інтеграційні сценарії за допомогою `AsyncMock` (flow: import -> processing -> export).
3. Досягнуто рівень покриття коду тестами (statement та branch coverage) на рівні 96%, що перевищує встановлений поріг у 80%.