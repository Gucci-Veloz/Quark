# Quark — Runbook de Instalación

> [!Tip] Documento operativo para agentes.
> - Describe cómo levantar Quark en un entorno limpio.
> - Contiene únicamente instrucciones y criterios de verificación.
> - Si un paso falla, consultar la sección 7 (Errores conocidos) antes de improvisar.

---

## 0. Precondición bloqueante

**NO ejecutar las secciones 3 y 4 (instalación, migraciones, arranque, despliegue) hasta que los cambios de arquitectura y de código de `specs.md` estén implementados en el repo**: todos los cambios de la §8 de `specs.md` y la Fase 0 de su §10 (wrapper `tenant_id`, wrapper de prefijos E5, auth por tabla `api_keys`, migraciones `alembic/`, eliminación de Airtable). Sin ellos, `alembic upgrade head` y el arranque fallan o producen un servicio inseguro.

Verificación de la precondición (ejecutar en la raíz del repo; todas deben cumplirse):

| # | Comando | Resultado esperado |
|---|---|---|
| 1 | `cat runtime.txt` | `python-3.12` |
| 2 | `test -f alembic.ini && test -d alembic && echo OK` | `OK` |
| 3 | `test ! -e app/modules/airtable.py && test ! -e render.yaml && echo OK` | `OK` |
| 4 | `test -f app/modules/profile.py && echo OK` | `OK` |
| 5 | `grep -ric airtable requirements.txt .env.example app/main.py` | `0` por cada archivo |
| 6 | `grep -c QUARK_API_KEY app/utils/auth.py` | `0` |
| 7 | `grep -n 'multilingual-e5-base' app/config.py` | al menos una coincidencia, sin `all-MiniLM` |

Si alguna falla: detenerse y completar primero lo indicado en `specs.md` §8.

## 1. Prerequisitos

- **Python 3.12** (obligatorio). Verificar: `python3.12 --version` → `Python 3.12.x`.
- **~5 GB de disco libres**: dependencias + modelo de embeddings (~1.1 GB).
- **Conexión a internet** en la instalación y primer arranque (descarga del modelo `intfloat/multilingual-e5-base`).
- **Docker + docker-compose** solo para despliegue en VPS (no requerido en desarrollo local).
- En Ubuntu, si `python3.12` no está disponible:

```
sudo apt update
sudo apt install -y python3.12 python3.12-venv python3.12-dev
```

## 2. Variables de entorno

Crear `.env` en la raíz del proyecto. Variables:

| Variable | Obligatoria | Valor / Descripción |
|---|---|---|
| `ADMIN_PASSWORD` | Sí, sin default | Password del admin inicial; sin ella la app NO arranca |
| `ADMIN_USERNAME` | No | Default `admin`. Username del admin que crea `python -m app.cli bootstrap` (§3.1 / §4.1) |
| `AUTH_SECRET_KEY` | Sí | Cadena aleatoria ≥32 caracteres |
| `DATABASE_URL` | Sí | `sqlite:///./data/quark.db` (dev) / `postgresql://user:pass@host:5432/quark` (prod) |
| `CHROMA_DB_DIR` | No | Default `./data/chroma` |
| `EMBEDDING_MODEL` | No | Default `intfloat/multilingual-e5-base` |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | No | Default `30` |

Ejemplo mínimo de `.env` para desarrollo:

```
ADMIN_PASSWORD=cambiar_por_password_seguro
AUTH_SECRET_KEY=cadena_aleatoria_de_al_menos_32_caracteres
DATABASE_URL=sqlite:///./data/quark.db
CHROMA_DB_DIR=./data/chroma
EMBEDDING_MODEL=intfloat/multilingual-e5-base
```

Restricción: NO existen variables de Airtable. Si `.env.example` las contiene, eliminarlas.

## 3. Secuencia de comandos (desarrollo local)

Ejecutar en orden:

```

cd /home/gusta/Projects/Negocios
git clone https://github.com/Gucci-Veloz/Quark.git
cd Quark
python3.12 -m venv venv
source venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
cp .env.example .env # editar con valores reales
mkdir -p data/chroma
alembic upgrade head
uvicorn app.main:app --host 0.0.0.0 --port 8000

```

Notas operativas:

- Si el repo es privado, usar SSH: `git clone git@github.com:Gucci-Veloz/Quark.git` (requiere llave SSH configurada en GitHub).
- `pip install` descarga ~2-3 GB (torch es el paquete más pesado). No interrumpir.
- `alembic upgrade head` crea las tablas `users`, `api_keys`, `profiles`. Debe ejecutarse antes del primer arranque.
- La primera query que use embeddings descarga el modelo (~1.1 GB); el arranque del servidor no lo descarga.

### 3.1 Bootstrap de credenciales (local)

Va después del arranque y antes de cualquier verificación autenticada (§5, puntos 3 y 4). Crea el admin inicial y la primera API key. Especificación completa: `specs.md` §4.2.

En una segunda terminal, con el venv activado y el mismo `.env`:

```
cd /home/gusta/Projects/Negocios/Quark
source venv/bin/activate
python -m app.cli bootstrap
```

Salida esperada en la primera ejecución (la key real es distinta en cada base):

```
[bootstrap] admin 'admin' creado (scopes: read,write,admin).
[bootstrap] API key creada para tenant_id=default (scopes: read,write).
qk_XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX
[bootstrap] Esta API key no se volverá a mostrar. Guárdala ahora.
```

- Copiar la línea `qk_...` (stdout) a un gestor de secretos. Se usa en el header `X-API-Key`.
- La base solo guarda su hash SHA-256: si se pierde, no se puede recuperar; hay que rotarla.

Segunda ejecución (prueba de idempotencia):

```
python -m app.cli bootstrap; echo "exit=$?"
```

Salida esperada: no imprime nada en stdout, no cambia la base y termina con código 0.

```
[bootstrap] admin 'admin' ya existe; sin cambios.
[bootstrap] ya existe una API key activa para tenant_id=default; no se emite otra (usar --rotate-key para rotarla).
exit=0
```

- Rotar la key (por ejemplo, si se perdió): `python -m app.cli bootstrap --rotate-key`. Desactiva las keys activas de `default` y muestra una nueva una sola vez.
- Cambiar el password del admin después de editar `ADMIN_PASSWORD` en `.env`: `python -m app.cli bootstrap --reset-admin-password`. Sin esta opción, un cambio en `.env` no modifica el password guardado.

## 4. Despliegue en VPS (producción)

- Dominio del servicio: `https://quark.vutik.online` (subdominio de `vutik.online`, enrutado por Traefik/coolify-proxy).
- `docker-compose.yml` debe incluir todas las variables obligatorias y el mapeo de puerto correcto:

```yaml
services:
  quark:
    build: .
    ports:
      - "127.0.0.1:8020:8000"
    volumes:
      - ./data:/app/data
    environment:
      - ADMIN_USERNAME=${ADMIN_USERNAME:-admin}
      - ADMIN_PASSWORD=${ADMIN_PASSWORD}
      - AUTH_SECRET_KEY=${AUTH_SECRET_KEY}
      - DATABASE_URL=${DATABASE_URL}
      - CHROMA_DB_DIR=/app/data/chroma
      - EMBEDDING_MODEL=intfloat/multilingual-e5-base
    restart: unless-stopped
```

### Reglas de puerto en el VPS:

- El contenedor escucha en `8000` interno; el host publica únicamente `127.0.0.1:8020`.
- NO publicar en `0.0.0.0`: el acceso público es solo vía Traefik (80/443).
- Puertos prohibidos: `8000` (panel Coolify), `8080`, `3000`, `3001`, `8010`, `18789`, `18790`, `3978`, rango efímero `32768–60999`.
- Deploy vía Coolify: conectar el repo Git, seleccionar docker-compose, definir las variables de entorno en el panel, asignar el dominio `quark.vutik.online` (HTTPS automático vía Traefik).
- Postgres en producción: servicio gestionado por Coolify o contenedor; apuntar `DATABASE_URL` a él.
- Verificar ≥2 GB RAM libres en el VPS antes del deploy (torch + sentence-transformers en runtime).
- El volumen `./data` persiste ChromaDB y la base SQL; incluir en backups.

### 4.1 Bootstrap de credenciales (VPS)

Va después de que el contenedor esté arriba con las migraciones aplicadas, y antes de cualquier verificación autenticada contra `https://quark.vutik.online`. Se ejecuta dentro del contenedor, que ya tiene `DATABASE_URL` y `ADMIN_PASSWORD` del panel de Coolify. Especificación: `specs.md` §4.2.

Desde el directorio del compose en el VPS:

```
docker compose exec quark python -m app.cli bootstrap
```

Si se trabaja desde Coolify, ejecutar `python -m app.cli bootstrap` en la terminal del contenedor `quark`.

Salida esperada en la primera ejecución:

```
[bootstrap] admin 'admin' creado (scopes: read,write,admin).
[bootstrap] API key creada para tenant_id=default (scopes: read,write).
qk_XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX
[bootstrap] Esta API key no se volverá a mostrar. Guárdala ahora.
```

- Guardar la key en el gestor de secretos.
- No pegarla en tickets, chats ni en variables del panel de Coolify.
- No redirigir la salida del comando a archivos dentro del volumen `./data`.

Segunda ejecución (prueba de idempotencia):

```
docker compose exec quark python -m app.cli bootstrap; echo "exit=$?"
```

Salida esperada:

```
[bootstrap] admin 'admin' ya existe; sin cambios.
[bootstrap] ya existe una API key activa para tenant_id=default; no se emite otra (usar --rotate-key para rotarla).
exit=0
```

- Un redeploy del contenedor NO repite el bootstrap ni rota credenciales: el admin y las keys viven en Postgres.
- Rotación: `docker compose exec quark python -m app.cli bootstrap --rotate-key`.

## 5. Criterio de éxito verificable

Alineado con `specs.md` §12 y las fases de §10. Quark se considera FUNCIONANDO en la fase inicial cuando pasan todas las verificaciones de **Fase 0** (local) y **Fase 1** (producción). Las de Fases 2 y 3 son posteriores y no bloquean la puesta en marcha inicial.

Convenciones de los comandos:

- `BASE`: `http://localhost:8000` (local) o `https://quark.vutik.online` (producción).
- `QUARK_KEY`: la API key `qk_...` que imprimió el bootstrap (§3.1 local, §4.1 VPS). Cargarla sin dejarla en el historial: `read -rs QUARK_KEY; export QUARK_KEY`.
- Las verificaciones 0.5 a 0.10, 0.12 y 0.13 son autenticadas: ejecutarlas **después** del bootstrap (§3.1 / §4.1).
- Las verificaciones 0.2, 0.4 y 0.5 leen `DATABASE_URL`. En local: `set -a; source .env; set +a`. En el VPS: anteponer `docker compose exec -e QUARK_KEY quark` al comando.

### Fase 0 — Base operativa (local; specs.md §10 Fase 0 y §12)

| # | Verificación | Comando | Resultado esperado |
|---|---|---|---|
| 0.1 | Servidor arriba | `curl -s -o /dev/null -w '%{http_code}\n' $BASE/docs` | `200` (HTML de Swagger UI) |
| 0.2 | Tablas creadas | `alembic current` y luego `python -c "import os;from sqlalchemy import create_engine,inspect;print(sorted(inspect(create_engine(os.environ['DATABASE_URL'])).get_table_names()))"` | `alembic current` muestra una revisión `(head)`; la lista contiene `api_keys`, `profiles`, `users` |
| 0.3 | Bootstrap, primera ejecución | `python -m app.cli bootstrap` (§3.1) y luego `python -c "import os;from sqlalchemy import create_engine,text;c=create_engine(os.environ['DATABASE_URL']).connect();print(c.execute(text('select count(*) from users')).scalar(),c.execute(text(\"select count(*) from api_keys where is_active and tenant_id='default'\")).scalar())"` | El bootstrap termina con exit 0 e imprime una línea `qk_...` en stdout; el conteo imprime `1 1` |
| 0.4 | Bootstrap idempotente | `python -m app.cli bootstrap; echo "exit=$?"` y `python -m app.cli bootstrap 2>/dev/null \| wc -c` | stdout vacío y `exit=0`; `wc -c` imprime `0`; los conteos de 0.3 siguen en `1 1` |
| 0.5 | Hashes, sin valores en claro | `python -c "import os,hashlib;from sqlalchemy import create_engine,text;c=create_engine(os.environ['DATABASE_URL']).connect();print(c.execute(text('select hashed_password from users')).scalar()[:4]);h=c.execute(text('select key_hash from api_keys where is_active')).scalar();print(len(h),h==hashlib.sha256(os.environ['QUARK_KEY'].encode()).hexdigest())"` | `$2b$` y luego `64 True` |
| 0.6 | Sin API key se rechaza | `curl -s -o /dev/null -w '%{http_code}\n' $BASE/external/collections` | `401` (o `403`) |
| 0.7 | Key del bootstrap aceptada; 7 colecciones | `curl -s -H "X-API-Key: $QUARK_KEY" $BASE/external/collections \| grep -oE 'identity_psychology\|business_strategy\|reminders_urls\|smart_connections\|learnings_reflections\|priority_filtering\|smart_suggestions' \| sort -u \| wc -l` | `7` |
| 0.8 | Escritura + lectura semántica | `curl -s -X POST $BASE/external/store -H "X-API-Key: $QUARK_KEY" -H 'Content-Type: application/json' -d '<cuerpo según /docs>'` y luego `curl -s -X POST $BASE/external/query -H "X-API-Key: $QUARK_KEY" -H 'Content-Type: application/json' -d '<consulta relacionada>'` | `store` responde 2xx; `query` devuelve el documento almacenado. La primera query tarda (descarga del modelo, ~1.1 GB). Confirma ChromaDB + embeddings extremo a extremo |
| 0.9 | Metadata obligatoria | En la respuesta de `query` de 0.8, inspeccionar la metadata del documento | Contiene `tenant_id`, `created_at`, `updated_at` |
| 0.10 | Rotación invalida la key anterior | Guardar la key actual en `OLD_KEY`; `python -m app.cli bootstrap --rotate-key` (imprime la nueva); luego `curl -s -o /dev/null -w '%{http_code}\n' -H "X-API-Key: $OLD_KEY" $BASE/external/collections` y lo mismo con la nueva | `401` con la key anterior y `200` con la nueva. Exportar la nueva como `QUARK_KEY` |
| 0.11 | Arranque sin variables obligatorias | Quitar `ADMIN_PASSWORD` de un `.env` de prueba y ejecutar `uvicorn app.main:app` | Falla con `ValidationError: admin_password Field required` |
| 0.12 | Metadata de `connections` | `store` en la colección `connections` (cuerpo según `/docs`) y luego `query` sobre ella | La metadata contiene `source_id`, `target_id`, `relation_type`, `collection_ref`, `timestamp` |
| 0.13 | Key en claro fuera de los logs | Tras 0.6–0.10: `grep -c "$QUARK_KEY" <log del servidor>` (en el VPS: `docker compose logs quark \| grep -c "$QUARK_KEY"`) | `0` |

Nota de 0.8: el cuerpo exacto de `store` y `query` está en el esquema OpenAPI de `$BASE/docs`; el runbook no lo fija.

### Fase 1 — Despliegue en producción (specs.md §10 Fase 1)

Repetir con `BASE=https://quark.vutik.online` y el bootstrap de §4.1 (dentro del contenedor):

| # | Verificación | Comando | Resultado esperado |
|---|---|---|---|
| 1.1 | Compose válido | `docker compose config -q; echo "exit=$?"` | `exit=0` |
| 1.2 | Puerto solo en loopback | `docker compose ps --format '{{.Ports}}'` | `127.0.0.1:8020->8000/tcp`; no aparece `0.0.0.0` |
| 1.3 | HTTPS vía Traefik | `curl -s -o /dev/null -w '%{http_code}\n' https://quark.vutik.online/docs` | `200` |
| 1.4 | Bootstrap en el contenedor | `docker compose exec quark python -m app.cli bootstrap` y después la misma comprobación de 0.4 con `docker compose exec quark ...` | Primera vez imprime `qk_...`; la segunda: stdout vacío y `exit=0` |
| 1.5 | Verificaciones 0.5 a 0.10, 0.12 y 0.13 contra producción | Los comandos de 0.5 a 0.10, 0.12 y 0.13 con `BASE=https://quark.vutik.online` | Mismos resultados que en Fase 0 |
| 1.6 | Persistencia tras redeploy | Redeploy del servicio y repetir 0.7 con la misma `QUARK_KEY` | `7`; no hace falta repetir el bootstrap |

### Fases posteriores (no bloquean la puesta en marcha inicial)

Se verifican cuando se implemente cada fase; los comandos se fijan entonces.

| Fase | Criterio (specs.md §10) | Verificación esperada |
|---|---|---|
| 2 — Servidor MCP | MCP sobre `/external/*` con tools `query`, `store`, `update`, `delete`, `list_collections`, `consolidate`; auth por API key | El cliente MCP lista las 6 tools y `list_collections` devuelve las 7 colecciones con una API key válida |
| 3 — Multi-tenancy | Aislamiento entre tenants; key propia por tenant | Un documento guardado con la key del tenant A no aparece en un `query` con la key del tenant B (misma consulta: 0 resultados) |
| 3 — Rate limiting y metering | Tabla `usage` y límites por plan | Cada `store`/`query` incrementa `usage`; al exceder el plan, la respuesta es `429` |

## 6. Restricciones

- NO usar Python 3.9/3.10 aunque `runtime.txt` lo indique (debe contener `python-3.12`).
- NO arrancar uvicorn sin `.env` editado ni sin `alembic upgrade head`.
- NO instalar `bcrypt>=4.1` (rompe `passlib`); usar `bcrypt==4.0.1`.
- NO interpretar la primera query lenta como cuelgue: es la descarga del modelo.
- NO crear una segunda instancia de Quark por equipo: una sola instancia es la fuente de verdad de memoria.
- NO publicar puertos en `0.0.0.0` en el VPS.

## 7. Errores conocidos y solución

| Error | Causa | Solución |
|---|---|---|
| `ValidationError: admin_password Field required` | `ADMIN_PASSWORD` ausente en `.env` | Definirla en `.env` en la raíz y reiniciar |
| `pip` falla resolviendo `torch==2.13.0` | Python <3.11 en el venv | Recrear venv con Python 3.12 |
| `AttributeError: module 'bcrypt' has no attribute '__about__'` | `bcrypt>=4.1` instalado | `pip install bcrypt==4.0.1` |
| `alembic` no encontrado o falla | Dependencias no instaladas o `DATABASE_URL` ausente | Activar venv, reinstalar requirements, verificar `.env` |
| Servidor "congelado" en primera query | Descarga del modelo e5 (~1.1 GB) en curso | Esperar; verificar `~/.cache/huggingface` |
| `401/403` en `/external/*` | API key ausente o inválida | Emitir la key con el bootstrap (§3.1 local, §4.1 VPS); si se perdió, rotarla con `--rotate-key`. Enviarla en el header `X-API-Key` |
| ChromaDB en ruta inesperada | `CHROMA_DB_DIR` leída antes de cargar `.env` | Definirla antes del primer arranque; borrar el directorio erróneo |
| `ModuleNotFoundError` al importar `app.main` | venv no activado | `source venv/bin/activate` y reinstalar requirements |
| `quark.vutik.online` no responde | Traefik no enrutado o contenedor no publicado en `127.0.0.1:8020` | Verificar config de dominio en Coolify y `docker ps` |
| `git clone` pide credenciales | Repo privado por HTTPS | Usar URL SSH con llave configurada en GitHub |

## 8. Estado final esperado

- Fase inicial: pasan las verificaciones 0.1 a 0.11 (local) y 1.1 a 1.6 (producción) de la sección 5.
- uvicorn corriendo en `:8000` sin errores en log; la API key en claro no aparece en los logs.
- `data/chroma/` poblado con las 7 colecciones.
- Base SQL inicializada con `users`, `api_keys`, `profiles`: 1 admin y 1 API key activa de `tenant_id = default` emitidas por el bootstrap (§3.1 / §4.1).
- Swagger UI accesible en `/docs`.
- Store + query semántico verificados vía `/external/*` con el header `X-API-Key`.
- En producción: instancia única accesible en `https://quark.vutik.online` para todos los agentes.
