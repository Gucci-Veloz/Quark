# Método GET

Este documento describe las operaciones GET disponibles en la API de QUARK.

## Endpoints Principales

### Obtener información general

```http
GET /
```

**Respuesta**
```json
{
  "name": "QUARK",
  "description": "API para almacenar y recuperar información estructurada",
  "version": "0.1.0",
  "documentation": "/docs",
  "modules": [
    {"name": "Identidad y Psicología", "endpoint": "/identity"},
    {"name": "Negocios y Estrategia", "endpoint": "/business"},
    {"name": "Recordatorios y URLs", "endpoint": "/reminders"},
    {"name": "Conexiones Inteligentes", "endpoint": "/conexiones"},
    {"name": "Aprendizajes y Reflexiones", "endpoint": "/aprendizajes"},
    {"name": "Priorización y Filtrado", "endpoint": "/prioridad"},
    {"name": "Sugerencias Inteligentes", "endpoint": "/sugerencias"},
    {"name": "Integración con Airtable", "endpoint": "/airtable"},
    {"name": "Acceso externo a QUARK", "endpoint": "/external"}
  ]
}
```

### Verificar autenticación

```http
GET /check-auth
```

**Encabezados**
```
Authorization: Bearer {token}
```

**Respuesta**
```json
{
  "authenticated": true,
  "user_info": {
    "username": "usuario123",
    "scopes": ["read", "write"]
  }
}
```

### Verificar permisos

```http
GET /check-write-permission
```

**Encabezados**
```
Authorization: Bearer {token}
```

**Respuesta**
```json
{
  "authorized": true,
  "scope": "write",
  "user_info": {
    "username": "usuario123",
    "scopes": ["read", "write"]
  }
}
```

## Módulo de Identidad y Psicología

### Listar items

```http
GET /identity?limit=100&offset=0
```

**Parámetros**
- `limit` (opcional): Número máximo de items a retornar (por defecto: 100)
- `offset` (opcional): Número de items a saltar (por defecto: 0)

**Respuesta**
```json
{
  "items": [
    {
      "id": "123e4567-e89b-12d3-a456-426614174000",
      "text": "Mi objetivo principal para abril es completar el proyecto X",
      "metadata": {
        "category": "objetivos",
        "priority": "high",
        "created_at": "2023-03-15T10:30:00Z",
        "updated_at": "2023-03-15T10:30:00Z"
      }
    },
    // Más items...
  ],
  "total": 42
}
```

### Obtener item específico

```http
GET /identity/{item_id}
```

**Respuesta**
```json
{
  "id": "123e4567-e89b-12d3-a456-426614174000",
  "text": "Mi objetivo principal para abril es completar el proyecto X",
  "metadata": {
    "category": "objetivos",
    "priority": "high",
    "created_at": "2023-03-15T10:30:00Z",
    "updated_at": "2023-03-15T10:30:00Z"
  }
}
```

### Buscar items

```http
GET /identity/search?query=objetivos&n_results=5&category=general
```

**Parámetros**
- `query`: Texto a buscar
- `n_results` (opcional): Número de resultados a retornar (por defecto: 5)
- `category` (opcional): Filtrar por categoría

**Respuesta**
```json
{
  "items": [
    {
      "id": "123e4567-e89b-12d3-a456-426614174000",
      "text": "Mi objetivo principal para abril es completar el proyecto X",
      "metadata": {
        "category": "objetivos",
        "priority": "high",
        "created_at": "2023-03-15T10:30:00Z",
        "updated_at": "2023-03-15T10:30:00Z"
      }
    },
    // Más items...
  ],
  "distances": [0.123, 0.234, 0.345]
}
```

## Módulo de acceso externo

### Listar colecciones

```http
GET /external/collections
```

**Encabezados**
```
X-API-Key: {api_key}
```

**Respuesta**
```json
{
  "identity": "identity_psychology",
  "business": "business_strategy",
  "reminders": "reminders_urls",
  "connections": "smart_connections",
  "learnings": "learnings_reflections",
  "priorities": "priority_filtering",
  "suggestions": "smart_suggestions"
}
```

Los demás módulos siguen patrones similares para sus operaciones GET. 