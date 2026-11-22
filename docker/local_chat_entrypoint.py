"""Local chat using the cached v0.12.3 runtime and the current application source.

Uses pgvector for the cached slim runtime. Full-image OCR, local embeddings and
automatic memory extraction are not advertised by this local launcher.
"""
import os
import re
import secrets
import signal
import subprocess
import sys
import time
from pathlib import Path

chat = Path('/data/openwebui')
chat.mkdir(parents=True, exist_ok=True)
(chat / '.integration-ready.json').unlink(missing_ok=True)
secret_file = chat / '.webui_secret_key'
if not secret_file.exists():
    with secret_file.open('x') as f:
        f.write(secrets.token_urlsafe(48))
    secret_file.chmod(0o600)
os.environ['GATEWAY_AUTH_SECRET'] = secrets.token_urlsafe(48)
origin = os.environ['APP_PUBLIC_URL'].rstrip('/')
index = Path('/app/build/index.html')
html = re.sub(r'<script id="anamnesis-theme-bridge">.*?</script>', '', index.read_text(), flags=re.S)
bridge = Path('/opt/anamnesis/deploy/theme-bridge.js').read_text().replace('__PARENT_ORIGINS__', '[window.location.origin]')
index.write_text(html.replace('</head>', '<script id="anamnesis-theme-bridge">' + bridge + '</script></head>'))
def local_origins(origin):
    from urllib.parse import urlsplit
    parsed = urlsplit(origin)
    if parsed.hostname in ('localhost', '127.0.0.1'):
        port = ':' + str(parsed.port) if parsed.port else ''
        return ';'.join(parsed.scheme + '://' + host + port for host in ('127.0.0.1', 'localhost'))
    return origin

word_env = {**os.environ, 'HOST': '127.0.0.1', 'PORT': '5052',
            'BUNDLED_WEBUI': '1', 'APP_URL_PREFIX': '/words', 'TRUSTED_PROXY': '127.0.0.1'}
chat_env = {**os.environ, 'HOST': '127.0.0.1', 'PORT': '5051', 'WEBUI_URL': origin,
            'WEBUI_SECRET_KEY': secret_file.read_text().strip(),
            'WEBUI_AUTH_TRUSTED_EMAIL_HEADER': 'X-Anamnesis-Email',
            'WEBUI_AUTH_TRUSTED_NAME_HEADER': 'X-Anamnesis-Name',
            'WEBUI_AUTH_TRUSTED_ROLE_HEADER': 'X-Anamnesis-Role',
            'ENABLE_SIGNUP': 'false', 'DEFAULT_USER_ROLE': 'user',
            'ENABLE_TOOL_SERVERS': 'true', 'CORS_ALLOW_ORIGIN': local_origins(origin),
            'CONTENT_SECURITY_POLICY': "frame-ancestors 'self' " + origin}
processes = []
stopping = False


def stop(*args):
    global stopping
    stopping = True
    for p in processes:
        if p.poll() is None:
            p.terminate()


signal.signal(signal.SIGTERM, stop)
signal.signal(signal.SIGINT, stop)
try:
    processes.append(subprocess.Popen(['/opt/anamnesis-venv/bin/python', '-u', 'web_server.py'], cwd='/opt/anamnesis', env=word_env))
    processes.append(subprocess.Popen([sys.executable, '-m', 'uvicorn', 'open_webui.main:app', '--host', '127.0.0.1', '--port', '5051'], cwd='/app/backend', env=chat_env))
    processes.append(subprocess.Popen([sys.executable, '/opt/anamnesis-docker/gateway.py']))
    processes.append(subprocess.Popen([sys.executable, '/opt/anamnesis-docker/local_services.py'], env={**os.environ, 'PYTHONPATH': '/data/openwebui/runtime-search'}))
    processes.append(subprocess.Popen([sys.executable, '/opt/anamnesis-docker/bootstrap_chat.py']))
    while not stopping:
        # Bootstrap exits successfully once configuration is complete.
        if any(p.poll() is not None for p in processes[:4]) or processes[4].poll() not in (None, 0):
            raise RuntimeError('A local chat service stopped; inspect container logs')
        time.sleep(.5)
finally:
    stop()
    for p in processes:
        try:
            p.wait(timeout=10)
        except subprocess.TimeoutExpired:
            p.kill()
