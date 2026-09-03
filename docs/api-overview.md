# Resumen de la API de QUARK

Este documento proporciona una visión general de la API de QUARK.

## Descripción General

QUARK es una API desarrollada con FastAPI que utiliza ChromaDB como base de datos vectorial para almacenar y recuperar información mediante búsquedas semánticas. Está diseñada para actuar como una memoria estructurada para aplicaciones externas y otros servicios.

## Estructura de la API

### Módulos Principales

1. **Identidad y Psicología** (`/identity`)
   - Almacena información personal, objetivos, valores y preferencias.

2. **Negocios y Estrategia** (`/business`)
   - Guarda ideas, decisiones y planes de acción relacionados con negocios.

3. **Recordatorios y URLs** (`/reminders`)
   - Almacena enlaces y tareas importantes con fechas de vencimiento.

4. **Conexiones Inteligentes** (`/connections`)
   - Establece relaciones entre diferentes piezas de información.

5. **Aprendizajes y Reflexiones** (`/learnings`)
   - Almacena lecciones, conocimientos y experiencias.

6. **Priorización y Filtrado** (`/priorities`)
   - Gestiona la relevancia y prioridad de la información.

7. **Sugerencias Inteligentes** (`/suggestions`)
   - Proporciona ideas y conexiones no evidentes entre datos.

8. **Integración con Airtable** (`/airtable`)
   - Sincroniza datos con Airtable para su visualización y gestión externa.

9. **Acceso externo a QUARK** (`/external`)
   - API específica para el acceso de aplicaciones externas a QUARK, incluyendo operaciones especializadas.

### Endpoints Comunes

Cada módulo generalmente expone los siguientes endpoints:

- **GET /module/** - Lista todos los items
- **GET /module/{id}** - Obtiene un item específico
- **GET /module/search** - Busca items por similitud semántica
- **POST /module/** - Crea un nuevo item
- **PUT /module/{id}** - Actualiza un item existente
- **DELETE /module/{id}** - Elimina un item

### Endpoints Especiales

Además, hay endpoints específicos para ciertas operaciones:

- **POST /token** - Autenticación y obtención de token JWT
- **GET /check-auth** - Verifica la autenticación del usuario
- **GET /check-write-permission** - Verifica permisos de escritura

El módulo de acceso externo tiene endpoints adicionales:

- **POST /external/query** - Consultas semánticas
- **POST /external/store** - Almacenamiento de datos
- **PUT /external/update/{collection}/{id}** - Actualización de datos
- **DELETE /external/delete/{collection}/{id}** - Eliminación de datos
- **GET /external/collections** - Lista las colecciones disponibles
- **POST /external/batch** - Operaciones por lotes
- **POST /external/consolidate** - Consolidación de datos de múltiples colecciones

## Autenticación

La API soporta dos métodos de autenticación:

1. **Token JWT** - Para aplicaciones con interfaz de usuario
   ```
   Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
   ```

2. **API Key** - Para integraciones entre servicios (aplicaciones externas)
   ```
   X-API-Key: your_api_key_here
   ```

## Respuestas y Códigos de Estado

La API utiliza códigos de estado HTTP estándar:

- **200 OK** - Petición exitosa
- **201 Created** - Recurso creado correctamente
- **400 Bad Request** - Error en la petición
- **401 Unauthorized** - Sin autenticación o credenciales inválidas
- **403 Forbidden** - Sin permisos suficientes
- **404 Not Found** - Recurso no encontrado
- **500 Internal Server Error** - Error en el servidor

## Ejemplos de Uso

Para ejemplos detallados de cada método (GET, POST, PUT, DELETE), consulte los archivos específicos:

- [Método GET](./methods/GET.md)
- [Método POST](./methods/POST.md)
- [Método PUT](./methods/PUT.md)
- [Método DELETE](./methods/DELETE.md)

Para ejemplos específicos de acceso externo a QUARK, consulte:

- [Acceso externo a QUARK](./external_access.md)

## Esquema de Datos

Cada item almacenado en QUARK tiene la siguiente estructura básica:

```json
{
  "id": "uuid-único",
  "text": "Contenido principal del item",
  "metadata": {
    "category": "categoría",
    "priority": "prioridad",
    "created_at": "fecha de creación",
    "updated_at": "fecha de actualización",
    "otros_metadatos": "valor"
  }
}
```

El campo `text` contiene el contenido principal y es utilizado para las búsquedas semánticas.
El campo `metadata` contiene información adicional estructurada que puede variar según el módulo y tipo de datos. 