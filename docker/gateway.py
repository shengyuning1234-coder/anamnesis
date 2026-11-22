"""One public port; isolated word routes and unmodified OpenWebUI routes.

OpenWebUI expects root-relative URLs. It keeps its root namespace while the
word app is mounted at /words/. Top-level visits to / enter the word app;
iframe visits use the chat home. No response buffering for SSE or uploads.
"""
import asyncio, os, json, time
from urllib.parse import quote
from aiohttp import ClientSession, ClientTimeout, ClientError, WSMsgType, web
from multidict import CIMultiDict

HOP = {'connection', 'keep-alive', 'proxy-authenticate', 'proxy-authorization',
       'te', 'trailer', 'transfer-encoding', 'upgrade', 'host', 'content-length'}

async def chat_identity(request):
    client=request.app['client']
    async with client.get('http://127.0.0.1:5052/api/auth/bridge',auto_decompress=True,headers={
        'Cookie':request.headers.get('Cookie',''),'X-Gateway-Secret':os.environ['GATEWAY_AUTH_SECRET']}) as response:
        if response.status!=200: raise web.HTTPUnauthorized(text='请先登录单词平台')
        identity=await response.json()
    return identity

async def chat_token(request,identity):
    cache=request.app.setdefault('chat_tokens',{})
    key=(identity['id'],identity['email'],identity['role'])
    saved=cache.get(key)
    if saved and saved[0]>time.monotonic(): return saved[1]
    async with request.app['client'].post('http://127.0.0.1:5051/api/v1/auths/signin',
        auto_decompress=True,json={'email':identity['email'],'password':'trusted-header'},headers={
            'X-Anamnesis-Email':identity['email'],'X-Anamnesis-Name':quote(identity['name']),
            'X-Anamnesis-Role':identity['role']}) as response:
        if response.status!=200: raise web.HTTPBadGateway(text='对话账号联动失败，请检查 OpenWebUI 配置')
        result=await response.json()
    token=result.get('token')
    if not token: raise web.HTTPBadGateway(text='对话服务没有返回登录凭据')
    cache[key]=(time.monotonic()+240,token)
    return token

def socket_identity(message,token):
    """Socket.IO transports carry auth inside Engine.IO packets, not only headers."""
    def replace(value):
        if isinstance(value,dict): return {k:token if k in ('token','access_token') else replace(v) for k,v in value.items()}
        if isinstance(value,list): return [replace(v) for v in value]
        return value
    packets=[]
    for packet in message.split('\x1e'):
        positions=[p for p in (packet.find('['),packet.find('{')) if p>=0]
        if positions:
            pos=min(positions)
            try: packet=packet[:pos]+json.dumps(replace(json.loads(packet[pos:])),separators=(',',':'))
            except (ValueError,TypeError): pass
        packets.append(packet)
    return '\x1e'.join(packets)

async def proxy(request):
    identity=None; token=None
    protected=bool(os.environ.get('GATEWAY_AUTH_SECRET'))
    bootstrap=request.path=='/words/api/chat/session'
    install=request.path=='/words/api/chat/install-tools'
    integration_status=request.path=='/words/api/chat/integration-status'
    if protected and request.path!='/health' and (not request.path.startswith('/words') or bootstrap or install or integration_status):
        try: identity=await chat_identity(request)
        except web.HTTPUnauthorized:
            if request.path=='/' or request.headers.get('Sec-Fetch-Dest') in ('document','iframe'): raise web.HTTPFound('/words/login')
            raise
        except (OSError,asyncio.TimeoutError,ClientError): raise web.HTTPBadGateway(text='单词服务正在启动，请稍后重试')
        try: token=await chat_token(request,identity)
        except (OSError,asyncio.TimeoutError,ClientError):
            raise web.HTTPBadGateway(text='内置对话正在启动，请稍后重新连接')
        if bootstrap: return web.json_response({'token':token,'user_id':identity['id']},headers={'Cache-Control':'no-store'})
        if install or integration_status:
            if install and request.method!='POST': raise web.HTTPMethodNotAllowed(request.method,['POST'])
            if install and identity['role']!='admin': raise web.HTTPForbidden(text='仅管理员可执行此操作')
            async with request.app['client'].get('http://127.0.0.1:5053/health',auto_decompress=True) as response:
                status=await response.json()
            status['message']='词库 MCP 和免密钥搜索随容器自动配置，无需手动安装。' if status.get('configured') else '内置集成正在初始化，请稍后刷新。'
            return web.json_response(status,headers={'Cache-Control':'no-store'})
    if request.path == '/':
        # Browser iframe navigations (including reload/auth redirects) retain
        # Sec-Fetch-Dest. For clients without Fetch Metadata use our Referer.
        destination = request.headers.get('Sec-Fetch-Dest', '')
        if destination != 'iframe' and not (destination == '' and '/words/' in request.headers.get('Referer', '')):
            raise web.HTTPFound('/words/')
    if request.path == '/words':
        raise web.HTTPPermanentRedirect('/words/')
    is_word = request.path.startswith('/words/')
    upstream = 'http://127.0.0.1:' + ('5052' if is_word else '5051')
    raw_path = request.raw_path[len('/words'):] if is_word else request.raw_path
    target = upstream + raw_path
    headers = CIMultiDict((k,v) for k,v in request.headers.items()
                           if k.lower() not in HOP and not k.lower().startswith(('x-forwarded-','x-anamnesis-','x-gateway-')))
    headers['Host'] = request.host
    headers['X-Forwarded-Host'] = request.host
    # This listener is reached directly or through the user's NAS reverse proxy.
    scheme = request.headers.get('X-Forwarded-Proto', request.scheme).split(',')[0].strip()
    headers['X-Forwarded-Proto'] = scheme if scheme in ('http', 'https') else request.scheme
    headers['X-Forwarded-For'] = request.headers.get('X-Forwarded-For', request.remote or '127.0.0.1')
    if is_word:
        headers['X-Forwarded-Prefix'] = '/words'
    client = request.app['client']
    if token:
        headers.popall('Authorization',None); headers.popall('Cookie',None)
        headers['Authorization']='Bearer '+token
        headers['X-Anamnesis-Email']=identity['email']; headers['X-Anamnesis-Name']=quote(identity['name']); headers['X-Anamnesis-Role']=identity['role']
    if request.headers.get('Upgrade','').lower() == 'websocket':
        try:
            protocols = tuple(p.strip() for p in request.headers.get('Sec-WebSocket-Protocol','').split(',') if p.strip())
            ws_headers = CIMultiDict((k,v) for k,v in headers.items() if not k.lower().startswith('sec-websocket-'))
            async with client.ws_connect(target, headers=ws_headers, protocols=protocols, autoping=True, max_msg_size=0) as upstream_ws:
                downstream = web.WebSocketResponse(protocols=protocols, max_msg_size=0)
                await downstream.prepare(request)
                async def relay(source, destination):
                    async for msg in source:
                        if token:
                            try:
                                current=await chat_identity(request)
                                if current['id']!=identity['id'] or current['email']!=identity['email']: break
                            except web.HTTPException: break
                        if msg.type == WSMsgType.TEXT: await destination.send_str(socket_identity(msg.data,token) if token and source is downstream else msg.data)
                        elif msg.type == WSMsgType.BINARY: await destination.send_bytes(msg.data)
                    await destination.close()
                tasks = [asyncio.create_task(relay(downstream, upstream_ws)), asyncio.create_task(relay(upstream_ws, downstream))]
                try:
                    await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
                finally:
                    for task in tasks: task.cancel()
                    await asyncio.gather(*tasks, return_exceptions=True)
                return downstream
        except (OSError, asyncio.TimeoutError, ClientError):
            raise web.HTTPBadGateway(text='对话服务正在启动，请稍后重试')
    try:
        data=request.content
        if token and request.path.startswith('/ws') and request.method=='POST':
            data=socket_identity(await request.text(),token).encode()
        async with client.request(request.method, target, headers=headers,
                                  data=data, allow_redirects=False) as upstream_response:
            response_headers = CIMultiDict((k,v) for k,v in upstream_response.headers.items() if k.lower() not in HOP)
            if token:
                response_headers.popall('Set-Cookie',None)
            if upstream_response.headers.get('Content-Type','').startswith('text/event-stream'):
                response_headers['X-Accel-Buffering']='no'; response_headers['Cache-Control']='no-cache, no-transform'
            response = web.StreamResponse(status=upstream_response.status, headers=response_headers)
            await response.prepare(request)
            async for chunk in upstream_response.content.iter_any():
                await response.write(chunk)
            await response.write_eof()
            return response
    except (OSError, asyncio.TimeoutError, ClientError):
        raise web.HTTPBadGateway(text='服务正在启动，请稍后重试')

async def client_context(app):
    async with ClientSession(timeout=ClientTimeout(total=None, sock_connect=10),
                             auto_decompress=False, cookie_jar=__import__('aiohttp').DummyCookieJar()) as client:
        app['client'] = client
        yield

app = web.Application(client_max_size=1024**3)
app.cleanup_ctx.append(client_context)
app.router.add_route('*', '/{path:.*}', proxy)
if __name__ == '__main__':
    web.run_app(app, host='0.0.0.0', port=5050, access_log=None)
