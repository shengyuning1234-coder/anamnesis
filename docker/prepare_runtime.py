"""Seed packaged assets and fetch missing models before starting dependent services."""
import os
import time
import subprocess
from pathlib import Path
from seed_cache import seed_cache


def prepare():
    data = Path(os.environ.get('DATA_DIR', '/data/openwebui'))
    seed_cache(Path('/opt/anamnesis-bundled-cache'), data / 'cache')
    model_path = Path(os.environ['LOCAL_EMBEDDING_MODEL_PATH'])
    seed_cache(Path('/opt/anamnesis-models/multilingual-minilm'), model_path)
    # Real inference verifies weights instead of trusting a partial download.
    try:
        subprocess.run(['/opt/anamnesis-embedding-venv/bin/python', '-c',
            "import sys;sys.path.insert(0,'/opt/anamnesis-docker');from embedding_model import load_model;next(load_model().embed(['模型启动校验']))"], check=True)
    except Exception:
        if os.getenv('AUTO_DOWNLOAD_MODELS', '1') != '1':
            raise RuntimeError('Local embedding files are missing; enable AUTO_DOWNLOAD_MODELS=1') from None
        for attempt in range(3):
            try:
                subprocess.run(['/opt/anamnesis-embedding-venv/bin/python', '/opt/anamnesis-docker/embedding_model.py'], check=True)
                break
            except Exception:
                if attempt == 2:
                    raise
                print('[Runtime] Model download interrupted; retrying', flush=True)
                time.sleep(3)
    if os.getenv('PREFETCH_WHISPER', '1') == '1':
        from faster_whisper import WhisperModel
        model = WhisperModel(os.getenv('WHISPER_MODEL', 'base'), device='cpu', compute_type='int8',
                             download_root=os.environ['WHISPER_MODEL_DIR'],
                             local_files_only=os.getenv('AUTO_DOWNLOAD_MODELS', '1') != '1')
        del model
    print('[Runtime] Local model assets verified', flush=True)


if __name__ == '__main__':
    prepare()
