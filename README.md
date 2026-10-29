# Course Catalog API

Лабораторная работа 7 — SQLAlchemy и Alembic. API каталога курсов хранит
данные в PostgreSQL, а структуру базы изменяют две последовательные миграции.
Это продолжение API лабораторной №5 в том же репозитории.

## Запуск

Требуются Python 3.11 или новее, PostgreSQL 16 или новее и `psql` в PATH.
Проверено на Windows, Python 3.12.14, PostgreSQL 18.6, SQLAlchemy 2.1.6,
Alembic 1.20.1, FastAPI 0.143.0 и psycopg 3.3.6.
Все команды приложения выполняются из корня репозитория.

Один раз на пустом сервере откройте `psql -h localhost -U postgres -d postgres`
и выполните:

```sql
CREATE ROLE catalog_app LOGIN PASSWORD 'change-me';
CREATE DATABASE course_catalog OWNER catalog_app;
\q
```

Уже существующие роль и базу повторно создавать не нужно. Пароль `change-me`
учебный; реальные пароли не публикуются. В PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item .env.example .env
$env:PGCLIENTENCODING = "UTF8"
```

При необходимости исправьте адрес и порт в `.env`. Образец использует порт
5432; локальная проверка выполнена на 55436. Переменная окружения DATABASE_URL
имеет приоритет над `.env`; после временного переключения базы удалите её
через `Remove-Item Env:DATABASE_URL`. Файл `.env` исключён из Git.
Если активация окружения недоступна, запускайте Python и инструменты напрямую
из `.venv/Scripts/`.

Для новой пустой базы:

```powershell
python check_db.py
python -m alembic upgrade head
psql -X -h localhost -U catalog_app -d course_catalog -v ON_ERROR_STOP=1 -f seed.sql
python check_models.py
python -m alembic check
python -m uvicorn main:app --reload
```

В команду psql добавьте `-p 55436`, если используете локальный учебный сервер
на этом порту. При запросе пароля введите `change-me`. На Linux/macOS окружение
активируется командой `source .venv/bin/activate`, а `.env` копируется через
`cp .env.example .env`; остальные команды одинаковы.

Документация API: [Swagger](http://localhost:8000/docs),
[ReDoc](http://localhost:8000/redoc). В другом терминале с активным окружением:

```powershell
python try_errors.py
```

Ожидаемый итог — `5 of 5 as expected`. Для другого адреса сервера:
`python try_errors.py --base-url http://127.0.0.1:8007`.

**seed.sql очищает учебные таблицы и сбрасывает счётчики ID.** Его можно
повторять для восстановления 6 курсов, 3 студентов и 6 записей. Все действия
в файле объединены в транзакцию. На рабочей базе с нужными данными этот файл
запускать нельзя. Схема создаётся миграциями; вызова `create_all()` в API нет.

### Если база уже создана в лабораторной №6

Сначала убедитесь, что таблицы, типы, ключи, ограничения и индекс соответствуют
миграции 0001. Затем выполните:

```powershell
python -m alembic stamp 0001
python -m alembic upgrade head
python -m alembic check
python check_models.py
```

`stamp` только записывает номер версии, не создаёт таблицы и не проверяет их
структуру. Здесь нужен именно `0001`: `stamp head` в готовом проекте означал бы
0002 и ошибочно объявил бы отсутствующий столбец level уже существующим.
В ходе работы 0001 сначала была проверена в отдельной пустой базе; затем
схема лабораторной №6 получила отметку 0001 и успешно прошла `alembic check`.

### Автоматические проверки

Создайте отдельную тестовую базу от имени администратора:

```sql
CREATE DATABASE course_catalog_test OWNER catalog_app;
```

Затем:

```powershell
python -m pip install -r requirements-dev.txt
$env:TEST_DATABASE_URL = "postgresql+psycopg://catalog_app:change-me@localhost:5432/course_catalog_test"
python -m pytest -q
Remove-Item Env:TEST_DATABASE_URL
```

Тесты требуют имя базы с окончанием `_test`, применяют миграции и загружают
учебные данные. Изменения каждого теста откатываются отдельной транзакцией.
Основная база приложения для тестов не используется.

## Изменения в API

Курсы, студенты и записи теперь находятся в PostgreSQL. Лайки, новые студенты
и регистрации сохраняются после перезапуска процесса API. На каждый запрос
выдаётся своя Session; после обработки она закрывается, соединение возвращается
в пул. Изменяющие маршруты выполняют COMMIT; ошибки вставки вызывают ROLLBACK.

| Метод и маршрут | Назначение |
|---|---|
| GET / | Проверка работы API |
| GET /courses | Фильтры is_elective, level, q; сортировка popular или title; page и page_size |
| GET /courses/{course_id} | Один курс, 404 при отсутствии |
| POST /courses/{course_id}/like | Атомарный UPDATE с likes + 1 и RETURNING |
| POST /students | Создание студента по name и email, ответ 201 |
| POST /enrollments | Запись существующего студента на курс, ответ 201 |
| GET /enrollments | Записи с именем студента и названием курса через JOIN |
| GET /stats/courses | Число записей каждого курса, включая нули |

JSON использует camelCase. Вместо studentName в POST /enrollments требуется
studentId. Пример: сначала `{"name":"Nurlan Abenov","email":"nurlan@example.com"}`
в POST /students, затем `{"courseId":"web-security","studentId":4}` в POST
/enrollments, где 4 заменяется фактическим id из первого ответа.
Frontend лабораторной №5 не изменён; его прежняя форма с studentName получит 422.
Проверять новый контракт следует через Swagger.

Ответ GET /enrollments включает courseTitle, studentName и enrolledAt с часовым
поясом. Статистика использует `count(Enrollment.id)`: count(*) ошибочно считает
одну строку LEFT JOIN даже у курса без записей.

Поле level обязательно и не имеет серверного значения по умолчанию.
Для существующих данных elective-курсам назначен beginner, остальным —
intermediate. Фильтр `?level=beginner` возвращает ai-integration и api-design;
`?level=advanced` на учебных данных возвращает пустой список. В рамках основной
работы level хранится как text; отдельного CHECK на три значения нет.

Поиск q из лабораторной №5 сохранён; `%` и `_` трактуются как обычные символы,
а значения передаются параметрами. Сортировка дополняется id для устойчивой
пагинации. page >= 1, размер страницы от 1 до 100.

| Ограничение | Ответ |
|---|---|
| students_email_key | 409 — Student with this email already exists |
| enrollments_course_id_student_id_key | 409 — Student is already enrolled in this course |
| enrollments_course_id_fkey | 404 — Course not found |
| enrollments_student_id_fkey | 404 — Student not found |

Короткое имя и неправильный email отклоняет Pydantic с 422. Неизвестное
нарушение БД повторно поднимается как ошибка сервера 500, а не маскируется
под ошибку клиента. После IntegrityError сессия явно откатывается.

## Миграции

История: `<base> → 0001 → 0002 (head)`.
0001 создаёт три таблицы, ограничения, identity-колонки и индекс student_id.
0002 добавляет обязательный level в три шага, сохраняя существующие строки.

| Команда | Действие |
|---|---|
| `alembic upgrade head` | Применить недостающие миграции |
| `alembic downgrade -1` | Откатить последнюю миграцию; при откате 0002 значения level теряются |
| `alembic current` | Показать версию базы |
| `alembic history` | Показать цепочку миграций |
| `alembic heads` | Показать конечные ревизии; в проекте одна — 0002 |
| `alembic revision --autogenerate -m "text"` | Составить черновик по различиям моделей и базы |
| `alembic check` | Проверить наличие автоматически определяемых различий |
| `alembic upgrade 0001:0002 --sql` | Напечатать SQL второй миграции без выполнения |
| `alembic stamp head` | Только отметить последнюю версию; допустимо, если схема уже точно ей соответствует |

Команды также доступны через `python -m alembic`. Alembic берёт адрес из
config.py, поэтому в alembic.ini нет пароля. env.py импортирует модели,
передаёт Base.metadata и использует NullPool. Проверяются типы и серверные
значения по умолчанию. Autogenerate всегда требует чтения результата:
он не знает, как заполнить новые столбцы существующих строк.

SQL второй миграции проверен до применения:

```sql
ALTER TABLE courses ADD COLUMN level TEXT;
UPDATE courses SET level = CASE
    WHEN is_elective THEN 'beginner' ELSE 'intermediate' END;
ALTER TABLE courses ALTER COLUMN level SET NOT NULL;
```

Все три шага выполняются в одной транзакции. Downgrade удаляет level;
повторный upgrade заполняет его по исходному правилу. Пользовательские изменения
уровней таким циклом не восстанавливаются.

## Журнал экспериментов

Эксперименты выполнены 29 октября 2026 года на отдельном учебном сервере
PostgreSQL 18.6. После каждого изменения исходный код и структура восстановлены.

| № | Эксперимент | Наблюдение | Причина | Исправление |
|---|---|---|---|---|
| 1 | Изменён шаблон uq | В моделях: enrollments_course_id_unique, students_email_unique; в БД: enrollments_course_id_student_id_key, students_email_key | Шаблон использует один столбец и суффикс unique | Возвращён `%(table_name)s_%(column_0_N_name)s_key`; check_models снова выводит none дважды |
| 2 | Убрано min_length, имя N | HTTP 500 Internal Server Error; строка не добавлена | CHECK students_name_check защищает данные, но не входит в словарь ожидаемых ошибок API | Возвращён Field(min_length=2); API отвечает 422 |
| 3 | students_email_key заменено на students_email_uniq | Повтор email дал HTTP 500 вместо 409 | Реальное имя ограничения отсутствует в словаре | Исправлено имя; повторный запрос даёт 409 |
| 4 | У title снят NOT NULL, затем тип заменён на varchar(100) | alembic check завершился ошибкой: modify_nullable, затем modify_type | Ручная правка БД расходится с моделями | Возвращены NOT NULL и text; check чистый |
| 5 | Автоматическая 0002 добавляет TEXT NOT NULL к заполненной таблице | NotNullViolation: column "level" ... contains null values; версия осталась 0001 | Существующим строкам нечего записать в новый обязательный столбец | Добавление nullable → UPDATE → SET NOT NULL; upgrade проходит |
| 6 | Закомментирован import models в env.py | Сгенерированная 0003_oops предлагает drop_table для всех трёх таблиц | Base.metadata пустая, Alembic считает таблицы лишними | Опасная миграция не применялась; файл удалён, импорт возвращён |
| 7 | В Student добавлено phone без миграции | alembic check: New upgrade operations detected, add_column students.phone | Модель описывает отсутствующий столбец | Экспериментальное поле удалено; check снова чистый |
| 8 | Созданы 0003 и 0004 от 0002 | heads показал две вершины; upgrade head: Multiple head revisions are present | История разветвилась, head неоднозначен | Создана merge-ревизия 0005 с двумя родителями; затем все три учебных файла удалены без применения, осталась одна head 0002 |

Дополнительно неправильный пароль дал OperationalError с сообщением
`password authentication failed for user "catalog_app"`; после восстановления
адреса подключение успешно. SQL_ECHO показал BEGIN, запросы и ROLLBACK для
чтения; постоянное журналирование параметров по умолчанию выключено.

При попытке применить 0001 поверх существующих таблиц получена DuplicateTable:
`relation "courses" already exists`; транзакция DDL откатилась. После проверки
схемы применён stamp 0001. На пустой базе, напротив, успешно выполнен upgrade.

Итоговая проверка включает запуск с нуля, повторный seed.sql, цикл
upgrade → downgrade → upgrade, совпадение моделей и БД, один head и пять
ожидаемых ответов try_errors.py. Автоматические тесты: **22 passed**. Проверены фильтры, страницы, сортировка,
контракт JSON, ограничения, восстановление сессии после ошибки, CORS и
каскадное удаление при загруженных связях.

Реальный HTTP-сервер запущен, получил два лайка (11 → 13), нового студента и
запись, затем был остановлен и запущен повторно. После перезапуска сохранились
13 лайков, студент и запись. Дополнительно 10 параллельных запросов лайка
увеличили счётчик с 13 до 23 без потери обновлений. Скрипт try_errors.py через
HTTP подтвердил `5 of 5 as expected`. После проверки seed.sql восстановил
6 / 3 / 6 строк и исходные лайки.

## Принятые решения

- SQLSTATE 23505 одинаков для разных нарушений уникальности, поэтому точный
  ответ выбирается по имени ограничения. INSERT и COMMIT проверяют реальное
  состояние БД; предварительный SELECT не защищает от конкурирующей вставки
  между проверкой и сохранением.
- Лайк увеличивается одной командой `UPDATE ... SET likes = likes + 1`.
  Блокировка строки и вычисление на стороне БД сохраняют оба одновременных
  изменения; схема «прочитать, прибавить в Python, записать» может потерять лайк.
- Новое обязательное поле добавляется в три шага, потому что существующим
  строкам сначала нужны значения. Решение beginner/intermediate относится
  к данным и не может быть автоматически выведено из структуры модели.
- У связей задано `passive_deletes="all"`: RESTRICT и CASCADE полностью
  выполняет PostgreSQL даже для уже загруженной коллекции дочерних объектов.
  ORM не пытается заменить обязательный внешний ключ на NULL.

## Самопроверка миграции 0002

| Критерий | Результат |
|---|---|
| Цель и шаги | Да: одно изменение — level; nullable, заполнение, NOT NULL |
| Данные | Да: все шесть строк сохранены; два beginner и четыре intermediate |
| Переименования и удаления | Да: upgrade ничего не удаляет и не переименовывает; downgrade удаляет только level |
| Откат | Да: downgrade работает, но удаляет значения level; для рабочей базы необходим план восстановления пользовательских значений |
| Проверка | Да: просмотрен SQL, выполнен цикл отката и повторного применения, alembic check чистый |
| История | Да: одна head 0002; модель, схема ответа, фильтр, seed и миграция в одном коммите |
| Приложение | Да: level возвращается в JSON и используется в фильтре; начальные данные обновлены; studentId заменяет studentName |

Документация: [SQLAlchemy relationships](https://docs.sqlalchemy.org/en/21/orm/cascades.html),
[Alembic autogenerate](https://alembic.sqlalchemy.org/en/latest/autogenerate.html).
