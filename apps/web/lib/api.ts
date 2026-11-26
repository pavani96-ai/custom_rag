/**
 * HTTP calls from the browser to the FastAPI service. Each call returns parsed JSON or
 * throws an Error whose message is safe to show to the user.
 */

import type { IngestResult, JobStatus, UploadResult } from "./upload-state";

/** A passage as returned by the API. Text is a snapshot taken when the answer was saved. */
export interface PassageView {
  chunk_id: string;
  document_id: string;
  filename: string;
  page: number;
  text: string;
  score: number;
}

/** A cited passage. The source_id matches the [n] marker in the answer text. */
export interface CitedPassage {
  source_id: number;
  passage: PassageView;
  rerank_score: number;
}

export interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  citations: CitedPassage[];
  created_at: string;
}

export interface ConversationSummary {
  id: string;
  title: string;
  created_at: string;
}

export interface ConversationDetail {
  id: string;
  title: string;
  messages: ChatMessage[];
}

export const DEFAULT_API_BASE = "http://127.0.0.1:8000";

export type AnswerFormat = "auto" | "prose" | "bullets";
export type AnswerLength = "brief" | "standard" | "detailed";

export interface CollectionForm {
  title: string;
  description: string;
  instructions: string;
  format: AnswerFormat;
  length: AnswerLength;
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
export async function errorMessage(response: Response): Promise<string> {
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
    body: JSON.stringify({
      title: form.title,
      description: form.description,
      instructions: form.instructions,
      response_preferences: { format: form.format, length: form.length },
    }),
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

/** List the user's saved conversations in the collection, newest first. */
export async function listConversations(
  base: string,
  collectionId: string,
): Promise<ConversationSummary[]> {
  return requestJson<ConversationSummary[]>(`${base}/collections/${collectionId}/conversations`, {});
}

/** Load one conversation with its messages and citations. */
export async function getConversation(
  base: string,
  collectionId: string,
  conversationId: string,
): Promise<ConversationDetail> {
  return requestJson<ConversationDetail>(
    `${base}/collections/${collectionId}/conversations/${conversationId}`,
    {},
  );
}

/** URL of a stored original, opened in a new tab at the cited page. */
export function originalUrl(
  base: string,
  collectionId: string,
  documentId: string,
  page: number,
): string {
  return `${base}/collections/${collectionId}/documents/${documentId}/original#page=${page}`;
}

/** Read the status of one ingest job. The upload page polls this until the file finishes. */
export async function getJob(
  base: string,
  collectionId: string,
  jobId: string,
): Promise<JobStatus> {
  return requestJson<JobStatus>(`${base}/collections/${collectionId}/jobs/${jobId}`, {});
}
