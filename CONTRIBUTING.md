# Contributing

## Development setup

Follow the [README](README.md) to install Python 3.12, Node.js, and the local
Ollama models. Install Python dependencies from `backend/requirements.lock.txt`
and frontend dependencies with `npm ci` from `frontend/`.

Keep backend commands in `backend/` so the default database path stays stable.
The application is intended for one local user and one backend worker.

## Before submitting a change

```sh
# In backend/ with the virtual environment active
python -m pytest -q

# In frontend/
npm ci
npm run build
```

For changes to extraction, retrieval, or prompts, also follow the
[live walkthrough](docs/WALKTHROUGH.md). Tests avoid downloading model weights;
the Chroma integration test uses deterministic local test embeddings.

Explain the behavior changed, why it matters, and the checks you ran in your
pull request. Add focused tests for new failure cases or retrieval behavior.
Update the README when API contracts, model defaults, or setup steps change.

## Repository hygiene

Never commit uploaded documents, databases, embeddings, `.env` files, secrets,
virtual environments, `node_modules`, or generated build output. The checked-in
`.env.example` contains only local defaults. Use fictional sample content in
tests and examples. Do not paste private document text into issues or logs.

When updating dependencies, refresh the appropriate lock file, run the checks,
and describe any model or index migration required. Changing embedding models
requires rebuilding the existing vector index.
