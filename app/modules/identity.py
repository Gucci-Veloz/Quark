from fastapi import APIRouter, HTTPException, Query, Path, Depends
from typing import List, Dict, Optional, Any
from datetime import datetime

from app.database import db_manager
from app.utils.auth import Principal, require_scope
from app.models.schemas import (
    Item, IdentityItemCreate, IdentityItemUpdate, 
    ItemList, QueryResult, generate_id
)

router = APIRouter(
    prefix="/identity",
    tags=["identity"],
    responses={404: {"description": "No encontrado"}},
)

COLLECTION_KEY = "identity"

@router.post("/", response_model=Item, status_code=201)
async def create_identity_item(item: IdentityItemCreate, principal: Principal = Depends(require_scope("write"))):
    """
    Crea un nuevo item en el módulo de Identidad y Psicología.
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
        raise HTTPException(status_code=500, detail=f"Error al crear el item: {str(e)}")

@router.get("/", response_model=ItemList)
async def list_identity_items(
    limit: int = Query(100, ge=1, le=1000, description="Número máximo de items a retornar"),
    offset: int = Query(0, ge=0, description="Número de items a saltar"),
    principal: Principal = Depends(require_scope("read"))
):
    """
    Lista todos los items del módulo de Identidad y Psicología.
    """
    try:
        items = db_manager.list_items(
            collection_key=COLLECTION_KEY,
            limit=limit,
            offset=offset,
            tenant_id=principal.tenant_id
        )
        
        # Obtener el total de items
        total = db_manager.count_items(collection_key=COLLECTION_KEY, tenant_id=principal.tenant_id)
        
        return {
            "items": items,
            "total": total
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error al listar los items: {str(e)}")

@router.get("/search", response_model=QueryResult)
async def search_identity_items(
    query: str = Query(..., min_length=1, description="Texto a buscar"),
    n_results: int = Query(5, ge=1, le=100, description="Número de resultados a retornar"),
    category: Optional[str] = Query(None, description="Filtrar por categoría"),
    principal: Principal = Depends(require_scope("read"))
):
    """
    Busca items en el módulo de Identidad y Psicología por similitud semántica.
    """
    try:
        # Construir el filtro si se proporciona una categoría
        filter_dict = None
        if category:
            filter_dict = {"category": category}
        
        results = db_manager.query_items(
            collection_key=COLLECTION_KEY,
            query_text=query,
            n_results=n_results,
            filter=filter_dict,
            tenant_id=principal.tenant_id
        )
        
        # Construir la respuesta
        items = []
        for i in range(len(results["ids"][0])):
            items.append({
                "id": results["ids"][0][i],
                "text": results["documents"][0][i],
                "metadata": results["metadatas"][0][i] if results["metadatas"] else {}
            })
        
        return {
            "items": items,
            "distances": results["distances"][0]
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error al buscar items: {str(e)}")

@router.get("/{item_id}", response_model=Item)
async def get_identity_item(
    item_id: str = Path(..., description="ID del item a obtener"),
    principal: Principal = Depends(require_scope("read"))
):
    """
    Obtiene un item específico del módulo de Identidad y Psicología.
    """
    try:
        item = db_manager.get_item(
            collection_key=COLLECTION_KEY,
            id=item_id,
            tenant_id=principal.tenant_id
        )
        
        if not item:
            raise HTTPException(status_code=404, detail=f"Item con ID '{item_id}' no encontrado")
        
        return item
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error al obtener el item: {str(e)}")

@router.put("/{item_id}", response_model=Item)
async def update_identity_item(
    item_id: str = Path(..., description="ID del item a actualizar"),
    item_update: IdentityItemUpdate = Depends(),
    principal: Principal = Depends(require_scope("write"))
):
    """
    Actualiza un item existente en el módulo de Identidad y Psicología.
    """
    try:
        # Verificar que el item existe
        existing_item = db_manager.get_item(
            collection_key=COLLECTION_KEY,
            id=item_id,
            tenant_id=principal.tenant_id
        )
        
        if not existing_item:
            raise HTTPException(status_code=404, detail=f"Item con ID '{item_id}' no encontrado")
        
        # Actualizar los metadatos si se proporcionan
        metadata = None
        if item_update.metadata is not None:
            metadata = existing_item["metadata"].copy()
            metadata.update(item_update.metadata)
            metadata["updated_at"] = datetime.now().isoformat()
        
        # Actualizar el item
        updated_item = db_manager.update_item(
            collection_key=COLLECTION_KEY,
            id=item_id,
            text=item_update.text,
            metadata=metadata,
            tenant_id=principal.tenant_id
        )
        
        return updated_item
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error al actualizar el item: {str(e)}")

@router.delete("/{item_id}")
async def delete_identity_item(
    item_id: str = Path(..., description="ID del item a eliminar"),
    principal: Principal = Depends(require_scope("write"))
):
    """
    Elimina un item del módulo de Identidad y Psicología.
    """
    try:
        result = db_manager.delete_item(
            collection_key=COLLECTION_KEY,
            id=item_id,
            tenant_id=principal.tenant_id
        )
        
        return result
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error al eliminar el item: {str(e)}") 