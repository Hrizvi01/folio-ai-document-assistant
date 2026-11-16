from io import BytesIO
from pathlib import Path
from zipfile import ZipFile, BadZipFile
from docx import Document as WordDocument
from pypdf import PdfReader
from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter
from .config import settings


def extract(name: str, content: bytes, document_id: str):
    suffix = Path(name).suffix.lower()
    pages = []
    if suffix == '.pdf':
        pdf = PdfReader(BytesIO(content))
        if pdf.is_encrypted:
            raise ValueError('Encrypted PDFs are unsupported. Upload an unlocked copy.')
        if len(pdf.pages) > 1000:
            raise ValueError('PDFs must have at most 1,000 pages.')
        total = 0
        for i, page in enumerate(pdf.pages):
            text = page.extract_text() or ''
            total += len(text)
            if total > settings.max_text_chars:
                raise ValueError('Document contains too much text.')
            pages.append((i + 1, text))
    elif suffix == '.docx':
        with ZipFile(BytesIO(content)) as archive:
            if sum(item.file_size for item in archive.infolist()) > 50_000_000:
                raise ValueError('Expanded DOCX exceeds the 50 MB limit.')
        word = WordDocument(BytesIO(content))
        text = '\n'.join([p.text for p in word.paragraphs] +
                         [' | '.join(c.text for c in row.cells) for table in word.tables for row in table.rows])
        pages = [(0, text)]
    elif suffix == '.txt':
        try:
            pages = [(0, content.decode('utf-8-sig'))]
        except UnicodeDecodeError as exc:
            raise ValueError('TXT files must use UTF-8 encoding.') from exc
    else:
        raise ValueError('Supported file types: PDF, DOCX, TXT.')
    if sum(len(text) for _, text in pages) > settings.max_text_chars:
        raise ValueError('Document contains too much text.')
    docs = [Document(page_content=text.strip(), metadata={
        'document_id': document_id, 'filename': name, 'page': page,
    }) for page, text in pages if text.strip()]
    if not docs:
        raise ValueError('No readable text found. Scanned PDFs require OCR before upload.')
    chunks = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=180).split_documents(docs)
    for i, chunk in enumerate(chunks):
        chunk.metadata['chunk'] = i + 1
    return chunks
