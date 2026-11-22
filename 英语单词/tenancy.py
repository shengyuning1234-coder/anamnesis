"""Request and worker scoped storage; legacy data remains in the root profile."""
from contextvars import ContextVar
from pathlib import Path
import os

ROOT = Path(os.environ.get('APP_DATA_DIR', Path(__file__).parent / 'data')).resolve()
profile = ContextVar('word_profile', default='admin')

def directory():
    user = profile.get()
    return ROOT if user == 'admin' else ROOT / 'users' / user

def path(name):
    folder = directory()
    folder.mkdir(parents=True, exist_ok=True)
    return str(folder / name)
