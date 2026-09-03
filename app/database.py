import chromadb
from chromadb.config import Settings
from chromadb.errors import NotFoundError
from app.config import CHROMA_DB_DIR, COLLECTIONS
from app.utils.embeddings import get_embedding_function

class ChromaDBManager:
    """Gestor de conexión y operaciones con ChromaDB."""
    
    def __init__(self):
        """Inicializa la conexión con ChromaDB."""
        self.client = chromadb.PersistentClient(
            path=CHROMA_DB_DIR,
            settings=Settings(allow_reset=True)
        )
        self.embedding_function = get_embedding_function()
        self._initialize_collections()
    
    def _initialize_collections(self):
        """Inicializa las colecciones si no existen."""
        self.collections = {}
        
        for key, name in COLLECTIONS.items():
            try:
                # Intentar obtener la colección
                collection = self.client.get_collection(
                    name=name,
                    embedding_function=self.embedding_function
                )
            except NotFoundError:
                # Si no existe, crearla
                collection = self.client.create_collection(
                    name=name,
                    embedding_function=self.embedding_function
                )
            
            self.collections[key] = collection
    
    def get_collection(self, collection_key):
        """Obtiene una colección por su clave."""
        if collection_key not in self.collections:
            raise ValueError(f"Colección '{collection_key}' no encontrada")
        
        return self.collections[collection_key]
    
    def add_item(self, collection_key, id, text, metadata=None):
        """Añade un item a una colección."""
        collection = self.get_collection(collection_key)
        
        collection.add(
            ids=[id],
            documents=[text],
            metadatas=[metadata or {}]
        )
        
        return {"id": id, "text": text, "metadata": metadata}
    
    def query_items(self, collection_key, query_text, n_results=5, filter=None):
        """Consulta items en una colección por similitud semántica."""
        collection = self.get_collection(collection_key)
        
        results = collection.query(
            query_texts=[query_text],
            n_results=n_results,
            where=filter
        )
        
        return results
    
    def get_item(self, collection_key, id):
        """Obtiene un item por su ID."""
        collection = self.get_collection(collection_key)
        
        results = collection.get(
            ids=[id]
        )
        
        if not results["ids"]:
            return None
        
        return {
            "id": results["ids"][0],
            "text": results["documents"][0],
            "metadata": results["metadatas"][0] if results["metadatas"] else {}
        }
    
    def update_item(self, collection_key, id, text=None, metadata=None):
        """Actualiza un item existente."""
        collection = self.get_collection(collection_key)
        
        # Obtener el item actual
        current_item = self.get_item(collection_key, id)
        if not current_item:
            raise ValueError(f"Item con ID '{id}' no encontrado")
        
        # Actualizar solo los campos proporcionados
        update_text = text if text is not None else current_item["text"]
        update_metadata = metadata if metadata is not None else current_item["metadata"]
        
        # Realizar la actualización
        collection.update(
            ids=[id],
            documents=[update_text],
            metadatas=[update_metadata]
        )
        
        return {
            "id": id,
            "text": update_text,
            "metadata": update_metadata
        }
    
    def delete_item(self, collection_key, id):
        """Elimina un item por su ID."""
        collection = self.get_collection(collection_key)
        
        # Verificar que el item existe
        item = self.get_item(collection_key, id)
        if not item:
            raise ValueError(f"Item con ID '{id}' no encontrado")
        
        # Eliminar el item
        collection.delete(ids=[id])
        
        return {"message": f"Item con ID '{id}' eliminado correctamente"}
    
    def list_items(self, collection_key, limit=100, offset=0):
        """Lista todos los items de una colección."""
        collection = self.get_collection(collection_key)
        
        # Obtener todos los items
        results = collection.get()
        
        # Aplicar paginación
        start_idx = min(offset, len(results["ids"]) if results["ids"] else 0)
        end_idx = min(start_idx + limit, len(results["ids"]) if results["ids"] else 0)
        
        items = []
        for i in range(start_idx, end_idx):
            items.append({
                "id": results["ids"][i],
                "text": results["documents"][i],
                "metadata": results["metadatas"][i] if results["metadatas"] else {}
            })
        
        return items

# Instancia global del gestor de ChromaDB
db_manager = ChromaDBManager()