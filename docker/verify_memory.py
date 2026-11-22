"""Real local embedding and native memory roundtrip; removes test memories.

Run in container: python /opt/anamnesis-docker/verify_memory.py
No user password is needed. Does not invoke a chat model or automatic extraction.
"""
import hashlib
import asyncio
import json
import os
import secrets
import sqlite3
import time
import sys
import urllib.request
from datetime import datetime
from pathlib import Path
from itsdangerous import URLSafeTimedSerializer
from embedding_model import MODEL, DIMENSIONS


async def verify_background(call):
    """Exercise native scheduling/write/next-chat recall with simulated inference.

    No provider credentials or paid model calls. Persistence and vectors use the
    real running API; only the chat model's returned operations are simulated.
    """
    sys.path.insert(0, '/app/backend')
    os.environ['WEBUI_SECRET_KEY'] = os.environ.get('WEBUI_SECRET_KEY') or (Path(os.getenv('DATA_DIR', '/data/openwebui'))/'.webui_secret_key').read_text().strip()
    from types import SimpleNamespace
    from unittest.mock import AsyncMock, patch
    from open_webui.utils import memory
    from open_webui.routers import memories as routes
    from open_webui.retrieval.vector.main import SearchResult
    tag = 'verification/background-'+secrets.token_hex(8)
    content = '自动记忆验证：我长期偏好使用中文并通过例句学习英语。'
    user = SimpleNamespace(**call('/api/v1/auths/'))
    request = SimpleNamespace(state=SimpleNamespace(metadata={'chat_id':'verification', 'model':{'id':'verification-model'}}))
    complete = asyncio.Event()
    async def write(request, form_data, user):
        response = call('/api/v1/memories/update', form_data.model_dump())
        complete.set()
        return response
    async def query(request, form_data, user):
        return SearchResult(**call('/api/v1/memories/query', form_data.model_dump()))
    generate = AsyncMock(return_value=[{'action':'add','type':'user','path':tag,'content':content}])
    try:
        with patch.object(memory, '_generate_memory_operations', generate), patch.object(routes, 'update_memories', write), patch.object(routes, 'query_memory', query):
            await memory.review_memory_after_turn(request=request, user=user, model={'id':'verification-model'},
                metadata={'features':{'memory':True}}, form_data={'model':'verification-model'},
                assistant_message={'role':'assistant','content':'我会记住你的长期学习偏好。'},
                messages=[{'role':'user','content':content}])
            await asyncio.wait_for(complete.wait(), timeout=45)
            generate.assert_awaited_once()
            assert content in generate.await_args.kwargs['transcript']
            stored = [row for row in call('/api/v1/memories/') if row.get('path') == tag]
            assert len(stored) == 1 and stored[0]['content'] == content
            # A fresh message list has no previous transcript to rely on.
            form = await memory.add_memory_context(request, {'messages':[{'role':'user','content':'你知道我的学习偏好吗？'}]}, user)
            assert any(content in message.get('content','') for message in form['messages'] if message['role']=='system')
        print('PASS native background scheduling, real memory write and next-chat context injection (simulated model response)', flush=True)
    finally:
        for row in call('/api/v1/memories/'):
            if row.get('path') == tag:
                call('/api/v1/memories/'+row['id'], method='DELETE')


def main():
    root = Path(os.getenv('APP_DATA_DIR', '/data/words'))
    sid = secrets.token_urlsafe(32)
    secret = (root/'.session-secret').read_text().strip()
    stamp = datetime.now().isoformat()
    with sqlite3.connect(root/'accounts.db', timeout=30) as db:
        db.execute('INSERT INTO devices VALUES (?,?,?,?,?,?,?)',
            (sid, 'admin', time.time()+300, '127.0.0.1', 'embedding-verification', stamp, stamp))
    cookie = URLSafeTimedSerializer(secret, salt='cookie-session',
        signer_kwargs={'key_derivation':'hmac', 'digest_method':hashlib.sha1}).dumps(
            {'device_id':sid, 'owner':'admin', 'authenticated':True})
    def call(path, data=None, method=None):
        request = urllib.request.Request('http://127.0.0.1:5050'+path,
            headers={'Cookie':'anamnesis_session='+cookie, 'Content-Type':'application/json'},
            data=json.dumps(data).encode() if data is not None else None, method=method)
        with urllib.request.urlopen(request, timeout=90) as response:
            return json.load(response)
    memories = []
    try:
        settings = call('/api/v1/retrieval/embedding')
        assert settings['RAG_EMBEDDING_MODEL'] == MODEL
        assert settings['openai_config']['url'] == 'http://127.0.0.1:5054/v1'
        request = urllib.request.Request(settings['openai_config']['url']+'/embeddings',
            headers={'Authorization':'Bearer '+settings['openai_config']['key'], 'Content-Type':'application/json'},
            data=json.dumps({'model':MODEL, 'input':['我喜欢喝绿茶', 'I enjoy drinking green tea', 'The engine needs oil']}).encode())
        with urllib.request.urlopen(request, timeout=60) as response:
            vectors = [x['embedding'] for x in json.load(response)['data']]
        assert all(len(v)==DIMENSIONS for v in vectors)
        dot = lambda a,b: sum(x*y for x,y in zip(a,b))
        assert dot(vectors[0],vectors[1]) > dot(vectors[0],vectors[2])
        print('PASS real offline CPU vectors: 384 dimensions and Chinese/English similarity', flush=True)
        tag = secrets.token_hex(8)
        for content in ['测试记忆：我喜欢喝绿茶而不是咖啡。', '测试记忆：汽车发动机需要定期更换机油。']:
            memory = call('/api/v1/memories/add', {'content':content, 'type':'context', 'path':'verification/'+tag})
            memories.append(memory['id'])
        result = call('/api/v1/memories/query', {'content':'I enjoy drinking green tea', 'k':30})
        ids = (result.get('ids') or [[]])[0]
        assert memories[0] in ids
        assert memories[1] not in ids or ids.index(memories[0]) < ids.index(memories[1])
        print('PASS OpenWebUI memory SQL write, local embedding, vector storage and semantic recall', flush=True)
        config = call('/api/v1/configs/export')
        assert config['memories.enable'] and config['memories.background_review.enable'] is True
        assert config['memories.system_context.enable'] and config['memories.review_interval_turns'] == 1
        assert config['models.default_metadata']['capabilities']['memory'] is True
        user_settings = call('/api/v1/users/user/settings?raw=true')
        assert user_settings['ui']['memory'] is True
        for model in call('/api/v1/models/all'):
            assert model['meta']['capabilities']['memory'] is True
        print('PASS automatic memory defaults: review each completed turn and recall across chats; scope=user.', flush=True)
        if '--background' in sys.argv:
            asyncio.run(verify_background(call))
    finally:
        # OpenWebUI writes SQL before embedding; even a failed add may leave a
        # row without returning its id. Limit cleanup to this run's random path.
        if 'tag' in locals():
            for memory in call('/api/v1/memories/'):
                if memory.get('path') == 'verification/'+tag and memory['id'] not in memories:
                    memories.append(memory['id'])
        for memory_id in memories:
            call('/api/v1/memories/'+memory_id, method='DELETE')
        with sqlite3.connect(root/'accounts.db', timeout=30) as db:
            db.execute('DELETE FROM devices WHERE id=?', (sid,))


if __name__ == '__main__': main()
