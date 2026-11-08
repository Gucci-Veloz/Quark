from fastapi import APIRouter, HTTPException, Query, Path, Depends, Body
from typing import List, Dict, Optional, Any
from datetime import datetime
from collections import Counter, defaultdict

from app.database import db_manager
from app.utils.auth import Principal, require_scope
from app.models.schemas import (
    Item, SuggestionItemCreate, SuggestionItemUpdate,
    SuggestionRequest, SuggestionAnalysisRequest, SuggestionResult,
    ItemList, QueryResult, generate_id
)
from app.utils.embeddings import cosine_similarity, embed_passages

router = APIRouter(
    prefix="/sugerencias",
    tags=["sugerencias"],
    responses={404: {"description": "No encontrado"}},
)

COLLECTION_KEY = "suggestions"

@router.post("/obtener", response_model=SuggestionResult)
async def get_suggestions(request: SuggestionRequest, principal: Principal = Depends(require_scope("write"))):
    """
    Genera sugerencias en función de los datos almacenados.
    
    Este endpoint:
    1. Analiza los datos en los módulos especificados
    2. Identifica patrones y tendencias
    3. Genera sugerencias basadas en el análisis
    """
    try:
        # Definir los módulos a analizar
        valid_modules = ["identity", "business", "reminders", "learnings"]
        modules_to_analyze = request.modules if request.modules else valid_modules
        
        # Validar que los módulos son válidos
        for module in modules_to_analyze:
            if module not in valid_modules:
                raise HTTPException(status_code=400, detail=f"Módulo '{module}' no válido")
        
        # Validar tipos de sugerencias
        valid_types = ["action", "insight", "connection"]
        suggestion_types = request.suggestion_types if request.suggestion_types else valid_types
        
        for stype in suggestion_types:
            if stype not in valid_types:
                raise HTTPException(status_code=400, detail=f"Tipo de sugerencia '{stype}' no válido")
        
        # Inicializar resultados
        suggestions = []
        by_type = {t: 0 for t in valid_types}
        analysis_summary = "Análisis de datos:\n\n"
        
        # Recopilar datos de todos los módulos
        all_data = {}
        for module in modules_to_analyze:
            all_data[module] = db_manager.list_items(collection_key=module, limit=None, tenant_id=principal.tenant_id)
        
        # Análisis 1: Identificar temas frecuentes
        all_texts = []
        for module, items in all_data.items():
            all_texts.extend([item["text"] for item in items])
        
        # Usar el modelo de embeddings para agrupar textos similares
        if all_texts:
            embeddings = embed_passages(all_texts)
            
            # Agrupar textos similares (implementación simplificada)
            clusters = defaultdict(list)
            for i, text in enumerate(all_texts):
                # Asignar cada texto a un grupo basado en similitud
                # (En una implementación real, usaríamos un algoritmo de clustering)
                cluster_id = i % 5  # Simplificación: asignar a 5 grupos
                clusters[cluster_id].append(text)
            
            # Identificar temas principales
            main_themes = []
            for cluster_id, texts in clusters.items():
                if len(texts) > 1:
                    # Seleccionar el texto más representativo del grupo
                    main_themes.append(texts[0][:100] + "...")
            
            # Añadir al resumen
            analysis_summary += "Temas principales identificados:\n"
            for i, theme in enumerate(main_themes[:3], 1):
                analysis_summary += f"{i}. {theme}\n"
            analysis_summary += "\n"
            
            # Generar sugerencias de tipo "insight" basadas en temas
            if "insight" in suggestion_types and main_themes:
                for theme in main_themes[:min(2, request.max_suggestions)]:
                    suggestion_id = generate_id()
                    suggestion_text = f"Se ha identificado un tema recurrente: '{theme}'. Considera profundizar en este tema."
                    
                    metadata = {
                        "type": "insight",
                        "context": "análisis de temas",
                        "relevance_score": 0.8,
                        "source_modules": modules_to_analyze,
                        "source_items": [],
                        "is_implemented": False,
                        "implementation_date": None,
                        "created_at": datetime.now().isoformat(),
                        "updated_at": datetime.now().isoformat()
                    }
                    
                    # Guardar la sugerencia
                    result = db_manager.add_item(
                        collection_key=COLLECTION_KEY,
                        id=suggestion_id,
                        text=suggestion_text,
                        metadata=metadata,
                        tenant_id=principal.tenant_id
                    )
                    
                    suggestions.append({
                        "id": result["id"],
                        "text": result["text"],
                        "metadata": result["metadata"]
                    })
                    
                    by_type["insight"] += 1
        
        # Análisis 2: Identificar items sin actividad reciente
        if "action" in suggestion_types:
            inactive_items = []
            
            for module, items in all_data.items():
                for item in items:
                    # Verificar si tiene registro de prioridad
                    priority_records = db_manager.list_items(collection_key="priorities", limit=None, tenant_id=principal.tenant_id)
                    priority_record = next((p for p in priority_records if p["metadata"].get("item_id") == item["id"] and p["metadata"].get("module") == module), None)
                    
                    if priority_record:
                        last_accessed = priority_record["metadata"].get("last_accessed")
                        if last_accessed:
                            # Simplificación: comparar solo la fecha (no la hora)
                            last_date = last_accessed.split("T")[0]
                            today = datetime.now().isoformat().split("T")[0]
                            
                            # Si la fecha es diferente, considerar como inactivo
                            if last_date != today:
                                inactive_items.append({
                                    "id": item["id"],
                                    "text": item["text"],
                                    "module": module
                                })
            
            # Generar sugerencias de tipo "action" basadas en items inactivos
            if inactive_items:
                # Limitar a 2 sugerencias de este tipo
                for inactive_item in inactive_items[:min(2, request.max_suggestions - len(suggestions))]:
                    suggestion_id = generate_id()
                    suggestion_text = f"Revisa y actualiza el item: '{inactive_item['text'][:100]}...'"
                    
                    metadata = {
                        "type": "action",
                        "context": "items inactivos",
                        "relevance_score": 0.7,
                        "source_modules": [inactive_item["module"]],
                        "source_items": [inactive_item["id"]],
                        "is_implemented": False,
                        "implementation_date": None,
                        "created_at": datetime.now().isoformat(),
                        "updated_at": datetime.now().isoformat()
                    }
                    
                    # Guardar la sugerencia
                    result = db_manager.add_item(
                        collection_key=COLLECTION_KEY,
                        id=suggestion_id,
                        text=suggestion_text,
                        metadata=metadata,
                        tenant_id=principal.tenant_id
                    )
                    
                    suggestions.append({
                        "id": result["id"],
                        "text": result["text"],
                        "metadata": result["metadata"]
                    })
                    
                    by_type["action"] += 1
        
        # Análisis 3: Identificar posibles conexiones entre módulos
        if "connection" in suggestion_types and len(modules_to_analyze) > 1:
            # Seleccionar items representativos de cada módulo
            representative_items = {}
            for module, items in all_data.items():
                if items:
                    # Simplificación: seleccionar los primeros 5 items
                    representative_items[module] = items[:5]
            
            # Buscar conexiones entre módulos
            potential_connections = []
            
            for module1, items1 in representative_items.items():
                for module2, items2 in representative_items.items():
                    # Evitar comparar un módulo consigo mismo
                    if module1 >= module2:
                        continue
                    
                    for item1 in items1:
                        for item2 in items2:
                            # Comparar textos usando el modelo de embeddings
                            # Calcular similitud coseno (embeddings E5 con prefijo passage)
                            similarity = cosine_similarity(item1["text"], item2["text"])
                            
                            # Si la similitud supera el umbral, registrar como posible conexión
                            if similarity >= 0.7:
                                potential_connections.append({
                                    "item1": {
                                        "id": item1["id"],
                                        "text": item1["text"][:100] + "..." if len(item1["text"]) > 100 else item1["text"],
                                        "module": module1
                                    },
                                    "item2": {
                                        "id": item2["id"],
                                        "text": item2["text"][:100] + "..." if len(item2["text"]) > 100 else item2["text"],
                                        "module": module2
                                    },
                                    "similarity": similarity
                                })
            
            # Generar sugerencias de tipo "connection" basadas en conexiones potenciales
            if potential_connections:
                # Ordenar por similitud y limitar
                sorted_connections = sorted(potential_connections, key=lambda x: x["similarity"], reverse=True)
                
                for connection in sorted_connections[:min(2, request.max_suggestions - len(suggestions))]:
                    suggestion_id = generate_id()
                    suggestion_text = f"Se ha detectado una posible conexión entre '{connection['item1']['text']}' y '{connection['item2']['text']}'"
                    
                    metadata = {
                        "type": "connection",
                        "context": "conexiones entre módulos",
                        "relevance_score": connection["similarity"],
                        "source_modules": [connection["item1"]["module"], connection["item2"]["module"]],
                        "source_items": [connection["item1"]["id"], connection["item2"]["id"]],
                        "is_implemented": False,
                        "implementation_date": None,
                        "created_at": datetime.now().isoformat(),
                        "updated_at": datetime.now().isoformat()
                    }
                    
                    # Guardar la sugerencia
                    result = db_manager.add_item(
                        collection_key=COLLECTION_KEY,
                        id=suggestion_id,
                        text=suggestion_text,
                        metadata=metadata,
                        tenant_id=principal.tenant_id
                    )
                    
                    suggestions.append({
                        "id": result["id"],
                        "text": result["text"],
                        "metadata": result["metadata"]
                    })
                    
                    by_type["connection"] += 1
        
        # Filtrar por relevancia mínima
        if request.min_relevance > 0:
            suggestions = [s for s in suggestions if s["metadata"].get("relevance_score", 0) >= request.min_relevance]
        
        # Limitar al número máximo de sugerencias
        suggestions = suggestions[:request.max_suggestions]
        
        # Actualizar conteo por tipo
        by_type = Counter([s["metadata"].get("type", "unknown") for s in suggestions])
        
        # Completar el resumen del análisis
        analysis_summary += f"Total de sugerencias generadas: {len(suggestions)}\n"
        for stype, count in by_type.items():
            analysis_summary += f"- {stype}: {count}\n"
        
        return {
            "suggestions": suggestions,
            "total": len(suggestions),
            "by_type": dict(by_type),
            "analysis_summary": analysis_summary
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error al generar sugerencias: {str(e)}")

@router.get("/listar", response_model=ItemList)
async def list_suggestions(
    limit: int = Query(100, ge=1, le=1000, description="Número máximo de sugerencias a retornar"),
    offset: int = Query(0, ge=0, description="Número de sugerencias a saltar"),
    type: Optional[str] = Query(None, description="Filtrar por tipo de sugerencia"),
    is_implemented: Optional[bool] = Query(None, description="Filtrar por estado de implementación"),
    min_relevance: float = Query(0.0, ge=0.0, le=1.0, description="Relevancia mínima"),
    principal: Principal = Depends(require_scope("read"))
):
    """
    Muestra el historial de recomendaciones generadas.
    """
    try:
        # Obtener todas las sugerencias
        all_items = db_manager.list_items(collection_key=COLLECTION_KEY, limit=None, tenant_id=principal.tenant_id)
        
        # Aplicar filtros si se proporcionan
        filtered_items = all_items
        
        if type:
            filtered_items = [item for item in filtered_items if item["metadata"].get("type") == type]
        
        if is_implemented is not None:
            filtered_items = [item for item in filtered_items if item["metadata"].get("is_implemented") == is_implemented]
        
        if min_relevance > 0.0:
            filtered_items = [item for item in filtered_items if item["metadata"].get("relevance_score", 0.0) >= min_relevance]
        
        # Aplicar paginación
        start_idx = min(offset, len(filtered_items))
        end_idx = min(start_idx + limit, len(filtered_items))
        
        paginated_items = filtered_items[start_idx:end_idx]
        
        return {
            "items": paginated_items,
            "total": len(filtered_items)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error al listar sugerencias: {str(e)}")

@router.post("/analizar", response_model=SuggestionResult)
async def analyze_data(request: SuggestionAnalysisRequest, principal: Principal = Depends(require_scope("write"))):
    """
    Permite forzar un análisis de datos en cualquier momento.
    
    Este endpoint es similar a /obtener, pero permite especificar parámetros adicionales
    para el análisis, como el rango de tiempo y áreas de enfoque.
    """
    try:
        # Convertir la solicitud de análisis a una solicitud de sugerencias
        suggestion_request = SuggestionRequest(
            modules=request.modules,
            max_suggestions=10,  # Valor predeterminado
            suggestion_types=None,  # Todos los tipos
            min_relevance=0.5  # Umbral predeterminado
        )
        
        # Realizar el análisis básico
        base_result = await get_suggestions(suggestion_request, principal)
        
        # Enriquecer el análisis con información adicional
        analysis_summary = base_result["analysis_summary"]
        
        # Añadir información sobre el rango de tiempo si se proporciona
        if request.time_range:
            start_date = request.time_range.get("start_date", "")
            end_date = request.time_range.get("end_date", "")
            
            if start_date and end_date:
                analysis_summary += f"\nAnálisis para el período: {start_date} a {end_date}\n"
        
        # Añadir información sobre áreas de enfoque si se proporcionan
        if request.focus_areas:
            analysis_summary += "\nÁreas de enfoque:\n"
            for i, area in enumerate(request.focus_areas, 1):
                analysis_summary += f"{i}. {area}\n"
        
        # Actualizar el resultado con la información enriquecida
        result = base_result.copy()
        result["analysis_summary"] = analysis_summary
        
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error al analizar datos: {str(e)}")

@router.put("/{suggestion_id}", response_model=Item)
async def update_suggestion(
    suggestion_id: str = Path(..., description="ID de la sugerencia a actualizar"),
    item_update: SuggestionItemUpdate = Body(...),
    principal: Principal = Depends(require_scope("write"))
):
    """
    Actualiza una sugerencia existente.
    """
    try:
        # Verificar que la sugerencia existe
        existing_item = db_manager.get_item(
            collection_key=COLLECTION_KEY,
            id=suggestion_id,
            tenant_id=principal.tenant_id
        )
        
        if not existing_item:
            raise HTTPException(status_code=404, detail=f"Sugerencia con ID '{suggestion_id}' no encontrada")
        
        # Actualizar los metadatos si se proporcionan
        metadata = None
        if item_update.metadata is not None:
            metadata = existing_item["metadata"].copy()
            metadata.update(item_update.metadata)
            metadata["updated_at"] = datetime.now().isoformat()
        
        # Actualizar el item
        updated_item = db_manager.update_item(
            collection_key=COLLECTION_KEY,
            id=suggestion_id,
            text=item_update.text if item_update.text is not None else existing_item["text"],
            metadata=metadata,
            tenant_id=principal.tenant_id
        )
        
        return updated_item
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error al actualizar la sugerencia: {str(e)}")

@router.post("/{suggestion_id}/implementar", response_model=Item)
async def mark_as_implemented(
    suggestion_id: str = Path(..., description="ID de la sugerencia a marcar como implementada"),
    principal: Principal = Depends(require_scope("write"))
):
    """
    Marca una sugerencia como implementada.
    """
    try:
        # Verificar que la sugerencia existe
        existing_item = db_manager.get_item(
            collection_key=COLLECTION_KEY,
            id=suggestion_id,
            tenant_id=principal.tenant_id
        )
        
        if not existing_item:
            raise HTTPException(status_code=404, detail=f"Sugerencia con ID '{suggestion_id}' no encontrada")
        
        # Actualizar los metadatos
        metadata = existing_item["metadata"].copy()
        metadata["is_implemented"] = True
        metadata["implementation_date"] = datetime.now().isoformat()
        metadata["updated_at"] = datetime.now().isoformat()
        
        # Actualizar el item
        updated_item = db_manager.update_item(
            collection_key=COLLECTION_KEY,
            id=suggestion_id,
            metadata=metadata,
            tenant_id=principal.tenant_id
        )
        
        return updated_item
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error al marcar la sugerencia como implementada: {str(e)}")

@router.get("/{suggestion_id}", response_model=Item)
async def get_suggestion(
    suggestion_id: str = Path(..., description="ID de la sugerencia a obtener"),
    principal: Principal = Depends(require_scope("read"))
):
    """
    Obtiene una sugerencia específica.
    """
    try:
        item = db_manager.get_item(
            collection_key=COLLECTION_KEY,
            id=suggestion_id,
            tenant_id=principal.tenant_id
        )
        
        if not item:
            raise HTTPException(status_code=404, detail=f"Sugerencia con ID '{suggestion_id}' no encontrada")
        
        return item
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error al obtener la sugerencia: {str(e)}")

@router.delete("/{suggestion_id}")
async def delete_suggestion(
    suggestion_id: str = Path(..., description="ID de la sugerencia a eliminar"),
    principal: Principal = Depends(require_scope("write"))
):
    """
    Elimina una sugerencia.
    """
    try:
        result = db_manager.delete_item(
            collection_key=COLLECTION_KEY,
            id=suggestion_id,
            tenant_id=principal.tenant_id
        )
        
        return result
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error al eliminar la sugerencia: {str(e)}") 