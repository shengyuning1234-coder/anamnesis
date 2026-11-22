"""Live acceptance audit. Prints no credentials; temporary login revoked on exit."""
import hashlib,json,os,secrets,sqlite3,time,urllib.request,urllib.error,sys
from pathlib import Path
from datetime import datetime
from itsdangerous import URLSafeTimedSerializer
root=Path('/data/words'); sid=secrets.token_urlsafe(32); stamp=datetime.now().isoformat()
with sqlite3.connect(root/'accounts.db') as c:c.execute('INSERT INTO devices VALUES (?,?,?,?,?,?,?)',(sid,'admin',time.time()+1800,'127.0.0.1','live-acceptance-test',stamp,stamp))
cookie=URLSafeTimedSerializer((root/'.session-secret').read_text().strip(),salt='cookie-session',signer_kwargs={'key_derivation':'hmac','digest_method':hashlib.sha1}).dumps({'device_id':sid,'owner':'admin','authenticated':True})
def call(path,data=None,method=None,base='http://127.0.0.1:5050',token=None,timeout=150):
 headers={'Content-Type':'application/json','Cookie':'session='+cookie}
 if token:headers['Authorization']='Bearer '+token;headers.pop('Cookie')
 req=urllib.request.Request(base+path,headers=headers,data=json.dumps(data,ensure_ascii=False).encode() if data is not None else None,method=method)
 with urllib.request.urlopen(req,timeout=timeout) as r:
  raw=r.read().decode()
  if 'text/event-stream' in r.headers.get('Content-Type',''):
   return {'events':raw[-24000:]}
  return json.loads(raw)
def check(name,fn):
 try:result=fn();print(json.dumps({'check':name,'result':result},ensure_ascii=False),flush=True)
 except Exception as e:print(json.dumps({'check':name,'error':type(e).__name__,'detail':str(e)[:160]},ensure_ascii=False),flush=True)
try:
 token=call('/words/api/chat/session')['token']
 models=call('/api/models').get('data',[]);ids=[m['id'] for m in models];print('MODELS',json.dumps(ids),flush=True)
 config=call('/api/v1/configs/export')
 print('FLAGS',json.dumps({k:config.get(k) for k in ['web.search.enable','web.search.engine','web.search.bypass_embedding_and_retrieval','memories.enable','memories.background_review.enable','memories.system_context.enable','models.default_metadata']},ensure_ascii=False),flush=True)
 def mcp(name,args):
  r=call('/mcp',{'jsonrpc':'2.0','id':1,'method':'tools/call','params':{'name':name,'arguments':args}},base='http://127.0.0.1:5053',token=token)
  return r.get('result',r)
 check('mcp_query_words',lambda:mcp('query_words',{}))
 check('keyless_mcp_search',lambda:mcp('search_web',{'query':'Python documentation official','count':3}))
 check('openwebui_native_search',lambda:call('/api/v1/retrieval/process/web/search',{'queries':['Python documentation official']}))
 model='gpt-6.1-sol' if 'gpt-6.1-sol' in ids else ids[0]
 def chat(prompt,**extra):
  r=call('/api/chat/completions',{'model':model,'stream':True,'messages':[{'role':'user','content':prompt}],**extra})
  return r
 if '--model' in sys.argv:
  check('real_model_basic',lambda:chat('这是连接验收测试。请只回复：连接测试成功'))
  check('real_model_mcp_search',lambda:chat('这是联网工具验收测试。必须实际调用 search_web 搜索 Python official documentation，返回你实际搜到的两个结果标题和网址。不要凭记忆回答；如果工具失败，请如实说明。',tool_ids=['server:mcp:anamnesis'],params={'function_calling':'native'}))
  check('real_model_vocabulary',lambda:chat('这是词库工具验收。请实际调用 query_words 查看我的词库，返回词条数量；不需要添加或修改数据。',tool_ids=['server:mcp:anamnesis'],params={'function_calling':'native'}))
finally:
 with sqlite3.connect(root/'accounts.db') as c:c.execute('DELETE FROM devices WHERE id=?',(sid,))
