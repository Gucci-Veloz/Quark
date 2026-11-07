# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Descripción general

QUARK es una API construida con FastAPI que actúa como memoria estructurada semántica: usa **ChromaDB** (base de datos vectorial persistida en disco) para guardar texto libre + metadatos y recuperarlos por similitud semántica en lugar de por consultas exactas. Sirve de backend de datos para aplicaciones externas, que consumen la API vía un módulo dedicado (`/external`). Todos los routers de negocio exigen autenticación (API Key o JWT).

## Comandos

```bash
make dev-install       # instala dependencias + herramientas de dev (pytest, flake8, black, isort, mypy)
make run                # uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
make migrate            # alembic upgrade head (aplica migraciones SQL)
make bootstrap          # python -m app.cli bootstrap (admin inicial + primera API key, idempotente)
make test                # pytest
make test-cov            # pytest --cov=app --cov-report=term --cov-report=html
make lint                 # flake8 + black --check + isort --check-only + mypy sobre app/ y tests/
make format               # black + isort (aplica cambios)
make docker-build / docker-run / docker-compose-up
```

Ejecutar un único test o módulo de tests:

```bash
pytest tests/test_api.py -v
pytest tests/test_api.py::test_external_query -v
pytest -m auth      # tests marcados como auth
pytest -m api       # tests marcados como api
```

Antes de correr la app localmente: `cp .env.example .env` y completar `ADMIN_PASSWORD` y `AUTH_SECRET_KEY` (ver variables abajo). Después, `make migrate` y `make bootstrap`. El bootstrap crea el admin (`ADMIN_USERNAME`, default `admin`) y emite una API key para el tenant `default`; la key se muestra una sola vez. Sin el bootstrap no hay credenciales válidas para usar la API.

## Arquitectura

### Patrón módulo → router → ChromaDB

Cada dominio de negocio vive en `app/modules/<nombre>.py` como un `APIRouter` independiente, incluido en `app/main.py`. Casi todos siguen el mismo patrón CRUD + búsqueda semántica sobre una única colección de ChromaDB:

- `POST /`      crea un item (genera un id, guarda `text` + `metadata` en la colección)
- `GET /`         lista items (algunos módulos filtran/paginan en memoria sobre `list_items`, no en ChromaDB)
- `GET /search`o `/buscar`  búsqueda semántica vía `db_manager.query_items` (embeddings + distancia coseno)
- `GET /{id}`, `PUT /{id}`, `DELETE /{id}`

`app/database.py` (`ChromaDBManager`, instancia global `db_manager`) es la única capa de acceso a ChromaDB: crea/obtiene colecciones definidas en `COLLECTIONS` (`app/config.py`) y expone `add_item`/`get_item`/`query_items`/`update_item`/`delete_item`/`list_items`. Los routers no hablan con ChromaDB directamente, siempre pasan por `db_manager`.

Los esquemas Pydantic de request/response viven todos centralizados en `app/models/schemas.py` (no hay un `schemas.py` por módulo); cada módulo tiene su propio `XxxItemCreate`/`XxxItemUpdate` con metadatos por defecto específicos del dominio (categoría, prioridad, tags, etc.).

**Los prefijos de router no son consistentes con los nombres de módulo/colección** — varios están en español y no coinciden con lo que documenta el README/`docs/api-overview.md`:

| Módulo (archivo/colección) | Prefijo real del router |
|---|---|
| `connections` | `/conexiones` |
| `learnings` | `/aprendizajes` |
| `priorities` | `/prioridad` |
| `suggestions` | `/sugerencias` |
| `identity`, `business`, `reminders`, `external` | coinciden con el nombre |

Tenerlo en cuenta al añadir tests o clientes: la ruta real puede no ser la que uno esperaría por el nombre del módulo.

### Base SQL y migraciones

`app/sql.py` define `engine`, `SessionLocal`, `Base`, los modelos `User`, `ApiKey` y `Profile`, y la dependencia `get_session()`. `DATABASE_URL` decide el motor: `sqlite:///./data/quark.db` en desarrollo y `postgresql://...` en producción. El esquema se versiona con **Alembic** (`alembic.ini` + `alembic/`); todo cambio de esquema se hace con una migración nueva, nunca tocando la base a mano. El tenant de cada dato está en metadata de ChromaDB y en las tablas SQL.

### Autenticación — todos los routers de negocio exigen auth

`app/utils/auth.py` expone `validate_access` (devuelve un `Principal` con `tenant_id`, `scopes`, `kind` y `subject`) y `require_scope(scope)` (403 si falta el scope). Los mecanismos son:

- **API Key**: cabecera `X-API-Key`. Se busca por `sha256(key)` en `api_keys` con `is_active=True`. Las keys nunca se guardan en claro.
- **JWT**: cabecera `Authorization: Bearer ...`, obtenido en `POST /token`, firmado con HS256 y `AUTH_SECRET_KEY`. El `sub` debe existir en `users` con `is_active=True`.

Los endpoints de lectura usan `require_scope("read")` y los de escritura `require_scope("write")`. Las rutas públicas son solo `/docs`, `/openapi.json`, `/redoc`, `/` (si existe) y `POST /token`. Si se agrega un endpoint nuevo, debe declarar su dependencia de auth explícitamente; no se asume protección heredada.

### Configuración (`app/config.py`)

Doble definición de settings: una clase `Settings(BaseSettings)` (pydantic-settings, lee `.env`) usada para host/puerto/CORS/admin_password, **y además** constantes sueltas a nivel de módulo (`CHROMA_DB_DIR`, `AUTH_SECRET_KEY`, `DATABASE_URL`, etc.) leídas con `os.getenv(...)` directamente. Los módulos importan mayormente las constantes sueltas, no `Settings`. Si se cambia una variable de entorno relevante hay que actualizarla en ambos sitios si aplica, y recordar que las constantes se evalúan al importar `app.config` — en tests, sobreescribir `os.environ["CHROMA_DB_DIR"]` solo funciona si se hace **antes** de que `app.database` (que instancia `db_manager` a nivel de módulo) sea importado por primera vez (ver `tests/conftest.py`, que fija `CHROMA_DB_DIR` vía fixture de sesión antes de importar `app.main`).

`ADMIN_PASSWORD` es obligatoria, sin default: la app no arranca sin ella. `AUTH_SECRET_KEY` debe ser una cadena aleatoria de al menos 32 caracteres. Ninguna credencial por defecto debe quedar en el código.

### Embeddings

El modelo es `intfloat/multilingual-e5-base` (`EMBEDDING_MODEL`, default en `app/config.py`). `app/utils/embeddings.py` antepone `"passage: "` al indexar y `"query: "` al consultar. No usar `all-MiniLM-L6-v2` ni otro modelo.

### Testing

`tests/conftest.py` usa un directorio temporal para `CHROMA_DB_DIR` por sesión de tests (fixture `temp_chroma_dir`) y una base SQL temporal, de forma que los tests no tocan `data/` real. Los tests de `test_api.py` usan marcadores `auth`/`api`/`integration` (definidos en `pytest.ini`) y ejercitan la API end-to-end vía `TestClient`, no mocks — las llamadas a `/external/*` generan embeddings reales con `sentence-transformers`, así que la primera ejecución puede tardar por la descarga/carga del modelo (`EMBEDDING_MODEL`, default `intfloat/multilingual-e5-base`).

### Logging

`app/utils/logger.py` reemplaza los métodos del logger estándar (`logger.info`, etc.) para aceptar un segundo argumento `context: dict` que se serializa a JSON y se anexa al mensaje — patrón usado en todo el código (`logger.info("mensaje", {"key": "value"})`), no es la firma estándar de `logging`. También registra un `LoggingMiddleware` global que loguea cada request/response con tiempo de proceso.

## Notas del repositorio

- Los specs OpenAPI legacy por método (`método_*.json`, nombres con tilde) viven únicamente en `methods/` — la copia duplicada en la raíz se eliminó (Fase 1 de escalamiento, ago 2026). No están referenciados por código ni por `docs/api-overview.md` (que apunta a `docs/methods/{GET,POST,PUT,DELETE}.md`, un tercer conjunto de docs en Markdown, no JSON); parecen specs manuales desactualizados (`servers.url` apunta a `api.quark.ai/v1`).
- `python-installer.exe` y `rustup-init.exe` se sacaron del working tree y quedaron en `.gitignore` (`*.exe`); seguían en el historial de git al momento de este cambio — no se reescribió el historial.
- La integración con Airtable y el despliegue en Render fueron retirados. El despliegue es vía Coolify (`docs/runbook.md` §4). La especificación vigente está en `docs/specs.md` y el procedimiento de instalación en `docs/runbook.md`.
