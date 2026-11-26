"""Tests for chunking and stable chunk IDs. Pure functions; no services."""

import io

from pypdf import PdfWriter

from app.config.settings import get_settings
from app.rag.pipeline import (
    build_chunks,
    chunk_id_for,
    extract_pages,
)


def test_split_text_respects_size_and_sentence_boundaries() -> None:
    sentence = "This is a sentence."
    chunks = build_chunks("doc-1", [" ".join([sentence] * 100)], get_settings())
    assert len(chunks) > 1
    assert all(len(chunk.text) <= get_settings().chunk_chars for chunk in chunks)
    for chunk in chunks:
        assert chunk.text.startswith(sentence)
        assert chunk.text.endswith(sentence)


def test_empty_pages_produce_no_chunks() -> None:
    """Blank pages, such as scans without a text layer, add no chunks."""
    assert build_chunks("doc-1", ["", "   \n  "], get_settings()) == []


def test_chunk_ids_are_stable_for_same_input() -> None:
    """The same document, page, index, and text always give the same ID."""
    first = build_chunks("doc-1", ["alpha beta gamma"], get_settings())
    second = build_chunks("doc-1", ["alpha beta gamma"], get_settings())
    assert [c.chunk_id for c in first] == [c.chunk_id for c in second]


def test_same_text_on_different_pages_gets_distinct_ids() -> None:
    """Repeated text at different locations keeps distinct chunk IDs."""
    assert chunk_id_for("doc-1", 1, 0, "same") != chunk_id_for("doc-1", 2, 0, "same")


def test_pages_are_numbered_from_one() -> None:
    """Chunk page numbers start at 1 to match the PDF viewer."""
    chunks = build_chunks("doc-1", ["first page", "second page"], get_settings())
    assert [c.page for c in chunks] == [1, 2]


def test_extract_pages_counts_blank_pdf_pages() -> None:
    """A blank PDF yields one empty string per page."""
    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    writer.add_blank_page(width=200, height=200)
    buffer = io.BytesIO()
    writer.write(buffer)
    assert extract_pages(buffer.getvalue()) == ["", ""]
