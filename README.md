# QUARK

Una API construida con FastAPI que funciona como memoria estructurada, utilizando ChromaDB como base de datos vectorial para organizar información por relevancia semántica.

## Módulos

1. **Módulo de Identidad y Psicología**: Almacena información sobre perfil cognitivo y estrategias mentales.
2. **Módulo de Negocios y Estrategia**: Guarda ideas, decisiones y planes de acción.
3. **Módulo de Recordatorios y URLs**: Almacena enlaces y tareas importantes.
4. **Módulo de Conexiones Inteligentes**: Establece relaciones entre diferentes piezas de información.
5. **Módulo de Aprendizajes y Reflexiones**: Almacena lecciones y conocimientos adquiridos.
6. **Módulo de Priorización y Filtrado**: Gestiona la relevancia y prioridad de la información.
7. **Módulo de Sugerencias Inteligentes**: Proporciona ideas y conexiones no evidentes.
8. **Módulo de Integración con Airtable**: Sincroniza datos con Airtable.
9. **Módulo de Acceso Externo**: API específica para el acceso de aplicaciones externas a QUARK.

## Requisitos

- Python 3.8+
- FastAPI
- ChromaDB
- Otras dependencias en `requirements.txt`

## Instalación

```bash
# Clonar el repositorio
git clone <url-del-repositorio>
cd <nombre-del-repositorio>

# Crear entorno virtual
python -m venv venv
source venv/bin/activate  # En Windows: venv\Scripts\activate

# Instalar dependencias
pip install -r requirements.txt

# Configurar variables de entorno
cp .env.example .env
# Editar .env con los valores correspondientes
```

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

## Seguridad

La API implementa un sistema de seguridad basado en:

1. **Autenticación JWT**: Para acceso mediante token de sesión
2. **API Keys**: Para integración con otros servicios
3. **Control de Permisos**: Sistema de permisos basado en scopes

Para obtener un token JWT:

```bash
curl -X POST "http://localhost:8000/token" \
     -H "Content-Type: application/x-www-form-urlencoded" \
     -d "username=admin&password=abundancia2026"
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

## Despliegue en Render

Para desplegar la aplicación en Render:

1. Crea un nuevo Web Service en Render
2. Conecta con el repositorio de GitHub
3. Configura las variables de entorno según `.env.example`
4. Render detectará automáticamente la configuración en `render.yaml`

## Docker

La aplicación puede ejecutarse en Docker:

```bash
# Construir la imagen
make docker-build

# Ejecutar el contenedor
make docker-run

# Usando docker-compose
make docker-compose-up
```

## Estructura del Proyecto Actualizada

```
.
├── app/
│   ├── __init__.py
│   ├── main.py
│   ├── config.py
│   ├── database.py
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
│   │   ├── airtable.py
│   │   └── external.py
│   └── utils/
│       ├── __init__.py
│       ├── embeddings.py
│       ├── airtable.py
│       ├── auth.py
│       └── logger.py
├── tests/
│   ├── __init__.py
│   ├── conftest.py
│   └── test_api.py
├── data/
│   └── chroma/
├── docs/
│   └── external_access.md
├── .env.example
├── .env
├── render.yaml
├── requirements.txt
├── Dockerfile
├── docker-compose.yml
├── Makefile
├── pytest.ini
└── README.md
```