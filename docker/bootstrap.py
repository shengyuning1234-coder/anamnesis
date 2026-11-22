"""Idempotently provision native MCP/search on every image start, including upgrades.

Use supported OpenWebUI APIs; retain model providers, keys, users and chats.
All credentials are internal runtime/session credentials, never user configuration.
"""
import copy
import json
import os
import time
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import quote, urlencode
from embedding_model import MODEL, REVISION, DIMENSIONS

MCP_ID = 'anamnesis'
MCP_TOOL_ID = 'server:mcp:' + MCP_ID
BASE = 'http://127.0.0.1:5051'


def call(path, data=None, token=None, headers=None, base=BASE, timeout=25):
    hdr = {'Content-Type': 'application/json', **(headers or {})}
    if token:
        hdr['Authorization'] = 'Bearer ' + token
    request = urllib.request.Request(base + path, headers=hdr,
        data=json.dumps(data, ensure_ascii=False).encode() if data is not None else None)
    with urllib.request.urlopen(request, timeout=timeout) as response:
        raw = response.read()
        return json.loads(raw) if raw else None


def metadata(value):
    meta = copy.deepcopy(value or {})
    tools = [x for x in (meta.get('toolIds') or []) if x != 'anamnesis_vocabulary']
    meta['toolIds'] = list(dict.fromkeys([*tools, MCP_TOOL_ID]))
    meta['capabilities'] = {**(meta.get('capabilities') or {}), 'web_search': True, 'memory': True}
    meta['defaultFeatureIds'] = list(dict.fromkeys([*(meta.get('defaultFeatureIds') or []), 'web_search']))
    return meta


def provision():
    secret = os.environ['GATEWAY_AUTH_SECRET']
    identity = call('/api/internal/integration-identity', headers={'X-Gateway-Secret': secret},
                    base='http://127.0.0.1:5052')
    auth = call('/api/v1/auths/signin', {'email': identity['email'], 'password': 'trusted-header'}, headers={
        'X-Anamnesis-Email': identity['email'], 'X-Anamnesis-Name': quote(identity['name']),
        'X-Anamnesis-Role': 'admin'})
    token = auth['token']
    config = call('/api/v1/configs/export', token=token)
    connection = {
        'type': 'mcp', 'url': 'http://127.0.0.1:5053/mcp', 'path': '',
        'auth_type': 'session', 'key': '',
        'info': {'id': MCP_ID, 'name': '忆溯词库与网络搜索（内置 MCP）',
                 'description': '自动使用当前用户的个人词库；提供查词、录词、分组和免密钥网络搜索。'},
        'config': {'enable': True, 'access_grants': [
            {'principal_type': 'user', 'principal_id': '*', 'permission': 'read'}]},
    }
    connections = [c for c in (config.get('tool_server.connections') or [])
                   if (c.get('info') or {}).get('id') != MCP_ID]
    connections.append(connection)
    if connections != config.get('tool_server.connections'):
        call('/api/v1/configs/tool_servers', {'TOOL_SERVER_CONNECTIONS': connections}, token)

    # Bypass embedding AND webpage-loader dependencies: source snippets and links
    # go straight to chat context; no embedding API or model download is needed.
    desired = {
        'web.search.enable': True, 'web.search.engine': 'external',
        'web.search.external_web_search_url': 'http://127.0.0.1:5053/search',
        'web.search.external_web_search_api_key': secret,
        'web.search.bypass_embedding_and_retrieval': True,
        'web.search.bypass_web_loader': True, 'web.search.result_count': 5,
        'web.search.concurrent_requests': 2,
        'models.default_metadata': metadata(config.get('models.default_metadata')),
        'memories.enable': True,
        'memories.system_context.enable': True,
        # Explicit project default: review every completed user turn so short
        # conversations can produce durable cross-chat memories as well.
        'memories.background_review.enable': True,
        'memories.review_interval_turns': 1,
    }
    interface = copy.deepcopy(config.get('ui.default_interface_settings') or {})
    interface['webSearch'] = 'always'
    desired['ui.default_interface_settings'] = interface
    changes = {k: v for k, v in desired.items() if config.get(k) != v}
    if changes:
        call('/api/v1/configs/import', {'config': changes}, token)

    # The UI defaults memory to config.features.enable_memories when the user's
    # setting is absent. Migrate the current admin's old override once, retaining
    # every other preference and respecting later manual opt-out.
    settings = call('/api/v1/users/user/settings?raw=true', token=token) or {}
    ui = settings.get('ui') or {}
    if ui.get('anamnesisMemoryDefaultsVersion') != 1:
        call('/api/v1/users/user/settings/update', {**settings, 'ui': {
            **ui, 'memory': True, 'anamnesisMemoryDefaultsVersion': 1}}, token)

    embed_health = call('/health', base='http://127.0.0.1:5054')
    if embed_health.get('model') != MODEL or embed_health.get('dimensions') != DIMENSIONS:
        raise RuntimeError('Local embedding model not ready')
    embedding = call('/api/v1/retrieval/embedding', token=token)
    embedding_url = 'http://127.0.0.1:5054/v1'
    if (embedding.get('RAG_EMBEDDING_ENGINE') != 'openai'
        or embedding.get('RAG_EMBEDDING_MODEL') != MODEL
        or embedding.get('openai_config') != {'url': embedding_url, 'key': secret}):
        # Use the update endpoint: raw config imports do not refresh the in-memory
        # embedding callable already constructed during OpenWebUI startup.
        call('/api/v1/retrieval/embedding/update', {
            'RAG_EMBEDDING_ENGINE': 'openai', 'RAG_EMBEDDING_MODEL': MODEL,
            'RAG_EMBEDDING_BATCH_SIZE': 8, 'ENABLE_ASYNC_EMBEDDING': True,
            'RAG_EMBEDDING_CONCURRENT_REQUESTS': 1,
            'openai_config': {'url': embedding_url, 'key': secret},
        }, token)
    vector_state = Path(os.getenv('DATA_DIR', '/data/openwebui'), '.embedding-model.json')
    fingerprint = {'model': MODEL, 'revision': REVISION, 'dimensions': DIMENSIONS,
                   'vector_store': 'chroma-1.5.9'}
    previous = json.loads(vector_state.read_text()) if vector_state.is_file() else None
    if previous != fingerprint:
        # Rebuild only memory vectors from retained SQL records. Do not delete
        # unrelated document/knowledge collections or their uploaded originals.
        call('/api/v1/memories/reindex', {}, token, timeout=240)
        temporary = vector_state.with_suffix('.tmp')
        temporary.write_text(json.dumps(fingerprint), encoding='utf8')
        temporary.replace(vector_state)

    # Existing workspace models may explicitly override global defaults.
    for model in call('/api/v1/models/all', token=token):
        updated = metadata(model.get('meta'))
        if updated != model.get('meta'):
            call('/api/v1/models/model/update?' + urlencode({'id': model['id']}),
                 {**model, 'meta': updated}, token)

    tools = call('/api/v1/tools/', token=token)
    if not any(t['id'] == MCP_TOOL_ID for t in tools):
        raise RuntimeError('Native MCP not visible in OpenWebUI')
    auth_headers = {'Authorization': 'Bearer ' + token}
    result = call('/mcp', {'jsonrpc': '2.0', 'id': 1, 'method': 'tools/list'},
                  headers=auth_headers, base='http://127.0.0.1:5053')
    names = {t['name'] for t in result['result']['tools']}
    if not {'query_words', 'create_group', 'search_web'}.issubset(names):
        raise RuntimeError('MCP tools are incomplete')
    state = {'version': 2, 'mcp': MCP_TOOL_ID, 'search': 'local-bing-rss-ddgs',
             'embedding': fingerprint, 'memory_scope': 'user', 'assistant_isolation': False,
             'automatic_memory': True, 'memory_review_interval_turns': 1,
             'requires_api_key': False, 'tools': sorted(names)}
    marker = Path(os.getenv('DATA_DIR', '/data/openwebui'), '.integration-ready.json')
    temporary = marker.with_suffix('.tmp')
    temporary.write_text(json.dumps(state, ensure_ascii=False), encoding='utf8')
    temporary.replace(marker)
    print('[Integration] MCP, search and local multilingual embeddings configured; native memory scope=user.', flush=True)


def main():
    deadline = time.monotonic() + 300
    while True:
        try:
            provision()
            return
        except Exception as exc:
            if time.monotonic() >= deadline:
                # Never print response bodies, auth headers or config/keys.
                raise SystemExit('[Integration] Provisioning failed: ' + type(exc).__name__)
            print('[Integration] Waiting/retrying: ' + type(exc).__name__, flush=True)
            time.sleep(5)


if __name__ == '__main__':
    main()
