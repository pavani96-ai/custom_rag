# Changelog

Read at the start of every session. Each date has about 10 short lines, covering only what affects future work. Move old entries to [ARCHIVE.md](ARCHIVE.md).

## 2026-11-26

- Settings: every config value is read in `src/app/config/settings.py` (grouped by section; `MAX_BATCH_FILES` added). Helpers take `settings` as an argument. Tests: 86 passed.
- Answers are plain text: `PLAIN_TEXT_RULE` in `src/app/rag/prompts.py` bans markdown and LaTeX because the chat page does not render markdown. Formulas are kept as plain-character text (`Attention(Q,K,V) = softmax(...)`). Verified live in the chat. Rendering markdown or math in the UI is not done.
- Local stack checked end to end: two PDFs indexed (28 and 120 chunks), three chat queries answered with citations, and an off-topic question refused.
- Milestone 1 is accepted and ticked in `docs/plan.md`. Baseline 4 of 5 hits; the cross-document miss (taxonomy page 1) is a milestone 3 fix.
- Retrieval, indexing, and generation use LlamaIndex wrappers (OpenSearch vector store, Jina embedding and rerank, PDFReader, GoogleGenAI) on native clients. Pins are in `src/requirements.txt`.
- Chunk index is `chunks_jina_v5_512_v2`. Changing the dimension or layout needs a new index name. Demo collections need re-ingest after the chunking and vector-store change (not done yet).
- Pins: `google-genai` must stay below 3 for the LlamaIndex Gemini package. The eval run on the new pins is not verified yet.
- Open: only PDFs are accepted. Scanned PDFs are untested; OCR is planned for milestone 3.
- Open: chat history is read from PostgreSQL only. The Redis cache is milestone 2. The workspace ID comes from `NEXT_PUBLIC_WORKSPACE_ID` until login in milestone 2.
- Open: `/ask` summaries use only top-k passages, so whole-document summaries are partial. Summary retrieval is milestone 3.
- Eval evidence: `evals/milestone1/` (`milestone1-v1`, six cases, baseline script). `evals/result.json` and the `taxonomy*` files are older runs.
- Not pushed: `feature/milestone-1-scaffold-and-db` needs `git push` from the user's terminal. The refactor is still uncommitted.
