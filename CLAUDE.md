# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Descripción general

QUARK es una API construida con FastAPI que actúa como memoria estructurada semántica: usa **ChromaDB** (base de datos vectorial persistida en disco) para guardar texto libre + metadatos y recuperarlos por similitud semántica en lugar de por consultas exactas. Es el backend de datos para un asistente llamado **SofIA**, que consume la API vía un módulo dedicado (`/sofia`) protegido con API Key.

## Comandos

```bash
make dev-install       # instala dependencias + herramientas de dev (pytest, flake8, black, isort, mypy)
make run                # uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
make test                # pytest
make test-cov            # pytest --cov=app --cov-report=term --cov-report=html
make lint                 # flake8 + black --check + isort --check-only + mypy sobre app/ y tests/
make format               # black + isort (aplica cambios)
make docker-build / docker-run / docker-compose-up
```

Ejecutar un único test o módulo de tests:

```bash
pytest tests/test_api.py -v
pytest tests/test_api.py::test_sofia_query -v
pytest -m auth      # tests marcados como auth
pytest -m api       # tests marcados como api
```

Antes de correr la app localmente hace falta `cp .env.example .env` (ver variables abajo). Sin `AIRTABLE_API_KEY`/`AIRTABLE_BASE_ID` reales, cualquier endpoint de `/airtable` fallará al construir `AirtableManager` (instancia global creada al importar `app.modules.airtable`).

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
| `identity`, `business`, `reminders`, `airtable`, `sofia` | coinciden con el nombre |

Tenerlo en cuenta al añadir tests o clientes: la ruta real puede no ser la que uno esperaría por el nombre del módulo.

### Autenticación — solo `/sofia` está protegido

`app/utils/auth.py` define dos mecanismos: JWT (`Authorization: Bearer ...`, obtenido en `POST /token`) y API Key (`X-API-Key`, comparada contra `SOFIA_API_KEY`). `validate_access` acepta cualquiera de los dos.

Sin embargo, **de todos los routers, solo `sofia.router` declara `dependencies=[Depends(validate_access)]`**. Los routers de `identity`, `business`, `reminders`, `connections`, `learnings`, `priorities`, `suggestions` y `airtable` no exigen autenticación por sí mismos — quedan abiertos salvo que se les añada explícitamente. Si se agrega un endpoint nuevo en uno de esos módulos y se espera que quede protegido, hay que añadir la dependencia manualmente (como hace `sofia.py`), no asumir que hereda protección global.

### Configuración (`app/config.py`)

Doble definición de settings: una clase `Settings(BaseSettings)` (pydantic-settings, lee `.env`) usada para host/puerto/CORS/admin_password, **y además** constantes sueltas a nivel de módulo (`CHROMA_DB_DIR`, `AUTH_SECRET_KEY`, `SOFIA_API_KEY`, etc.) leídas con `os.getenv(...)` directamente. Los módulos importan mayormente las constantes sueltas, no `Settings`. Si se cambia una variable de entorno relevante hay que actualizarla en ambos sitios si aplica, y recordar que las constantes se evalúan al importar `app.config` — en tests, sobreescribir `os.environ["CHROMA_DB_DIR"]` solo funciona si se hace **antes** de que `app.database` (que instancia `db_manager` a nivel de módulo) sea importado por primera vez (ver `tests/conftest.py`, que fija `CHROMA_DB_DIR` vía fixture de sesión antes de importar `app.main`).

`AUTH_SECRET_KEY` y `admin_password` tienen defaults inseguros hardcodeados (`insecure_default_key_change_in_production`, `sofia2023`) pensados solo para desarrollo local.

### Integración con Airtable

`app/utils/airtable.py` (`AirtableManager`, instancia global `airtable_manager`) sincroniza items de ChromaDB hacia/desde una tabla de Airtable, aplanando `metadata` a campos `metadata_<key>` (los valores dict/list se serializan como string porque Airtable no acepta anidamiento). El router `airtable.py` expone tanto sincronización explícita (`/airtable/sync/{collection_key}/{item_id}`, `/airtable/sync-from-airtable/...`) como un CRUD que escribe en ambos sistemas a la vez.

### Testing

`tests/conftest.py` fuerza `SOFIA_API_KEY=test_sofia_api_key` y usa un directorio temporal para `CHROMA_DB_DIR` por sesión de tests (fixture `temp_chroma_dir`), de forma que los tests no tocan `data/chroma/` real. Los tests de `test_api.py` usan marcadores `auth`/`api`/`integration` (definidos en `pytest.ini`) y ejercitan la API end-to-end vía `TestClient`, no mocks — las llamadas a `/sofia/*` generan embeddings reales con `sentence-transformers`, así que la primera ejecución puede tardar por la descarga/carga del modelo (`EMBEDDING_MODEL`, default `all-MiniLM-L6-v2`).

### Logging

`app/utils/logger.py` reemplaza los métodos del logger estándar (`logger.info`, etc.) para aceptar un segundo argumento `context: dict` que se serializa a JSON y se anexa al mensaje — patrón usado en todo el código (`logger.info("mensaje", {"key": "value"})`), no es la firma estándar de `logging`. También registra un `LoggingMiddleware` global que loguea cada request/response con tiempo de proceso.

## Notas del repositorio

- Los specs OpenAPI legacy por método (`método_*.json`, nombres con tilde) viven únicamente en `methods/` — la copia duplicada en la raíz se eliminó (Fase 1 de escalamiento, ago 2026). No están referenciados por código ni por `docs/api-overview.md` (que apunta a `docs/methods/{GET,POST,PUT,DELETE}.md`, un tercer conjunto de docs en Markdown, no JSON); parecen specs manuales desactualizados (`servers.url` apunta a `api.quark.ai/v1`).
- `python-installer.exe` y `rustup-init.exe` se sacaron del working tree y quedaron en `.gitignore` (`*.exe`); seguían en el historial de git al momento de este cambio — no se reescribió el historial.
