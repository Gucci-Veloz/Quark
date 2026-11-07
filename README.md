# QUARK

Una API construida con FastAPI que funciona como memoria estructurada, utilizando ChromaDB como base de datos vectorial para organizar información por relevancia semántica. Los metadatos estructurados (usuarios, API keys, perfiles) viven en una base SQL gestionada con SQLAlchemy y migrada con Alembic.

## Módulos

1. **Módulo de Identidad y Psicología**: Almacena información sobre perfil cognitivo y estrategias mentales.
2. **Módulo de Negocios y Estrategia**: Guarda ideas, decisiones y planes de acción.
3. **Módulo de Recordatorios y URLs**: Almacena enlaces y tareas importantes.
4. **Módulo de Conexiones Inteligentes**: Establece relaciones entre diferentes piezas de información.
5. **Módulo de Aprendizajes y Reflexiones**: Almacena lecciones y conocimientos adquiridos.
6. **Módulo de Priorización y Filtrado**: Gestiona la relevancia y prioridad de la información.
7. **Módulo de Sugerencias Inteligentes**: Proporciona ideas y conexiones no evidentes.
8. **Módulo de Acceso Externo**: API específica para el acceso de aplicaciones externas a QUARK.

## Requisitos

- Python 3.12 (obligatorio)
- FastAPI
- ChromaDB
- SQLAlchemy y Alembic
- Otras dependencias en `requirements.txt`

## Instalación

```bash
# Clonar el repositorio
git clone <url-del-repositorio>
cd <nombre-del-repositorio>

# Crear entorno virtual con Python 3.12
python3.12 -m venv .venv
source .venv/bin/activate  # En Windows: .venv\Scripts\activate

# Instalar dependencias
pip install -r requirements.txt

# Configurar variables de entorno
cp .env.example .env
# Editar .env: ADMIN_PASSWORD, AUTH_SECRET_KEY (>=32 caracteres) y DATABASE_URL

# Aplicar migraciones de la base SQL (Alembic)
make migrate        # equivale a: alembic upgrade head

# Crear el admin inicial y la primera API key (idempotente)
make bootstrap      # equivale a: python -m app.cli bootstrap
```

El comando `python -m app.cli bootstrap` crea el usuario admin (`ADMIN_USERNAME`, por defecto `admin`, con la contraseña `ADMIN_PASSWORD`) y emite una API key para el tenant `default`. La key se muestra una única vez: guárdala en un gestor de secretos. Opciones: `--rotate-key` rota la API key y `--reset-admin-password` restablece la contraseña del admin.

## Ejecución

```bash
# Usando uvicorn directamente
uvicorn app.main:app --reload

# Usando el Makefile
make run
```

## Pruebas

El proyecto incluye pruebas automatizadas para verificar su funcionamiento:

```bash
# Ejecutar todas las pruebas
pytest

# Ejecutar pruebas con cobertura
make test-cov

# Ejecutar pruebas específicas
pytest tests/test_api.py -v

# Ejecutar pruebas con marcadores específicos
pytest -m auth
pytest -m api
```

## Documentación QUARK

Una vez que la aplicación esté en ejecución, puedes acceder a la documentación Swagger UI en:

```
http://localhost:8000/docs
```

Las rutas públicas son solo `/docs`, `/openapi.json`, `/redoc` y `POST /token`. Todos los demás endpoints exigen autenticación.

## Seguridad

Todos los routers de negocio exigen autenticación (dependencia `validate_access`). Hay dos mecanismos:

1. **API Key**: cabecera `X-API-Key`. Se valida por hash SHA-256 contra la tabla `api_keys` (solo activas). Es la vía para integraciones y aplicaciones externas.
2. **JWT**: cabecera `Authorization: Bearer <token>`, obtenido en `POST /token`. El usuario (`sub`) debe existir y estar activo en la tabla `users`.

Cada credencial lleva un tenant y unos scopes: `read` para consultas y `write` para escrituras.

Para obtener un token JWT (sustituye los valores por los tuyos; no se usan credenciales por defecto):

```bash
curl -X POST "http://localhost:8000/token" \
     -H "Content-Type: application/x-www-form-urlencoded" \
     -d "username=<ADMIN_USERNAME>&password=<ADMIN_PASSWORD>"
```

Para llamar a un endpoint con API Key:

```bash
curl "http://localhost:8000/external/collections" \
     -H "X-API-Key: <tu-api-key>"
```

## Acceso externo a QUARK

El módulo de acceso externo proporciona los siguientes endpoints para aplicaciones externas:

- `/external/query`: Consultas semánticas
- `/external/store`: Almacenamiento de datos
- `/external/update/{collection_key}/{item_id}`: Actualización de datos
- `/external/delete/{collection_key}/{item_id}`: Eliminación de datos
- `/external/collections`: Listado de colecciones disponibles
- `/external/batch`: Operaciones por lotes
- `/external/consolidate`: Consolidación de datos de múltiples colecciones

## Embeddings

El modelo de embeddings es `intfloat/multilingual-e5-base` (variable `EMBEDDING_MODEL`). Los textos se indexan con el prefijo `passage: ` y las consultas con `query: `. La primera ejecución descarga el modelo (~1.1 GB).

## Docker

La aplicación puede ejecutarse en Docker (imagen base `python:3.12-slim`):

```bash
# Construir la imagen
make docker-build

# Ejecutar el contenedor
make docker-run

# Usando docker-compose (publica solo 127.0.0.1:8020)
make docker-compose-up
```

## Despliegue en producción

El despliegue de producción es vía Coolify + Traefik en el VPS, no en Render. El procedimiento completo está en `docs/runbook.md` (§4): el contenedor debe tener `DATABASE_URL` y `ADMIN_PASSWORD` configurados en el panel, las migraciones aplicadas y, después, el bootstrap de credenciales:

```bash
docker compose exec quark python -m app.cli bootstrap
```

## Estructura del Proyecto Actualizada

```
.
├── app/
│   ├── __init__.py
│   ├── main.py
│   ├── cli.py
│   ├── config.py
│   ├── database.py
│   ├── sql.py
│   ├── models/
│   │   ├── __init__.py
│   │   └── schemas.py
│   ├── modules/
│   │   ├── __init__.py
│   │   ├── identity.py
│   │   ├── business.py
│   │   ├── reminders.py
│   │   ├── connections.py
│   │   ├── learnings.py
│   │   ├── priorities.py
│   │   ├── suggestions.py
│   │   ├── profile.py
│   │   └── external.py
│   └── utils/
│       ├── __init__.py
│       ├── embeddings.py
│       ├── auth.py
│       └── logger.py
├── alembic/
├── tests/
│   ├── __init__.py
│   ├── conftest.py
│   └── test_api.py
├── data/
│   └── chroma/
├── docs/
│   ├── external_access.md
│   ├── specs.md
│   └── runbook.md
├── alembic.ini
├── .env.example
├── .env
├── requirements.txt
├── Dockerfile
├── docker-compose.yml
├── Makefile
├── pytest.ini
└── README.md
```
