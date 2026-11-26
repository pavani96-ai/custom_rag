/**
 * Unit tests for the per-file upload state. Run with `npm test`. No network calls are made.
 */

import assert from "node:assert/strict";
import { test } from "node:test";

import { resolveWorkspaceId } from "../lib/api";
import {
  applyJobStatus,
  applyUploadResults,
  isFinished,
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

test("a job status updates only its own row through each stage", () => {
  const start = pendingRows(["a.pdf", "b.pdf"]).map((row) => ({ ...row, state: "queued" as const }));
  const base = { document_id: "d", job_id: "j", error_message: null };
  const running = applyJobStatus(start, 0, { ...base, status: "running" });
  assert.equal(running[0].state, "processing");
  assert.equal(running[1].state, "queued");
  const done = applyJobStatus(running, 0, { ...base, status: "succeeded" });
  assert.equal(done[0].state, "ready");
  assert.equal(isFinished(done[0]), true);
  assert.equal(isFinished(done[1]), false);
});

test("a failed job shows its safe error message", () => {
  const rows = applyJobStatus(pendingRows(["a.pdf"]), 0, {
    job_id: "j",
    document_id: "d",
    status: "failed",
    error_message: "Could not read the PDF.",
  });
  assert.equal(rows[0].state, "failed");
  assert.equal(rows[0].message, "Could not read the PDF.");
});
