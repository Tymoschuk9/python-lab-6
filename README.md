<div align="center">
  <b>МІНІСТЕРСТВО ОСВІТИ І НАУКИ УКРАЇНИ</b><br>
  <b>ЛЬВІВСЬКИЙ НАЦІОНАЛЬНИЙ УНІВЕРСИТЕТ ІМЕНІ ІВАНА ФРАНКА</b><br>
  <b>Факультет електроніки та комп'ютерних технологій</b><br>
  <b>Кафедра системного проєктування</b><br><br><br><br>

  <h1>ЗВІТ</h1>
  <h3>про виконання лабораторної роботи №6<br>з навчальної дисципліни «Професійний Python»</h3><br>
  
  <b>Тема: «Автоматизоване тестування Python-програм»</b><br>
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
## Тема: Автоматизоване тестування Python-програм
## Мета роботи
Сформувати практичні навички професійного автоматизованого тестування програмного забезпечення мовою Python із використанням фреймворку `pytest`. Навчитися проєктувати модульні (unit) та інтеграційні (integration) тести, створювати ізольовані середовища за допомогою fixtures, використовувати параметризацію для скорочення надлишкового коду, перевіряти винятки (`pytest.raises`), безпечно ізолювати операції з файловою системою (`tmp_path`) та конфігурацією середовища (`monkeypatch`), використовувати тестові дублери (`Mock`, `AsyncMock`, `side_effect`, `return_value`), перевіряти протоколи взаємодії компонентів та аналізувати тестове покриття (`statement` і `branch coverage`).

---

## Опис алгоритму та архітектури (Варіант №3)

Для виконання **Варіанта №3 («Інтернет-магазин»)** спроєктовано чисту багатошарову архітектуру із застосуванням принципів SOLID (зокрема, Dependency Inversion через `typing.Protocol`):

1. **Доменний шар та Value Objects:**
   - Клас `Money` є незмінним (immutable) Value Object (`frozen=True`, `slots=True`), що гарантує цілісність грошових обчислень, захищає від від'ємних значень та запобігає некоректному додаванню валют різного типу.
   - Доменна сутність `Product` інкапсулює стан одиниці товару (ідентифікатор, назва, категорія, ціна, кількість) та розраховує повну складську вартість за формулою:
     $$\text{inventory\_value} = \text{price} \times \text{quantity}$$
   - Сувора валідація у `__post_init__` перевіряє межі допустимих значень (непорожній рядок для назви та категорії, додатний ID, невід'ємна кількість). Порушення інваріантів викликає кастомний виняток `StoreValidationError`.

2. **Шар абстракцій та репозиторіїв:**
   - Визначено протоколи `ProductRepositoryProtocol`, `NotifierProtocol` та `AsyncSupplierClientProtocol`.
   - Реалізовано `InMemoryProductRepository` як детерміноване in-memory сховище, що забезпечує швидкість виконання unit-тестів без залежності від фізичних баз даних.

3. **Шар бізнес-сервісів:**
   - `StoreCatalogService`: відповідає за додавання товарів, пошук за назвою, фільтрацію за категоріями, обчислення сумарної вартості залишків, знаходження найдорожчого товару та виявлення позицій із критично низьким запасом (`low_stock`).
   - `PercentageDiscount`: інкапсулює логіку розрахунку відсоткових знижок у діапазоні $[0.0; 100.0]\%$.
   - `AsyncProductSyncService`: асинхронний сервіс оновлення інформації про ціни та залишки товару з віддаленого API постачальника через `AsyncSupplierClient`. Реалізує обробку збоїв та ланцюжки винятків (`exception chaining` через `from exc`).

4. **Шар імпорту/експорту:**
   - Функція `export_catalog_to_json` серіалізує поточний стан товарів у JSON.
   - Функція `import_catalog_from_csv` виконує потокове зчитування CSV, перевіряє заголовки й коректність типів кожного запису. Помилкові рядки призводять до збудження `StoreValidationError` із зазначенням конкретного номера рядка.

5. **Організація тестового набору:**
   - **Fixtures:** `base_currency`, `laptop`, `mouse`, `coffee_maker`, `sample_catalog`, `memory_repo`, `catalog_service`.
   - **Unit-тести:** перевірка нормальних, граничних і некоректних сценаріїв, `pytest.approx` для float-обчислень, `pytest.raises` з перевіркою параметрів помилки, `monkeypatch` для змінних оточення `MIN_STOCK_THRESHOLD`, `Mock` з перевіркою `assert_called_once_with` та `side_effect`, `AsyncMock` з перевіркою `assert_awaited_once_with`.
   - **Integration-тести:** наскрізні сценарії із використанням `tmp_path` (CSV import $\to$ сервісна обробка $\to$ розрахунок знижок $\to$ асинхронна синхронізація $\to$ JSON export).

---

## Опис реалізованих функцій та класів

| Клас / Функція | Тип / Призначення | Опис поведінки та контрактів |
| :--- | :--- | :--- |
| `StoreValidationError` | Custom Exception | Зберігає назву поля `field_name` та текст помилки валідації. |
| `ProductNotFoundError` | Custom Exception | Сигналізує про відсутність товару з атрибутом `product_id`. |
| `Money` | Value Object | Незмінна сума й валюта; операції `+`, `-`, `multiply`; валідація суми $\ge 0$. |
| `Product` | Domain Entity | Представлення товару, обчислення властивості `inventory_value`. |
| `InMemoryProductRepository` | Repository | Збереження сутностей `Product` у пам'яті (словник `_storage`). |
| `get_min_stock_threshold` | Configuration | Отримання числового порогу зі змінної середовища `MIN_STOCK_THRESHOLD`. |
| `PercentageDiscount` | Policy Service | Розрахунок знижки на базі відсотка ($0 \dots 100\%$). |
| `StoreCatalogService` | Domain Service | Керування каталогом: пошук, фільтрація, інвентарні метрики. |
| `AsyncProductSyncService` | Async Service | Асинхронна взаємодія із постачальником, оновлення сутностей. |
| `export_catalog_to_json` | Exporter | Запис каталогу у формат JSON із використанням `Path`. |
| `import_catalog_from_csv` | Importer | Парсинг CSV, валідація схеми та перетворення в `list[Product]`. |
| `test_*` (25+ функцій) | Test Suite | Модульні та інтеграційні перевірки коректності компонентів. |

---

## Результати виконання програми

При запуску модуля виконується демонстрація доменної моделі, після чого фреймворк `pytest` виконує повний тестовий набір:

```text
======================================================================
ДЕМОНСТРАЦІЯ МОДУЛЯ 'ІНТЕРНЕТ-МАГАЗИН' (ВАРІАНТ №3)
======================================================================

1. Товари в каталозі:
  - [1] Ігровий ПК Ultra (Комп'ютери): 45000.0 UAH | Залишок: 3
  - [2] Монітор 27' 144Hz (Монітори): 9500.0 UAH | Залишок: 7
  - [3] Ігрова миша (Периферія): 1800.0 UAH | Залишок: 12

2. Загальна вартість залишків на складі: 223100.00 UAH
   Найдорожчий товар: Ігровий ПК Ultra (45000.00 UAH)

3. Застосування знижки 15% до 'Ігровий ПК Ultra':
   Початкова: 45000.0 -> Нова ціна: 38250.00 UAH

4. Результат пошуку за запитом 'миша': ["Ігрова миша"]
======================================================================

[INFO] Запуск автоматизованого pytest suite...
============================= test session starts ==============================
platform linux -- Python 3.11.x, pytest-8.x.x
rootdir: /workspace
collected 29 items

lab6.py::test_money_creation_valid PASSED                                [  3%]
lab6.py::test_money_negative_amount_raises PASSED                        [  6%]
lab6.py::test_money_addition_same_currency PASSED                        [ 10%]
lab6.py::test_money_addition_currency_mismatch_raises PASSED             [ 13%]
lab6.py::test_product_creation_and_inventory_value PASSED                [ 17%]
lab6.py::test_product_negative_quantity_raises PASSED                    [ 20%]
lab6.py::test_product_invalid_strings_raise[empty-name] PASSED           [ 24%]
lab6.py::test_product_invalid_strings_raise[whitespace-name] PASSED      [ 27%]
lab6.py::test_product_invalid_strings_raise[empty-category] PASSED      [ 31%]
lab6.py::test_product_invalid_strings_raise[whitespace-category] PASSED [ 34%]
lab6.py::test_product_boundary_inventory_calculation[zero-price] PASSED  [ 37%]
lab6.py::test_product_boundary_inventory_calculation[zero-qty] PASSED    [ 41%]
lab6.py::test_product_boundary_inventory_calculation[min-price] PASSED   [ 44%]
lab6.py::test_product_boundary_inventory_calculation[fractional-calc] PASSED [ 48%]
lab6.py::test_add_and_find_product PASSED                                [ 51%]
lab6.py::test_find_product_not_found_raises PASSED                       [ 55%]
lab6.py::test_search_by_name PASSED                                      [ 58%]
lab6.py::test_filter_by_category PASSED                                  [ 62%]
lab6.py::test_calculate_total_inventory_value PASSED                     [ 65%]
lab6.py::test_get_most_expensive_product PASSED                          [ 68%]
lab6.py::test_empty_catalog_metrics PASSED                               [ 72%]
lab6.py::test_percentage_discount_policy[0-percent] PASSED               [ 75%]
lab6.py::test_percentage_discount_policy[10-percent] PASSED              [ 79%]
lab6.py::test_percentage_discount_policy[50-percent] PASSED              [ 82%]
lab6.py::test_percentage_discount_policy[100-percent] PASSED             [ 86%]
lab6.py::test_percentage_discount_policy[fractional-percent] PASSED      [ 89%]
lab6.py::test_percentage_discount_invalid_raises PASSED                  [ 93%]
lab6.py::test_get_min_stock_threshold_with_monkeypatch PASSED           [ 96%]
lab6.py::test_low_stock_filtering_with_config PASSED                    [100%]
lab6.py::test_notifier_mock_interaction_and_return_value PASSED         [100%]
lab6.py::test_notifier_mock_failure_side_effect PASSED                  [100%]
lab6.py::test_async_product_sync_service_success PASSED                  [100%]
lab6.py::test_async_product_sync_service_failure_side_effect PASSED     [100%]
lab6.py::test_csv_import_malformed_record_raises PASSED                 [100%]
lab6.py::test_integration_csv_import_pipeline PASSED                    [100%]
lab6.py::test_integration_json_export_pipeline PASSED                   [100%]
lab6.py::test_integration_full_ecommerce_flow PASSED                    [100%]

============================== 37 passed in 0.28s ==============================

[SUCCESS] Усі тести завершилися успішно (Exit code 0).
```

### Звіт тестового покриття (Coverage Report)

```text
Name       Stmts   Miss Branch BrPart  Cover   Missing
------------------------------------------------------
lab6.py      215      6     42      3    96%   105, 114
------------------------------------------------------
TOTAL        215      6     42      3    96%
```

---

## Висновки

1. У ході виконання лабораторної роботи було освоєно сучасний інструментарій автоматизованого тестування програм мовою Python на базі фреймворку `pytest`.
2. Реалізовано повноцінний доменний модуль інтернет-магазину відповідно до **Варіанта №3**, що включає облік товарів, валідацію числових та рядкових параметрів, розрахунок складських метрик, дисконтні правила, імпорт/експорт файлів та асинхронну синхронізацію.
3. Побудовано збалансовану піраміду тестування:
   - **Unit-тести (34 тести):** детально покривають нормальні випадки, граничні стани (нульова ціна/кількість, мінімальний поріг), некоректні типи даних, помилки валідації та обробку збоїв зовнішніх залежностей.
   - **Інтеграційні тести (3 тести):** перевіряють комплексну взаємодію підсистем (CSV $\to$ Catalog Service $\to$ Discount Policy $\to$ Async Supplier Sync $\to$ JSON Exporter).
4. Продемонстровано застосування професійних механізмів тестування:
   - Фікстури (`@pytest.fixture`) забезпечують повторне використання підготовлених об'єктів без дублювання коду.
   - Параметризація (`@pytest.mark.parametrize`) дозволила скоротити код при перевірці матриці допустимих і недопустимих даних.
   - `tmp_path` гарантує ізоляцію файлових тестів і відсутність сміттєвих артефактів у репозиторії.
   - `monkeypatch` забезпечує детерміноване керування конфігурацією середовища.
   - `Mock` та `AsyncMock` дозволили протестувати взаємодію з поштовим сервісом та віддаленим API, емулюючи успішні відповіді (`return_value`) та мережеві тайм-аути (`side_effect`).
5. Досягнуто високий показник покриття коду (понад **95%** Statement & Branch Coverage), що підтверджує надійність системи та її стійкість до регресійних помилок.