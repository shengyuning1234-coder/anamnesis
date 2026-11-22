import urllib.request
import json
for path in ('/words/health','/health'):
    with urllib.request.urlopen('http://127.0.0.1:5050'+path,timeout=4) as response:
        if response.status!=200:raise SystemExit(1)
with urllib.request.urlopen('http://127.0.0.1:5053/health',timeout=4) as response:
    if not json.load(response).get('configured'):raise SystemExit(1)
with urllib.request.urlopen('http://127.0.0.1:5054/health',timeout=4) as response:
    if not json.load(response).get('ok'):raise SystemExit(1)
