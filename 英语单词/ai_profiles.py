"""Server-side model routing. Credentials never appear in configuration responses."""
import json
import os
import uuid
from pathlib import Path
from urllib.parse import urlparse
from flask import jsonify
import tenancy

SCENES = ('general','quiz','vision','lookup','classification','report')

def read():
    file=Path(tenancy.path('ai-profiles.json'))
    return json.loads(file.read_text(encoding='utf8')) if file.exists() else {'providers':[],'routes':{}}

def resolve(config,scene='general'):
    profile=read(); own=tenancy.profile.get()!='admin'
    route=profile['routes'].get(scene) or profile['routes'].get('general')
    provider=next((p for p in profile['providers'] if p['id']==(route or {}).get('provider')),None)
    if provider and provider.get('key'):
        return {'key':provider['key'],'base':provider['base'],'model':route['model'],'own':own,'proxy':config._load_settings().get('proxy_url','')}
    key=config._load_apikey()
    if key:
        s=config._load_settings()
        return {'key':key,'base':s['api_base'],'model':s['model'],'own':own,'proxy':s.get('proxy_url','')}
    if own:
        token=tenancy.profile.set('admin')
        try:
            resolved=resolve(config,scene); resolved['own']=False
            return resolved
        finally: tenancy.profile.reset(token)
    return {'key':'','base':config.get_ai_api_base(),'model':config.get_ai_model(),'own':False,'proxy':''}

def register(a):
    @a.app.route('/api/ai/providers',methods=['GET','PUT'])
    def profiles():
        current=read()
        if a.request.method=='PUT':
            data=a.body(); providers=data.get('providers',[]); routes=data.get('routes',{})
            if not isinstance(providers,list) or len(providers)>20 or not isinstance(routes,dict): raise ValueError('模型配置格式错误')
            old={p['id']:p for p in current['providers']}; result=[]; ids=set()
            for p in providers:
                if not isinstance(p,dict): raise ValueError('供应商格式错误')
                pid=str(p.get('id') or uuid.uuid4().hex)
                if pid in ids: raise ValueError('供应商 ID 重复')
                ids.add(pid); base=str(p.get('base','')).rstrip('/'); models=p.get('models',[])
                if urlparse(base).scheme not in ('http','https') or not urlparse(base).netloc or urlparse(base).username: raise ValueError('供应商需填写有效 HTTP/HTTPS 地址')
                if not isinstance(models,list) or not 1<=len(models)<=100 or any(not isinstance(m,str) or not m.strip() or len(m)>200 for m in models): raise ValueError('每个供应商需配置模型名称')
                key=str(p.get('key','')).strip() or old.get(pid,{}).get('key','')
                if p.get('clear_key'): key=''
                result.append({'id':pid,'name':str(p.get('name','AI 服务'))[:100],'base':base,'models':models,'key':key})
            by_id={p['id']:p for p in result}
            for scene,route in routes.items():
                if scene not in SCENES or not isinstance(route,dict) or route.get('provider') not in by_id or route.get('model') not in by_id[route['provider']]['models']: raise ValueError('场景引用了不存在的供应商或模型')
            current={'providers':result,'routes':routes}
            target=Path(tenancy.path('ai-profiles.json')); temp=target.with_suffix('.tmp')
            with a.SETTINGS_LOCK:
                temp.write_text(json.dumps(current,ensure_ascii=False,indent=2),encoding='utf8'); os.replace(temp,target)
        return jsonify(providers=[{**{k:v for k,v in p.items() if k!='key'},'has_key':bool(p.get('key'))} for p in current['providers']],routes=current['routes'],scenes=SCENES)
    a.config.resolve_ai=lambda scene='general':resolve(a.config,scene)
