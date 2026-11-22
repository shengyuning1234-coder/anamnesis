"""Inject a one-way theme receiver into the bundled OpenWebUI frontend.

Fails visibly if the selected upstream image changes its frontend layout.
It does not read or modify OpenWebUI's settings/database.
"""
import os, json, re
from pathlib import Path
paths=[Path('/app/build/index.html'),Path('/app/backend/open_webui/static/index.html')]
target=next((p for p in paths if p.exists()),None)
if target is None: raise RuntimeError('OpenWebUI index.html layout changed; update deploy/inject_theme.py for the selected image')
allowed=[x.strip().rstrip('/') for x in os.getenv('ANAMNESIS_PARENT_ORIGINS','http://localhost:5050,http://127.0.0.1:5050').split(',') if x.strip()]
script=Path('/opt/anamnesis/deploy/theme-bridge.js').read_text().replace('__PARENT_ORIGINS__',json.dumps(allowed))
html=target.read_text()
html=re.sub(r'<script id="anamnesis-theme-bridge">.*?</script>','',html,flags=re.S)
html=html.replace('</head>','<script id="anamnesis-theme-bridge">'+script+'</script></head>')
target.write_text(html)
