"""Tests for the eval scoring rules. No services are called; passages are plain dicts."""

from app.evals.scoring import score_case

NAMES = {"transformer_notes": "notes.pdf", "taxonomy_guide": "guide.pdf"}


def passage(filename: str, page: int) -> dict:
    """Build a minimal passage with the fields the scorer reads."""
    return {"filename": filename, "page": page}


def test_expected_page_in_results_is_a_hit() -> None:
    """A case is a hit when its expected page is among the returned passages."""
    case = {"type": "fact", "expected_documents": ["transformer_notes"], "expected_pages": [3]}
    outcome = score_case(case, [passage("notes.pdf", 3)], NAMES)
    assert outcome == {"hit": True, "missing_expected": []}


def test_accepted_alternate_page_is_a_hit() -> None:
    """An accepted alternate page, such as a table of contents, also counts as a hit."""
    case = {
        "type": "exact_identifier",
        "expected_documents": ["transformer_notes"],
        "expected_pages": [45],
        "acceptable_pages": [2],
    }
    outcome = score_case(case, [passage("notes.pdf", 2)], NAMES)
    assert outcome["hit"] is True


def test_missing_expected_page_is_a_miss_and_is_reported() -> None:
    """A case misses when the expected page is absent, and the missing pair is listed."""
    case = {"type": "fact", "expected_documents": ["transformer_notes"], "expected_pages": [3]}
    outcome = score_case(case, [passage("notes.pdf", 9)], NAMES)
    assert outcome == {"hit": False, "missing_expected": [["notes.pdf", 3]]}


def test_cross_document_case_needs_every_expected_pair() -> None:
    """A question spanning two documents misses unless both documents' pages are returned."""
    case = {
        "type": "cross_document",
        "expected_documents": ["transformer_notes", "taxonomy_guide"],
        "expected_pages": {"transformer_notes": [21], "taxonomy_guide": [1]},
    }
    partial = score_case(case, [passage("notes.pdf", 21)], NAMES)
    assert partial["hit"] is False
    assert partial["missing_expected"] == [["guide.pdf", 1]]
    both = score_case(case, [passage("notes.pdf", 21), passage("guide.pdf", 1)], NAMES)
    assert both["hit"] is True


def test_unanswerable_case_is_not_scored_by_search() -> None:
    """Abstention is checked in chat, so an unanswerable case has no search hit value."""
    case = {"type": "unanswerable", "expected_documents": [], "expected_pages": []}
    outcome = score_case(case, [passage("notes.pdf", 1)], NAMES)
    assert outcome["hit"] is None
