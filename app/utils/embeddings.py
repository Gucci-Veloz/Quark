"""Embeddings E5 para ChromaDB (specs.md §5).

Los modelos E5 exigen prefijos: ``"passage: "`` para los documentos que se
indexan y ``"query: "`` para las consultas. ChromaDB 1.5.x distingue ambos
casos: ``collection.add/update/upsert`` llaman a ``__call__`` y
``collection.query`` llama a ``embed_query``. ``E5EmbeddingFunction``
implementa los dos métodos con el prefijo que corresponde.
"""
from typing import Any, Callable, Dict, List, Optional

from chromadb.api.types import Documents, EmbeddingFunction, Embeddings

from app.config import EMBEDDING_MODEL

PASSAGE_PREFIX = "passage: "
QUERY_PREFIX = "query: "


class E5EmbeddingFunction(EmbeddingFunction[Documents]):
    """Función de embedding E5 con prefijos passage/query.

    El modelo se carga de forma perezosa (primer uso) para que importar la
    app no descargue ni cargue ~1.1 GB. ``model`` permite inyectar un objeto
    con ``encode(list[str], **kwargs)`` (tests).
    """

    def __init__(self, model_name: Optional[str] = None, model: Any = None):
        self._model_name = model_name or EMBEDDING_MODEL
        self._model = model

    def _get_model(self) -> Any:
        if self._model is None:
            from sentence_transformers import SentenceTransformer

            self._model = SentenceTransformer(self._model_name)
        return self._model

    def _encode(self, texts: List[str], prefix: str) -> Embeddings:
        prefixed = [prefix + t for t in texts]
        vectors = self._get_model().encode(
            prefixed, normalize_embeddings=True, convert_to_numpy=True
        )
        return [list(map(float, v)) for v in vectors]

    def __call__(self, input: Documents) -> Embeddings:
        """Indexación: antepone ``"passage: "``."""
        return self._encode(list(input), PASSAGE_PREFIX)

    def embed_query(self, input: Documents) -> Embeddings:
        """Consulta: antepone ``"query: "``."""
        return self._encode(list(input), QUERY_PREFIX)

    @staticmethod
    def name() -> str:
        return "quark_e5"

    def default_space(self) -> Any:
        return "cosine"

    def supported_spaces(self) -> List[Any]:
        return ["cosine", "l2", "ip"]

    def get_config(self) -> Dict[str, Any]:
        return {"model_name": self._model_name}

    @staticmethod
    def build_from_config(config: Dict[str, Any]) -> "E5EmbeddingFunction":
        return E5EmbeddingFunction(model_name=config.get("model_name"))


_default_ef: Optional[E5EmbeddingFunction] = None


def get_embedding_function(
    model_name: Optional[str] = None, model: Any = None
) -> E5EmbeddingFunction:
    """Retorna la función de embedding E5 usada por ChromaDB.

    Sin argumentos devuelve una instancia compartida (un solo modelo en memoria).
    """
    global _default_ef
    if model_name is not None or model is not None:
        return E5EmbeddingFunction(model_name=model_name, model=model)
    if _default_ef is None:
        _default_ef = E5EmbeddingFunction()
    return _default_ef


def get_embedding_model():
    """Retorna el modelo SentenceTransformer (acceso directo, sin prefijos).

    Quien lo use debe anteponer ``"passage: "``/``"query: "`` por su cuenta;
    preferir ``embed_passages`` / ``cosine_similarity``.
    """
    return get_embedding_function()._get_model()


def embed_passages(texts: List[str]) -> Embeddings:
    """Embeddings normalizados de textos como documentos (prefijo ``passage: ``)."""
    return get_embedding_function()(texts)


def cosine_similarity(text_a: str, text_b: str) -> float:
    """Similitud coseno entre dos textos tratados como documentos."""
    a, b = embed_passages([text_a, text_b])
    return float(sum(x * y for x, y in zip(a, b)))  # vectores ya normalizados
