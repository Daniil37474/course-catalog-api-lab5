# Course Catalog API

Backend лабораторных работ 4–5 на FastAPI. Возвращает шесть курсов, фильтрует и сортирует их, принимает лайки и записи на курс. Frontend: https://github.com/Gisg22/course-catalog.

## Запуск

Python 3.10 или новее. Команды из корня проекта:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\fastapi.exe dev main.py --port 8000
```

На macOS/Linux: `python3 -m venv .venv`, `source .venv/bin/activate`, `pip install -r requirements.txt`, `fastapi dev main.py --port 8000`.

API: http://localhost:8000. Swagger UI: http://localhost:8000/docs. Также доступны `/redoc` и `/openapi.json`. Frontend запускается по адресу **http://localhost:3000**.

## Маршруты и контракт

| Метод и путь | Результат |
| --- | --- |
| `GET /` | 200, сообщение о работе API |
| `GET /courses` | Шесть курсов, по убыванию likes |
| `GET /courses/{course_id}` | 200, курс; неизвестный id — 404 |
| `POST /courses/{course_id}/like` | 200, курс с увеличенным likes; неизвестный id — 404 |
| `POST /enrollments` | 201, запись с новым id; неизвестный курс — 404; неверные поля — 422 |
| `GET /enrollments` | 200, список записей |

Фильтры из лабораторной 4 сохранены: `is_elective`, `q`, `sort=popular|title`, `page` от 1, `page_size` от 1 до 100. Фильтрация и сортировка выполняются до пагинации. `?is_elective=true` возвращает два курса. Неизвестный параметр `?isElective=true` игнорируется и возвращает все шесть.

Python-модели используют snake_case. Общая модель `CamelModel` задаёт `alias_generator=to_camel`, `validate_by_name=True`, `validate_by_alias=True`; JSON и OpenAPI используют camelCase. Требуется Pydantic 2.11+.

Пример тела записи:

```json
{"courseId":"web-security","studentName":"Aigerim"}
```

Ответ 201:

```json
{"courseId":"web-security","studentName":"Aigerim","id":1}
```

Имя короче двух символов отклоняется со статусом 422 и `loc: ["body", "studentName"]`. `Content-Type` запроса должен быть `application/json`.

## CORS

Разрешён только `http://localhost:3000`, без завершающего слеша. Разрешены все методы и заголовки. Для разрешённого origin API возвращает `Access-Control-Allow-Origin`; чужой origin не получает этот заголовок. Preflight для JSON POST отвечает 200 и `Access-Control-Max-Age: 600`.

```powershell
curl.exe -i -X OPTIONS http://localhost:8000/enrollments -H "Origin: http://localhost:3000" -H "Access-Control-Request-Method: POST" -H "Access-Control-Request-Headers: content-type"
```

CORS не запрещает обработку простого запроса, а ограничивает доступ браузерного JavaScript к ответу. Server Components обращаются к API напрямую, без браузерной проверки CORS.

## Тесты

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

Проверяются исходные маршруты, поиск, фильтрация, сортировка, пагинация, модели, OpenAPI, CORS, preflight, лайки, запись, статусы 200/201/404/422 и оба варианта имён полей. Изменения данных в тестах восстанавливаются после каждого сценария.

Данные находятся в памяти. Перезапуск сервера сбрасывает лайки, записи и нумерацию. Это учебная реализация для одного процесса; постоянное хранение и авторизация не подключены.
