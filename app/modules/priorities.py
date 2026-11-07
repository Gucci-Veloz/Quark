from fastapi import APIRouter, HTTPException, Query, Path, Depends, Body
from typing import List, Dict, Optional, Any
from datetime import datetime
from collections import defaultdict

from app.database import db_manager
from app.utils.auth import Principal, require_scope
from app.models.schemas import (
    Item, PriorityItemCreate, PriorityItemUpdate,
    PriorityReviewRequest, PriorityAdjustRequest, PriorityOptimizeRequest,
    PriorityReviewResult, PriorityOptimizeResult,
    ItemList, QueryResult, generate_id
)
from app.utils.embeddings import cosine_similarity, embed_passages

router = APIRouter(
    prefix="/prioridad",
    tags=["prioridad"],
    responses={404: {"description": "No encontrado"}},
)

COLLECTION_KEY = "priorities"

@router.post("/revisar", response_model=PriorityReviewResult)
async def review_priorities(request: PriorityReviewRequest, principal: Principal = Depends(require_scope("write"))):
    """
    Analiza los datos y sugiere qué priorizar o limpiar.
    
    Este endpoint:
    1. Revisa los items en los módulos especificados
    2. Detecta posibles duplicados
    3. Identifica items con baja relevancia
    4. Sugiere acciones para optimizar la base de datos
    """
    try:
        # Definir los módulos a revisar
        valid_modules = ["identity", "business", "reminders", "learnings"]
        modules_to_review = [request.module] if request.module else valid_modules
        
        # Validar que los módulos son válidos
        for module in modules_to_review:
            if module not in valid_modules:
                raise HTTPException(status_code=400, detail=f"Módulo '{module}' no válido")
        
        # Inicializar resultados
        total_items_reviewed = 0
        potential_duplicates = []
        low_relevance_items = []
        suggested_actions = []
        
        # Revisar cada módulo
        for module in modules_to_review:
            # Obtener todos los items del módulo
            items = db_manager.list_items(collection_key=module, limit=None, tenant_id=principal.tenant_id)
            total_items_reviewed += len(items)
            
            # Limitar el número de items si es necesario
            if len(items) > request.max_items:
                items = items[:request.max_items]
            
            # Buscar duplicados
            if request.include_duplicates and len(items) > 1:
                for i, item1 in enumerate(items):
                    for j, item2 in enumerate(items):
                        # Evitar comparar un item consigo mismo y duplicar comparaciones
                        if i >= j:
                            continue
                        
                        # Comparar textos usando el modelo de embeddings
                        # Calcular similitud coseno (embeddings E5 con prefijo passage)
                        similarity = cosine_similarity(item1["text"], item2["text"])
                        
                        # Si la similitud supera el umbral, registrar como posible duplicado
                        if similarity >= request.min_similarity:
                            duplicate_pair = {
                                "item1": {
                                    "id": item1["id"],
                                    "text": item1["text"][:100] + "..." if len(item1["text"]) > 100 else item1["text"],
                                    "module": module
                                },
                                "item2": {
                                    "id": item2["id"],
                                    "text": item2["text"][:100] + "..." if len(item2["text"]) > 100 else item2["text"],
                                    "module": module
                                },
                                "similarity": similarity,
                                "suggested_action": "merge" if similarity > 0.95 else "review"
                            }
                            potential_duplicates.append(duplicate_pair)
                            
                            # Añadir acción sugerida
                            if similarity > 0.95:
                                suggested_actions.append({
                                    "action": "merge_duplicates",
                                    "items": [item1["id"], item2["id"]],
                                    "module": module,
                                    "reason": f"Duplicados con similitud {similarity:.2f}"
                                })
            
            # Identificar items con baja relevancia
            if request.include_low_relevance:
                # Aquí podríamos implementar diferentes heurísticas para determinar la relevancia
                # Por ahora, usaremos una lógica simple basada en la longitud del texto
                for item in items:
                    # Verificar si ya existe un registro de prioridad para este item
                    priority_records = db_manager.list_items(collection_key=COLLECTION_KEY, limit=None, tenant_id=principal.tenant_id)
                    priority_record = next((p for p in priority_records if p["metadata"].get("item_id") == item["id"] and p["metadata"].get("module") == module), None)
                    
                    # Calcular una puntuación de relevancia simple
                    relevance_score = min(1.0, len(item["text"]) / 1000)  # Texto más largo = más relevante, hasta cierto punto
                    
                    # Si existe un registro de prioridad, usar su puntuación
                    if priority_record:
                        relevance_score = priority_record["metadata"].get("relevance_score", relevance_score)
                        usage_count = priority_record["metadata"].get("usage_count", 0)
                        
                        # Ajustar relevancia según el uso
                        if usage_count == 0:
                            relevance_score *= 0.8  # Penalizar items nunca usados
                    else:
                        usage_count = 0
                    
                    # Si la relevancia es baja, añadir a la lista
                    if relevance_score < 0.3:
                        low_relevance_item = {
                            "id": item["id"],
                            "text": item["text"][:100] + "..." if len(item["text"]) > 100 else item["text"],
                            "module": module,
                            "relevance_score": relevance_score,
                            "usage_count": usage_count,
                            "suggested_action": "archive" if relevance_score < 0.2 and usage_count == 0 else "review"
                        }
                        low_relevance_items.append(low_relevance_item)
                        
                        # Añadir acción sugerida
                        if relevance_score < 0.2 and usage_count == 0:
                            suggested_actions.append({
                                "action": "archive_item",
                                "item_id": item["id"],
                                "module": module,
                                "reason": f"Baja relevancia ({relevance_score:.2f}) y sin uso"
                            })
        
        # Retornar resultados
        return {
            "total_items_reviewed": total_items_reviewed,
            "potential_duplicates": potential_duplicates,
            "low_relevance_items": low_relevance_items,
            "suggested_actions": suggested_actions
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error al revisar prioridades: {str(e)}")

@router.post("/ajustar", response_model=Item)
async def adjust_priority(request: PriorityAdjustRequest, principal: Principal = Depends(require_scope("write"))):
    """
    Permite modificar manualmente la prioridad de un elemento.
    """
    try:
        # Verificar que el módulo es válido
        valid_modules = ["identity", "business", "reminders", "learnings"]
        if request.module not in valid_modules:
            raise HTTPException(status_code=400, detail=f"Módulo '{request.module}' no válido")
        
        # Verificar que el nivel de prioridad es válido
        valid_priorities = ["high", "medium", "low"]
        if request.priority_level not in valid_priorities:
            raise HTTPException(status_code=400, detail=f"Nivel de prioridad '{request.priority_level}' no válido")
        
        # Verificar que el item existe
        item = db_manager.get_item(
            collection_key=request.module,
            id=request.item_id,
            tenant_id=principal.tenant_id
        )
        
        if not item:
            raise HTTPException(status_code=404, detail=f"Item con ID '{request.item_id}' no encontrado en el módulo '{request.module}'")
        
        # Buscar si ya existe un registro de prioridad para este item
        priority_records = db_manager.list_items(collection_key=COLLECTION_KEY, limit=None, tenant_id=principal.tenant_id)
        priority_record = next((p for p in priority_records if p["metadata"].get("item_id") == request.item_id and p["metadata"].get("module") == request.module), None)
        
        if priority_record:
            # Actualizar el registro existente
            priority_id = priority_record["id"]
            
            # Preparar los metadatos actualizados
            updated_metadata = priority_record["metadata"].copy()
            updated_metadata["priority_level"] = request.priority_level
            if request.relevance_score is not None:
                updated_metadata["relevance_score"] = request.relevance_score
            updated_metadata["updated_at"] = datetime.now().isoformat()
            
            # Actualizar el registro
            updated_record = db_manager.update_item(
                collection_key=COLLECTION_KEY,
                id=priority_id,
                text=f"Prioridad para item '{item['text'][:50]}...' en módulo '{request.module}'",
                metadata=updated_metadata,
                tenant_id=principal.tenant_id
            )
            
            return updated_record
        else:
            # Crear un nuevo registro de prioridad
            priority_id = generate_id()
            
            # Preparar los metadatos
            metadata = {
                "item_id": request.item_id,
                "module": request.module,
                "priority_level": request.priority_level,
                "relevance_score": request.relevance_score if request.relevance_score is not None else 0.5,
                "usage_count": 0,
                "last_accessed": datetime.now().isoformat(),
                "is_duplicate": False,
                "duplicate_of": None,
                "created_at": datetime.now().isoformat(),
                "updated_at": datetime.now().isoformat()
            }
            
            # Crear el registro
            result = db_manager.add_item(
                collection_key=COLLECTION_KEY,
                id=priority_id,
                text=f"Prioridad para item '{item['text'][:50]}...' en módulo '{request.module}'",
                metadata=metadata,
                tenant_id=principal.tenant_id
            )
            
            return {
                "id": result["id"],
                "text": result["text"],
                "metadata": result["metadata"]
            }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error al ajustar la prioridad: {str(e)}")

@router.post("/optimizar", response_model=PriorityOptimizeResult)
async def optimize_priorities(request: PriorityOptimizeRequest, principal: Principal = Depends(require_scope("write"))):
    """
    Reorganiza automáticamente la información según su importancia.
    """
    try:
        # Definir los módulos a optimizar
        valid_modules = ["identity", "business", "reminders", "learnings"]
        modules_to_optimize = [request.module] if request.module else valid_modules
        
        # Validar que los módulos son válidos
        for module in modules_to_optimize:
            if module not in valid_modules:
                raise HTTPException(status_code=400, detail=f"Módulo '{module}' no válido")
        
        # Inicializar resultados
        total_items_optimized = 0
        merged_duplicates = []
        archived_items = []
        reprioritized_items = []
        
        # Primero, realizar una revisión para identificar duplicados y items de baja relevancia
        review_request = PriorityReviewRequest(
            module=request.module,
            min_similarity=0.9,  # Umbral alto para fusiones automáticas
            max_items=1000,
            include_low_relevance=True,
            include_duplicates=True
        )
        
        review_result = await review_priorities(review_request, principal)
        
        # Procesar duplicados si se solicita
        if request.auto_merge_duplicates:
            # Agrupar duplicados por item principal
            duplicate_groups = defaultdict(list)
            
            for duplicate in review_result["potential_duplicates"]:
                if duplicate["suggested_action"] == "merge":
                    # Usar el ID del primer item como clave del grupo
                    group_key = duplicate["item1"]["id"]
                    duplicate_groups[group_key].append(duplicate["item2"])
            
            # Fusionar cada grupo de duplicados
            for primary_id, duplicates in duplicate_groups.items():
                # Obtener el módulo del item principal
                module = next((d["item1"]["module"] for d in review_result["potential_duplicates"] 
                              if d["item1"]["id"] == primary_id), None)
                
                if not module:
                    continue
                
                # Obtener el item principal
                primary_item = db_manager.get_item(
                    collection_key=module,
                    id=primary_id,
                    tenant_id=principal.tenant_id
                )
                
                if not primary_item:
                    continue
                
                # Fusionar los duplicados
                for duplicate in duplicates:
                    duplicate_id = duplicate["id"]
                    duplicate_module = duplicate["module"]
                    
                    # Obtener el item duplicado
                    duplicate_item = db_manager.get_item(
                        collection_key=duplicate_module,
                        id=duplicate_id,
                        tenant_id=principal.tenant_id
                    )
                    
                    if not duplicate_item:
                        continue
                    
                    # Registrar la fusión
                    merged_duplicates.append({
                        "primary_item": {
                            "id": primary_id,
                            "text": primary_item["text"][:100] + "..." if len(primary_item["text"]) > 100 else primary_item["text"],
                            "module": module
                        },
                        "duplicate_item": {
                            "id": duplicate_id,
                            "text": duplicate_item["text"][:100] + "..." if len(duplicate_item["text"]) > 100 else duplicate_item["text"],
                            "module": duplicate_module
                        }
                    })
                    
                    # Actualizar el registro de prioridad del duplicado
                    priority_records = db_manager.list_items(collection_key=COLLECTION_KEY, limit=None, tenant_id=principal.tenant_id)
                    priority_record = next((p for p in priority_records if p["metadata"].get("item_id") == duplicate_id and p["metadata"].get("module") == duplicate_module), None)
                    
                    if priority_record:
                        # Marcar como duplicado
                        updated_metadata = priority_record["metadata"].copy()
                        updated_metadata["is_duplicate"] = True
                        updated_metadata["duplicate_of"] = primary_id
                        updated_metadata["updated_at"] = datetime.now().isoformat()
                        
                        db_manager.update_item(
                            collection_key=COLLECTION_KEY,
                            id=priority_record["id"],
                            metadata=updated_metadata,
                            tenant_id=principal.tenant_id
                        )
                    
                    total_items_optimized += 1
        
        # Archivar items de baja relevancia si se solicita
        if request.auto_archive_low_relevance:
            for item in review_result["low_relevance_items"]:
                if item["suggested_action"] == "archive":
                    item_id = item["id"]
                    module = item["module"]
                    
                    # Obtener el item
                    low_relevance_item = db_manager.get_item(
                        collection_key=module,
                        id=item_id,
                        tenant_id=principal.tenant_id
                    )
                    
                    if not low_relevance_item:
                        continue
                    
                    # Registrar el archivado
                    archived_items.append({
                        "id": item_id,
                        "text": low_relevance_item["text"][:100] + "..." if len(low_relevance_item["text"]) > 100 else low_relevance_item["text"],
                        "module": module,
                        "relevance_score": item["relevance_score"]
                    })
                    
                    # Actualizar el registro de prioridad
                    priority_records = db_manager.list_items(collection_key=COLLECTION_KEY, limit=None, tenant_id=principal.tenant_id)
                    priority_record = next((p for p in priority_records if p["metadata"].get("item_id") == item_id and p["metadata"].get("module") == module), None)
                    
                    if priority_record:
                        # Marcar como archivado
                        updated_metadata = priority_record["metadata"].copy()
                        updated_metadata["priority_level"] = "archived"
                        updated_metadata["updated_at"] = datetime.now().isoformat()
                        
                        db_manager.update_item(
                            collection_key=COLLECTION_KEY,
                            id=priority_record["id"],
                            metadata=updated_metadata,
                            tenant_id=principal.tenant_id
                        )
                    else:
                        # Crear un nuevo registro de prioridad
                        priority_id = generate_id()
                        
                        metadata = {
                            "item_id": item_id,
                            "module": module,
                            "priority_level": "archived",
                            "relevance_score": item["relevance_score"],
                            "usage_count": 0,
                            "last_accessed": datetime.now().isoformat(),
                            "is_duplicate": False,
                            "duplicate_of": None,
                            "created_at": datetime.now().isoformat(),
                            "updated_at": datetime.now().isoformat()
                        }
                        
                        db_manager.add_item(
                            collection_key=COLLECTION_KEY,
                            id=priority_id,
                            text=f"Prioridad para item '{low_relevance_item['text'][:50]}...' en módulo '{module}'",
                            metadata=metadata,
                            tenant_id=principal.tenant_id
                        )
                    
                    total_items_optimized += 1
        
        # Repriorizar items basados en su uso y relevancia
        for module in modules_to_optimize:
            # Obtener todos los items del módulo
            items = db_manager.list_items(collection_key=module, limit=None, tenant_id=principal.tenant_id)
            
            for item in items:
                # Verificar si ya existe un registro de prioridad
                priority_records = db_manager.list_items(collection_key=COLLECTION_KEY, limit=None, tenant_id=principal.tenant_id)
                priority_record = next((p for p in priority_records if p["metadata"].get("item_id") == item["id"] and p["metadata"].get("module") == module), None)
                
                if priority_record:
                    # Calcular nueva prioridad basada en uso y relevancia
                    usage_count = priority_record["metadata"].get("usage_count", 0)
                    relevance_score = priority_record["metadata"].get("relevance_score", 0.5)
                    current_priority = priority_record["metadata"].get("priority_level", "medium")
                    
                    # Lógica simple de repriorización
                    new_priority = current_priority
                    if usage_count > 10 and relevance_score > 0.7:
                        new_priority = "high"
                    elif usage_count < 2 and relevance_score < 0.3:
                        new_priority = "low"
                    
                    # Si la prioridad cambió, actualizar
                    if new_priority != current_priority and current_priority != "archived":
                        updated_metadata = priority_record["metadata"].copy()
                        updated_metadata["priority_level"] = new_priority
                        updated_metadata["updated_at"] = datetime.now().isoformat()
                        
                        db_manager.update_item(
                            collection_key=COLLECTION_KEY,
                            id=priority_record["id"],
                            metadata=updated_metadata,
                            tenant_id=principal.tenant_id
                        )
                        
                        reprioritized_items.append({
                            "id": item["id"],
                            "text": item["text"][:100] + "..." if len(item["text"]) > 100 else item["text"],
                            "module": module,
                            "old_priority": current_priority,
                            "new_priority": new_priority
                        })
                        
                        total_items_optimized += 1
        
        # Retornar resultados
        return {
            "total_items_optimized": total_items_optimized,
            "merged_duplicates": merged_duplicates,
            "archived_items": archived_items,
            "reprioritized_items": reprioritized_items
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error al optimizar prioridades: {str(e)}")

@router.get("/", response_model=ItemList)
async def list_priorities(
    limit: int = Query(100, ge=1, le=1000, description="Número máximo de items a retornar"),
    offset: int = Query(0, ge=0, description="Número de items a saltar"),
    module: Optional[str] = Query(None, description="Filtrar por módulo"),
    priority_level: Optional[str] = Query(None, description="Filtrar por nivel de prioridad"),
    is_duplicate: Optional[bool] = Query(None, description="Filtrar por estado de duplicado"),
    principal: Principal = Depends(require_scope("read"))
):
    """
    Lista todos los registros de prioridad.
    """
    try:
        # Obtener todos los registros
        all_items = db_manager.list_items(collection_key=COLLECTION_KEY, limit=None, tenant_id=principal.tenant_id)
        
        # Aplicar filtros si se proporcionan
        filtered_items = all_items
        
        if module:
            filtered_items = [item for item in filtered_items if item["metadata"].get("module") == module]
        
        if priority_level:
            filtered_items = [item for item in filtered_items if item["metadata"].get("priority_level") == priority_level]
        
        if is_duplicate is not None:
            filtered_items = [item for item in filtered_items if item["metadata"].get("is_duplicate") == is_duplicate]
        
        # Aplicar paginación
        start_idx = min(offset, len(filtered_items))
        end_idx = min(start_idx + limit, len(filtered_items))
        
        paginated_items = filtered_items[start_idx:end_idx]
        
        return {
            "items": paginated_items,
            "total": len(filtered_items)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error al listar prioridades: {str(e)}")

@router.get("/{priority_id}", response_model=Item)
async def get_priority(
    priority_id: str = Path(..., description="ID del registro de prioridad a obtener"),
    principal: Principal = Depends(require_scope("read"))
):
    """
    Obtiene un registro de prioridad específico.
    """
    try:
        item = db_manager.get_item(
            collection_key=COLLECTION_KEY,
            id=priority_id,
            tenant_id=principal.tenant_id
        )
        
        if not item:
            raise HTTPException(status_code=404, detail=f"Registro de prioridad con ID '{priority_id}' no encontrado")
        
        return item
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error al obtener el registro de prioridad: {str(e)}")

@router.delete("/{priority_id}")
async def delete_priority(
    priority_id: str = Path(..., description="ID del registro de prioridad a eliminar"),
    principal: Principal = Depends(require_scope("write"))
):
    """
    Elimina un registro de prioridad.
    """
    try:
        result = db_manager.delete_item(
            collection_key=COLLECTION_KEY,
            id=priority_id,
            tenant_id=principal.tenant_id
        )
        
        return result
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error al eliminar el registro de prioridad: {str(e)}") 