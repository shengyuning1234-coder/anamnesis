"""Exercise prefix forwarding, cookies, streaming and WebSocket relay."""
import asyncio
import unittest
from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer
import gateway

class GatewayTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        async def echo(request):
            return web.json_response({'path':request.path,'prefix':request.headers.get('X-Forwarded-Prefix'),
                                      'scheme':request.headers.get('X-Forwarded-Proto'),
                                      'body':await request.text(),'cookie':request.headers.get('Cookie')})
        async def socket(request):
            ws=web.WebSocketResponse(); await ws.prepare(request)
            async for msg in ws: await ws.send_str(msg.data)
            return ws
        self.release=asyncio.Event()
        async def stream(request):
            response=web.StreamResponse(headers={'Content-Type':'text/event-stream'})
            await response.prepare(request); await response.write(b'data: first\n\n')
            await self.release.wait(); await response.write(b'data: last\n\n'); return response
        upstream=web.Application();upstream.router.add_get('/ws',socket);upstream.router.add_get('/events',stream);upstream.router.add_route('*','/{rest:.*}',echo)
        self.upstream=TestServer(upstream);await self.upstream.start_server()
        app=web.Application();app.cleanup_ctx.append(gateway.client_context)
        # Redirect the gateway's two fixed internal services into the fixture.
        original=__import__('aiohttp').ClientSession
        upstream_url=str(self.upstream.make_url('/')).rstrip('/')
        class FixtureSession(original):
            def request(self, method, url, **kwargs):
                url=url.replace('http://127.0.0.1:5052',upstream_url).replace('http://127.0.0.1:5051',upstream_url)
                return super().request(method,url,**kwargs)
            def ws_connect(self,url,**kwargs):
                return super().ws_connect(url.replace('http://127.0.0.1:5051',upstream_url),**kwargs)
        self.original=gateway.ClientSession;gateway.ClientSession=FixtureSession
        app.router.add_route('*','/{rest:.*}',gateway.proxy)
        self.client=TestClient(TestServer(app));await self.client.start_server()
    async def asyncTearDown(self):
        self.release.set();await self.client.close();await self.upstream.close();gateway.ClientSession=self.original
    async def test_entry_and_prefix(self):
        r=await self.client.get('/',allow_redirects=False);self.assertEqual(r.headers['Location'],'/words/')
        r=await self.client.post('/words/api/test',data='payload',headers={'X-Forwarded-Proto':'https','Cookie':'anamnesis_session=test'})
        d=await r.json();self.assertEqual((d['path'],d['prefix'],d['scheme'],d['body']),('/api/test','/words','https','payload'))
        self.assertEqual(d['cookie'],'anamnesis_session=test')
        r=await self.client.get('/',headers={'Sec-Fetch-Dest':'iframe'});self.assertEqual((await r.json())['path'],'/')
    async def test_websocket(self):
        async with self.client.ws_connect('/ws') as ws:
            await ws.send_str('relay');self.assertEqual((await ws.receive(timeout=2)).data,'relay')
    async def test_stream_not_buffered(self):
        r=await self.client.get('/events')
        first=await asyncio.wait_for(r.content.read(13),2)
        self.assertEqual(first,b'data: first\n\n')
        self.release.set();self.assertEqual(await r.read(),b'data: last\n\n')

if __name__=='__main__': unittest.main()
