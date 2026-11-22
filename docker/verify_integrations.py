"""Run inside the image: python /opt/anamnesis-docker/verify_integrations.py.

Creates and removes a short-lived local test login; never needs a user's password.
Exercises real OpenWebUI configuration, MCP SDK and public-network search.
"""
import asyncio
import hashlib
import json
import os
import secrets
import sqlite3
import time
import urllib.request
from datetime import datetime
from pathlib import Path

from itsdangerous import URLSafeTimedSerializer
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client


async def verify(call, token):
    config = call('/api/v1/configs/export')
    native = [c for c in config['tool_server.connections'] if (c.get('info') or {}).get('id') == 'anamnesis']
    assert len(native) == 1 and native[0]['auth_type'] == 'session'
    assert config['web.search.engine'] == 'external' and config['web.search.enable']
    assert config['web.search.bypass_embedding_and_retrieval']
    assert 'server:mcp:anamnesis' in config['models.default_metadata']['toolIds']
    assert call('/words/api/chat/integration-status')['configured']
    print('PASS OpenWebUI native MCP, local search and model defaults', flush=True)
    async with streamablehttp_client('http://127.0.0.1:5053/mcp',
                                     headers={'Authorization': 'Bearer ' + token}) as streams:
        async with ClientSession(streams[0], streams[1]) as session:
            await session.initialize()
            tools = await session.list_tools()
            names = {t.name for t in tools.tools}
            assert {'query_words', 'create_group', 'search_web'}.issubset(names)
            result = await session.call_tool('query_words', {})
            assert not result.isError
            print('PASS MCP SDK initialize, tool discovery and personal vocabulary query', flush=True)
            result = await session.call_tool('search_web', {'query': 'Python documentation', 'count': 3})
            assert not result.isError, result
            results = json.loads(result.content[0].text)
            assert len(results) >= 1 and all(x.get('link', '').startswith('https://') for x in results)
            assert any('python' in (x['title'] + x['link']).lower() for x in results)
            print('PASS real internet search through native MCP:', len(results), 'sources', flush=True)
    result = call('/api/v1/retrieval/process/web/search', {'queries': ['Python documentation']})
    assert result['status'] and result['loaded_count'] > 0
    assert any('python' in (x.get('title', '') + x.get('link', '')).lower() for x in result['items'])
    print('PASS OpenWebUI built-in search returns sources without an embedding/API key', flush=True)


def main():
    root = Path(os.getenv('APP_DATA_DIR', '/data/words'))
    secret = (root / '.session-secret').read_text().strip()
    sid = secrets.token_urlsafe(32)
    stamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    with sqlite3.connect(root / 'accounts.db', timeout=30) as conn:
        conn.execute('INSERT INTO devices VALUES (?,?,?,?,?,?,?)',
                     (sid, 'admin', time.time() + 300, '127.0.0.1', 'integration-verification', stamp, stamp))
    cookie = URLSafeTimedSerializer(secret, salt='cookie-session',
        signer_kwargs={'key_derivation': 'hmac', 'digest_method': hashlib.sha1}).dumps(
            {'device_id': sid, 'owner': 'admin', 'authenticated': True})

    def call(path, data=None):
        request = urllib.request.Request('http://127.0.0.1:5050' + path,
            headers={'Cookie': 'anamnesis_session=' + cookie, 'Content-Type': 'application/json'},
            data=json.dumps(data).encode() if data is not None else None)
        with urllib.request.urlopen(request, timeout=90) as response:
            return json.load(response)
    try:
        token = call('/words/api/chat/session')['token']
        asyncio.run(verify(call, token))
        print('ALL LIVE INTEGRATION CHECKS PASSED', flush=True)
    finally:
        with sqlite3.connect(root / 'accounts.db', timeout=30) as conn:
            conn.execute('DELETE FROM devices WHERE id=?', (sid,))


if __name__ == '__main__':
    main()
