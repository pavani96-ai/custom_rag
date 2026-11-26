"""Score retrieval results against expected document and page pairs."""

from typing import Any

Pair = tuple[str, int]


def hit_pairs(passages: list[dict[str, Any]]) -> set[Pair]:
    """Return the (filename, page) pairs found in the passages."""
    return {(passage["filename"], passage["page"]) for passage in passages}


def expected_pairs(case: dict[str, Any], names: dict[str, str]) -> set[Pair]:
    """Return the (filename, page) pairs that count as a hit for one case."""
    expected = case["expected_pages"]
    if isinstance(expected, dict):
        return {(names[key], page) for key, pages in expected.items() for page in pages}
    return {(names[case["expected_documents"][0]], page) for page in expected}


def acceptable_pairs(case: dict[str, Any], names: dict[str, str]) -> set[Pair]:
    """Return the extra (filename, page) pairs accepted as hits for one case."""
    extra = case.get("acceptable_pages", [])
    return {(names[case["expected_documents"][0]], page) for page in extra}


def score_case(
    case: dict[str, Any], passages: list[dict[str, Any]], names: dict[str, str]
) -> dict[str, Any]:
    """Mark a case as hit when every expected pair appears and one accepted pair is found."""
    if case["type"] == "unanswerable":
        return {"hit": None, "note": "no expected pages; abstention is checked in chat"}
    found = hit_pairs(passages)
    wanted = expected_pairs(case, names)
    missing = sorted(wanted - found)
    return {
        "hit": _is_hit(case, found, wanted, names),
        "missing_expected": [list(pair) for pair in missing],
    }


def _is_hit(
    case: dict[str, Any], found: set[Pair], wanted: set[Pair], names: dict[str, str]
) -> bool:
    """Single-document cases hit on any expected or accepted page. Multi-document cases need all."""
    if isinstance(case["expected_pages"], dict):
        return wanted <= found
    return bool(found & (wanted | acceptable_pairs(case, names)))
