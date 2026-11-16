from io import BytesIO
from unittest.mock import Mock
import pytest
from fastapi.testclient import TestClient
from docx import Document
from app.config import settings
from app.main import app
from app import rag, store
from app.extraction import extract


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, 'data_dir', tmp_path)
    index = Mock()
    monkeypatch.setattr(rag, 'vectors', lambda: index)
    with TestClient(app) as client:
        yield client, index


def test_extract_utf8_and_docx():
    chunks = extract('notes.txt', b'Hello world. ' * 250, 'doc')
    assert len(chunks) > 1
    assert chunks[0].metadata == {'document_id': 'doc', 'filename': 'notes.txt', 'page': 0, 'chunk': 1}
    word = Document()
    word.add_paragraph('A paragraph')
    word.add_table(rows=1, cols=1).cell(0, 0).text = 'Table evidence'
    buf = BytesIO()
    word.save(buf)
    assert 'Table evidence' in extract('report.docx', buf.getvalue(), 'doc')[0].page_content


def test_upload_batch_and_delete(client):
    client, index = client
    response = client.post('/api/documents', files=[('files', ('good.txt', b'Source material')),
                                                  ('files', ('bad.exe', b'not supported'))])
    assert response.status_code == 201
    results = response.json()['results']
    assert [r['status'] for r in results] == ['indexed', 'error']
    document_id = results[0]['id']
    assert len(client.get('/api/documents').json()) == 1
    assert client.delete('/api/documents/' + document_id).status_code == 204
    index.delete.assert_called_with(where={'document_id': document_id})
    assert client.get('/api/documents').json() == []


def test_failed_index_is_not_registered(client):
    client, index = client
    index.add_documents.side_effect = RuntimeError('offline')
    response = client.post('/api/documents', files={'files': ('notes.txt', b'Evidence')})
    assert response.json()['results'][0]['status'] == 'error'
    assert client.get('/api/documents').json() == []
    index.delete.assert_called_once()


def test_chat_persistence_and_atomic_failure(client, monkeypatch):
    client, _ = client
    doc = client.post('/api/documents', files={'files': ('notes.txt', b'Evidence')}).json()['results'][0]['id']
    chat = client.post('/api/chats').json()['id']
    monkeypatch.setattr(rag, 'answer', lambda q, ids, h: ('A supported fact [1].', [{'id': 1, 'excerpt': 'Evidence'}]))
    payload = {'question': 'What does it say?', 'document_ids': [doc]}
    assert client.post(f'/api/chats/{chat}/messages', json=payload).status_code == 200
    messages = client.get(f'/api/chats/{chat}/messages').json()
    assert len(messages) == 2 and messages[1]['sources'][0]['excerpt'] == 'Evidence'
    assert client.get('/api/chats').json()[0]['title'] == payload['question']
    def fail(*args):
        raise RuntimeError('Ollama offline')
    monkeypatch.setattr(rag, 'answer', fail)
    assert client.post(f'/api/chats/{chat}/messages', json=payload).status_code == 503
    assert len(client.get(f'/api/chats/{chat}/messages').json()) == 2
    payload['document_ids'] = ['missing']
    assert client.post(f'/api/chats/{chat}/messages', json=payload).status_code == 400
    assert client.delete(f'/api/chats/{chat}').status_code == 204
    assert client.get(f'/api/chats/{chat}/messages').status_code == 404


def test_retrieval_scope_and_source_metadata(monkeypatch):
    from langchain_core.documents import Document as Chunk
    index = Mock()
    index.similarity_search.return_value = [Chunk(page_content='Ground truth', metadata={
        'document_id': 'one', 'filename': 'report.pdf', 'page': 3, 'chunk': 4})]
    llm = Mock()
    llm.invoke.return_value.content = 'Ground truth [1].'
    monkeypatch.setattr(rag, 'vectors', lambda: index)
    monkeypatch.setattr(rag, 'ChatOllama', lambda **kwargs: llm)
    text, sources = rag.answer('What is true?', ['one', 'two'], [])
    assert index.similarity_search.call_args.kwargs['filter'] == {'document_id': {'$in': ['one', 'two']}}
    assert sources[0]['page'] == 3 and sources[0]['excerpt'] == 'Ground truth'
    assert text.endswith('[1].')


@pytest.mark.parametrize('name,content', [('empty.txt', b'  '), ('invalid.txt', b'\xff'), ('bad.csv', b'a,b')])
def test_reject_unreadable(name, content):
    with pytest.raises(ValueError):
        extract(name, content, 'id')


def test_chroma_persistence_filter_and_delete(tmp_path):
    from langchain_chroma import Chroma
    from langchain_core.embeddings import Embeddings
    class LocalEmbeddings(Embeddings):
        def embed_documents(self, texts):
            return [[1.0, 0.1, 0.2] for _ in texts]
        def embed_query(self, text):
            return [1.0, 0.1, 0.2]
    kwargs = dict(collection_name='test_documents', persist_directory=str(tmp_path / 'chroma'),
                  embedding_function=LocalEmbeddings())
    index = Chroma(**kwargs)
    index.add_documents(extract('one.txt', b'First document evidence.', 'one'), ids=['one:0'])
    index.add_documents(extract('two.txt', b'Second document evidence.', 'two'), ids=['two:0'])
    reopened = Chroma(**kwargs)
    found = reopened.similarity_search('evidence', k=5, filter={'document_id': 'one'})
    assert len(found) == 1 and found[0].metadata['filename'] == 'one.txt'
    reopened.delete(where={'document_id': 'one'})
    assert reopened.similarity_search('evidence', filter={'document_id': 'one'}) == []


def test_pdf_page_metadata(monkeypatch):
    import app.extraction as extraction
    reader = Mock(is_encrypted=False)
    reader.pages = [Mock(), Mock()]
    reader.pages[0].extract_text.return_value = 'First page evidence'
    reader.pages[1].extract_text.return_value = 'Second page evidence'
    monkeypatch.setattr(extraction, 'PdfReader', lambda stream: reader)
    chunks = extraction.extract('report.pdf', b'pdf fixture', 'id')
    assert [c.metadata['page'] for c in chunks] == [1, 2]
