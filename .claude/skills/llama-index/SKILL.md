---
name: llama-index
description: Use for any task that uses LlamaIndex here (ingestion, chunking, retrievers, fusion, reranking, LLM calls, chat messages). Applies this repo's pinned versions and conventions, and checks the installed API before relying on it.
---

Use this skill whenever code touches `llama_index` in this repo. Read `.claude/skills/production-code/SKILL.md` too.

## Pinned versions and where LlamaIndex lives

- `src/requirements.txt` pins `llama-index-core==0.14.6` and `llama-index-llms-google-genai==0.12.0`.
- `google-genai` must stay below 3. Newer versions break the LlamaIndex Gemini package.
- Do not upgrade these pins without a test run and a CHANGELOG entry.

## Current usage in this repo (follow these patterns)

| Need | Where | Import |
|---|---|---|
| Split pages into chunks | `src/app/rag/pipeline.py` | `SentenceSplitter`, `IngestionPipeline`, `Document` from `llama_index.core` |
| Generate answers and stream chat | `src/app/rag/llm.py`, `src/app/rag/chat.py` | `GoogleGenAI` from `llama_index.llms.google_genai`, `ChatMessage`, `MessageRole` from `llama_index.core.llms` |
| Fuse vector and keyword results | `src/app/api/routes.py` | `QueryFusionRetriever` from `llama_index.core.retrievers` |
| Rerank candidates | `llama_index.postprocessor.jinaai_rerank` (JinaRerank, in `src/app/rag/retrieval.py`) | `BaseNodePostprocessor` from `llama_index.core.postprocessor.types` |
| Node and query types | `routes.py`, `reranker.py` | `NodeWithScore`, `QueryBundle`, `TextNode` from `llama_index.core.schema` |
| Placeholder LLM object | `routes.py:385` | `MockLLM` from `llama_index.core.llms`. It is not a test double here; check why before reusing it. |

## Rules

1. **Own the IDs.** LlamaIndex assigns node IDs, but this repo derives chunk IDs with `chunk_id_for` in `pipeline.py` (UUIDv5 over document, page, index, and text hash). Keep that. Never store LlamaIndex's random IDs as identities.
2. **Keep operational data out of text.** Metadata like page numbers goes in `metadata`, and `excluded_embed_metadata_keys` keeps it out of embeddings. Do not put IDs or upload times in node text.
3. **Disable hidden caches in pipelines.** `IngestionPipeline` runs with `disable_cache=True` here. Our own cache identities (see `docs/architecture.md`) decide what is reused. Do not rely on LlamaIndex's cache.
4. **Chunk by characters with the repo constants.** Use `CHUNK_CHARS` and `OVERLAP_CHARS` from `pipeline.py`, and a `tokenizer` that matches the budget, as the code does now.
5. **Route every provider call through our layer.** LLM and embedding calls go through `src/app/rag/llm.py` or `src/app/rag/embedder.py`. Do not call a provider directly from a route. Provider calls need leases and cache keys (see `CLAUDE.md`).
6. **Stream with the existing event contract.** Chat streams use the SSE events `conversation`, `delta`, `done`, and `error`. Save a turn only when its citations are valid.
7. **Keep retrieval scoped.** Every retriever gets the workspace, collection, and document filters. A retriever must never search outside the authorized document set.
8. **Test with mocks.** Use a fake client in tests, not a real provider. The repo has no `MockLLM` test double yet. Count provider calls when checking cache reuse. Tests never call real services.

## Before writing new LlamaIndex code

LlamaIndex changes between releases. Before using a class or argument you have not used in this repo, check the installed version:

- Inside the API container: `docker compose --env-file .env -f ops/compose.yaml exec -T api python -c "import llama_index.core as c; print(c.__file__)"`, then read the source at that path.
- Confirm the signature with `inspect.signature` on the class.
- If you cannot confirm it, say so and leave the call out until it is verified.

## Verify

Run `make check` in Docker. Add or update a test for each new LlamaIndex path, and record any API change in `docs/architecture.md` and the CHANGELOG.
