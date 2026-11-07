"""Prefijos E5 (specs.md §5): "passage: " al indexar, "query: " al consultar."""
import numpy as np
import pytest

from app.database import ChromaDBManager
from app.utils import embeddings
from app.utils.embeddings import E5EmbeddingFunction, PASSAGE_PREFIX, QUERY_PREFIX
from tests.fake_embeddings import FakeE5Model


def test_prefix_constants():
    assert PASSAGE_PREFIX == "passage: "
    assert QUERY_PREFIX == "query: "


def test_call_indexes_with_passage_prefix():
    model = FakeE5Model()
    ef = E5EmbeddingFunction(model=model)
    vectors = ef(["hola mundo", "otro texto"])
    assert model.calls == [["passage: hola mundo", "passage: otro texto"]]
    assert len(vectors) == 2


def test_embed_query_uses_query_prefix():
    model = FakeE5Model()
    ef = E5EmbeddingFunction(model=model)
    ef.embed_query(["hola mundo"])
    assert model.calls == [["query: hola mundo"]]


def test_embeddings_are_normalized_lists_of_floats():
    ef = E5EmbeddingFunction(model=FakeE5Model())
    (vec,) = ef(["texto"])
    assert isinstance(vec, (list, np.ndarray))
    assert abs(float(np.linalg.norm(vec)) - 1.0) < 1e-5


def test_model_is_lazy_and_not_loaded_on_init(monkeypatch):
    def boom(*a, **k):
        raise AssertionError("no debe cargarse el modelo al instanciar")

    monkeypatch.setattr("sentence_transformers.SentenceTransformer", boom)
    ef = E5EmbeddingFunction(model_name="intfloat/multilingual-e5-base")
    assert ef.get_config() == {"model_name": "intfloat/multilingual-e5-base"}


def test_default_model_is_e5():
    assert embeddings.EMBEDDING_MODEL == "intfloat/multilingual-e5-base"


def test_config_roundtrip():
    ef = E5EmbeddingFunction(model_name="intfloat/multilingual-e5-base")
    rebuilt = E5EmbeddingFunction.build_from_config(ef.get_config())
    assert rebuilt.get_config() == ef.get_config()
    assert E5EmbeddingFunction.name() == "quark_e5"


def test_chromadb_add_uses_passage_and_query_uses_query(tmp_path):
    """ChromaDB 1.5.x: add -> __call__ (passage), query -> embed_query (query)."""
    model = FakeE5Model()
    manager = ChromaDBManager(path=str(tmp_path), embedding_function=E5EmbeddingFunction(model=model))
    manager.add_item("identity", "a", "me gusta el café", tenant_id="t1")
    assert model.calls[-1] == ["passage: me gusta el café"]

    manager.query_items("identity", "café", tenant_id="t1")
    assert model.calls[-1] == ["query: café"]

    manager.update_item("identity", "a", text="me gusta el té", tenant_id="t1")
    assert model.calls[-1] == ["passage: me gusta el té"]


def test_cosine_similarity_helper_uses_passage_prefix(monkeypatch):
    model = FakeE5Model()
    monkeypatch.setattr(embeddings, "_default_ef", E5EmbeddingFunction(model=model))
    sim = embeddings.cosine_similarity("gato negro", "gato negro")
    assert model.calls == [["passage: gato negro", "passage: gato negro"]]
    assert sim == pytest.approx(1.0, abs=1e-5)
