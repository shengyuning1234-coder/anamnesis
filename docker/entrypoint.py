"""PID 1 supervises the gateway and both services, propagates signals and persists WebUI secrets."""
import json, os, re, secrets, signal, subprocess, sys, time
from pathlib import Path
from seed_cache import seed_cache

words=Path(os.environ.get('APP_DATA_DIR','/data/words'))
chat=Path(os.environ.get('DATA_DIR','/data/openwebui'))
for folder in (words,chat):folder.mkdir(parents=True,exist_ok=True)
os.environ.setdefault('LOCAL_EMBEDDING_MODEL_PATH', str(chat/'cache/multilingual-minilm'))
from prepare_runtime import prepare
prepare()
(chat/'.integration-ready.json').unlink(missing_ok=True)
parent=os.environ.get('APP_PUBLIC_URL','http://localhost:5050').rstrip('/')
webui=parent
for url in (parent,webui):
    from urllib.parse import urlsplit
    parsed=urlsplit(url)
    if parsed.scheme not in ('http','https') or not parsed.netloc or parsed.path not in ('','/') or parsed.query or parsed.fragment:raise SystemExit('APP_PUBLIC_URL must be a full origin, without a path')
secret=chat/'.webui_secret_key'
try:
    with secret.open('x',encoding='utf-8') as stream:stream.write(secrets.token_urlsafe(48))
    secret.chmod(0o600)
except FileExistsError:pass
build=Path(os.environ.get('FRONTEND_BUILD_DIR','/app/build'))
index=build/'index.html'
bridge=Path('/opt/anamnesis/deploy/theme-bridge.js').read_text(encoding='utf-8').replace('__PARENT_ORIGINS__','[window.location.origin]')
html=re.sub(r'<script id="anamnesis-theme-bridge">.*?</script>','',index.read_text(encoding='utf-8'),flags=re.S)
index.write_text(html.replace('</head>','<script id="anamnesis-theme-bridge">'+bridge+'</script></head>'),encoding='utf-8')
os.environ['GATEWAY_AUTH_SECRET']=secrets.token_urlsafe(48)
def local_origins(origin):
    from urllib.parse import urlsplit
    parsed = urlsplit(origin)
    if parsed.hostname in ('localhost', '127.0.0.1'):
        port = ':' + str(parsed.port) if parsed.port else ''
        return ';'.join(parsed.scheme + '://' + host + port for host in ('127.0.0.1', 'localhost'))
    return origin

word_env={**os.environ,'HOST':'127.0.0.1','PORT':'5052','OPENWEBUI_EMBED_URL':'/','APP_URL_PREFIX':'/words','BUNDLED_WEBUI':'1','TRUSTED_PROXY':'127.0.0.1',
          'COOKIE_SECURE':'1' if parent.startswith('https://') else '0'}
chat_env={**os.environ,'HOST':'127.0.0.1','PORT':'5051','WEBUI_URL':webui,
          'WEBUI_AUTH_TRUSTED_EMAIL_HEADER':'X-Anamnesis-Email',
          'WEBUI_AUTH_TRUSTED_NAME_HEADER':'X-Anamnesis-Name',
          'WEBUI_AUTH_TRUSTED_ROLE_HEADER':'X-Anamnesis-Role',
          'ENABLE_SIGNUP':'false','DEFAULT_USER_ROLE':'user',
          'ENABLE_TOOL_SERVERS':'true','ENABLE_WEB_SEARCH':'true',
          'ENABLE_MEMORIES':'true','ENABLE_MEMORY_BACKGROUND_REVIEW':'true',
          'MEMORIES_REVIEW_INTERVAL_TURNS':'1','ENABLE_MEMORY_SYSTEM_CONTEXT':'true',
          'WEBUI_SECRET_KEY':os.environ.get('WEBUI_SECRET_KEY') or secret.read_text().strip(),
          'CORS_ALLOW_ORIGIN':local_origins(parent),
          'CONTENT_SECURITY_POLICY':"frame-ancestors 'self' "+parent}
processes=[]
stopping=False
def stop(signum=None,frame=None):
    global stopping
    stopping=True
    for process in processes:
        if process.poll() is None:process.terminate()
signal.signal(signal.SIGTERM,stop);signal.signal(signal.SIGINT,stop)
try:
    processes.append(subprocess.Popen(['/opt/anamnesis-venv/bin/python','-u','web_server.py'],cwd='/opt/anamnesis',env=word_env))
    processes.append(subprocess.Popen([sys.executable,'-m','uvicorn','open_webui.main:app','--host','127.0.0.1','--port','5051','--forwarded-allow-ips',os.getenv('FORWARDED_ALLOW_IPS','127.0.0.1')],cwd='/app/backend',env=chat_env))
    processes.append(subprocess.Popen([sys.executable,'/opt/anamnesis-docker/gateway.py']))
    processes.append(subprocess.Popen(['/opt/anamnesis-search-venv/bin/python','/opt/anamnesis-docker/local_services.py']))
    processes.append(subprocess.Popen(['/opt/anamnesis-embedding-venv/bin/python','/opt/anamnesis-docker/embedding_service.py']))
    bootstrap=subprocess.Popen([sys.executable,'/opt/anamnesis-docker/bootstrap.py'])
    print('Anamnesis:',parent,'OpenWebUI:',webui,flush=True)
    while not stopping and all(p.poll() is None for p in processes) and bootstrap.poll() in (None,0):time.sleep(.5)
    failed=not stopping
finally:
    if 'bootstrap' in globals() and bootstrap.poll() is None:bootstrap.terminate()
    stop()
    deadline=time.monotonic()+25
    for process in processes:
        try:process.wait(timeout=max(.1,deadline-time.monotonic()))
        except subprocess.TimeoutExpired:process.kill();process.wait()
    if 'bootstrap' in globals():
        try:bootstrap.wait(timeout=3)
        except subprocess.TimeoutExpired:bootstrap.kill();bootstrap.wait()
raise SystemExit(1 if failed else 0)
