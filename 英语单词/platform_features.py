"""Personal dictionary imports and installable web application resources."""
import json
import re
import uuid
from pathlib import Path
from flask import jsonify, request, Response, send_file

def register(a):
    original_lookup=a.lookup_data

    def lookup(text,use_ai=False):
        file=a.DATA/'dictionary-choice.json'
        selected=json.loads(file.read_text(encoding='utf8')).get('id') if file.exists() else None
        if selected:
            with a.conn() as c:
                row=c.execute('SELECT payload FROM dictionary_entries WHERE dictionary_id=? AND word=?',(selected,a.norm(text))).fetchone()
            if row:
                data=json.loads(row[0]); data.update(word=text.strip(),source='imported-dictionary')
                return {'found':True,'data':data,'source':'imported-dictionary'}
        return original_lookup(text,use_ai)
    a.lookup_data=lookup

    def tables(c):
        c.executescript('''CREATE TABLE IF NOT EXISTS imported_dictionaries(id TEXT PRIMARY KEY,name TEXT NOT NULL,created_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS dictionary_entries(dictionary_id TEXT NOT NULL REFERENCES imported_dictionaries(id) ON DELETE CASCADE,word TEXT NOT NULL,payload TEXT NOT NULL,PRIMARY KEY(dictionary_id,word));''')

    @a.app.route('/api/dictionaries/imported',methods=['GET','POST'])
    def imported_dictionaries():
        with a.conn() as c:
            tables(c)
            if request.method=='POST':
                file=request.files.get('file')
                if not file: raise ValueError('请选择 JSON 字典')
                try: data=json.load(file)
                except (ValueError,UnicodeError): raise ValueError('无法读取 JSON 字典')
                if isinstance(data,dict) and 'entries' in data:
                    name=str(data.get('name',file.filename))[:100]; entries=data['entries']
                else:
                    name=str(file.filename)[:100]; entries=[{'word':k,'chinese_meaning':v} for k,v in data.items()] if isinstance(data,dict) else data
                if not isinstance(entries,list) or not 1<=len(entries)<=100000: raise ValueError('字典需包含 1–100000 个词条')
                prepared=[]
                for row in entries:
                    if not isinstance(row,dict) or not isinstance(row.get('word'),str) or not 1<=len(row['word'])<=200 or not isinstance(row.get('chinese_meaning'),str) or not row['chinese_meaning'].strip(): raise ValueError('每个词条必须包含 word 和 chinese_meaning')
                    prepared.append((a.norm(row['word']),json.dumps({k:str(row.get(k,''))[:30000] for k in a.FIELDS},ensure_ascii=False)))
                did=uuid.uuid4().hex
                c.execute('INSERT INTO imported_dictionaries VALUES (?,?,?)',(did,name,a.now()))
                c.executemany('INSERT OR REPLACE INTO dictionary_entries VALUES (?,?,?)',[(did,*row) for row in prepared])
            result=[dict(row) for row in c.execute('SELECT d.*,COUNT(e.word) AS entries FROM imported_dictionaries d LEFT JOIN dictionary_entries e ON e.dictionary_id=d.id GROUP BY d.id')]
        choice=a.DATA/'dictionary-choice.json'
        return jsonify(dictionaries=result,selected=json.loads(choice.read_text(encoding='utf8')).get('id') if choice.exists() else None)

    @a.app.put('/api/dictionaries/selected')
    def select_dictionary():
        did=a.body().get('id')
        with a.conn() as c:
            tables(c)
            if did and not c.execute('SELECT 1 FROM imported_dictionaries WHERE id=?',(did,)).fetchone(): raise ValueError('字典不存在')
        (a.DATA/'dictionary-choice.json').write_text(json.dumps({'id':did}),encoding='utf8')
        return jsonify(ok=True)

    @a.app.get('/manifest.webmanifest')
    def manifest():
        prefix=request.script_root
        return Response(json.dumps({'id':prefix+'/','name':'忆溯 · AI 单词学习','short_name':'忆溯','lang':'zh-CN',
            'start_url':prefix+'/','scope':prefix+'/','display':'standalone','background_color':'#e8e3ff','theme_color':'#5b4ae0',
            'icons':[{'src':prefix+'/static/icon-'+str(n)+'.png','sizes':f'{n}x{n}','type':'image/png','purpose':'any maskable'} for n in (192,512)]},ensure_ascii=False),mimetype='application/manifest+json')

    @a.app.get('/service-worker.js')
    def service_worker():
        # Never cache authenticated pages, API data, images or chat credentials.
        return Response("self.addEventListener('install',()=>self.skipWaiting());self.addEventListener('activate',event=>event.waitUntil(self.clients.claim()));self.addEventListener('fetch',()=>{});",mimetype='application/javascript',headers={'Service-Worker-Allowed':request.script_root+'/','Cache-Control':'no-store'})
