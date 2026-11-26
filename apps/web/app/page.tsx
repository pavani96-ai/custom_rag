"use client";

/**
 * Collection setup and upload screen. Creates the collection, uploads the selected PDFs,
 * then queues indexing for each stored file and shows per-file status.
 */

import { type FormEvent, useState } from "react";

import {
  apiBase,
  createCollection,
  ingestUpload,
  resolveWorkspaceId,
  uploadFiles,
  type CollectionForm,
} from "../lib/api";
import {
  applyUploadResults,
  markIngestFailed,
  markQueued,
  pendingRows,
  type FileRow,
} from "../lib/upload-state";

const EMPTY_FORM: CollectionForm = { title: "", description: "", instructions: "" };

/** Turn a FileList into an array, or an empty array when nothing was selected. */
function selectedFiles(list: FileList | null): File[] {
  return list ? Array.from(list) : [];
}

/** Queue indexing for every stored file, one request each, updating rows as results arrive. */
async function queueStoredFiles(
  base: string,
  collectionId: string,
  start: FileRow[],
  onChange: (rows: FileRow[]) => void,
): Promise<void> {
  let rows = start;
  for (let index = 0; index < rows.length; index += 1) {
    const row = rows[index];
    if (row.state !== "stored" || !row.uploadId) {
      continue;
    }
    try {
      const result = await ingestUpload(base, collectionId, row.uploadId, row.name);
      rows = markQueued(rows, index, result);
    } catch (caught) {
      const message = caught instanceof Error ? caught.message : "Indexing could not start.";
      rows = markIngestFailed(rows, index, message);
    }
    onChange(rows);
  }
}

export default function Home() {
  const [form, setForm] = useState<CollectionForm>(EMPTY_FORM);
  const [rows, setRows] = useState<FileRow[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  /** Run the three steps in order and report failures without losing per-file state. */
  async function handleSubmit(event: FormEvent<HTMLFormElement>): Promise<void> {
    event.preventDefault();
    const input = event.currentTarget.elements.namedItem("files") as HTMLInputElement | null;
    const files = selectedFiles(input?.files ?? null);
    setError(null);
    const workspaceId = resolveWorkspaceId(process.env.NEXT_PUBLIC_WORKSPACE_ID);
    if (!workspaceId) {
      setError("Workspace is not configured. Set NEXT_PUBLIC_WORKSPACE_ID in .env and rebuild.");
      return;
    }
    if (files.length === 0) {
      setError("Choose at least one PDF.");
      return;
    }
    setBusy(true);
    try {
      const base = apiBase();
      const collection = await createCollection(base, workspaceId, form);
      const uploading = pendingRows(files.map((file) => file.name));
      setRows(uploading.map((row) => ({ ...row, state: "uploading", message: "Uploading." })));
      const results = await uploadFiles(base, collection.id, files);
      const stored = applyUploadResults(uploading, results);
      setRows(stored);
      await queueStoredFiles(base, collection.id, stored, setRows);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Something went wrong.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <main>
      <h1>New collection</h1>
      <form onSubmit={handleSubmit}>
        <label>
          Title
          <input
            required
            maxLength={200}
            value={form.title}
            onChange={(event) => setForm({ ...form, title: event.target.value })}
          />
        </label>
        <label>
          Description
          <textarea
            maxLength={2000}
            value={form.description}
            onChange={(event) => setForm({ ...form, description: event.target.value })}
          />
        </label>
        <label>
          Instructions
          <textarea
            maxLength={8000}
            value={form.instructions}
            onChange={(event) => setForm({ ...form, instructions: event.target.value })}
          />
        </label>
        <label>
          PDF files
          <input name="files" type="file" accept="application/pdf" multiple required />
        </label>
        <button type="submit" disabled={busy}>
          {busy ? "Working..." : "Create and index"}
        </button>
      </form>

      {error ? <p role="alert">{error}</p> : null}

      {rows.length > 0 ? (
        <ul aria-label="Upload status">
          {rows.map((row, index) => (
            <li key={index}>
              <strong>{row.name}</strong>: {row.state}. {row.message}
            </li>
          ))}
        </ul>
      ) : null}
    </main>
  );
}

