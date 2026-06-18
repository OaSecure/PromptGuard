from app.atoms import AnalysisAtom, TextRange
from app.ml.embedding import AtomEmbeddingModelLoader, AtomEmbeddingRequest, QWEN3_EMBEDDING_MODEL, embed_atoms
from app.ml.segment_embedding import SegmentEmbeddingBuildRequest, SegmentEmbeddingPolicy, build_segment_embeddings
from app.segmenter import SegmentBuildRequest, SegmentPolicy, build_segments


class FakeBackend:
    model_version = QWEN3_EMBEDDING_MODEL
    dimension = 2
    is_frozen = True

    def embed_texts(self, texts: list[str], normalize: bool) -> list[list[float]]:
        return [[1.0, 0.0], [0.0, 1.0]][: len(texts)]


def atom(atom_id: str, text: str, ordinal: int) -> AnalysisAtom:
    return AnalysisAtom(
        atom_id=atom_id,
        input_id="input-1",
        block_id="block-1",
        text=text,
        original_range=TextRange(start=ordinal * 10, end=ordinal * 10 + len(text)),
        location=None,
        atom_type="paragraph",
        ordinal=ordinal,
    )


def test_atom_embedding_segmenter_output_feeds_segment_embedding_builder():
    atoms = [atom("a1", "payment terms", 0), atom("a2", "credential risk", 1)]
    embedding_result = embed_atoms(
        AtomEmbeddingRequest(
            input_id="input-1",
            atoms=atoms,
            model_name=QWEN3_EMBEDDING_MODEL,
            normalize_vectors=True,
            timeout_ms=1_000,
        ),
        AtomEmbeddingModelLoader(lambda model_name: FakeBackend()),
    )
    segment_result = build_segments(
        SegmentBuildRequest(
            input_id="input-1",
            atoms=atoms,
            atom_embeddings=embedding_result.embeddings,
            segment_policy=SegmentPolicy(cosine_break_threshold=-1.0),
        )
    )

    result = build_segment_embeddings(
        SegmentEmbeddingBuildRequest(
            input_id="input-1",
            segments=segment_result.segments,
            atom_embeddings=embedding_result.embeddings,
            embedding_model_version=embedding_result.embedding_model_version,
            policy=SegmentEmbeddingPolicy(normalize_vectors=False),
        )
    )

    assert embedding_result.failure is None
    assert segment_result.failure is None
    assert result.failure is None
    assert [item.segment_id for item in result.segment_embeddings] == [segment_result.segments[0].segment_id]
    assert result.segment_embeddings[0].vector == [0.5, 0.5]
