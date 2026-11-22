"""Configure personal native MCP for the local chat runtime, without embeddings."""
import json
import os
import time
from pathlib import Path
from urllib.parse import quote
from bootstrap import call, MCP_ID, MCP_TOOL_ID, metadata


def provision():
    identity = call('/api/internal/integration-identity',
                    headers={'X-Gateway-Secret': os.environ['GATEWAY_AUTH_SECRET']}, base='http://127.0.0.1:5052')
    token = call('/api/v1/auths/signin', {'email': identity['email'], 'password': 'trusted-header'},
                 headers={'X-Anamnesis-Email': identity['email'], 'X-Anamnesis-Name': quote(identity['name']),
                          'X-Anamnesis-Role': identity['role']})['token']
    config = call('/api/v1/configs/export', token=token)
    connections = [c for c in config.get('tool_server.connections', []) if (c.get('info') or {}).get('id') != MCP_ID]
    connections.append({'type': 'mcp', 'url': 'http://127.0.0.1:5053/mcp', 'path': '',
                        'auth_type': 'session', 'key': '',
                        'info': {'id': MCP_ID, 'name': '忆溯个人词库与搜索'},
                        'config': {'enable': True, 'access_grants': [
                            {'principal_type': 'user', 'principal_id': '*', 'permission': 'read'}]}})
    call('/api/v1/configs/tool_servers', {'TOOL_SERVER_CONNECTIONS': connections}, token)
    call('/api/v1/configs/import', {'config': {
        'web.search.enable': True, 'web.search.engine': 'external',
        'web.search.external_web_search_url': 'http://127.0.0.1:5053/search',
        'web.search.external_web_search_api_key': os.environ['GATEWAY_AUTH_SECRET'],
        'web.search.bypass_embedding_and_retrieval': True,
        'web.search.bypass_web_loader': True, 'web.search.result_count': 5,
        'web.search.concurrent_requests': 2,
        'models.default_metadata': {**metadata(config.get('models.default_metadata')),
                                    'capabilities': {**metadata(config.get('models.default_metadata'))['capabilities'], 'memory': False}},
    }}, token)
    for model in call('/api/v1/models/all', token=token):
        updated = metadata(model.get('meta'))
        updated['capabilities']['memory'] = False
        if updated != model.get('meta'):
            from urllib.parse import urlencode
            call('/api/v1/models/model/update?' + urlencode({'id': model['id']}), {**model, 'meta': updated}, token)
    result = call('/mcp', {'jsonrpc': '2.0', 'id': 1, 'method': 'tools/list'},
                  headers={'Authorization': 'Bearer ' + token}, base='http://127.0.0.1:5053')
    if 'query_words' not in {t['name'] for t in result['result']['tools']}:
        raise RuntimeError('Personal vocabulary tools unavailable')
    marker = Path('/data/openwebui/.integration-ready.json')
    marker.write_text(json.dumps({'mcp': MCP_TOOL_ID, 'automatic_memory': False, 'embedding': None}))
    print('[Local chat] Account bridge and personal vocabulary MCP ready', flush=True)


if __name__ == '__main__':
    deadline = time.monotonic() + 300
    while True:
        try:
            provision()
            break
        except Exception as exc:
            if time.monotonic() >= deadline:
                raise SystemExit('Local chat setup failed: ' + type(exc).__name__)
            print('[Local chat] Waiting for startup: ' + type(exc).__name__, flush=True)
            time.sleep(5)
