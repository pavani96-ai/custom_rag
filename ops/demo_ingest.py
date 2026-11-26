"""Upload a PDF to the local stack and wait for indexing to finish."""

import json
import subprocess
import sys
import time
from pathlib import Path
from uuid import UUID

COLLECTION_URL = (
    "http://localhost:8000/collections/00000000-0000-4000-8000-000000000003"
)
WAIT_SECONDS = 300


def run(*command, input_text=None):
    return subprocess.run(
        command, input=input_text, capture_output=True, text=True, timeout=60, check=True
    ).stdout.strip()


def post(route, *args):
    return json.loads(run("curl", "--silent", "--show-error", "--fail-with-body",
                          *args, COLLECTION_URL + route))[0]


def ingest(pdf, compose):
    if not pdf.is_file() or pdf.suffix.lower() != ".pdf":
        raise ValueError(f"Choose an existing PDF file: {pdf}")

    print(f"Uploading {pdf.name}", flush=True)
    uploaded = post("/uploads", "--form", f"files=@{json.dumps(str(pdf), ensure_ascii=False)}")
    if uploaded["status"] != "stored":
        raise ValueError(uploaded.get("error") or "Upload failed")
    print("Upload stored", flush=True)

    queued = post(
        "/documents/ingest", "--header", "Content-Type: application/json", "--data",
        json.dumps({"documents": [{
            "filename": uploaded["filename"], "upload_id": uploaded["upload_id"]
        }]}),
    )
    document_id = str(UUID(queued["document_id"]))
    print(f"Indexing queued for document {document_id}", flush=True)

    deadline = time.monotonic() + WAIT_SECONDS
    while time.monotonic() < deadline:
        status = run(
            *compose, "exec", "-T", "postgres", "psql", "-XAt", "-U", "rag", "-d", "rag",
            "-v", "ON_ERROR_STOP=1", "-v", f"document_id={document_id}",
            input_text="SELECT status FROM documents WHERE id = :'document_id'::uuid;\n",
        )
        if status == "ready":
            print(f"{uploaded['filename']} is ready")
            return
        if status == "failed":
            raise ValueError("Indexing failed. Run make logs to see the worker error.")
        time.sleep(2)

    raise ValueError(f"Still waiting after {WAIT_SECONDS}s. Check with make document-status "
                     f"DOCUMENT_ID={document_id}")


if __name__ == "__main__":
    try:
        ingest(Path(sys.argv[1]), sys.argv[2:])
    except subprocess.CalledProcessError as error:
        sys.exit((error.stderr or error.stdout or str(error)).strip())
    except (ValueError, OSError, subprocess.TimeoutExpired) as error:
        sys.exit(str(error))
