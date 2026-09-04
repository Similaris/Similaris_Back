"""Benchmark simples do motor semântico.

Execute na raiz do projeto com:
    python -m scripts.benchmark_semantic_similarity
"""

from time import perf_counter

from app.services.analysis.semantic_similarity import (
    compare_embeddings,
    generate_embedding,
    generate_embeddings,
    get_model,
)

TEXTS = [
    "The student submitted the final assignment.",
    "The learner delivered the completed coursework.",
    "Volcanoes release magma from beneath the Earth's crust.",
]


def main() -> None:
    get_model()

    started_at = perf_counter()
    generate_embedding(TEXTS[0])
    single_duration = perf_counter() - started_at

    started_at = perf_counter()
    embeddings = generate_embeddings(TEXTS)
    batch_duration = perf_counter() - started_at

    started_at = perf_counter()
    compare_embeddings(embeddings[0], embeddings[1])
    comparison_duration = perf_counter() - started_at

    print(f"Embedding individual: {single_duration:.6f} s")
    print(f"Batch com {len(TEXTS)} textos: {batch_duration:.6f} s")
    print(f"Comparação de embeddings: {comparison_duration:.6f} s")


if __name__ == "__main__":
    main()
