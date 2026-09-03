# Método PUT

Este documento describe las operaciones PUT disponibles en la API de QUARK.

## Módulo de Identidad y Psicología

### Actualizar un item existente

```http
PUT /identity/{item_id}
```

**Cuerpo de la petición**
```json
{
  "text": "Mi objetivo actualizado para abril es completar el proyecto X y comenzar el proyecto Z",
  "metadata": {
    "priority": "high",
    "status": "in_progress",
    "progress": 25
  }
}
```

**Respuesta**
```json
{
  "id": "123e4567-e89b-12d3-a456-426614174000",
  "text": "Mi objetivo actualizado para abril es completar el proyecto X y comenzar el proyecto Z",
  "metadata": {
    "category": "objetivos",
    "priority": "high",
    "status": "in_progress",
    "progress": 25,
    "due_date": "2023-04-30",
    "created_at": "2023-03-15T10:30:00Z",
    "updated_at": "2023-03-15T11:45:00Z"
  }
}
```

## Módulo de acceso externo

### Actualizar información

```http
PUT /external/update/{collection_key}/{item_id}
```

**Encabezados**
```
X-API-Key: {api_key}
```

**Cuerpo de la petición**
```json
{
  "text": "Texto actualizado para pruebas",
  "metadata": {
    "priority": "high",
    "status": "in_progress",
    "progress": 50
  }
}
```

**Respuesta**
```json
{
  "id": "123e4567-e89b-12d3-a456-426614174000",
  "text": "Texto actualizado para pruebas",
  "metadata": {
    "category": "objetivos",
    "priority": "high",
    "status": "in_progress",
    "progress": 50,
    "due_date": "2023-04-30",
    "created_at": "2023-03-15T10:30:00Z",
    "updated_at": "2023-03-15T11:45:00Z",
    "last_update_source": "quark_api"
  }
}
```

Nota: En la operación PUT, solo se actualizan los campos proporcionados en la petición. Los campos no incluidos mantienen sus valores anteriores.

Los demás módulos siguen patrones similares para sus operaciones PUT. 