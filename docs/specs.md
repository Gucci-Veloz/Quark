# Quark — Especificación Técnica del Sistema

>[!tip] Documento normativo para agentes. 
> Describe el sistema a construir y operar.
> Contiene únicamente especificaciones, instrucciones y criterios de aceptación.

---

## 1. Definición del sistema

Quark es una API de memoria persistente para agentes de IA. Almacena información en colecciones semánticas y la recupera por similitud vectorial y filtros de metadata. Se expone por REST y, en una fase posterior, por un servidor MCP.

## 2. Stack obligatorio

| Componente                 | Especificación                                           |
| -------------------------- | -------------------------------------------------------- |
| Lenguaje                   | Python 3.12                                              |
| Framework                  | FastAPI + uvicorn                                        |
| Vector store               | ChromaDB (`PersistentClient`)                            |
| Base de datos estructurada | SQLAlchemy + SQLite (desarrollo) / Postgres (producción) |
| ORM/migraciones            | SQLAlchemy + Alembic                                     |
| Modelo de embeddings       | `intfloat/multilingual-e5-base`                          |
| Contenedores               | Docker + docker-compose                                  |
| OS de referencia           | Ubuntu 24.04.5 LTS                                       |
| Despliegue producción      | VPS Hetzner vía Coolify + Traefik                        |
| Dominio producción         | `https://quark.vutik.online`                             |

Restricciones:

- NO usar bases de datos de grafos.
- NO usar `all-MiniLM-L6-v2` ni ningún modelo distinto al especificado.
- NO usar `bcrypt>=4.1` (rompe `passlib`); usar `bcrypt==4.0.1`.
- NO existe módulo Airtable.
- NO publicar puertos en `0.0.0.0` en el VPS; el acceso público es solo vía Traefik (80/443).

## 3. Estructura de datos

### 3.1 Colecciones ChromaDB

| Clave         | Nombre de colección     |
| ------------- | ----------------------- |
| `identity`    | `identity_psychology`   |
| `business`    | `business_strategy`     |
| `reminders`   | `reminders_urls`        |
| `connections` | `smart_connections`     |
| `learnings`   | `learnings_reflections` |
| `priorities`  | `priority_filtering`    |
| `suggestions` | `smart_suggestions`     |

### 3.2 Metadata obligatoria en todo documento

Todo documento almacenado en cualquier colección DEBE incluir en su metadata:

- `tenant_id` (string, obligatorio; valor por defecto en esta etapa: `"default"`)
- `created_at` (ISO 8601)
- `updated_at` (ISO 8601)

Toda operación de lectura/escritura DEBE filtrar por `tenant_id` mediante un wrapper central; el filtro se inyecta en el servidor y nunca se acepta desde el cliente.

### 3.3 Documentos de la colección `connections`

Además de la metadata obligatoria, incluyen:
- `source_id` (string): ID del documento origen
- `target_id` (string): ID del documento destino
- `relation_type` (string): tipo de relación
- `collection_ref` (string): colección del documento relacionado
- `timestamp` (ISO 8601)

### 3.4 Tablas SQL

- `users`: `id`, `username`, `hashed_password`, `scopes`, `created_at`, `is_active`
- `api_keys`: `id`, `key_hash`, `tenant_id`, `scopes`, `is_active`, `created_at`
- `profiles`: `id`, `tenant_id`, `key`, `value`, `updated_at` — hechos estructurados y preferencias de largo plazo

## 4. Autenticación

- JWT firmado con `AUTH_SECRET_KEY` (algoritmo `HS256`); el token se verifica contra la tabla `users`.
- API keys por cliente almacenadas hasheadas en `api_keys`; cada key resuelve su `tenant_id` y scopes en el middleware de auth.
- No existe una API key global hardcodeada.
- Header de la API key: `X-API-Key`.

### 4.1 Algoritmos de hash

- Passwords (`users.hashed_password`): bcrypt vía `passlib` (`CryptContext(schemes=["bcrypt"])`, `bcrypt==4.0.1`, ver §2). El hash bcrypt incluye su propia sal.
- API keys (`api_keys.key_hash`): SHA-256 en hexadecimal (64 caracteres) de la key completa, con índice único sobre `key_hash` para resolver la key con un solo lookup. No lleva sal porque la key tiene 256 bits aleatorios generados con `secrets`; no es adivinable por diccionario. No usar bcrypt para API keys: obligaría a comparar fila por fila.
- Formato de API key: `qk_` + `secrets.token_urlsafe(32)`.
- En ninguna tabla, log ni salida de la app se guarda o se imprime un password o una API key en claro. La única excepción es la salida del comando de bootstrap (§4.2), una sola vez.

### 4.2 Bootstrap de credenciales (admin inicial y primera API key)

- Mecanismo: comando CLI `python -m app.cli bootstrap`, implementado en `app/cli.py`. En el VPS se ejecuta dentro del contenedor: `docker compose exec quark python -m app.cli bootstrap`.
- Es el único camino para crear el admin inicial y la primera API key. La app NO los crea al arrancar, para que ninguna key en claro termine en los logs del servidor.
- Requisitos previos: `alembic upgrade head` aplicado. Lee `DATABASE_URL`, `ADMIN_PASSWORD` y `ADMIN_USERNAME` (§6). Si falta `ADMIN_PASSWORD` o `DATABASE_URL`, o las tablas no existen, termina con código ≠ 0 sin escribir nada.
- Acciones, dentro de una sola transacción:
  1. Admin: si no existe un usuario con `username = ADMIN_USERNAME`, lo crea con `hashed_password = bcrypt(ADMIN_PASSWORD)`, `scopes = ["read", "write", "admin"]` e `is_active = true`.
  2. Primera API key: si no existe ninguna key con `is_active = true` para `tenant_id = "default"`, genera una con `scopes = ["read", "write"]` (sin `admin`, por menor privilegio) y guarda solo su `key_hash`.
- Idempotencia:
  - Si el admin ya existe, no lo duplica ni cambia su password, aunque `ADMIN_PASSWORD` haya cambiado.
  - Si ya hay una key activa para `default`, no emite otra.
  - Una segunda ejecución sin opciones no modifica la base y termina con código 0.
  - La unicidad de `users.username` y de `api_keys.key_hash` está garantizada por constraints de la base, no solo por el código.
- Rotación, solo con opción explícita:
  - `--rotate-key`: pone `is_active = false` en las keys activas de `tenant_id = "default"` y emite una nueva. Las keys desactivadas no se borran.
  - `--reset-admin-password`: vuelve a hashear `ADMIN_PASSWORD` y lo guarda en el admin existente.
- Salida:
  - La API key en claro se imprime en stdout una sola vez, en la ejecución que la crea. Nunca se vuelve a mostrar ni se puede recuperar; si se pierde, se rota con `--rotate-key`.
  - El password nunca se imprime.
  - Los mensajes informativos van a stderr con prefijo `[bootstrap]`.
- Códigos de salida: `0` si terminó bien (haya creado algo o no); `≠ 0` ante cualquier error, en cuyo caso no deja escrituras parciales.

## 5. Embeddings

- Modelo: `intfloat/multilingual-e5-base` (~1.1 GB de descarga en primer uso).
- Los modelos E5 requieren prefijos obligatorios para rendir correctamente:
- Documentos almacenados: prefijo `"passage: "` antes del texto.
- Consultas: prefijo `"query: "` antes del texto.
- `app/utils/embeddings.py` DEBE implementar una función de embedding que aplique estos prefijos; `SentenceTransformerEmbeddingFunction` de ChromaDB no los añade por sí sola. Implementar un wrapper (clase o función compatible con la interfaz de embedding de ChromaDB) que anteponga el prefijo correspondiente según se indexen documentos o se ejecuten queries.

## 6. Variables de entorno

| Variable                      | Obligatoria     | Descripción                                                   |
| ----------------------------- | --------------- | ------------------------------------------------------------- |
| `ADMIN_PASSWORD`              | Sí, sin default | Password del admin inicial; sin ella la app no arranca. La usa `python -m app.cli bootstrap` (§4.2) |
| `ADMIN_USERNAME`              | No              | Default `admin`. Username del admin que crea el bootstrap (§4.2) |
| `AUTH_SECRET_KEY`             | Sí              | Cadena aleatoria ≥32 caracteres                               |
| `DATABASE_URL`                | Sí              | `sqlite:///./data/quark.db` (dev) / `postgresql://...` (prod) |
| `CHROMA_DB_DIR`               | No              | Default `./data/chroma`                                       |
| `EMBEDDING_MODEL`             | No              | Default `intfloat/multilingual-e5-base`                       |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | No              | Default `30`                                                  |

## 7. Endpoints

- Módulos: `identity`, `business`, `reminders`, `connections`, `learnings`, `priorities`, `suggestions`, `external`, `profile`.
- `profile`: CRUD sobre la tabla `profiles` (`GET/POST/PUT/DELETE /profile/*`).
- `/external/*`: `query`, `store`, `update/{collection_key}/{item_id}`, `delete/{collection_key}/{item_id}`, `collections`, `batch`, `consolidate` — todos con resolución de `tenant_id` por API key.

## 8. Cambios requeridos en archivos del repo

| Archivo | Cambio |
|---|---|
| `runtime.txt` | Reemplazar `python-3.9` por `python-3.12` |
| `requirements.txt` | Eliminar dependencias de Airtable; añadir `sqlalchemy` y `alembic`; mantener `bcrypt==4.0.1` |
| `app/config.py` | Cambiar default de `EMBEDDING_MODEL` a `intfloat/multilingual-e5-base` (líneas 43 y 66); añadir `DATABASE_URL` a `Settings` |
| `app/utils/embeddings.py` | Implementar wrapper de embedding con prefijos E5 (`"passage: "` / `"query: "`) según §5 |
| `app/utils/auth.py` | Eliminar comparación con `QUARK_API_KEY`; reemplazar por lookup de key hasheada en tabla `api_keys` con resolución de `tenant_id` y scopes; verificar JWT contra tabla `users` |
| `app/cli.py` | Crear comando `python -m app.cli bootstrap` (admin inicial + primera API key, idempotente, opciones `--rotate-key` y `--reset-admin-password`) según §4.2 |
| `alembic/` (migración de auth) | Índice único en `users.username` y en `api_keys.key_hash` (§4.2) |
| `app/database.py` | Añadir wrapper que inyecte `tenant_id` en metadata de escrituras y en filtro `where` de todas las queries |
| `app/modules/airtable.py` | Eliminar archivo completo |
| `app/main.py` | Eliminar `app.include_router(airtable.router)`; añadir router de `profile` |
| `app/modules/profile.py` | Crear módulo nuevo con CRUD sobre tabla `profiles` |
| `alembic/` + `alembic.ini` | Crear configuración de migraciones con las tablas `users`, `api_keys`, `profiles` |
| `.env.example` | Eliminar variables `AIRTABLE_*`; añadir `DATABASE_URL` y `ADMIN_USERNAME` (comentada, default `admin`); actualizar `EMBEDDING_MODEL` |
| `docker-compose.yml` | Añadir `ADMIN_PASSWORD`, `AUTH_SECRET_KEY`, `DATABASE_URL`; cambiar `EMBEDDING_MODEL`; mapear puerto `127.0.0.1:8020:8000` |
| `render.yaml` | Eliminar archivo (el despliegue es vía Coolify, no Render) |
| `CLAUDE.md` | Actualizar referencias al modelo de embeddings y eliminar menciones a Airtable |

## 9. Despliegue producción (VPS)

- Dominio: `https://quark.vutik.online` enrutado por Traefik (coolify-proxy) al contenedor.
- Puerto: el contenedor escucha en `8000` interno; el host publica únicamente `127.0.0.1:8020`. NO publicar en `0.0.0.0`.
- Puertos prohibidos en el VPS: `8000` (panel Coolify), `8080`, `3000`, `3001`, `8010`, `18789`, `18790`, `3978`, rango efímero `32768–60999`.
- Postgres como servicio gestionado por Coolify o contenedor; `DATABASE_URL` apunta a él.
- Volumen persistente `./data` para ChromaDB y la base SQL; incluir en backups.
- Verificar ≥2 GB RAM libres antes del deploy.

## 10. Fases de construcción

### Fase 0 — Base operativa

- [ ] Ejecutar todos los cambios de §8
- [ ] Wrapper `tenant_id` operativo en todas las lecturas/escrituras
- [ ] Wrapper de prefijos E5 operativo en indexación y queries
- [ ] Comando `python -m app.cli bootstrap` operativo e idempotente según §4.2, ejecutado antes de cualquier verificación autenticada
- [ ] Verificación end-to-end según §12

### Fase 1 — Despliegue producción

#### Bloque 1.0 — Endurecimiento de seguridad (obligatorio, antes de cualquier deploy)

Origen: revisiones de seguridad del PR #1 (2026-11-07). Varios ítems son hallazgos de seguridad, no solo mejoras de rendimiento o despliegue. Ningún deploy a producción procede hasta cerrar este bloque.

- [ ] **DoS (Media):** acotar `n_results`/`limit` con `le=100` en `/external/batch` y `/external/consolidate` (`app/modules/external.py`); tope de ~50 operaciones por batch; eliminar `list_items(limit=None)` donde no haga falta (`app/database.py`); en `/prioridad/optimizar` calcular cada embedding una sola vez en vez de por par (`app/modules/priorities.py`); quitar el `embed_passages` sin uso de `/sugerencias` (`app/modules/suggestions.py`).
- [ ] **`.dockerignore` (Media):** excluir `.env*` (salvo `.env.example`), `data/`, `logs/`, `.git/`, `.venv/`, `*.db`, `tests/`, `.pytest_cache`, notas locales. Hoy `COPY . .` mete secretos y datos en la imagen.
- [ ] **CORS (Media):** default sin `*`; `ALLOWED_ORIGINS` explícito en producción; `allow_credentials=False` salvo necesidad; métodos y headers explícitos (`app/config.py`, `app/main.py`).
- [ ] **Datos sensibles en logs (Media):** `LoggingMiddleware` registra solo `request.url.path` (sin query string); no registrar el `username` de logins fallidos en claro (`app/utils/logger.py`, `app/main.py`).
- [ ] **Login y contraseñas (Baja):** rate limit en `POST /token` (app o proxy Traefik); `min_length=12` en `ADMIN_PASSWORD` y rechazo de placeholders `your_*` en el bootstrap; `.env.example` sin valores de ejemplo usables.
- [ ] **JWT (Baja):** `jwt.decode(..., options={"require_exp": True})`; claim `iat` e invalidación de tokens emitidos antes de un cambio de contraseña (`app/utils/auth.py`, `app/cli.py`).
- [ ] **Errores 500 (Baja):** respuesta genérica sin `str(e)`; filtros `where` inválidos → 400; detalle solo en el log. El handler de `HTTPException` debe propagar `exc.headers` (`WWW-Authenticate`) (`app/main.py`).
- [ ] **Umbrales de similitud E5 (Media, funcional):** recalibrar `min_similarity` y cortes de duplicados/merge (`connections.py`, `suggestions.py`, `priorities.py`), calibrados para MiniLM; con E5 casi todo supera 0.7.
- [ ] **CI (Baja):** el workflow `Test and Deploy` está deshabilitado en GitHub (`gh workflow disable`, 2026-11-07) para que el merge no dispare el deploy obsoleto a Render. Antes de rehabilitarlo: eliminar el job `deploy` de `.github/workflows/test-and-deploy.yml` y pasar la matriz a Python 3.12 con `ADMIN_PASSWORD`, `AUTH_SECRET_KEY` y `DATABASE_URL` de test. Subir ese cambio requiere un token de `gh` con scope `workflow`.
- [ ] **Credenciales de producción:** valores nuevos y aleatorios para `ADMIN_PASSWORD`, `AUTH_SECRET_KEY` y Postgres; nunca reutilizar defaults del historial público (p. ej. la contraseña y la secret por defecto de versiones anteriores de `app/config.py`).
- [ ] **Menores:** validar `tenant_id` e ids de item con `^[a-z0-9_-]+$` (evita colisiones `<tenant>:<id>`); `USER` no root en el Dockerfile; `validate_access` como `def` para no bloquear el event loop; error 422 (no 404) ante `metadata` no dict en `PUT /external/update`; deshabilitar `/docs` y `/openapi.json` en producción si se decide; `pip-audit` con red.

#### Bloque 1.1 — Despliegue

- [ ] Dockerfile con Python 3.12 y pre-descarga del modelo en el build
- [ ] Deploy vía Coolify desde el repo Git con docker-compose
- [ ] DNS/dominio `quark.vutik.online` configurado en Traefik con HTTPS
- [ ] Postgres productivo + `DATABASE_URL`
- [ ] Verificación end-to-end contra `https://quark.vutik.online`

### Fase 2 — Servidor MCP

- [ ] MCP server sobre `/external/*` con tools: `query`, `store`, `update`, `delete`, `list_collections`, `consolidate`
- [ ] Auth por API key en la configuración del cliente MCP
- [ ] Embebido en el proceso FastAPI

### Fase 3 — Multi-tenancy y monetización

- [ ] Onboarding: signup → emisión de API key → `tenant_id` propio
- [ ] Tests de aislamiento entre tenants
- [ ] Tabla `usage` en SQL: metering por API key (queries, stores, tokens de embedding)
- [ ] Stripe: planes, checkout, webhooks → activación/suspensión de keys
- [ ] Rate limiting por plan

## 11. Instalación local (referencia)

```

cd /home/gusta/Projects/Negocios
git clone https://github.com/Gucci-Veloz/Quark.git cd Quark
python3.12 -m venv venv
source venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
cp .env.example .env # editar con valores reales
mkdir -p data/chroma
alembic upgrade head
uvicorn app.main:app --host 0.0.0.0 --port 8000

```

## 12. Criterios de aceptación

- `GET /docs` devuelve Swagger UI.
- `GET /external/collections` con API key válida devuelve las 7 colecciones.
- `POST /external/store` + `POST /external/query` recuperan un documento por similitud semántica.
- Todo documento almacenado contiene `tenant_id`, `created_at`, `updated_at` en metadata.
- Los documentos de `connections` contienen `source_id`, `target_id`, `relation_type`, `collection_ref`, `timestamp`.
- Un request sin API key válida es rechazado (Fase 0); una API key solo accede a datos de su `tenant_id` (se verifica con los tests de aislamiento de Fase 3).
- `alembic upgrade head` crea `users`, `api_keys`, `profiles` sin errores.
- La app arranca solo si `ADMIN_PASSWORD`, `AUTH_SECRET_KEY` y `DATABASE_URL` están definidas.
- Bootstrap, primera ejecución de `python -m app.cli bootstrap` sobre una base recién migrada:
  - Termina con código 0.
  - Crea exactamente 1 fila en `users` (`ADMIN_USERNAME`, scopes `read,write,admin`) y 1 fila activa en `api_keys` (`tenant_id = "default"`, scopes `read,write`).
  - Imprime la API key en stdout una sola vez.
- Bootstrap, segunda ejecución sin opciones:
  - Termina con código 0 e imprime en stdout 0 bytes.
  - El conteo de filas de `users` y `api_keys` no cambia, y `users.hashed_password` tampoco.
- Bootstrap, `--rotate-key`: la key anterior queda con `is_active = false` y es rechazada (401); la nueva es aceptada.
- Ni `users.hashed_password` ni `api_keys.key_hash` contienen el valor en claro:
  - `hashed_password` empieza con `$2b$` (bcrypt).
  - `key_hash` es hexadecimal de 64 caracteres, igual a SHA-256 de la key.
  - La key en claro no aparece en los logs del servidor.
- La API key emitida por el bootstrap, enviada en el header `X-API-Key`, es aceptada por `GET /external/collections`.
- En producción: `https://quark.vutik.online/docs` responde vía HTTPS.

## 13. Errores conocidos

| Error                                                          | Causa                                                             | Solución                                                                        |
| -------------------------------------------------------------- | ----------------------------------------------------------------- | ------------------------------------------------------------------------------- |
| `ValidationError: admin_password Field required`               | `ADMIN_PASSWORD` ausente en `.env`                                | Definirla y reiniciar                                                           |
| Fallo de `pip` resolviendo `torch`                             | Python <3.11                                                      | Recrear venv con Python 3.12                                                    |
| `AttributeError: module 'bcrypt' has no attribute '__about__'` | `bcrypt>=4.1`                                                     | `pip install bcrypt==4.0.1`                                                     |
| Primera query lenta                                            | Descarga del modelo e5 (~1.1 GB)                                  | Esperar; verificar `~/.cache/huggingface`                                       |
| `401/403` en `/external/*`                                     | API key ausente o inválida                                        | Ejecutar `python -m app.cli bootstrap` (o `--rotate-key` si se perdió la key) y enviarla en el header `X-API-Key` |
| ChromaDB en ruta inesperada                                    | `CHROMA_DB_DIR` leída antes de cargar `.env`                      | Definirla antes del primer arranque; borrar el directorio erróneo               |
| Puerto 8020 no responde en VPS                                 | Traefik no enrutado o contenedor no publicado en `127.0.0.1:8020` | Verificar labels/config de Coolify y `docker ps`                                |