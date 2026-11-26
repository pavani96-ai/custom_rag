/**
 * Unit tests for the per-file upload state. Run with `npm test`. No network calls are made.
 */

import assert from "node:assert/strict";
import { test } from "node:test";

import { resolveWorkspaceId } from "../lib/api";
import {
  applyUploadResults,
  markIngestFailed,
  markQueued,
  pendingRows,
} from "../lib/upload-state";

test("stored and failed uploads keep their own messages", () => {
  const rows = applyUploadResults(pendingRows(["a.pdf", "b.pdf"]), [
    { filename: "a.pdf", status: "stored", upload_id: "f".repeat(64), error: null },
    { filename: "b.pdf", status: "failed", upload_id: null, error: "File content is not a PDF." },
  ]);
  assert.equal(rows[0].state, "stored");
  assert.equal(rows[0].uploadId, "f".repeat(64));
  assert.equal(rows[1].state, "failed");
  assert.equal(rows[1].message, "File content is not a PDF.");
});

test("a missing result marks that file failed and leaves the others alone", () => {
  const rows = applyUploadResults(pendingRows(["a.pdf", "b.pdf"]), [
    { filename: "a.pdf", status: "stored", upload_id: "a".repeat(64), error: null },
  ]);
  assert.equal(rows[0].state, "stored");
  assert.equal(rows[1].state, "failed");
  assert.equal(rows[1].message, "No result returned.");
});

test("queued files record document and job IDs", () => {
  const rows = markQueued(pendingRows(["a.pdf"]), 0, {
    document_id: "doc-1",
    job_id: "job-1",
    filename: "a.pdf",
    status: "queued",
  });
  assert.equal(rows[0].state, "queued");
  assert.equal(rows[0].documentId, "doc-1");
  assert.equal(rows[0].jobId, "job-1");
});

test("an ingest failure changes only its own row and does not mutate the input", () => {
  const start = pendingRows(["a.pdf", "b.pdf"]);
  const rows = markIngestFailed(start, 1, "Original not stored: b.pdf");
  assert.equal(rows[1].state, "failed");
  assert.equal(rows[0].state, "pending");
  assert.equal(start[1].state, "pending");
});

test("workspace ID comes from the build setting, trimmed, and empty when unset", () => {
  assert.equal(resolveWorkspaceId(" 0000-abc \n"), "0000-abc");
  assert.equal(resolveWorkspaceId(""), "");
  assert.equal(resolveWorkspaceId(undefined), "");
});
