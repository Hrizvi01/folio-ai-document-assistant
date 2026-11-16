import logging
import threading
from contextlib import asynccontextmanager
from pathlib import Path
from uuid import uuid4
import json
import httpx
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from .config import settings
from . import store, rag
from .extraction import extract

logger = logging.getLogger(__name__)
mutation_lock = threading.RLock()


@asynccontextmanager
async def lifespan(app):
    store.initialize()
    yield


app = FastAPI(title='Folio • Local Document Assistant', version='1.0.0', lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origins,
                   allow_methods=['GET', 'POST', 'DELETE'], allow_headers=['Content-Type'])


class Question(BaseModel):
    question: str = Field(min_length=1, max_length=4000)
    document_ids: list[str] = Field(min_length=1, max_length=100)


def require_chat(chat_id):
    if not store.rows('SELECT id FROM chats WHERE id=?', (chat_id,)):
        raise HTTPException(404, 'Chat not found.')


@app.get('/api/health')
def health():
    try:
        response = httpx.get(settings.ollama_url + '/api/tags', timeout=3)
        response.raise_for_status()
        models = [m['name'] for m in response.json()['models']]
        missing = [m for m in [settings.chat_model, settings.embedding_model]
                   if m not in models and m + ':latest' not in models]
        return {'status': 'ready' if not missing else 'missing_models', 'models': models,
                'missing_models': missing, 'chat_model': settings.chat_model}
    except Exception:
        return {'status': 'offline', 'models': [], 'chat_model': settings.chat_model}


@app.get('/api/documents')
def documents():
    return store.rows('SELECT * FROM documents ORDER BY created_at DESC, id')


@app.post('/api/documents', status_code=201)
def upload(files: list[UploadFile] = File(...)):
    if len(files) > 10:
        raise HTTPException(400, 'Upload at most 10 files per batch.')
    results = []
    for file in files:
        document_id = uuid4().hex
        name = (file.filename or 'untitled').replace('\\', '/').split('/')[-1][:240]
        try:
            content = file.file.read(settings.max_upload_mb * 1024 * 1024 + 1)
            if len(content) > settings.max_upload_mb * 1024 * 1024:
                raise ValueError(f'File exceeds the {settings.max_upload_mb} MB limit.')
            if not content:
                raise ValueError('File is empty.')
            chunks = extract(name, content, document_id)
            with mutation_lock:
                try:
                    rag.vectors().add_documents(chunks, ids=[f'{document_id}:{i}' for i in range(len(chunks))])
                    store.execute('INSERT INTO documents(id,name,size,chunks) VALUES(?,?,?,?)',
                                  (document_id, name, len(content), len(chunks)))
                except Exception:
                    # Remove even a partially written batch before reporting failure.
                    try:
                        rag.vectors().delete(where={'document_id': document_id})
                    except Exception:
                        logger.exception('Index cleanup failed for %s', document_id)
                    raise
            results.append({'filename': name, 'id': document_id, 'status': 'indexed', 'chunks': len(chunks)})
        except ValueError as exc:
            results.append({'filename': name, 'status': 'error', 'error': str(exc)})
        except Exception:
            logger.exception('Upload failed: %s', name)
            results.append({'filename': name, 'status': 'error',
                            'error': 'Could not parse or index this file. Check the file and Ollama embedding model; see backend logs.'})
        finally:
            file.file.close()
    return {'results': results}


@app.delete('/api/documents/{document_id}', status_code=204)
def delete_document(document_id: str):
    with mutation_lock:
        if not store.rows('SELECT id FROM documents WHERE id=?', (document_id,)):
            raise HTTPException(404, 'Document not found.')
        try:
            rag.vectors().delete(where={'document_id': document_id})
            store.execute('DELETE FROM documents WHERE id=?', (document_id,))
        except Exception as exc:
            logger.exception('Deletion failed')
            raise HTTPException(503, 'Could not delete document. Please retry.') from exc


@app.get('/api/chats')
def chats():
    return store.rows('SELECT * FROM chats ORDER BY created_at DESC, id')


@app.post('/api/chats', status_code=201)
def create_chat():
    chat_id = uuid4().hex
    store.execute('INSERT INTO chats(id,title) VALUES(?,?)', (chat_id, 'New conversation'))
    return {'id': chat_id, 'title': 'New conversation'}


@app.get('/api/chats/{chat_id}/messages')
def get_messages(chat_id: str):
    require_chat(chat_id)
    return store.messages(chat_id)


@app.delete('/api/chats/{chat_id}', status_code=204)
def delete_chat(chat_id: str):
    with mutation_lock:
        require_chat(chat_id)
        store.execute('DELETE FROM chats WHERE id=?', (chat_id,))


@app.post('/api/chats/{chat_id}/messages')
def ask(chat_id: str, body: Question):
    question = body.question.strip()
    if not question:
        raise HTTPException(422, 'Question cannot be blank.')
    with mutation_lock:
        require_chat(chat_id)
        available = {d['id'] for d in documents()}
        if not set(body.document_ids).issubset(available):
            raise HTTPException(400, 'Some selected documents are missing. Refresh your library.')
        history = store.messages(chat_id)
        try:
            content, sources = rag.answer(question, list(dict.fromkeys(body.document_ids)), history)
        except Exception as exc:
            logger.exception('Generation failed')
            raise HTTPException(503, 'Ollama could not answer. Check that Ollama is running and both models are installed.') from exc
        # Commit both messages together; failed generation never leaves half a turn.
        with store.connection() as db:
            db.execute('INSERT INTO messages(chat_id,role,content) VALUES(?,?,?)', (chat_id, 'user', question))
            db.execute('INSERT INTO messages(chat_id,role,content,sources) VALUES(?,?,?,?)',
                       (chat_id, 'assistant', content, json.dumps(sources)))
            if not history:
                db.execute('UPDATE chats SET title=? WHERE id=?', (question[:65], chat_id))
        return {'role': 'assistant', 'content': content, 'sources': sources}
