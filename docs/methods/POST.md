# Método POST

Este documento describe las operaciones POST disponibles en la API de QUARK.

## Endpoints de Autenticación

### Obtener token de acceso

```http
POST /token
```

**Cuerpo de la petición**
```
username=admin&password=<tu_ADMIN_PASSWORD>
```

**Respuesta**
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "bearer"
}
```

## Módulo de Identidad y Psicología

### Crear un nuevo item

```http
POST /identity
```

**Cuerpo de la petición**
```json
{
  "text": "Mi objetivo principal para abril es completar el proyecto X",
  "metadata": {
    "category": "objetivos",
    "priority": "high",
    "due_date": "2023-04-30"
  }
}
```

**Respuesta**
```json
{
  "id": "123e4567-e89b-12d3-a456-426614174000",
  "text": "Mi objetivo principal para abril es completar el proyecto X",
  "metadata": {
    "category": "objetivos",
    "priority": "high",
    "due_date": "2023-04-30",
    "created_at": "2023-03-15T10:30:00Z",
    "updated_at": "2023-03-15T10:30:00Z"
  }
}
```

## Módulo de acceso externo

### Consulta semántica

```http
POST /external/query
```

**Encabezados**
```
X-API-Key: {api_key}
```

**Cuerpo de la petición**
```json
{
  "text": "¿Cuáles son mis objetivos principales para este mes?",
  "collection": "identity",
  "n_results": 5,
  "filter": {
    "category": "objetivos",
    "status": "active"
  }
}
```

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

### Almacenar información

```http
POST /external/store
```

**Encabezados**
```
X-API-Key: {api_key}
```

**Cuerpo de la petición**
```json
{
  "text": "Mi objetivo principal para abril es completar el proyecto X y aprender tecnología Y",
  "collection": "identity",
  "metadata": {
    "category": "objetivos",
    "priority": "high",
    "due_date": "2023-04-30"
  }
}
```

**Respuesta**
```json
{
  "id": "123e4567-e89b-12d3-a456-426614174000",
  "text": "Mi objetivo principal para abril es completar el proyecto X y aprender tecnología Y",
  "metadata": {
    "category": "objetivos",
    "priority": "high",
    "due_date": "2023-04-30",
    "created_at": "2023-03-15T10:30:00Z",
    "updated_at": "2023-03-15T10:30:00Z",
    "external_source": "quark_api"
  }
}
```

### Operaciones por lotes

```http
POST /external/batch
```

**Encabezados**
```
X-API-Key: {api_key}
```

**Cuerpo de la petición**
```json
{
  "operations": [
    {
      "type": "store",
      "collection": "business",
      "text": "Nueva idea de negocio: plataforma de X para Y",
      "metadata": {
        "category": "idea",
        "priority": "medium"
      }
    },
    {
      "type": "query",
      "collection": "business",
      "query": "ideas rentables negocio online",
      "n_results": 3
    },
    {
      "type": "update",
      "collection": "reminders",
      "id": "existing-id-123",
      "text": "Recordatorio actualizado",
      "metadata": {
        "status": "completed"
      }
    }
  ]
}
```

**Respuesta**
```json
{
  "total_operations": 3,
  "successful_operations": 3,
  "failed_operations": 0,
  "results": [
    {
      "operation_index": 0,
      "success": true,
      "type": "store",
      "data": {
        "id": "123e4567-e89b-12d3-a456-426614174000",
        "text": "Nueva idea de negocio: plataforma de X para Y",
        "metadata": {
          "category": "idea",
          "priority": "medium",
          "created_at": "2023-03-15T10:30:00Z",
          "updated_at": "2023-03-15T10:30:00Z",
          "external_source": "quark_api_batch"
        }
      }
    },
    {
      "operation_index": 1,
      "success": true,
      "type": "query",
      "data": {
        "items": [],
        "distances": []
      }
    },
    {
      "operation_index": 2,
      "success": true,
      "type": "update",
      "data": {
        "id": "existing-id-123",
        "text": "Recordatorio actualizado",
        "metadata": {
          "status": "completed",
          "updated_at": "2023-03-15T10:30:00Z",
          "last_update_source": "quark_api_batch"
        }
      }
    }
  ],
  "errors": []
}
```

### Consolidación de datos

```http
POST /external/consolidate
```

**Encabezados**
```
X-API-Key: {api_key}
```

**Cuerpo de la petición**
```json
{
  "query": "estrategias de productividad",
  "collections": ["identity", "business", "learnings"],
  "limit": 10
}
```

**Respuesta**
```json
{
  "query": "estrategias de productividad",
  "collections": ["identity", "business", "learnings"],
  "total_results": 3,
  "results": [
    {
      "collection": "learnings",
      "id": "123e4567-e89b-12d3-a456-426614174000",
      "text": "La técnica Pomodoro mejora la productividad al dividir el trabajo en intervalos de 25 minutos",
      "metadata": {
        "category": "productividad",
        "importance": "high",
        "source": "libro técnicas de productividad"
      },
      "similarity": 0.123
    },
    {
      "collection": "identity",
      "id": "123e4567-e89b-12d3-a456-426614174001",
      "text": "Implementar la estrategia de bloques de tiempo para mejorar la productividad",
      "metadata": {
        "category": "objetivos",
        "priority": "medium"
      },
      "similarity": 0.234
    },
    {
      "collection": "business",
      "id": "123e4567-e89b-12d3-a456-426614174002",
      "text": "Usar herramientas de automatización para incrementar la productividad del equipo",
      "metadata": {
        "category": "idea",
        "priority": "high"
      },
      "similarity": 0.345
    }
  ]
}
```

Los demás módulos siguen patrones similares para sus operaciones POST. 