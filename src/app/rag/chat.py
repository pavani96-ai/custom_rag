"""Chat turn helpers: prompt assembly, streamed generation, citation checks, and SSE frames."""

import json
import re
from collections.abc import Iterator

from llama_index.llms.google_genai import GoogleGenAI

from app.rag.llm import make_messages
from app.schema.models import CitedPassage

# Matches [1], [1][2], and [1, 2]. The group holds the comma-separated IDs.
CITATION_PATTERN = re.compile(r"\[(\d+(?:\s*,\s*\d+)*)\]")


def cited_ids(text: str) -> list[int]:
    """Return the distinct source IDs cited in the text, in order of first appearance."""
    numbers = (
        number
        for group in CITATION_PATTERN.findall(text)
        for number in re.findall(r"\d+", group)
    )
    return list(dict.fromkeys(int(number) for number in numbers))


def citations_are_valid(ids: list[int], source_count: int) -> bool:
    """Return True when every cited ID refers to a passage that was supplied."""
    return all(1 <= index <= source_count for index in ids)


def build_contents(
    question: str, history: list[dict[str, str]], sources: list[CitedPassage]
) -> str:
    """Serialize the question, earlier turns, and passages as JSON so passages stay data."""
    return json.dumps(
        {
            "history": history,
            "question": question,
            "passages": [
                {"source_id": source.source_id, "text": source.passage.text}
                for source in sources
            ],
        }
    )


def stream_answer(llm: GoogleGenAI, contents: str, instruction: str) -> Iterator[str]:
    """Yield answer text as the model produces it. Callers join the pieces."""
    messages = make_messages(instruction, contents)
    for chunk in llm.stream_chat(messages):
        if chunk.delta:
            yield chunk.delta


def sse_frame(event: str, data: dict) -> str:
    """Format one server-sent event with a JSON payload."""
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


def cited_passages(sources: list[CitedPassage], ids: list[int]) -> list[CitedPassage]:
    """Return the supplied passages that the answer cited, in citation order."""
    return [sources[index - 1] for index in ids]
