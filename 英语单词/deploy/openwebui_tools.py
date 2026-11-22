"""
title: 忆溯单词工具
description: 通过已认证的 MCP 接口查词、建组、录词，不暴露系统设置。
version: 1.0.0
"""
import json, os, urllib.request
from pydantic import BaseModel, Field


class Tools:
    class Valves(BaseModel):
        MCP_URL: str = Field(default='http://127.0.0.1:5052/mcp',description='同容器的忆溯 MCP 地址')
    class UserValves(BaseModel):
        AGENT_TOKEN: str = Field(default='',description='你自己的忆溯设置 > 对话与 MCP > Agent Token，不能使用他人 Token')

    def __init__(self): self.valves=self.Valves()

    def _call(self,name,args,user=None):
        valves=(user or {}).get('valves')
        token=valves.get('AGENT_TOKEN','') if isinstance(valves,dict) else getattr(valves,'AGENT_TOKEN','')
        secret=os.environ.get('GATEWAY_AUTH_SECRET','')
        if secret and (user or {}).get('email'):
            req=urllib.request.Request('http://127.0.0.1:5052/api/internal/agent-token',
                data=json.dumps({'email':user['email']}).encode(),headers={'Content-Type':'application/json','X-Gateway-Secret':secret})
            try:
                with urllib.request.urlopen(req,timeout=10) as response: token=json.load(response)['token']
            except Exception: return {'error':'平台身份验证失败，请重新登录或检查账号绑定'}
        if not token: return {'error':'请在此工具的个人设置中配置自己的忆溯 Agent Token'}
        raw=json.dumps({'jsonrpc':'2.0','id':1,'method':'tools/call','params':{'name':name,'arguments':args}},ensure_ascii=False).encode()
        req=urllib.request.Request(self.valves.MCP_URL,data=raw,headers={'Authorization':'Bearer '+token,'Content-Type':'application/json','Accept':'application/json, text/event-stream'})
        try:
            with urllib.request.urlopen(req,timeout=160) as response: result=json.load(response)
            if 'error' in result: return {'error':result['error']['message']}
            result=result['result']; text=result['content'][0]['text']
            return {'error':text} if result.get('isError') else json.loads(text)
        except Exception: return {'error':'MCP 连接失败，请检查工具配置与本地服务日志'}

    def create_vocabulary_group(self,name:str,tags:list[str]=[],__user__:dict=None) -> str:
        """创建英语学习分组，返回 group_id。name 是分组名，tags 是可选标签。"""
        return json.dumps(self._call('create_group',{'name':name,'tags':tags},__user__),ensure_ascii=False)

    def query_vocabulary(self,search:str='',group_id:int=0,__user__:dict=None) -> str:
        """查询个人词库已有内容，group_id=0 表示全局。"""
        return json.dumps(self._call('query_words',{'search':search,**({'group_id':group_id} if group_id else {})},__user__),ensure_ascii=False)

    def queue_vocabulary(self,entries:list[dict],group_id:int=0,__user__:dict=None) -> str:
        """异步录入词条，entries 每项包含 word，可选 context_meaning（仅分组文中义）。重名须用户确认后加 update_existing=true；返回 job_ids，需查询状态。"""
        return json.dumps(self._call('quick_entry',{'entries':entries,**({'group_id':group_id} if group_id else {})},__user__),ensure_ascii=False)

    def vocabulary_job_status(self,job_ids:list[str],__user__:dict=None) -> str:
        """查询快速录词状态，只有 status=done 才代表录入成功。"""
        return json.dumps(self._call('entry_status',{'job_ids':job_ids},__user__),ensure_ascii=False)

    def save_vocabulary_definition(self,definition:dict,groups:list[dict]=[],__user__:dict=None) -> str:
        """写入完整词条，definition 含 word,chinese_meaning,example_sentence,example_translation,notes 等；groups 每项含 group_id 和可选 context_meaning。重复保存需用户确认 update_existing=true。"""
        return json.dumps(self._call('save_full_definition',{'definition':definition,'groups':groups},__user__),ensure_ascii=False)

    def manage_vocabulary_group(self,action:str,group_id:int=0,name:str='',__user__:dict=None) -> str:
        """action=list/rename/delete。删除分组保留单词。delete 仅在用户明确要求时调用。"""
        operation={'list':('list_groups',{}),'rename':('rename_group',{'group_id':group_id,'name':name}),'delete':('delete_group',{'group_id':group_id})}.get(action)
        return json.dumps(self._call(*operation,__user__) if operation else {'error':'无效操作'},ensure_ascii=False)
