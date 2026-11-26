"""Run the frozen milestone 1 cases through the current search and record a baseline.

Usage: python evals/milestone1/baseline.py <collection_id> [api_base_url]
Writes evals/milestone1/baseline-results.json next to this file.
"""

import json
import sys
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
TOP_K = 5


def load_cases() -> dict:
    """Read the frozen case file."""
    return json.loads((HERE / "cases.json").read_text(encoding="utf-8"))


def search(api: str, collection_id: str, query: str) -> list[dict]:
    """Call the collection search endpoint and return its passages."""
    body = json.dumps({"query": query, "top_k": TOP_K}).encode("utf-8")
    request = urllib.request.Request(
        f"{api}/collections/{collection_id}/search",
        data=body,
        headers={"content-type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=120) as response:
        return json.loads(response.read().decode("utf-8"))


def hit_pairs(passages: list[dict]) -> set[tuple[str, int]]:
    """Return the (filename, page) pairs found in the passages."""
    return {(p["filename"], p["page"]) for p in passages}


def expected_pairs(case: dict, names: dict[str, str]) -> set[tuple[str, int]]:
    """Return the (filename, page) pairs that count as a hit for one case."""
    expected = case["expected_pages"]
    if isinstance(expected, dict):
        return {(names[key], page) for key, pages in expected.items() for page in pages}
    return {(names[case["expected_documents"][0]], page) for page in expected}


def acceptable_pairs(case: dict, names: dict[str, str]) -> set[tuple[str, int]]:
    """Return the extra (filename, page) pairs accepted as hits for one case."""
    extra = case.get("acceptable_pages", [])
    if not extra:
        return set()
    return {(names[case["expected_documents"][0]], page) for page in extra}


def score_case(case: dict, passages: list[dict], names: dict[str, str]) -> dict:
    """Mark a case as hit when every expected pair appears in the top results."""
    found = hit_pairs(passages)
    wanted = expected_pairs(case, names)
    accepted = wanted | acceptable_pairs(case, names)
    missing = sorted(wanted - found)
    if case["type"] == "unanswerable":
        return {"hit": None, "note": "no expected pages; abstention is checked in chat"}
    return {
        "hit": not missing and bool(found & accepted),
        "missing_expected": [list(pair) for pair in missing],
    }


def main() -> None:
    """Run every case, print a summary, and write the results file."""
    collection_id = sys.argv[1]
    api = sys.argv[2] if len(sys.argv) > 2 else "http://127.0.0.1:8000"
    cases = load_cases()
    names = {doc["key"]: Path(doc["file"]).name for doc in cases["documents"]}
    results = []
    for case in cases["cases"]:
        if case["page_status"] == "todo":
            continue
        passages = search(api, collection_id, case["question"])
        outcome = score_case(case, passages, names)
        results.append(
            {
                "id": case["id"],
                "type": case["type"],
                "top_results": [[p["filename"], p["page"], round(p["score"], 4)] for p in passages],
                **outcome,
            }
        )
        print(case["id"], outcome)
    scored = [r for r in results if r["hit"] is not None]
    summary = {"hits": sum(r["hit"] for r in scored), "scored": len(scored), "top_k": TOP_K}
    payload = {
        "cases_version": cases["version"],
        "retrieval": "current collection search (vector + BM25 fusion)",
        "collection_id": collection_id,
        "summary": summary,
        "results": results,
    }
    out = HERE / "baseline-results.json"
    out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print("summary", summary, "->", out)


if __name__ == "__main__":
    main()
