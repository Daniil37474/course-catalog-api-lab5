# Course Catalog API

Самостоятельный backend каталога курсов на FastAPI для лабораторной работы № 4: Pydantic, параметры запросов и зависимости Depends.

## Как запустить

Нужен Python 3.10 или новее. Все команды выполняются из папки, где находятся `main.py`, `models.py` и `data.py`: из корня отдельного репозитория `course-catalog-api` или из одноимённой папки проекта `course-catalog-lab1`.

Windows PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
fastapi dev main.py
```

Если PowerShell запрещает активацию, можно запустить всё напрямую, без изменения настроек системы:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\fastapi.exe dev main.py
```

macOS / Linux:

```sh
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
fastapi dev main.py
```

Сервер: http://127.0.0.1:8000. Интерактивная документация: http://127.0.0.1:8000/docs. Дополнительно доступны `/redoc` и `/openapi.json`. Если порт занят: `fastapi dev main.py --port 8001`.

В `/docs` раскройте маршрут, нажмите **Try it out**, заполните параметры и нажмите **Execute**. Страница показывает URL запроса, код и тело ответа.

Структура:

```text
course-catalog-api/
├── .gitignore
├── README.md
├── requirements.txt
├── models.py
├── data.py
├── main.py
└── tests/
    └── test_api.py
```

`Course` содержит обязательные `id`, `title`, `description`, `credits`, а также `is_elective=False` и `likes=0`. Шесть записей перенесены из исходного `lib/courses.ts`, включая его описания. В JSON используется `is_elective`. Данные хранятся в памяти; подключение Next.js к API предусмотрено в лабораторной № 5.

Сначала выполняются фильтрация и поиск, затем сортировка, затем выбор страницы. Функция `pagination` вычисляет `offset` и `limit` и передаётся в маршрут через `Depends(pagination)`. `get_all_courses` возвращает копию списка.

Дополнительно выполнены три бонусных задания: `sort` ограничен значениями `popular` и `title`; `page >= 1`, `1 <= page_size <= 100`; `q` ищет подстроку в названии без учёта регистра. В OpenAPI остаются ровно три GET-маршрута.

## Что проверено

Проверено на Python 3.12.14 и FastAPI 0.143.0. `fastapi dev main.py` запускается; `/docs` показывает три маршрута и схему `Course`. Через Swagger выполнен запрос второй страницы. Все 15 автоматических тестов проходят:

```sh
python -m unittest discover -s tests -v
python -m pip check
```

| Запрос | Результат |
| --- | --- |
| `/` | 200, `{"message":"Course Catalog API is running"}` |
| `/courses` | 6 курсов: ai-integration, modern-frontend, web-security, backend-fastapi, databases-postgresql, api-design |
| `/courses/web-security` | 200, объект курса Web Security Essentials |
| `/courses/nope` | 404, `{"detail":"Course not found"}` |
| `/courses?is_elective=true` | ai-integration, api-design |
| `/courses?is_elective=false` | modern-frontend, web-security, backend-fastapi, databases-postgresql |
| `/courses?sort=title` | ai-integration, api-design, backend-fastapi, modern-frontend, databases-postgresql, web-security |
| `/courses?page=1&page_size=2` | ai-integration, modern-frontend |
| `/courses?page=2&page_size=2` | web-security, backend-fastapi |
| `/courses?page=3&page_size=2` | databases-postgresql, api-design |
| `/courses?page=4&page_size=2` | 200, пустой список `[]` |
| `/courses?is_elective=false&sort=title&page=2&page_size=2` | databases-postgresql, web-security |
| `/courses?q=react` и `/courses?q=ReAcT` | modern-frontend |
| `/courses?q=api` | backend-fastapi, api-design |
| `/courses?q=unknown` | 200, пустой список `[]` |
| `/courses?q=api&sort=title&page=2&page_size=1` | backend-fastapi |
| `/courses?sort=banana` | 422, ошибка проверки сортировки |
| `/courses?page=0` | 422, номер страницы должен быть положительным |
| `/courses?page_size=1000` | 422, размер страницы не должен превышать 100 |
| `/docs`, `/redoc`, `/openapi.json` | 200, документация и схема API |

Тесты также проверяют значения модели по умолчанию, преобразование `credits="5"` в число, ошибку для `credits="five"`, использование зависимости пагинации и сохранность исходного списка после запросов. Окружение `.venv` и Python-кэш исключены из Git.
