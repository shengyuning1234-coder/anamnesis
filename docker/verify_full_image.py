"""Real container smoke checks for the full runtime; no external AI calls."""
import importlib
import os
import shutil
import subprocess
import sys
import tempfile
from collections import defaultdict
from pathlib import Path


def main():
    sys.path.insert(0, '/app/backend')
    os.environ['WEBUI_SECRET_KEY'] = os.environ.get('WEBUI_SECRET_KEY') or (Path(os.getenv('DATA_DIR', '/data/openwebui'))/'.webui_secret_key').read_text().strip()
    os.environ.setdefault('CORS_ALLOW_ORIGIN', 'http://127.0.0.1:5050')
    from open_webui.env import USE_SLIM
    assert not USE_SLIM, 'A full base image is required'
    for name in ('torch', 'sentence_transformers', 'transformers', 'faster_whisper',
                 'pydub', 'playwright', 'unstructured', 'pypdf', 'docx', 'openpyxl',
                 'azure.storage.blob', 'chromadb'):
        importlib.import_module(name)
    for name in ('ffmpeg', 'pandoc', 'tesseract', 'pdftoppm', 'libreoffice'):
        assert shutil.which(name), name
    print('PASS full runtime imports, document/audio/OCR binaries and native Chroma', flush=True)

    from playwright.sync_api import sync_playwright
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page()
        page.set_content('<div id="result"></div><script>document.querySelector("#result").textContent="rendered"</script>')
        assert page.locator('#result').inner_text() == 'rendered'
        browser.close()
    print('PASS container Chromium starts and executes JavaScript', flush=True)

    from docx import Document
    from openpyxl import Workbook
    from open_webui.retrieval.loaders.main import Loader
    config = defaultdict(lambda: None, {'rag.content_extraction_engine': '',
        'rag.pdf_extract_images': False, 'rag.pdf_loader_mode': 'page'})
    loader = Loader(config)
    with tempfile.TemporaryDirectory() as temp:
        root = Path(temp)
        document = Document()
        document.add_paragraph('Anamnesis full document verification')
        document.save(root/'sample.docx')
        docs = loader.load('sample.docx', 'application/vnd.openxmlformats-officedocument.wordprocessingml.document', str(root/'sample.docx'))
        assert any('Anamnesis full' in doc.page_content for doc in docs)
        workbook = Workbook()
        workbook.active.append(['Anamnesis spreadsheet verification', 'value'])
        workbook.active.append(['local', 42])
        workbook.save(root/'sample.xlsx')
        docs = loader.load('sample.xlsx', 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', str(root/'sample.xlsx'))
        assert any('Anamnesis spreadsheet' in doc.page_content for doc in docs)
        subprocess.run(['libreoffice', '-env:UserInstallation=file://'+temp+'/lo-profile',
            '--headless', '--convert-to', 'pdf', '--outdir', temp, str(root/'sample.docx')],
            check=True, capture_output=True, timeout=90)
        docs = loader.load('sample.pdf', 'application/pdf', str(root/'sample.pdf'))
        assert any('Anamnesis full' in doc.page_content for doc in docs)
        from PIL import Image, ImageDraw, ImageFont
        image = Image.new('RGB', (900, 160), 'white')
        font = ImageFont.truetype('/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf', 56)
        ImageDraw.Draw(image).text((25, 35), 'LOCAL MEMORY 12345', font=font, fill='black')
        image.save(root/'ocr.png')
        text = subprocess.run(['tesseract', str(root/'ocr.png'), 'stdout', '-l', 'eng'],
            capture_output=True, check=True, text=True, timeout=30).stdout
        assert 'MEMORY' in text and '12345' in text
    print('PASS native OpenWebUI DOCX/XLSX/PDF extraction and headless Office conversion', flush=True)
    print('PASS local image OCR without any hosted service or API key', flush=True)

    from faster_whisper import WhisperModel
    whisper = WhisperModel(os.getenv('WHISPER_MODEL', 'base'), device='cpu', compute_type='int8',
        download_root=os.environ['WHISPER_MODEL_DIR'], local_files_only=True)
    import numpy as np
    segments, _ = whisper.transcribe(np.zeros(16000, dtype=np.float32), language='en', vad_filter=False)
    list(segments)
    print('PASS bundled Whisper loads offline and transcribes local audio on CPU', flush=True)


if __name__ == '__main__':
    main()
