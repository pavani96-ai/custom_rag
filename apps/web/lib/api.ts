/**
 * HTTP calls from the browser to the FastAPI service. Each call returns parsed JSON or
 * throws an Error whose message is safe to show to the user.
 */

import type { IngestResult, UploadResult } from "./upload-state";

export const DEFAULT_API_BASE = "http://127.0.0.1:8000";

export interface CollectionForm {
  title: string;
  description: string;
  instructions: string;
}

/**
 * Return the workspace ID from the build-time setting, trimmed. Empty means it was not set.
 * Milestone 2 replaces this with the signed-in user's workspace.
 */
export function resolveWorkspaceId(value: string | undefined): string {
  return (value ?? "").trim();
}

/** Return the API base URL, from the build-time public setting when one is provided. */
export function apiBase(): string {
  return process.env.NEXT_PUBLIC_API_BASE_URL || DEFAULT_API_BASE;
}

/** Read the `detail` field from a FastAPI error body, or fall back to the status code. */
async function errorMessage(response: Response): Promise<string> {
  try {
    const body = (await response.json()) as { detail?: unknown };
    if (typeof body.detail === "string") {
      return body.detail;
    }
  } catch {
    // Body was not JSON. Use the generic message below.
  }
  return `Request failed (${response.status}).`;
}

/** Send a request and parse the JSON response, or throw with a readable message. */
async function requestJson<T>(url: string, init: RequestInit): Promise<T> {
  const response = await fetch(url, init);
  if (!response.ok) {
    throw new Error(await errorMessage(response));
  }
  return (await response.json()) as T;
}

/** Create a collection in the given workspace. Returns the new collection ID. */
export async function createCollection(
  base: string,
  workspaceId: string,
  form: CollectionForm,
): Promise<{ id: string }> {
  return requestJson<{ id: string }>(`${base}/workspaces/${workspaceId}/collections`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ ...form, response_preferences: {} }),
  });
}

/** Upload PDFs in one request. The API returns one result per file, in the same order. */
export async function uploadFiles(
  base: string,
  collectionId: string,
  files: File[],
): Promise<UploadResult[]> {
  const body = new FormData();
  for (const file of files) {
    body.append("files", file, file.name);
  }
  return requestJson<UploadResult[]>(`${base}/collections/${collectionId}/uploads`, {
    method: "POST",
    body,
  });
}

/** Queue indexing for one stored upload. One request per file keeps failures per file. */
export async function ingestUpload(
  base: string,
  collectionId: string,
  uploadId: string,
  filename: string,
): Promise<IngestResult> {
  const results = await requestJson<IngestResult[]>(
    `${base}/collections/${collectionId}/documents/ingest`,
    {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ documents: [{ upload_id: uploadId, filename }] }),
    },
  );
  return results[0];
}
