"""Modelo de embeddings simulado para tests (no descarga los ~1.1 GB de E5)."""
import hashlib
from typing import List

import numpy as np

DIM = 64


class FakeE5Model:
    """Imita `SentenceTransformer.encode`: bolsa de palabras hasheada y normalizada.

    Guarda en `calls` los textos recibidos (ya con prefijo) para poder
    comprobar que se aplican "passage: " y "query: ".
    """

    def __init__(self):
        self.calls: List[List[str]] = []

    def encode(self, texts, normalize_embeddings=False, convert_to_numpy=True, **kwargs):
        self.calls.append(list(texts))
        out = np.zeros((len(texts), DIM), dtype=np.float32)
        for row, text in enumerate(texts):
            for word in text.lower().replace("passage:", "").replace("query:", "").split():
                h = int(hashlib.md5(word.encode()).hexdigest(), 16)
                out[row, h % DIM] += 1.0
            out[row, 0] += 0.01  # evita el vector nulo
        if normalize_embeddings:
            out /= np.linalg.norm(out, axis=1, keepdims=True)
        return out
