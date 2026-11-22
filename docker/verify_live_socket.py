"""Verify the real authenticated Socket.IO route and streamed model events."""
import asyncio,json,time,uuid,sqlite3
from pathlib import Path
exec((Path(__file__).with_name('audit_live.py')).read_text().split('try:\n token=')[0])
import socketio
async def main():
 token=await asyncio.to_thread(call,'/words/api/chat/session')
 for origin in ['http://127.0.0.1:5050','http://localhost:5050']:
  client=socketio.AsyncClient(reconnection=False)
  try:
   await client.connect('http://127.0.0.1:5050',headers={'Cookie':'session='+cookie,'Origin':origin},auth={'token':token['token']},socketio_path='ws/socket.io',transports=['websocket'],wait_timeout=15)
   print('SOCKET_OK',origin,flush=True)
   if '--chat' in sys.argv and origin.endswith('127.0.0.1:5050'):
    done=asyncio.Event();texts=[];started=time.monotonic();first=None
    @client.on('events')
    async def events(event):
     nonlocal first
     data=event.get('data',{}); payload=data.get('data',{})
     if data.get('type')=='chat:completion':
      if first is None:first=time.monotonic();print('FIRST_EVENT_SECONDS',round(first-started,2),flush=True)
      texts.append(payload)
      if payload.get('done') or payload.get('error'):done.set()
    payload={'model':'gpt-6.1-sol','stream':True,'messages':[{'role':'user','content':'仅回复：实时显示测试成功'}],'session_id':client.get_sid(),'chat_id':'local:'+uuid.uuid4().hex,'id':uuid.uuid4().hex}
    print('ACK',await asyncio.to_thread(call,'/api/chat/completions',payload),flush=True)
    await asyncio.wait_for(done.wait(),90)
    print('LIVE_EVENTS',json.dumps(texts,ensure_ascii=False)[-10000:],flush=True)
  except Exception as e:print('SOCKET_FAIL',origin,type(e).__name__,str(e)[:120],flush=True)
  finally:await client.disconnect()
try:asyncio.run(main())
finally:
 with sqlite3.connect(root/'accounts.db') as c:c.execute('DELETE FROM devices WHERE id=?',(sid,))
