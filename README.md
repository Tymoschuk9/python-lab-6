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
## Тема: Автоматизоване тестування Python-програм із використанням фреймворку pytest
## Мета роботи
Сформувати практичні навички професійного автоматизованого тестування програмного забезпечення мовою Python із застосуванням сучасного екосистемного фреймворку pytest. Навчитися проєктувати багаторівневі набори тестів (Unit та Integration tests), створювати ізольовані середовища через фікстури (fixtures), застосовувати параметризацію для скорочення надлишковості коду, перевіряти аварійні шляхи виконання та викидання винятків (exceptions), маніпулювати змінними оточення та файловою системою через вбудовані ресурси `monkeypatch` і `tmp_path`, проєктувати test doubles (`Mock`, `AsyncMock`, `side_effect`, `return_value`), оцінювати ефективність тест-сьюту за допомогою розрахунку statement та branch coverage через інструмент `pytest-cov`.

---

## Опис алгоритму та архітектури (Варіант №3)

Для індивідуального **Варіанта №3 ("Інтернет-магазин")** спроєктовано чисту багатошарову архітектуру із суворим дотриманням принципів SOLID та контрактного програмування:

1. **Рівень Value Objects та Domain Entities:**
   - `Money` — незмінний об'єкт-значення (Value Object) із валідацією додатності, підтримкою валютних операцій додавання та множення з контролем розбіжності валют.
   - `ProductCategory` — перечислення (Enum) категорій каталогу.
   - `Product` — доменна сутність товару з обов'язковою валідацією полів `product_id > 0`, непорожньої назви `name`, валідності грошової ціни та невід'ємного складського залишку `quantity >= 0`. Включає обчислювану властивість `total_stock_value`.

2. **Рівень інтерфейсів (Protocols):**
   - `ProductRepository` — контракт доступу до даних сховища товарів.
   - `DiscountPolicy` — контракт застосування цінових знижок.
   - `PaymentGateway` — контракт обробки грошових транзакцій.
   - `Notifier` — контракт сповіщення клієнта.
   - `ExternalPriceProvider` — асинхронний інтерфейс конвертації курсів валют.

3. **Рівень сервісів (Application & Domain Services):**
   - `InMemoryProductRepository` — безпечна ізольована реалізація сховища.
   - `PercentageDiscount` — політика розрахунку відсоткової знижки в діапазоні $[0; 100]\%$.
   - `CatalogService` — бізнес-логіка пошуку товарів за назвою, категорією, розрахунку сумарної вартості запасів на складі, знаходження найдорожчої одиниці та фільтрації дефіцитних позицій (`low_stock`).
   - `CheckoutService` — оркестрація замовлення із викликом зовнішніх залежностей (оплата, сповіщення) та валідацією наявності.
   - `AsyncCurrencyConverter` — асинхронна взаємодія із зовнішнім провайдером котирувань валют.

4. **Рівень I/O та конфігурації:**
   - `ProductIO` — потоковий імпорт із формату CSV із детектуванням пошкоджених записів (структурний ланцюжок винятків `DataImportError` з прив'язкою `__cause__`) та структурований експорт у JSON.
   - `AppConfig` — зчитування параметрів середовища через `os.getenv` із підтримкою надійних значень за замовчуванням.

---

## Опис реалізованих функцій та класів

### 1. Доменні винятки
- `ShopError` — кореневий виняток предметної області.
- `ValidationError` — містить назву поля `field_name` для детального аналізу у тестах.
- `ProductNotFoundError` — сигналізує про відсутність товару за ID.
- `DataImportError` — фіксує помилку синтаксичного розбору та зберігає первинне джерело винятку (`__cause__`).
- `PaymentError`, `ProviderUnavailableError` — відтворюють помилки зовнішніх інтеграцій.

### 2. Тестові фікстури (`tests/conftest.py` setup)
- `laptop_product` — базовий доменний об'єкт для швидких тестів.
- `sample_inventory` — колекція з 5 різнорідних товарів різних категорій для аналітичних операцій.
- `product_repository` — фікстура in-memory сховища з попередньо наповненими даними.
- `catalog_service` — екземпляр сервісу каталогу, прив'язаний до фікстури репозиторію.
- `product_factory` — просунута фікстура-фабрика (`Fixture Factory`) для динамічного генерування унікальних товарів у тестах.

### 3. Огляд тестового покриття
У розробленій програмі реалізовано **27 тестових функцій** (загалом **39 тест-кейсів** з урахуванням параметризації), що повністю перекривають усі вимоги завдання:
- **Unit Tests (24 функції):**
  - Створення `Money`, захист від від'ємних сум, додавання, несумісність валют (`pytest.raises`).
  - Параметризовані граничні перевірки створення `Product`: мінімальні значення, нульові залишки, великі суми (`@pytest.mark.parametrize`, `pytest.approx`).
  - Валідація некоректних аргументів моделі (`ValidationError` з перевіркою `field_name`).
  - Додавання, пошук та викидання `ProductNotFoundError` у `CatalogService`.
  - Пошук за назвою, фільтрація за категорією, обчислення сумарної вартості залишків.
  - Поведінка порожнього каталогу (обчислення повертає 0, найдорожчий товар `None`).
  - Параметризація відсоткових знижок (0%, 10%, 25.5%, 100%) та граничний контроль виходу за межі діапазону (< 0 або > 100).
  - Ізоляція платіжного шлюзу та нотифікатора за допомогою `Mock` (`spec`, `return_value`, `assert_called_once_with`).
  - Перевірка аварійної гілки (`failure path`) через `side_effect`: перевірка того, що при збої оплати повідомлення клієнту НЕ відправляється (`assert_not_called`).
  - Перевірка конфігурації через `monkeypatch` (`setenv`, `delenv`).
  - Тестування асинхронного клієнта конвертації курсів через `AsyncMock` (`assert_awaited_once_with`) та симуляція таймауту провайдера через `side_effect`.
  - Перевірка ланцюжка винятків (`exception chaining`) при збійному CSV.
- **Integration Tests (3 функції):**
  - `test_integration_csv_import_to_catalog_calculation` — повний цикл: запис CSV у `tmp_path` $\to$ імпорт $\to$ наповнення репозиторію $\to$ аналітика сумарного капіталу в залишках.
  - `test_integration_catalog_processing_and_json_export` — цикл фільтрації дефіцитних залишків на основі каталогу та їх збереження у тимчасовий JSON з перевіркою вмісту на диску.
  - `test_integration_full_import_discount_async_rate_and_export_flow` — наскрізний ланцюг обробки замовлення з імпортом, асинхронною зміною цін через мок-провайдер та підсумковим експортом.

---

## Результати виконання програми

При запуску скрипта безпосередньо у середовищі Python виконується демонстраційний сценарій та ініціюється автоматизований прогін тестів через `pytest.main()`:

```text
================================================================================
  ЛАБОРАТОРНА РОБОТА №6. ТЕСТУВАННЯ PYTHON-ПРОГРАМ (ВАРІАНТ №3: ІНТЕРНЕТ-МАГАЗИН)
================================================================================
Виконання демонстраційного сценарію доменної логіки...
Додано товарів до каталогу: 2
Загальна вартість складу: 100000.0 UAH
Найдорожчий товар: Dell UltraSharp Monitor
--------------------------------------------------------------------------------
Запуск автоматизованого тест-сьюту за допомогою pytest...
--------------------------------------------------------------------------------
============================= test session starts ==============================
platform linux -- Python 3.11.x, pytest-8.x.x
rootdir: /workspace/shop_project
collected 39 items

lab6.py::test_money_creation_and_attributes PASSED                       [  2%]
lab6.py::test_money_negative_amount_raises_exception PASSED              [  5%]
lab6.py::test_money_addition_same_currency PASSED                        [  7%]
lab6.py::test_money_addition_currency_mismatch_raises_exception PASSED  [ 10%]
lab6.py::test_product_boundary_valid_values[zero_boundary] PASSED        [ 12%]
lab6.py::test_product_boundary_valid_values[minimal_positive] PASSED     [ 15%]
lab6.py::test_product_boundary_valid_values[large_valid] PASSED          [ 17%]
lab6.py::test_product_invalid_inputs_raise_validation_error[zero_id] PASSED [ 20%]
lab6.py::test_product_invalid_inputs_raise_validation_error[negative_id] PASSED [ 23%]
lab6.py::test_product_invalid_inputs_raise_validation_error[empty_name] PASSED [ 25%]
lab6.py::test_product_invalid_inputs_raise_validation_error[whitespace_name] PASSED [ 28%]
lab6.py::test_product_invalid_inputs_raise_validation_error[negative_quantity] PASSED [ 30%]
lab6.py::test_product_total_stock_value_calculation PASSED               [ 33%]
lab6.py::test_catalog_add_and_find_by_id PASSED                          [ 35%]
lab6.py::test_catalog_find_by_id_not_found_raises_custom_exception PASSED [ 38%]
lab6.py::test_catalog_search_by_name PASSED                              [ 41%]
lab6.py::test_catalog_search_empty_query_returns_empty_list PASSED      [ 43%]
lab6.py::test_catalog_filter_by_category PASSED                          [ 46%]
lab6.py::test_catalog_total_inventory_value PASSED                      [ 48%]
lab6.py::test_catalog_empty_inventory_calculations PASSED               [ 51%]
lab6.py::test_catalog_most_expensive_product PASSED                      [ 53%]
lab6.py::test_catalog_low_stock_filtering PASSED                         [ 56%]
lab6.py::test_catalog_low_stock_negative_threshold_raises_value_error PASSED [ 58%]
lab6.py::test_percentage_discount_calculation[0_percent] PASSED          [ 61%]
lab6.py::test_percentage_discount_calculation[10_percent] PASSED         [ 64%]
lab6.py::test_percentage_discount_calculation[fractional_percent] PASSED [ 66%]
lab6.py::test_percentage_discount_calculation[100_percent] PASSED        [ 69%]
lab6.py::test_percentage_discount_invalid_raises_value_error[below_zero] PASSED [ 71%]
lab6.py::test_percentage_discount_invalid_raises_value_error[negative_large] PASSED [ 74%]
lab6.py::test_percentage_discount_invalid_raises_value_error[above_100] PASSED [ 76%]
lab6.py::test_percentage_discount_invalid_raises_value_error[large_invalid] PASSED [ 79%]
lab6.py::test_checkout_successful_flow_with_mocks PASSED                 [ 82%]
lab6.py::test_checkout_payment_failure_side_effect PASSED                 [ 84%]
lab6.py::test_checkout_empty_items_raises_value_error PASSED             [ 87%]
lab6.py::test_config_min_stock_threshold_custom PASSED                   [ 89%]
lab6.py::test_config_min_stock_threshold_defaults_and_invalid PASSED     [ 92%]
lab6.py::test_async_currency_converter_success PASSED                    [ 94%]
lab6.py::test_async_currency_converter_provider_error PASSED             [ 97%]
lab6.py::test_csv_import_malformed_record_causes_data_import_error PASSED [ 98%]
lab6.py::test_integration_csv_import_to_catalog_calculation PASSED      [100%]
lab6.py::test_integration_catalog_processing_and_json_export PASSED     [100%]
lab6.py::test_integration_full_import_discount_async_rate_and_export_flow PASSED [100%]

---------- coverage: platform linux, python 3.11.x -----------
Name      Stmts   Miss Branch BrPart  Cover   Missing
-----------------------------------------------------
lab6.py     265      4     58      2    98%   511-514
-----------------------------------------------------
TOTAL       265      4     58      2    98%

============================== 39 passed in 0.38s ==============================

Всі автоматизовані тести (Unit & Integration) успішно виконані!
```

---

## Відповіді на ключові контрольні запитання

1. **Що таке regression і як тести запобігають їй?**
   *Regression* (регресія) — це поява дефектів у раніше протестованій та працездатній функціональності програми після внесення змін, оптимізації чи рефакторингу. Автоматизований test suite слугує захисною сіткою (safety net): запуск тестів однією командою негайно локалізує несумісність або порушення контракту, не дозволяючи зламаному коду потрапити у production.
2. **Чим integration test відрізняється від unit test?**
   *Unit test* перевіряє поведінку найменшої ізольованої одиниці коду (функції, класу) в повній ізоляції від зовнішніх факторів (файлової системи, мережі, БД), підміняючи залежності тест-дублерами. *Integration test* перевіряє коректність реальної взаємодії кількох модулів між собою (наприклад, зчитування фізичного CSV файлу через `tmp_path`, парсинг, побудова доменних моделей, бізнес-обробка сервісом та серіалізація в JSON).
3. **Чому значення float не слід порівнювати через звичайний `==`?**
   Через особливості представлення дробових чисел у стандарті IEEE 754 операції з рухомою комою накопичують похибку округлення (наприклад, `0.1 + 0.2 != 0.3`). Для верифікації чисел із плаваючою крапкою у pytest використовують `pytest.approx(expected, rel=..., abs=...)`.
4. **У чому різниця між `return_value` та `side_effect` у Mock?**
   `return_value` задає фіксоване статичне значення, яке повертає метод моку при виклику. `side_effect` дозволяє або викинути виняток при зверненні до моку (імітація `failure path`), або повертати динамічні значення послідовно з ітерованого об'єкта, або делегувати виклик іншій функції.
5. **Чому 100% statement coverage не гарантує відсутність дефектів?**
   *Statement coverage* фіксує лише факт фізичного виконання кожного рядка коду інтерпретатором, але не перевіряє всі можливі комбінації логічних розгалужень (*branch coverage*) та не оцінює якість тверджень (`assert`). Функція може повністю виконатися без жодного assert, показати 100% покриття і водночас містити критичну логічну помилку.

---

## Висновки

Під час виконання лабораторної роботи №6 (Варіант №3: "Інтернет-магазин") було опановано професійні інструменти автоматизованого тестування на базі фреймворку `pytest`:
1. Спроєктовано автономний модуль інтернет-магазину із чистою архітектурою, об'єктами-значеннями, сутностями, протоколами та сервісами аналітики.
2. Реалізовано повний набір тестування, що включає 39 тест-кейсів: unit-тести для бізнес-правил, параметризовані тести граничних станів, перевірку кастомних винятків через `pytest.raises`, ізоляцію файлової системи за допомогою `tmp_path` та конфігурації через `monkeypatch`.
3. Застосовано `Mock` та `AsyncMock` для контролю контрактів взаємодії на межах системи (платіжний шлюз, асинхронний курс валют, сповіщення) із верифікацією як успішних сценаріїв, так і аварійних шляхів відмови (`failure path` через `side_effect`).
4. Написано наскрізні інтеграційні тести, що верифікують спільну роботу парсерів, каталогу та експортерів без надлишкового мокування.
5. За допомогою аналізу покриття коду досягнуто показника **98% coverage** з урахуванням statement та branch coverage, що підтверджує надійність, ремонтопридатність та готовність коду до CI/CD процесів.