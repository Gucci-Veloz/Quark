# Acceso externo a QUARK

Este documento proporciona ejemplos y guías sobre cómo integrar aplicaciones externas con la API de QUARK.

## Autenticación

Para todas las peticiones a la API, el cliente debe proporcionar una clave API en el encabezado HTTP:

```
X-API-Key: your_quark_api_key_here
```

## Ejemplos de Peticiones

### 1. Consulta de Información

Para buscar información semántica:

```javascript
// Ejemplo para GPT Actions
const query = {
  url: 'https://quark-api.onrender.com/external/query',
  method: 'POST',
  headers: {
    'Content-Type': 'application/json',
    'X-API-Key': process.env.QUARK_API_KEY
  },
  body: JSON.stringify({
    text: "¿Cuáles son mis objetivos principales para este mes?",
    collection: "identity",
    n_results: 5
  })
};

// La respuesta incluirá los items más relevantes con sus metadatos
```

### 2. Almacenamiento de Información

Para guardar nueva información:

```javascript
const storeData = {
  url: 'https://quark-api.onrender.com/external/store',
  method: 'POST',
  headers: {
    'Content-Type': 'application/json',
    'X-API-Key': process.env.QUARK_API_KEY
  },
  body: JSON.stringify({
    text: "Mi objetivo principal para abril es completar el proyecto X y aprender tecnología Y",
    collection: "identity",
    metadata: {
      category: "objetivos",
      priority: "high",
      due_date: "2023-04-30"
    }
  })
};

// La respuesta incluirá el ID del nuevo item
```

### 3. Actualización de Información

Para actualizar información existente:

```javascript
const updateData = {
  url: 'https://quark-api.onrender.com/external/update/identity/123e4567-e89b-12d3-a456-426614174000',
  method: 'PUT',
  headers: {
    'Content-Type': 'application/json',
    'X-API-Key': process.env.QUARK_API_KEY
  },
  body: JSON.stringify({
    text: "Texto actualizado con más detalles",
    metadata: {
      status: "in_progress",
      updated_reason: "Refinamiento de objetivos"
    }
  })
};
```

### 4. Eliminación de Información

Para eliminar información:

```javascript
const deleteData = {
  url: 'https://quark-api.onrender.com/external/delete/identity/123e4567-e89b-12d3-a456-426614174000',
  method: 'DELETE',
  headers: {
    'X-API-Key': process.env.QUARK_API_KEY
  }
};
```

### 5. Operaciones por Lotes

Para realizar múltiples operaciones en una sola llamada:

```javascript
const batchOperations = {
  url: 'https://quark-api.onrender.com/external/batch',
  method: 'POST',
  headers: {
    'Content-Type': 'application/json',
    'X-API-Key': process.env.QUARK_API_KEY
  },
  body: JSON.stringify({
    operations: [
      {
        type: "store",
        collection: "business",
        text: "Nueva idea de negocio: plataforma de X para Y",
        metadata: {
          category: "idea",
          priority: "medium"
        }
      },
      {
        type: "query",
        collection: "business",
        query: "ideas rentables negocio online",
        n_results: 3
      },
      {
        type: "update",
        collection: "reminders",
        id: "existing-id-123",
        text: "Recordatorio actualizado",
        metadata: {
          status: "completed"
        }
      }
    ]
  })
};

// La respuesta incluirá los resultados de cada operación
```

### 6. Consolidación de Datos

Para obtener información consolidada de múltiples colecciones:

```javascript
const consolidateRequest = {
  url: 'https://quark-api.onrender.com/external/consolidate',
  method: 'POST',
  headers: {
    'Content-Type': 'application/json',
    'X-API-Key': process.env.QUARK_API_KEY
  },
  body: JSON.stringify({
    query: "estrategias de productividad",
    collections: ["identity", "business", "learnings"],
    limit: 10
  })
};

// La respuesta incluirá resultados ordenados por relevancia de todas las colecciones
```

## Mejores Prácticas

1. **Manejo de Errores**: Siempre implementar manejo adecuado de errores para respuestas no exitosas
2. **Seguridad de API Key**: Nunca exponer la API Key en el código cliente
3. **Validación**: Siempre validar los datos antes de enviarlos a la API
4. **Caché**: Considerar implementar caché para consultas frecuentes
5. **Rate Limiting**: Respetar los límites de frecuencia de la API

## Esquema de Metadatos Recomendados

Para mantener consistencia, se recomienda usar estos campos en los metadatos:

- `category`: Categoría general del item
- `priority`: Prioridad (high, medium, low)
- `status`: Estado (pending, in_progress, completed, archived)
- `tags`: Array de etiquetas
- `source`: Origen de la información
- `created_at`: Fecha de creación (automática)
- `updated_at`: Fecha de actualización (automática)
- `expires_at`: Fecha de expiración (opcional)

## Ejemplos de Uso Comunes

### Seguimiento de Objetivos

```javascript
// Almacenar objetivo
const storeGoal = {
  url: 'https://quark-api.onrender.com/external/store',
  method: 'POST',
  headers: {
    'Content-Type': 'application/json',
    'X-API-Key': process.env.QUARK_API_KEY
  },
  body: JSON.stringify({
    text: "Objetivo: Aprender programación funcional en JavaScript",
    collection: "identity",
    metadata: {
      category: "objetivo",
      priority: "high",
      status: "in_progress",
      target_date: "2023-06-30",
      progress: 25,
      metrics: "Completar 3 proyectos usando paradigma funcional",
      related_resources: ["libro X", "curso Y"]
    }
  })
};

// Consultar progreso
const queryGoals = {
  url: 'https://quark-api.onrender.com/external/query',
  method: 'POST',
  headers: {
    'Content-Type': 'application/json',
    'X-API-Key': process.env.QUARK_API_KEY
  },
  body: JSON.stringify({
    text: "objetivos aprendizaje programación",
    collection: "identity",
    filter: {
      status: "in_progress"
    }
  })
};
```

### Almacenamiento de Aprendizajes

```javascript
const storeLearning = {
  url: 'https://quark-api.onrender.com/external/store',
  method: 'POST',
  headers: {
    'Content-Type': 'application/json',
    'X-API-Key': process.env.QUARK_API_KEY
  },
  body: JSON.stringify({
    text: "He aprendido que las arrow functions en JavaScript no tienen su propio contexto 'this'",
    collection: "learnings",
    metadata: {
      category: "programación",
      subcategory: "javascript",
      importance: "medium",
      context: "Desarrollo web frontend con React",
      source: "Documentación de MDN",
      url: "https://developer.mozilla.org/es/docs/Web/JavaScript/Reference/Functions/Arrow_functions",
      tags: ["javascript", "funciones", "arrow-functions", "this", "contexto"]
    }
  })
};
```
