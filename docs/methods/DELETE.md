# Método DELETE

Este documento describe las operaciones DELETE disponibles en la API de QUARK.

## Módulo de Identidad y Psicología

### Eliminar un item

```http
DELETE /identity/{item_id}
```

**Respuesta**
```json
{
  "message": "Item con ID '123e4567-e89b-12d3-a456-426614174000' eliminado correctamente"
}
```

## Módulo de acceso externo

### Eliminar información

```http
DELETE /external/delete/{collection_key}/{item_id}
```

**Encabezados**
```
X-API-Key: {api_key}
```

**Respuesta**
```json
{
  "message": "Item con ID '123e4567-e89b-12d3-a456-426614174000' eliminado correctamente"
}
```

## Notas importantes sobre las operaciones DELETE

1. Las operaciones DELETE son irreversibles. Una vez eliminado un item, no puede ser recuperado.
2. Antes de realizar una operación DELETE, el sistema verifica que el item exista. Si no existe, se devuelve un error 404.
3. Algunas operaciones DELETE pueden eliminar también datos relacionados (por ejemplo, conexiones asociadas a un item).

Los demás módulos siguen patrones similares para sus operaciones DELETE. 