"""Shared JSON AI requests with bounded retries and tolerant JSON decoding."""
import json, re, time, urllib.request, urllib.error
import config
from config import get_ai_api_key, get_ai_api_base, get_ai_model, _load_settings

class AIError(RuntimeError):
    pass

def parse_json(content):
    if isinstance(content, dict): return content
    if isinstance(content, list): content = ''.join(x.get('text', '') for x in content if isinstance(x, dict))
    text = re.sub(r'<think>.*?</think>', '', str(content), flags=re.S).strip()
    for match in re.finditer(r'[\{\[]', text):
        try:
            value, _ = json.JSONDecoder().raw_decode(text[match.start():])
            if isinstance(value, dict): return value
        except ValueError: pass
    raise AIError('AI 返回的内容不是有效 JSON，请重试或切换模型')

def complete(prompt, system='你是专业的英语学习助手，严格返回 JSON 对象。', max_tokens=2200, timeout=45, attempts=3, scene='general'):
    route=config.resolve_ai(scene) if hasattr(config,'resolve_ai') else {'key':get_ai_api_key(),'base':get_ai_api_base(),'model':get_ai_model(),'proxy':_load_settings().get('proxy_url',''),'own':False}
    if not route['key']: raise AIError('尚未配置 AI Key，本地词典与手动录入仍可使用')
    if hasattr(config,'reserve_ai'): config.reserve_ai(route['own'])
    proxy = route['proxy'].strip()
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({'http':proxy,'https':proxy})) if proxy else urllib.request.build_opener()
    payload = json.dumps({'model':route['model'], 'messages':[{'role':'system','content':system},{'role':'user','content':prompt}], 'temperature':0.2, 'max_tokens':max_tokens}, ensure_ascii=False).encode('utf8')
    for attempt in range(attempts):
        try:
            req = urllib.request.Request(route['base'].rstrip('/')+'/chat/completions', data=payload, headers={'Authorization':'Bearer '+route['key'],'Content-Type':'application/json'})
            with opener.open(req, timeout=timeout) as response: data=json.load(response)
            choices=data.get('choices') if isinstance(data,dict) else None
            if not isinstance(choices,list) or not choices or not isinstance(choices[0],dict): raise AIError('AI 响应缺少有效 choices，请重试')
            choice=choices[0]
            if choice.get('finish_reason')=='length': raise AIError('AI 返回内容被截断，请重试或切换模型')
            message=choice.get('message')
            if not isinstance(message,dict): raise AIError('AI 响应缺少 message，请重试')
            return parse_json(message.get('content',''))
        except urllib.error.HTTPError as error:
            if error.code not in (408,429,500,502,503,504): raise AIError('AI 请求被拒绝（HTTP %s），请检查地址、模型和 Key'%error.code) from None
            failure='AI 服务繁忙（HTTP %s）'%error.code
            try: delay=min(5, float(error.headers.get('Retry-After', '1')))
            except ValueError: delay=1
        except (OSError, ValueError, AIError) as error:
            failure=str(error) if isinstance(error,AIError) else 'AI 网络连接或响应异常，请检查网络和代理'; delay=1
        if attempt<attempts-1: time.sleep(min(5,delay*2**attempt))
    raise AIError(failure)
