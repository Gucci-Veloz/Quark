from fastapi import APIRouter, HTTPException, Query, Path, Depends, Body
from typing import List, Dict, Optional, Any
from datetime import datetime
from collections import Counter

from app.database import db_manager
from app.utils.auth import Principal, require_scope
from app.models.schemas import (
    Item, LearningItemCreate, LearningItemUpdate, 
    LearningSummaryRequest, LearningSummary,
    ItemList, QueryResult, generate_id
)

router = APIRouter(
    prefix="/aprendizajes",
    tags=["aprendizajes"],
    responses={404: {"description": "No encontrado"}},
)

COLLECTION_KEY = "learnings"

@router.post("/guardar", response_model=Item, status_code=201)
async def create_learning_item(item: LearningItemCreate, principal: Principal = Depends(require_scope("write"))):
    """
    Guarda un nuevo aprendizaje o reflexión.
    """
    item_id = generate_id()
    
    try:
        result = db_manager.add_item(
            collection_key=COLLECTION_KEY,
            id=item_id,
            text=item.text,
            metadata=item.metadata,
            tenant_id=principal.tenant_id
        )
        
        return {
            "id": result["id"],
            "text": result["text"],
            "metadata": result["metadata"]
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error al crear el aprendizaje: {str(e)}")

@router.get("/listar", response_model=ItemList)
async def list_learning_items(
    limit: int = Query(100, ge=1, le=1000, description="Número máximo de aprendizajes a retornar"),
    offset: int = Query(0, ge=0, description="Número de aprendizajes a saltar"),
    category: Optional[str] = Query(None, description="Filtrar por categoría"),
    source: Optional[str] = Query(None, description="Filtrar por fuente"),
    importance: Optional[str] = Query(None, description="Filtrar por importancia"),
    tag: Optional[str] = Query(None, description="Filtrar por etiqueta"),
    principal: Principal = Depends(require_scope("read"))
):
    """
    Lista todos los aprendizajes almacenados.
    """
    try:
        # Obtener todos los aprendizajes
        all_items = db_manager.list_items(collection_key=COLLECTION_KEY, limit=None, tenant_id=principal.tenant_id)
        
        # Aplicar filtros si se proporcionan
        filtered_items = all_items
        
        if category:
            filtered_items = [item for item in filtered_items if item["metadata"].get("category") == category]
        
        if source:
            filtered_items = [item for item in filtered_items if item["metadata"].get("source") == source]
        
        if importance:
            filtered_items = [item for item in filtered_items if item["metadata"].get("importance") == importance]
        
        if tag:
            filtered_items = [item for item in filtered_items if tag in item["metadata"].get("tags", [])]
        
        # Aplicar paginación
        start_idx = min(offset, len(filtered_items))
        end_idx = min(start_idx + limit, len(filtered_items))
        
        paginated_items = filtered_items[start_idx:end_idx]
        
        return {
            "items": paginated_items,
            "total": len(filtered_items)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error al listar los aprendizajes: {str(e)}")

@router.get("/buscar", response_model=QueryResult)
async def search_learning_items(
    query: str = Query(..., min_length=1, description="Texto a buscar"),
    n_results: int = Query(5, ge=1, le=100, description="Número de resultados a retornar"),
    category: Optional[str] = Query(None, description="Filtrar por categoría"),
    source: Optional[str] = Query(None, description="Filtrar por fuente"),
    importance: Optional[str] = Query(None, description="Filtrar por importancia"),
    tag: Optional[str] = Query(None, description="Filtrar por etiqueta"),
    principal: Principal = Depends(require_scope("read"))
):
    """
    Busca aprendizajes por tema, palabra clave o categoría.
    """
    try:
        # Construir el filtro si se proporcionan parámetros
        filter_dict = {}
        
        if category:
            filter_dict["category"] = category
        
        if source:
            filter_dict["source"] = source
        
        if importance:
            filter_dict["importance"] = importance
        
        # ChromaDB no soporta búsqueda en arrays directamente, así que
        # filtramos por tags después de la búsqueda
        
        # Si no hay filtros, establecer a None
        if not filter_dict:
            filter_dict = None
        
        results = db_manager.query_items(
            collection_key=COLLECTION_KEY,
            query_text=query,
            n_results=n_results * 2,  # Obtener más resultados para filtrar por tags después
            filter=filter_dict,
            tenant_id=principal.tenant_id
        )
        
        # Construir la respuesta
        items = []
        distances = []
        
        if results["ids"] and results["ids"][0]:
            for i in range(len(results["ids"][0])):
                # Filtrar por tag si se proporciona
                if tag:
                    metadata = results["metadatas"][0][i] if results["metadatas"] else {}
                    if tag not in metadata.get("tags", []):
                        continue
                
                items.append({
                    "id": results["ids"][0][i],
                    "text": results["documents"][0][i],
                    "metadata": results["metadatas"][0][i] if results["metadatas"] else {}
                })
                distances.append(results["distances"][0][i])
                
                # Limitar a n_results
                if len(items) >= n_results:
                    break
        
        return {
            "items": items,
            "distances": distances
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error al buscar aprendizajes: {str(e)}")

@router.post("/resumir", response_model=LearningSummary)
async def summarize_learnings(request: LearningSummaryRequest, principal: Principal = Depends(require_scope("write"))):
    """
    Genera un resumen de los aprendizajes más importantes.
    """
    try:
        # Obtener todos los aprendizajes
        all_items = db_manager.list_items(collection_key=COLLECTION_KEY, limit=None, tenant_id=principal.tenant_id)
        
        # Aplicar filtros si se proporcionan
        filtered_items = all_items
        
        if request.category:
            filtered_items = [item for item in filtered_items if item["metadata"].get("category") == request.category]
        
        if request.importance:
            filtered_items = [item for item in filtered_items if item["metadata"].get("importance") == request.importance]
        
        if request.tags:
            filtered_items = [
                item for item in filtered_items 
                if any(tag in item["metadata"].get("tags", []) for tag in request.tags)
            ]
        
        # Ordenar por importancia
        importance_order = {"high": 0, "medium": 1, "low": 2}
        sorted_items = sorted(
            filtered_items, 
            key=lambda x: (
                importance_order.get(x["metadata"].get("importance", "low"), 3),
                x["metadata"].get("created_at", "")
            )
        )
        
        # Limitar al número máximo de items
        summary_items = sorted_items[:request.max_items]
        
        # Contar categorías
        categories = Counter([item["metadata"].get("category", "general") for item in summary_items])
        
        # Generar texto de resumen
        summary_text = "Resumen de aprendizajes:\n\n"
        
        for i, item in enumerate(summary_items, 1):
            category = item["metadata"].get("category", "general")
            source = item["metadata"].get("source", "")
            importance = item["metadata"].get("importance", "medium")
            
            summary_text += f"{i}. [{category.upper()} - {importance.upper()}] {item['text'][:100]}...\n"
            if source:
                summary_text += f"   Fuente: {source}\n"
            summary_text += "\n"
        
        return {
            "items": summary_items,
            "total": len(summary_items),
            "categories": dict(categories),
            "summary_text": summary_text
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error al generar el resumen: {str(e)}")

@router.get("/{learning_id}", response_model=Item)
async def get_learning_item(
    learning_id: str = Path(..., description="ID del aprendizaje a obtener"),
    principal: Principal = Depends(require_scope("read"))
):
    """
    Obtiene un aprendizaje específico.
    """
    try:
        item = db_manager.get_item(
            collection_key=COLLECTION_KEY,
            id=learning_id,
            tenant_id=principal.tenant_id
        )
        
        if not item:
            raise HTTPException(status_code=404, detail=f"Aprendizaje con ID '{learning_id}' no encontrado")
        
        return item
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error al obtener el aprendizaje: {str(e)}")

@router.put("/{learning_id}", response_model=Item)
async def update_learning_item(
    learning_id: str = Path(..., description="ID del aprendizaje a actualizar"),
    item_update: LearningItemUpdate = Body(...),
    principal: Principal = Depends(require_scope("write"))
):
    """
    Actualiza un aprendizaje existente.
    """
    try:
        # Verificar que el item existe
        existing_item = db_manager.get_item(
            collection_key=COLLECTION_KEY,
            id=learning_id,
            tenant_id=principal.tenant_id
        )
        
        if not existing_item:
            raise HTTPException(status_code=404, detail=f"Aprendizaje con ID '{learning_id}' no encontrado")
        
        # Actualizar los metadatos si se proporcionan
        metadata = None
        if item_update.metadata is not None:
            metadata = existing_item["metadata"].copy()
            metadata.update(item_update.metadata)
            metadata["updated_at"] = datetime.now().isoformat()
        
        # Actualizar el item
        updated_item = db_manager.update_item(
            collection_key=COLLECTION_KEY,
            id=learning_id,
            text=item_update.text,
            metadata=metadata,
            tenant_id=principal.tenant_id
        )
        
        return updated_item
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error al actualizar el aprendizaje: {str(e)}")

@router.delete("/{learning_id}")
async def delete_learning_item(
    learning_id: str = Path(..., description="ID del aprendizaje a eliminar"),
    principal: Principal = Depends(require_scope("write"))
):
    """
    Elimina un aprendizaje.
    """
    try:
        result = db_manager.delete_item(
            collection_key=COLLECTION_KEY,
            id=learning_id,
            tenant_id=principal.tenant_id
        )
        
        return result
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error al eliminar el aprendizaje: {str(e)}") 