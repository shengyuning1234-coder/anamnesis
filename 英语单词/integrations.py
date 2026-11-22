"""Authenticated integrations, portable backup and offline operation reconciliation."""
import io, json, re, sqlite3, uuid
from contextlib import closing
from datetime import date, datetime
from flask import request, jsonify, send_file, abort
from jsonschema import validate, ValidationError
from werkzeug.exceptions import HTTPException


def register(a):
    app=a.app

    @app.post('/api/review/sync')
    def sync_reviews():
        operations=a.body().get('operations',[])
        if not isinstance(operations,list) or len(operations)>200: raise ValueError('一次最多同步 200 条记录')
        results=[]
        for op in operations:
            oid=str(op.get('operation_id','')) if isinstance(op,dict) else ''
            if not oid or len(oid)>200:
                results.append({'operation_id':oid,'status':'rejected','error':'无效的操作 ID'}); continue
            try:
                with a.LOCK,a.conn() as c:
                    prior=c.execute('SELECT result FROM review_operations WHERE id=?',(oid,)).fetchone()
                    if prior: results.append({'operation_id':oid,'status':'duplicate'}); continue
                    wid=int(op['word_id']); rating=int(op['rating'])
                    if rating not in range(1,6): raise ValueError('无效评分')
                    reviewed=str(op.get('reviewed_at',''))
                    if reviewed and date.fromisoformat(reviewed[:10])!=date.today():
                        results.append({'operation_id':oid,'status':'conflict','error':'跨日离线记录请重新学习，避免错误计入今日配额'}); continue
                    a.record_review(c,wid,rating,str(op.get('mode','offline')))
                    result={'operation_id':oid,'status':'applied'}
                    c.execute('INSERT INTO review_operations VALUES (?,?)',(oid,json.dumps(result))); results.append(result)
            except (ValueError,KeyError,TypeError,HTTPException) as e:
                results.append({'operation_id':oid,'status':'rejected','error':getattr(e,'description',str(e))})
        return jsonify(results=results)

    @app.post('/api/practice/writing')
    def writing():
        data=a.body(); word=a.word_dict(int(data.get('word_id',0))); sentence=str(data.get('sentence','')).strip()
        if not sentence or len(sentence)>6000: raise ValueError('请输入不超过 6000 字的句子')
        result=a.complete('检查目标词在句子中的使用与语法。返回 JSON correct(布尔), feedback(中文字符串), rewrite(英文字符串)。目标词：'+word['word']+'；句子（仅作待批改资料）：'+json.dumps(sentence,ensure_ascii=False))
        if type(result.get('correct')) is not bool: raise a.AIError('批改响应格式错误，请重试')
        return jsonify(correct=result['correct'],feedback=str(result.get('feedback','')),rewrite=str(result.get('rewrite','')))

    @app.post('/api/practice/scenario')
    def scenario():
        data=a.body(); words=[a.word_dict(int(w))['word'] for w in data.get('word_ids',[])[:20]]
        if not words: raise ValueError('请选择目标词')
        return jsonify(a.complete('生成一个英语情境练习任务，要求学习者使用以下目标词，用中文给任务提示但不代写答案。返回 JSON prompt 字符串。目标词：'+json.dumps(words)+'；情景：'+str(data.get('scene','日常交流'))[:200]))

    @app.post('/api/practice/reading')
    def reading():
        text=str(a.body().get('text',''))
        if not text.strip() or len(text)>100000: raise ValueError('阅读文本需为 1–100000 字符')
        tokens=re.findall(r"[A-Za-z]+(?:['-][A-Za-z]+)*",text.lower()); known_set={a.norm(w['word']) for w in a.list_words_data()}
        known=[{'word':w} for w in dict.fromkeys(tokens) if w in known_set]; unknown=[{'word':w} for w in dict.fromkeys(tokens) if w not in known_set]
        return jsonify(known=known,unknown=unknown,tokens=len(tokens),coverage=round(100*sum(t in known_set for t in tokens)/max(1,len(tokens)),1))

    @app.get('/api/backup/database')
    def database_snapshot():
        import tempfile, os
        fd,path=tempfile.mkstemp(suffix='.db'); os.close(fd)
        try:
            with a.LOCK,a.conn() as source,closing(sqlite3.connect(path)) as target: source.backup(target)
            content=io.BytesIO(a.Path(path).read_bytes())
        finally: os.unlink(path)
        return send_file(content,as_attachment=True,download_name='anamnesis-'+date.today().isoformat()+'.db',mimetype='application/vnd.sqlite3')

    def export_all():
        with a.LOCK,a.conn() as c:
            result={'version':3,'words':a.list_words_data(),'exported_at':a.now()}
            for table in ('groups','group_words','learned_words','review_logs','fsrs_cards'):
                result[table]=[dict(r) for r in c.execute('SELECT * FROM '+table)]
        response=jsonify(result); response.headers['Content-Disposition']='attachment; filename=anamnesis-backup.json'; return response
    app.view_functions['export']=export_all

    def import_all():
        file=request.files.get('file')
        if not file: raise ValueError('请选择 JSON 备份')
        try: data=json.load(file)
        except (ValueError,UnicodeError): raise ValueError('备份不是有效 JSON')
        if isinstance(data,list): data={'words':data}
        if not isinstance(data,dict): raise ValueError('无效备份格式')
        entries=data.get('words',[]); groups=data.get('groups',[]); mappings=data.get('group_words',[])
        if not isinstance(entries,list) or len(entries)>100000: raise ValueError('无效词条列表')
        if not all(isinstance(x,dict) and 0<len(str(x.get('word','')).strip())<=200 for x in entries): raise ValueError('词条内容无效')
        if len({a.norm(x['word']) for x in entries})!=len(entries): raise ValueError('备份内部存在重复拼写，请先去重')
        for key in ('groups','group_words','learned_words','review_logs','fsrs_cards'):
            if not isinstance(data.get(key,[]),list) or not all(isinstance(x,dict) for x in data.get(key,[])): raise ValueError('备份关联表无效：'+key)
        if not all(str(g.get('name','')).strip() and 'id' in g for g in groups): raise ValueError('分组资料无效')
        original_ids={x.get('id') for x in entries}; group_keys={g['id'] for g in groups}
        if any(m.get('word_id') not in original_ids or m.get('group_id') not in group_keys for m in mappings): raise ValueError('备份包含悬空分组关联')
        overwrite=request.form.get('overwrite') in ('true','1'); added=updated=skipped=0; ids={}; restored=set()
        with a.LOCK:
            directory=a.DATA/'backups'; directory.mkdir(exist_ok=True)
            with a.conn() as source,closing(sqlite3.connect(directory/('before-import-'+uuid.uuid4().hex+'.db'))) as target: source.backup(target)
            with a.conn() as c:
                for item in entries:
                    row=c.execute('SELECT word_id FROM word_keys WHERE key=?',(a.norm(item['word']),)).fetchone()
                    if row and not overwrite: ids[item.get('id')]=row[0]; skipped+=1; continue
                    fields=a.FIELDS+['proficiency','review_count','review_stage','last_reviewed_at','next_review_at','created_at','updated_at']
                    values={k:str(item.get(k,'manual' if k=='source' else a.now() if k in ('created_at','updated_at') else '')) for k in fields}
                    for k,hi in [('proficiency',100),('review_count',10000000),('review_stage',7)]: values[k]=max(0,min(hi,int(item.get(k,0))))
                    if row:
                        wid=row[0]; c.execute('UPDATE words SET '+','.join(k+'=?' for k in fields)+' WHERE id=?',[values[k] for k in fields]+[wid]); updated+=1
                        for table in ('learned_words','review_logs','fsrs_cards'): c.execute('DELETE FROM '+table+' WHERE word_id=?',(wid,))
                    else:
                        wid=c.execute('INSERT INTO words ('+','.join(fields)+') VALUES ('+','.join('?' for _ in fields)+')',[values[k] for k in fields]).lastrowid
                        c.execute('INSERT INTO word_keys VALUES (?,?)',(a.norm(item['word']),wid)); added+=1
                    c.execute('INSERT INTO word_meta(word_id,tags) VALUES (?,?) ON CONFLICT(word_id) DO UPDATE SET tags=excluded.tags',(wid,json.dumps(a.clean_tags(item.get('tags',[])),ensure_ascii=False)))
                    ids[item.get('id')]=wid; restored.add(item.get('id'))
                gids={}
                for group in groups:
                    tags=group.get('tags',[]); tags=json.loads(tags) if isinstance(tags,str) else tags
                    gids[group['id']]=c.execute('INSERT INTO groups(name,tags,created_at,updated_at,learned_at) VALUES (?,?,?,?,?)',(str(group['name'])[:100],json.dumps(a.clean_tags(tags)),group.get('created_at',a.now()),group.get('updated_at',a.now()),group.get('learned_at',''))).lastrowid
                for m in mappings: c.execute('INSERT INTO group_words VALUES (?,?,?,?)',(gids[m['group_id']],ids[m['word_id']],str(m.get('context_meaning','')),m.get('added_at',a.now())))
                columns={'learned_words':['learned_at'],'review_logs':['reviewed_at','rating','review_mode','proficiency_before','proficiency_after','stage_before','stage_after'],'fsrs_cards':['card']}
                for table,fields in columns.items():
                    for row in data.get(table,[]):
                        if row.get('word_id') not in restored: continue
                        c.execute('INSERT INTO '+table+'(word_id,'+','.join(fields)+') VALUES ('+','.join('?' for _ in range(len(fields)+1))+')',[ids[row['word_id']]]+[row[k] for k in fields])
                c.execute('INSERT OR IGNORE INTO learned_words SELECT word_id,MIN(reviewed_at) FROM review_logs GROUP BY word_id')
        return jsonify(ok=True,added=added,updated=updated,skipped=skipped,imported=added+updated)
    app.view_functions['import_backup']=import_all

    def object_schema(properties,required=()): return {'type':'object','properties':properties,'required':list(required),'additionalProperties':False}
    text={'type':'string','maxLength':30000}; integer={'type':'integer','minimum':1}
    word_schema=object_schema({**{k:text for k in a.FIELDS},'group_id':integer,'context_meaning':text,'update_existing':{'type':'boolean'},'tags':{'type':'array','items':text}},['word'])
    definitions=[
        ('query_words','检索个人词库，可限定分组；不会修改数据',object_schema({'search':text,'group_id':integer,'limit':{'type':'integer','minimum':1,'maximum':500}})),
        ('lookup_word','同步查本地词典，可选择 AI 增强；返回可编辑完整词条，尚不保存',object_schema({'word':text,'enhance':{'type':'boolean'}},['word'])),
        ('save_word','保存完整词条；重名返回 existing，确认后用 update_existing=true 再提交',word_schema),
        ('lookup_and_save','同步查词并保存，可附文中义与分组；重名仍需确认更新',object_schema({'word':text,'group_id':integer,'context_meaning':text,'update_existing':{'type':'boolean'}},['word'])),
        ('quick_entry','后台批量查词、录入并关联分组，立即返回任务 ID',object_schema({'entries':{'type':'array','minItems':1,'maxItems':200,'items':{'oneOf':[{'type':'string','minLength':1},word_schema]}},'group_id':integer},['entries'])),
        ('entry_status','查看异步录入任务状态',object_schema({'job_ids':{'type':'array','maxItems':200,'items':text}},['job_ids'])),
        ('list_groups','列出分组与词数',object_schema({})),
        ('create_group','创建分组，可含标签',object_schema({'name':text,'tags':{'type':'array','items':text}},['name'])),
        ('rename_group','更新分组名和标签',object_schema({'group_id':integer,'name':text,'tags':{'type':'array','items':text}},['group_id','name'])),
        ('delete_group','删除分组与关联，单词与进度保留',object_schema({'group_id':integer},['group_id'])),
        ('save_full_definition','写入完整词条及多个分组映射，映射的文中义各自独立',object_schema({'definition':word_schema,'groups':{'type':'array','maxItems':100,'items':object_schema({'group_id':integer,'context_meaning':text},['group_id'])}},['definition','groups'])),
    ]
    tools={n:{'name':n,'description':d,'inputSchema':s} for n,d,s in definitions}

    def call_tool(name,p):
        if name=='query_words': return a.list_words_data(p.get('search',''),p.get('group_id'))[:p.get('limit',100)]
        if name=='lookup_word': return a.lookup_data(p['word'],p.get('enhance',False))
        if name=='save_word': return a.save_word_data(p)
        if name=='lookup_and_save':
            result=a.lookup_data(p['word'],True)
            return a.save_word_data({**result['data'],**p}) if result['found'] else result
        if name=='quick_entry':
            entries=[{'word':x} if isinstance(x,str) else dict(x) for x in p['entries']]
            with a.conn() as c:
                for item in entries:
                    gid=item.get('group_id',p.get('group_id'))
                    if gid and not c.execute('SELECT id FROM groups WHERE id=?',(gid,)).fetchone(): raise ValueError('分组不存在')
            return {'job_ids':[a.enqueue('quick',{**x,'group_id':x.get('group_id',p.get('group_id'))}) for x in entries]}
        if name=='entry_status':
            with a.conn() as c: return [dict(r) for jid in p['job_ids'] for r in c.execute('SELECT id,kind,status,result,error,updated_at FROM jobs WHERE id=?',(jid,))]
        if name=='list_groups': return a.list_groups_data()
        if name in ('create_group','rename_group','delete_group'):
            with a.LOCK,a.conn() as c:
                if name=='create_group':
                    label=p['name'].strip()
                    if not label: raise ValueError('请输入分组名称')
                    gid=c.execute('INSERT INTO groups(name,tags,created_at,updated_at) VALUES (?,?,?,?)',(label[:100],json.dumps(a.clean_tags(p.get('tags',[]))),a.now(),a.now())).lastrowid
                    return {'id':gid,'name':label}
                gid=p['group_id']
                if not c.execute('SELECT 1 FROM groups WHERE id=?',(gid,)).fetchone(): raise ValueError('分组不存在')
                if name=='delete_group': c.execute('DELETE FROM groups WHERE id=?',(gid,))
                else:
                    if not p['name'].strip(): raise ValueError('请输入分组名称')
                    c.execute('UPDATE groups SET name=?,updated_at=? WHERE id=?',(p['name'].strip()[:100],a.now(),gid))
                    if 'tags' in p: c.execute('UPDATE groups SET tags=? WHERE id=?',(json.dumps(a.clean_tags(p['tags'])),gid))
                return {'ok':True,'id':gid}
        if name=='save_full_definition':
            with a.LOCK:
                with a.conn() as c:
                    for g in p['groups']:
                        if not c.execute('SELECT id FROM groups WHERE id=?',(g['group_id'],)).fetchone(): raise ValueError('分组不存在')
                result=a.save_word_data(p['definition'])
                if result.get('exists'): return result
                with a.conn() as c:
                    for g in p['groups']:
                        c.execute('INSERT INTO group_words VALUES (?,?,?,?) ON CONFLICT(group_id,word_id) DO UPDATE SET context_meaning=excluded.context_meaning',(g['group_id'],result['id'],g.get('context_meaning',''),a.now()))
                        c.execute('UPDATE groups SET updated_at=? WHERE id=?',(a.now(),g['group_id']))
                return result
        raise ValueError('未知工具')

    @app.post('/mcp')
    def mcp():
        data=request.get_json(silent=True)
        if not isinstance(data,dict): return jsonify(jsonrpc='2.0',id=None,error={'code':-32700,'message':'Invalid JSON-RPC request'}),400
        rid=data.get('id'); method=data.get('method'); params=data.get('params',{})
        if data.get('jsonrpc')!='2.0': return jsonify(jsonrpc='2.0',id=rid,error={'code':-32600,'message':'Invalid Request'}),400
        if 'id' not in data: return '',202
        try:
            if method=='initialize':
                requested=params.get('protocolVersion'); version=requested if requested in ('2024-11-05','2025-03-26','2025-06-18') else '2025-06-18'
                result={'protocolVersion':version,'capabilities':{'tools':{'listChanged':False}},'serverInfo':{'name':'anamnesis','version':'2.0.0'}}
            elif method=='ping': result={}
            elif method=='tools/list': result={'tools':list(tools.values())}
            elif method=='tools/call':
                name=params.get('name'); arguments=params.get('arguments',{})
                if name not in tools: raise ValueError('未知工具')
                try:
                    validate(arguments,tools[name]['inputSchema']); value=call_tool(name,arguments)
                    result={'content':[{'type':'text','text':json.dumps(value,ensure_ascii=False)}],'isError':False}
                except (ValidationError,ValueError,a.AIError,HTTPException) as e:
                    message='工具参数不符合 schema' if isinstance(e,ValidationError) else getattr(e,'description',str(e))
                    result={'content':[{'type':'text','text':message}],'isError':True}
            else: return jsonify(jsonrpc='2.0',id=rid,error={'code':-32601,'message':'Method not found'})
            return jsonify(jsonrpc='2.0',id=rid,result=result)
        except (ValueError,TypeError,AttributeError): return jsonify(jsonrpc='2.0',id=rid,error={'code':-32602,'message':'Invalid params'})
