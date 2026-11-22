"""OpenAI-compatible embedding API; CPU-only, loopback-only, no external key.

Model files are baked into the image and loaded with local_files_only=True.
Short chunks keep this 128-token model suitable for compact user memories.
Long inputs pool overlapping segments rather than silently discard the tail.
"""
import asyncio
import hmac
import math
import os

from aiohttp import web
from embedding_model import MODEL, DIMENSIONS, REVISION, load_model


def chunks(text, size=160, overlap=32):
    if not text:
        return ['']
    return [text[i:i+size] for i in range(0, len(text), size-overlap)]


def encode(model, texts):
    segments = [chunks(text) for text in texts]
    vectors = iter(model.embed([piece for parts in segments for piece in parts], batch_size=16))
    result = []
    for parts in segments:
        summed = [0.0] * DIMENSIONS
        for _ in parts:
            vector = next(vectors)
            for idx, value in enumerate(vector):
                summed[idx] += float(value)
        norm = math.sqrt(sum(x*x for x in summed)) or 1
        result.append([x/norm for x in summed])
    return result


async def embeddings(request):
    secret = request.app['secret']
    if not secret or not hmac.compare_digest(request.headers.get('Authorization', ''), 'Bearer '+secret):
        raise web.HTTPUnauthorized()
    data = await request.json()
    if not isinstance(data, dict) or data.get('model', MODEL) != MODEL:
        raise web.HTTPBadRequest(text='Unknown embedding model')
    texts = data.get('input')
    if isinstance(texts, str):
        texts = [texts]
    if not isinstance(texts, list) or not 1 <= len(texts) <= 64 or any(not isinstance(t, str) for t in texts):
        raise web.HTTPBadRequest(text='input must be a string or 1–64 strings')
    if any(len(t) > 32000 for t in texts) or sum(map(len, texts)) > 128000:
        raise web.HTTPRequestEntityTooLarge(max_size=128000, actual_size=sum(map(len, texts)))
    if data.get('encoding_format', 'float') != 'float' or data.get('dimensions', DIMENSIONS) != DIMENSIONS:
        raise web.HTTPBadRequest(text='Only float encoding and 384 dimensions are supported')
    async with request.app['slots']:
        vectors = await asyncio.to_thread(encode, request.app['model'], texts)
    return web.json_response({'object': 'list', 'model': MODEL, 'data': [
        {'object': 'embedding', 'index': i, 'embedding': vector} for i, vector in enumerate(vectors)]})


async def health(request):
    return web.json_response({'ok': True, 'model': MODEL, 'dimensions': DIMENSIONS,
        'revision': REVISION, 'runtime': 'onnx-cpu', 'offline': True})


async def model_context(app):
    app['model'] = await asyncio.to_thread(load_model)
    await asyncio.to_thread(encode, app['model'], ['向量服务就绪'])
    yield


def create_app():
    app = web.Application(client_max_size=2*1024**2)
    app['secret'] = os.environ.get('GATEWAY_AUTH_SECRET', '')
    app['slots'] = asyncio.Semaphore(1)
    app.cleanup_ctx.append(model_context)
    app.router.add_post('/v1/embeddings', embeddings)
    app.router.add_get('/health', health)
    return app


if __name__ == '__main__':
    web.run_app(create_app(), host='127.0.0.1', port=5054, access_log=None)
