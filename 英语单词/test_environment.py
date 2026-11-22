"""Set the disposable data directory before importing any application module."""
import os
import sys
import tempfile
from pathlib import Path

if 'config' in sys.modules:
    active = Path(sys.modules['config']._DATA_DIR).resolve()
    if not (active.is_relative_to(Path(tempfile.gettempdir()).resolve()) and active.name.startswith('anamnesis-test-')):
        raise RuntimeError('Refusing tests: config was already imported with a non-test database')
    TEST_DATA = active
else:
    TEST_DATA = Path(tempfile.mkdtemp(prefix='anamnesis-test-'))
os.environ['APP_DATA_DIR'] = str(TEST_DATA)
