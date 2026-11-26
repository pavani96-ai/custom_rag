"""Build a test dataset from a local PDF and evaluate answers with Ragas metrics.

Usage from Python:

    dataset = create_eval_dataset(Path("docs/demo-docs/Transformer_Theory_Notes.pdf"))
    # Fill in dataset.samples[i].response and .retrieved_contexts with your system's output.
    metrics = create_metrics(client, settings)
    result = evaluate(dataset=dataset, metrics=metrics)

The dataset is built from the PDF directly. It never calls the running API.
"""

import argparse
import asyncio
import inspect
import json
import math
from contextlib import closing
from pathlib import Path
from typing import Any

import httpx
from google import genai
from google.genai import types
from llama_index.core import Settings as LlamaSettings
from llama_index.core.llama_dataset.generator import RagDatasetGenerator
from llama_index.core.llms import CompletionResponse, CustomLLM, LLMMetadata
from llama_index.core.schema import TextNode
from pydantic import BaseModel, PrivateAttr
from ragas import EvaluationDataset, SingleTurnSample
from ragas.embeddings.base import BaseRagasEmbedding
from ragas.llms.base import InstructorBaseRagasLLM
from ragas.metrics.base import Metric
from ragas.metrics.collections import (
    AnswerRelevancy,
    ContextPrecision,
    ContextRecall,
    Faithfulness,
)

from app.api.routes import get_gemini_client
from app.rag.providers.embedder import JinaEmbedder
from app.rag.pipeline import extract_pages, normalize
from app.config.settings import Settings, get_settings


# Judge calls write whole questions from long PDF pages, so they need more than the API's 30 s.
JUDGE_TIMEOUT_MS = 180_000


class DatasetGemini(CustomLLM):
    """Route LlamaIndex dataset generation through the shared Google SDK client."""

    model: str
    _client: genai.Client = PrivateAttr()

    def __init__(self, client: genai.Client, model: str) -> None:
        """Store the client and the model name used for generation."""
        super().__init__(model=model)
        self._client = client

    @property
    def metadata(self) -> LLMMetadata:
        """Describe the model to LlamaIndex."""
        return LLMMetadata(model_name=self.model, context_window=65536, num_output=2048)

    def complete(self, prompt: str, formatted: bool = False, **kwargs: Any) -> CompletionResponse:
        """Return Gemini's text for one prompt."""
        response = self._client.models.generate_content(model=self.model, contents=prompt)
        if not response.text:
            raise ValueError("Gemini returned no text during dataset generation.")
        return CompletionResponse(text=response.text)

    async def acomplete(
        self, prompt: str, formatted: bool = False, **kwargs: Any
    ) -> CompletionResponse:
        """Run the blocking completion in a worker thread."""
        return await asyncio.to_thread(self.complete, prompt, formatted, **kwargs)

    def stream_complete(self, prompt: str, formatted: bool = False, **kwargs: Any):
        """Yield the whole completion as one chunk; generation does not need streaming."""
        response = self.complete(prompt, formatted=formatted, **kwargs)
        yield CompletionResponse(text=response.text, delta=response.text)


class GeminiJudge(InstructorBaseRagasLLM):
    """Give Ragas metrics Gemini structured JSON output that matches a Pydantic model."""

    def __init__(self, client: genai.Client, model: str) -> None:
        """Store the client and the judge model name."""
        self.client = client
        self.model = model

    def generate(self, prompt: str, response_model: type[BaseModel]) -> BaseModel:
        """Ask Gemini for JSON matching response_model and validate the result."""
        response = self.client.models.generate_content(
            model=self.model,
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=response_model,
            ),
        )
        return response_model.model_validate_json(response.text or "")

    async def agenerate(self, prompt: str, response_model: type[BaseModel]) -> BaseModel:
        """Run the blocking judge call in a worker thread."""
        return await asyncio.to_thread(self.generate, prompt, response_model)


def is_usable(question: str, reference_answer: str | None, seen: set[str]) -> bool:
    """Reject empty questions, empty answers, and duplicate questions (case-insensitive)."""
    key = question.casefold()
    return bool(question) and bool((reference_answer or "").strip()) and key not in seen


def to_samples(generated: list[Any]) -> list[SingleTurnSample]:
    """Convert LlamaIndex examples into Ragas samples, dropping unusable ones."""
    samples: list[SingleTurnSample] = []
    seen: set[str] = set()
    for example in generated:
        question = normalize(example.query)
        if not is_usable(question, example.reference_answer, seen):
            continue
        seen.add(question.casefold())
        samples.append(SingleTurnSample(
            user_input=question,
            reference=normalize(example.reference_answer),
            reference_contexts=[normalize(context) for context in example.reference_contexts or []],
        ))
    return samples


def create_eval_dataset(pdf_path: Path, questions_per_page: int = 2) -> EvaluationDataset:
    """Generate test questions and reference answers from a local PDF, without the API.

    Samples come back with user_input, reference, and reference_contexts. Fill in response
    and retrieved_contexts before passing the dataset to evaluate.
    """
    if questions_per_page < 1:
        raise ValueError("questions_per_page must be positive")
    pages = extract_pages(pdf_path.read_bytes())
    nodes = [TextNode(text=normalize(page)) for page in pages if page.strip()]
    settings = get_settings()
    # Count tokens by characters so LlamaIndex does not download a tokenizer.
    LlamaSettings.tokenizer = list
    with closing(get_gemini_client(settings, timeout_ms=JUDGE_TIMEOUT_MS)) as client:
        generator = RagDatasetGenerator(
            nodes=nodes,
            llm=DatasetGemini(client, settings.gemini_judge_model),
            num_questions_per_chunk=questions_per_page,
        )
        generated = generator.generate_dataset_from_nodes().examples
    samples = to_samples(generated)
    if not samples:
        raise ValueError("The generator produced no usable evaluation examples.")
    return EvaluationDataset(samples=samples)


class IngestionEmbeddings(BaseRagasEmbedding):
    """Embed with the same Jina model the ingestion pipeline uses, for Ragas metrics."""

    def __init__(self, embedder: JinaEmbedder) -> None:
        """Wrap the ingestion embedder."""
        self._embedder = embedder

    def embed_text(self, text: str) -> list[float]:
        """Embed one text."""
        return self._embedder.embed([text])[0]

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        """Embed several texts in one request."""
        return self._embedder.embed(list(texts))

    async def aembed_text(self, text: str) -> list[float]:
        """Run the blocking embedding call in a worker thread."""
        return await asyncio.to_thread(self.embed_text, text)

    async def aembed_texts(self, texts: list[str]) -> list[list[float]]:
        """Run the blocking batch call in a worker thread."""
        return await asyncio.to_thread(self.embed_texts, texts)


def create_metrics(client: genai.Client, settings: Settings) -> list[Metric]:
    """Create the four Ragas metrics: Gemini judges answers, Jina embeds for relevancy."""
    judge = GeminiJudge(client, settings.gemini_judge_model)
    # Same model as ingestion; the query task matches how the API embeds user questions.
    embeddings = IngestionEmbeddings(JinaEmbedder(settings.jina_api_key, "retrieval.query"))
    return [
        Faithfulness(llm=judge),
        AnswerRelevancy(llm=judge, embeddings=embeddings),
        ContextRecall(llm=judge),
        ContextPrecision(llm=judge),
    ]


def metric_inputs(metric: Metric, sample: SingleTurnSample) -> dict[str, Any]:
    """Pass each metric only the sample fields its ascore method accepts."""
    fields = sample.model_dump()
    parameters = inspect.signature(metric.ascore).parameters
    return {name: fields[name] for name in parameters if name in fields}


def finite_or_none(value: float | None) -> float | None:
    """Return the score as a float, or None when no finite number was produced."""
    if value is None or not math.isfinite(value):
        return None
    return float(value)


async def evaluate_async(
    dataset: EvaluationDataset, metrics: list[Metric]
) -> dict[str, list[float | None]]:
    """Score every sample with every metric, one sample at a time."""
    scores: dict[str, list[float | None]] = {metric.name: [] for metric in metrics}
    for sample in dataset.samples:
        for metric in metrics:
            result = await metric.ascore(**metric_inputs(metric, sample))
            scores[metric.name].append(finite_or_none(result.value))
    return scores


def evaluate(
    dataset: EvaluationDataset, metrics: list[Metric]
) -> dict[str, list[float | None]]:
    """Return per-sample scores for each metric, keyed by metric name."""
    return asyncio.run(evaluate_async(dataset, metrics))


def load_dataset(path: Path, limit: int = 0) -> EvaluationDataset:
    """Read a dataset JSON file written by generate; limit 0 keeps every sample."""
    samples = json.loads(path.read_text())["samples"]
    if limit > 0:
        samples = samples[:limit]
    return EvaluationDataset(samples=[SingleTurnSample(**sample) for sample in samples])


def ask_api(http: httpx.Client, collection_id: str, question: str, top_k: int) -> dict[str, Any]:
    """Ask the running API one question and return its answer with the retrieved passages."""
    response = http.post(
        f"/collections/{collection_id}/ask",
        params={"include_contexts": "true"},
        json={"query": question, "top_k": top_k},
    )
    response.raise_for_status()
    return response.json()


def fill_from_api(
    dataset: EvaluationDataset, http: httpx.Client, collection_id: str, top_k: int
) -> EvaluationDataset:
    """Set each sample's response and retrieved_contexts from what the RAG API returns."""
    for sample in dataset.samples:
        answer = ask_api(http, collection_id, sample.user_input, top_k)
        sample.response = answer["answer"]
        passages = answer.get("retrieved_contexts") or []
        sample.retrieved_contexts = [item["passage"]["text"] for item in passages]
    return dataset


def average(values: list[float | None]) -> float | None:
    """Mean of the finite scores, or None when every score is missing."""
    present = [value for value in values if value is not None]
    return sum(present) / len(present) if present else None


def score_dataset(
    dataset_path: Path, report_path: Path, collection_id: str, top_k: int, limit: int
) -> dict[str, Any]:
    """Query the running API for every sample, score the answers, and write a report."""
    settings = get_settings()
    dataset = load_dataset(dataset_path, limit)
    with httpx.Client(base_url=settings.eval_api_base_url, timeout=120) as http:
        dataset = fill_from_api(dataset, http, collection_id, top_k)
    with closing(get_gemini_client(settings)) as client:
        scores = evaluate(dataset, create_metrics(client, settings))
    report = {
        "judge_model": settings.gemini_judge_model,
        "rag_model": settings.gemini_model,
        "samples": len(dataset.samples),
        "averages": {name: average(values) for name, values in scores.items()},
        "scores": scores,
    }
    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n")
    return report


def build_parser() -> argparse.ArgumentParser:
    """Define the generate and score subcommands."""
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    generate = commands.add_parser("generate", help="Write eval questions from a PDF.")
    generate.add_argument("pdf", type=Path)
    generate.add_argument("output", type=Path)
    generate.add_argument("--questions-per-page", type=int, default=2)
    score = commands.add_parser("score", help="Query the running API and score the answers.")
    score.add_argument("dataset", type=Path)
    score.add_argument("report", type=Path)
    score.add_argument("--collection-id", required=True)
    score.add_argument("--top-k", type=int, default=5)
    score.add_argument("--limit", type=int, default=0)
    return parser


def run_generate(args: argparse.Namespace) -> None:
    """Write the dataset generated from a PDF to a JSON file for manual editing."""
    dataset = create_eval_dataset(args.pdf, args.questions_per_page)
    samples = [sample.model_dump(exclude_none=True) for sample in dataset.samples]
    args.output.write_text(json.dumps({"samples": samples}, indent=2, ensure_ascii=False) + "\n")
    print(f"Wrote {len(samples)} samples to {args.output}", flush=True)


def run_score(args: argparse.Namespace) -> None:
    """Score the RAG API against a dataset and print the averages."""
    report = score_dataset(args.dataset, args.report, args.collection_id, args.top_k, args.limit)
    print(json.dumps(report["averages"], indent=2), flush=True)


def main() -> None:
    """Run the eval command selected on the command line."""
    args = build_parser().parse_args()
    if args.command == "generate":
        run_generate(args)
    else:
        run_score(args)


if __name__ == "__main__":
    main()
