/**
 * Per-file state for the upload and ingest flow. Pure functions, so they can be tested
 * without a browser. Each function returns a new array and never mutates its input.
 */

export type FileState =
  | "pending"
  | "uploading"
  | "stored"
  | "queued"
  | "processing"
  | "ready"
  | "failed";

export interface FileRow {
  name: string;
  state: FileState;
  message: string;
  uploadId?: string;
  documentId?: string;
  jobId?: string;
}

/** One entry from POST /collections/{id}/uploads. Results come back in request order. */
export interface UploadResult {
  filename: string;
  status: "stored" | "failed";
  upload_id: string | null;
  error: string | null;
}

/** One entry from POST /collections/{id}/documents/ingest. */
export interface IngestResult {
  document_id: string;
  job_id: string;
  filename: string;
  status: string;
}

/** Build rows for the selected files before any request is sent. */
export function pendingRows(names: string[]): FileRow[] {
  return names.map((name) => ({ name, state: "pending", message: "Waiting to upload." }));
}

/** Return a copy of the rows with one row changed. */
export function updateRow(rows: FileRow[], index: number, patch: Partial<FileRow>): FileRow[] {
  return rows.map((row, i) => (i === index ? { ...row, ...patch } : row));
}

/** Apply the upload response. Stored rows keep their upload ID for the ingest step. */
export function applyUploadResults(rows: FileRow[], results: UploadResult[]): FileRow[] {
  return rows.reduce<FileRow[]>((current, _row, index) => {
    const result = results[index];
    if (!result) {
      return updateRow(current, index, { state: "failed", message: "No result returned." });
    }
    if (result.status === "stored" && result.upload_id) {
      return updateRow(current, index, {
        state: "stored",
        uploadId: result.upload_id,
        message: "Stored. Indexing will start next.",
      });
    }
    return updateRow(current, index, {
      state: "failed",
      message: result.error ?? "Upload failed.",
    });
  }, rows);
}

/** Record that the ingest endpoint accepted this file. */
export function markQueued(rows: FileRow[], index: number, result: IngestResult): FileRow[] {
  return updateRow(rows, index, {
    state: "queued",
    documentId: result.document_id,
    jobId: result.job_id,
    message: "Queued for indexing.",
  });
}

/** One entry from GET /collections/{id}/jobs/{job_id}. */
export interface JobStatus {
  job_id: string;
  document_id: string;
  status: "queued" | "running" | "succeeded" | "failed";
  error_message: string | null;
}

/** Update one row from its job status. Other rows are left as they are. */
export function applyJobStatus(rows: FileRow[], index: number, job: JobStatus): FileRow[] {
  if (job.status === "running") {
    return updateRow(rows, index, { state: "processing", message: "Indexing." });
  }
  if (job.status === "succeeded") {
    return updateRow(rows, index, { state: "ready", message: "Ready to search." });
  }
  if (job.status === "failed") {
    return updateRow(rows, index, {
      state: "failed",
      message: job.error_message ?? "Indexing failed.",
    });
  }
  return updateRow(rows, index, { state: "queued", message: "Queued for indexing." });
}

/** True once a row will not change again: indexed, or failed. */
export function isFinished(row: FileRow): boolean {
  return row.state === "ready" || row.state === "failed";
}

/** Record a per-file ingest failure without touching other files. */
export function markIngestFailed(rows: FileRow[], index: number, message: string): FileRow[] {
  return updateRow(rows, index, { state: "failed", message });
}
