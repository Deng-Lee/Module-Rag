from __future__ import annotations

from dataclasses import dataclass

from src.ingestion.stages.embedding.dense import DenseEncoder
from src.ingestion.stages.embedding.sparse import SparseEncoderStage
from src.libs.interfaces.splitter import ChunkIR
from src.libs.providers.embedding.cache import canonical, content_hash


@dataclass
class RecordingEmbedder:
    last_inputs: list[str] | None = None

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        self.last_inputs = list(texts)
        # return dummy vectors with stable length
        return [[0.0] * 4 for _ in texts]


def test_fingerprint_vs_content_hash_split_and_encoding_input() -> None:
    chunk = ChunkIR(
        chunk_id="c1",
        section_path="S",
        text="facts",
        metadata={
            "chunk_retrieval_text": "facts\n\n[caption] extra",
            "text_norm_profile_id": "default",
            "doc_id": "d1",
            "version_id": "v1",
        },
    )

    fp = content_hash(chunk.text, text_norm_profile_id="default")
    ch = content_hash(chunk.metadata["chunk_retrieval_text"], text_norm_profile_id="default")
    assert fp != ch

    rec = RecordingEmbedder()
    encoder = DenseEncoder(embedder=rec)
    encoder.encode([chunk])

    assert rec.last_inputs is not None
    assert rec.last_inputs[0] == canonical(chunk.metadata["chunk_retrieval_text"], profile_id="default")

    sparse = SparseEncoderStage()
    docs = sparse.encode([chunk])
    assert docs[0].text == chunk.metadata["chunk_retrieval_text"]
