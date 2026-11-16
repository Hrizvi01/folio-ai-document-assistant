# Folio · Local AI Document Assistant

A private document workspace with multi-file uploads, document-scoped RAG, persistent conversations, and inspectable source citations. Built with React, FastAPI, LangChain, ChromaDB, SQLite, and Ollama. No paid API keys or cloud inference services.

## Features

- Batch upload PDF, DOCX, and TXT documents with per-file results.
- Select exactly which documents inform each answer.
- Ask follow-up questions and reopen persisted conversations.
- Inspect source excerpts, PDF page numbers, and chunk references.
- Search the document library and delete indexed documents or chats.
- Monitor local model readiness without configuring a paid API key.

See the [first-run walkthrough](docs/WALKTHROUGH.md) for a reproducible demo with
[fictional sample content](examples/project-brief.txt), and the
[contribution guide](CONTRIBUTING.md) for development and validation.

## Prerequisites

- Python **3.11 or 3.12** (recommended for Chroma compatibility)
- Node.js **20.19+ or 22.12+** and npm
- [Ollama](https://ollama.com/download), running locally
- Enough disk space for model downloads; 8 GB RAM minimum, 16 GB recommended. CPU inference works but may take a while.

The first installation and model download need internet access. Inference, embeddings, document storage, and the UI run locally afterward.

## Quick start

Download the two free local models:

```sh
ollama pull llama3.2:3b
ollama pull nomic-embed-text
```

Start Ollama with its desktop app, or `ollama serve` if it is not already running. It listens on port 11434 by default.

From `backend/`, create a Python environment and start the API:

```sh
python -m venv .venv
```

Activate on Windows PowerShell: `.venv\Scripts\Activate.ps1`

Activate on macOS/Linux: `source .venv/bin/activate`

```sh
python -m pip install -r requirements.lock.txt
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

In another terminal, from `frontend/`:

```sh
npm ci
npm run dev
```

Open **http://127.0.0.1:5173**. API documentation is available at **http://127.0.0.1:8000/docs**. Keep both terminals running. No environment file is required for the default setup.

1. Upload up to 10 PDF, DOCX, or UTF-8 TXT files at once (20 MB each).
2. Select the documents to include using their checkboxes.
3. Ask a question. Use Enter to send and Shift+Enter for a new line.
4. Click a citation or retrieved source to inspect its original excerpt and PDF page number.
5. Reopen conversations from the sidebar; manage and delete documents in the library.

## Architecture

```text
React → FastAPI → text extraction → LangChain text splitter
                                → Ollama embeddings → persistent ChromaDB

Question + recent user turns → scoped similarity search → numbered source excerpts
                            → local Ollama chat model → answer + source metadata
                                                     → SQLite conversation history
```

- **Extraction:** pypdf for PDF pages; python-docx for paragraphs and tables; UTF-8 decoding for TXT. DOCX/TXT citations use chunk numbers because they have no reliable page boundaries.
- **Chunking:** recursive character splitting with 1,000-character chunks and 180-character overlap.
- **Retrieval:** five nearest chunks filtered to selected document IDs. Recent user messages help resolve follow-up queries. Similarity retrieval can return weak matches; the model is instructed to abstain when evidence is insufficient.
- **Generation:** temperature 0, 8,192-token context, bounded output, numbered source context, and instructions to treat documents as untrusted data.
- **Persistence:** Chroma holds chunk text, metadata, and embeddings; SQLite holds document metadata and chat turns. Both live in `backend/data/`. Original binary uploads are not retained.
- **Failure handling:** individual upload results, partial index cleanup, actionable service errors, and atomic chat-turn commits. A process-local lock serializes generation and document mutation to avoid deletion races. Run **one backend worker**.

## Project layout

```text
backend/
  app/config.py       Environment configuration
  app/extraction.py   Parsing and chunking
  app/rag.py          Ollama embeddings, retrieval, generation
  app/store.py        SQLite persistence
  app/main.py         REST API and orchestration
  tests/test_api.py   Extraction, retrieval, lifecycle and failure tests
frontend/
  src/api.js          REST client
  src/main.jsx        Chat, library, uploads and citation viewer
  src/styles.css     Responsive workspace UI
```

## REST API

| Method | Route | Purpose |
|---|---|---|
| GET | `/api/health` | Ollama status and missing models |
| GET | `/api/documents` | Indexed document metadata |
| POST | `/api/documents` | Multipart upload; repeat the `files` field |
| DELETE | `/api/documents/{id}` | Delete document chunks and metadata |
| GET / POST | `/api/chats` | List / create conversations |
| DELETE | `/api/chats/{id}` | Delete a conversation and messages |
| GET | `/api/chats/{id}/messages` | Load full chat history and source snapshots |
| POST | `/api/chats/{id}/messages` | Answer and persist a question |

Question body:

```json
{"question":"What are the main findings?","document_ids":["document-id"]}
```

The answer includes `content`, `role`, and `sources`. Each source includes its numeric `id`, document ID, filename, PDF page (0 for other formats), chunk number, and full retrieved excerpt. Upload returns per-file `indexed` or `error` results; a successful HTTP batch response can contain failed files. Generation returns 503 on model/service failures and does not save an incomplete turn. Unknown resources return 404; invalid scope returns 400; invalid request bodies return 422.

## Configuration

Copy `backend/.env.example` to `backend/.env` if customizing. Run backend commands from `backend/` so relative paths are stable.

| Variable | Default |
|---|---|
| `OLLAMA_URL` | `http://localhost:11434` |
| `CHAT_MODEL` | `llama3.2:3b` |
| `EMBEDDING_MODEL` | `nomic-embed-text` |
| `DATA_DIR` | `data` |
| `MAX_UPLOAD_MB` | `20` |
| `MAX_TEXT_CHARS` | `2000000` |
| `RETRIEVAL_K` | `5` |
| `CORS_ORIGINS` | JSON list of localhost/127.0.0.1 origins on port 5173 |

Changing embedding models requires a fresh Chroma index and re-uploading documents. Back up `data/` first, then remove both `data/chroma/` and `data/assistant.db` for a complete reset. This deletes the library and chats. Keep the same model for an existing index.

## Validation

```sh
# backend/
python -m pytest -q
# frontend/
npm run build
```

Backend tests use temporary databases, mocked Ollama calls, and a real local Chroma integration test with deterministic test embeddings; they do not require Ollama or download models. They cover batch upload errors, index rollback, deletion, DOCX tables, extraction rejection, retrieval scoping, citation metadata, chat persistence, and generation failure. GitHub Actions runs the backend tests and frontend build on pushes and pull requests. For live verification, follow the [walkthrough](docs/WALKTHROUGH.md).

Build output is in `frontend/dist/`. For a local build preview, run `npm run preview`; its `/api` proxy points to FastAPI on port 8000. For deployment, configure a reverse proxy that serves `dist/` and forwards `/api` to FastAPI. `requirements.lock.txt` records the tested Python environment; `requirements.txt` contains the supported direct dependency ranges. Use `npm ci` to install the locked frontend dependencies.

## Limitations and troubleshooting

- **Ollama offline / missing models:** run `ollama list`, verify both model names, then check `http://localhost:11434/api/tags`. The UI checks readiness every 30 seconds.
- **No readable text:** scanned PDFs need OCR first. Password-protected PDFs are rejected. TXT must be UTF-8. DOCX images, headers, footnotes, and embedded objects are not extracted; paragraph/table order is simplified.
- **Slow first answer:** model loading and CPU inference can take time; generation is synchronous and the UI shows a loading state. Answers are not streamed.
- **Citations:** sources are retrieved excerpts, not a guarantee of entailment. The LLM may omit or misuse citation numbers. Verify claims against the excerpt; this app does not guarantee factual accuracy or implement a citation verifier.
- **Deletion:** removing a document deletes its searchable text and vectors. Historical chats retain the answer and source excerpt snapshots until that conversation is deleted.
- **Privacy/security:** intended as a single-user local application. There is no authentication, tenant isolation, or internet-facing upload hardening. Bind to loopback. Do not expose the API publicly. Document instructions are treated as untrusted, but prompt injection remains possible.
- **Upload resource limits:** per-file parsing limits and DOCX expansion checks are included. Multipart bodies are parsed by the server before per-file validation; use reverse-proxy body/time limits for any deployment beyond trusted local use.
- **Crash consistency:** SQLite and Chroma do not share a transaction. Normal failures are cleaned up, but abrupt termination during indexing can leave orphan chunks; retrieval only searches registered document IDs. Back up both stores together.

## References

[Ollama API](https://github.com/ollama/ollama/blob/main/docs/api.md) · [LangChain Ollama embeddings](https://reference.langchain.com/python/langchain-ollama/embeddings/OllamaEmbeddings) · [Chroma](https://docs.trychroma.com/)
