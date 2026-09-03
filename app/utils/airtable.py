from pyairtable import Api, Table
from typing import Dict, List, Optional, Any, cast, Sequence
from app.config import AIRTABLE_API_KEY, AIRTABLE_BASE_ID, AIRTABLE_TABLE_ID

class AirtableManager:
    """Gestor de conexión y operaciones con Airtable."""

    def __init__(self):
        """Inicializa la conexión con Airtable, si hay credenciales configuradas."""
        if AIRTABLE_API_KEY and AIRTABLE_BASE_ID:
            self.api = Api(AIRTABLE_API_KEY)
            self.table = Table(AIRTABLE_API_KEY, AIRTABLE_BASE_ID, AIRTABLE_TABLE_ID)
        else:
            self.api = None
            self.table = None

    def _require_table(self) -> Table:
        if self.table is None:
            raise ValueError(
                "Airtable no está configurado: faltan AIRTABLE_API_KEY/AIRTABLE_BASE_ID"
            )
        return self.table

    def create_record(self, fields: Dict[str, Any]) -> Dict[str, Any]:
        """Crea un nuevo registro en Airtable."""
        try:
            record = self._require_table().create(fields)
            return cast(Dict[str, Any], record)
        except Exception as e:
            raise ValueError(f"Error al crear registro en Airtable: {str(e)}")
    
    def get_record(self, record_id: str) -> Dict[str, Any]:
        """Obtiene un registro específico de Airtable."""
        try:
            record = self._require_table().get(record_id)
            return cast(Dict[str, Any], record)
        except Exception as e:
            raise ValueError(f"Error al obtener registro de Airtable: {str(e)}")
    
    def list_records(self, formula: Optional[str] = None, max_records: Optional[int] = None) -> Sequence[Dict[str, Any]]:
        """Lista registros de Airtable con filtros opcionales."""
        try:
            records = self._require_table().all(formula=formula, max_records=max_records)
            return cast(Sequence[Dict[str, Any]], records)
        except Exception as e:
            raise ValueError(f"Error al listar registros de Airtable: {str(e)}")
    
    def update_record(self, record_id: str, fields: Dict[str, Any]) -> Dict[str, Any]:
        """Actualiza un registro existente en Airtable."""
        try:
            record = self._require_table().update(record_id, fields)
            return cast(Dict[str, Any], record)
        except Exception as e:
            raise ValueError(f"Error al actualizar registro en Airtable: {str(e)}")
    
    def delete_record(self, record_id: str) -> Dict[str, Any]:
        """Elimina un registro de Airtable."""
        try:
            result = self._require_table().delete(record_id)
            return cast(Dict[str, Any], result)
        except Exception as e:
            raise ValueError(f"Error al eliminar registro de Airtable: {str(e)}")
    
    def search_records(self, field_name: str, value: Any) -> List[Dict[str, Any]]:
        """Busca registros en Airtable por un campo específico."""
        formula = f"{{{field_name}}} = '{value}'"
        return list(self.list_records(formula=formula))
    
    def sync_to_airtable(self, collection_key: str, item_id: str, item_data: Dict[str, Any]) -> Dict[str, Any]:
        """Sincroniza un item de ChromaDB a Airtable."""
        # Preparar los datos para Airtable
        airtable_data = {
            "collection_key": collection_key,
            "item_id": item_id,
            "text": item_data.get("text", ""),
        }
        
        # Añadir metadatos si existen
        metadata = item_data.get("metadata", {})
        for key, value in metadata.items():
            # Airtable no acepta objetos anidados, así que convertimos a string si es necesario
            if isinstance(value, (dict, list)):
                airtable_data[f"metadata_{key}"] = str(value)
            else:
                airtable_data[f"metadata_{key}"] = value
        
        # Buscar si ya existe un registro con este item_id
        existing_records = self.search_records("item_id", item_id)
        
        if existing_records:
            # Actualizar el registro existente
            return self.update_record(existing_records[0]["id"], airtable_data)
        else:
            # Crear un nuevo registro
            return self.create_record(airtable_data)
    
    def sync_from_airtable(self, record_id: str) -> Dict[str, Any]:
        """Obtiene datos de un registro de Airtable para sincronizar con ChromaDB."""
        record = self.get_record(record_id)
        fields = record.get("fields", {})
        
        # Extraer datos básicos
        item_data = {
            "collection_key": fields.get("collection_key"),
            "item_id": fields.get("item_id"),
            "text": fields.get("text", ""),
            "metadata": {}
        }
        
        # Extraer metadatos
        for key, value in fields.items():
            if key.startswith("metadata_"):
                metadata_key = key.replace("metadata_", "")
                item_data["metadata"][metadata_key] = value
        
        return item_data

# Instancia global del gestor de Airtable
airtable_manager = AirtableManager()