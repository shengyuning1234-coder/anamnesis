"""Anamnesis: local dictionary, durable learning and MCP HTTP server."""
import os, json, uuid, secrets, hashlib, hmac, threading, time, io, weakref, random
from pathlib import Path
from datetime import date, datetime, timedelta
from urllib.parse import urlparse
from flask import Flask, request, jsonify, send_from_directory, session, redirect, render_template, abort
from werkzeug.security import generate_password_hash, check_password_hash
from PIL import Image, UnidentifiedImageError
import config
from contextlib import contextmanager
from services.database import Database
from services.legacy_upgrade import upgrade, legacy_password_exists, verify_legacy_password
from services.review_service import ReviewService
from services.quiz_service import QuizService
from services.distractors import first_meaning
from services.local_dict import local_dict
from services import lexicon
from services.wordbook_service import WordBookService
from services.ai_client import complete, AIError
from services.lookup_prompt import build_lookup_prompt
from services import ai_quiz
from models.word import Word

BASE=Path(__file__).resolve().parent
DATA=Path(config._DATA_DIR); DATA.mkdir(parents=True,exist_ok=True)
LOCK=threading.RLock(); SETTINGS_LOCK=threading.RLock()
QUESTION_LOCKS=weakref.WeakValueDictionary()
CATEGORIES=['小学','初中','高中','四级','六级','考研','雅思','托福','专四','专八','日常','商务','科技','短语']
DEFAULTS={**config._DEFAULT_AI_CONFIG, **config._DEFAULT_LEARNING_CONFIG, 'scheduling_mode':'ebbinghaus','fsrs':{'target_R':0.9},'appearance':{'background_type':'default','background_image_path':'','background_blur':15,'background_brightness':75,'card_opacity':78},'study_modes':{},'manual_tags':False,'openwebui_url':os.getenv('OPENWEBUI_EMBED_URL',''),'proxy_url':''}

def compatible_background(path):
    """Map historical URLs to files inside the persisted data directory only."""
    prefix='/static/uploads/background/'
    if isinstance(path,str) and path.startswith(prefix):
        name=path[len(prefix):]
        if name and name not in ('.','..') and '/' not in name and '\\' not in name:
            return '/api/background/legacy/'+name
    return path

def settings():
    with SETTINGS_LOCK:
        result=json.loads(json.dumps(DEFAULTS))
        for key,value in config._load_settings().items():
            if isinstance(value,dict) and isinstance(result.get(key),dict): result[key].update(value)
            else: result[key]=value
        for key,default in DEFAULTS.items():
            if isinstance(default,dict) and not isinstance(result.get(key),dict): result[key]=json.loads(json.dumps(default))
        result['appearance']['background_image_path']=compatible_background(result['appearance'].get('background_image_path',''))
        if not result.get('password_hash') and legacy_password_exists(DATA):
            result['password_hash']='legacy-nas-password'
        if os.getenv('BUNDLED_WEBUI')=='1': result['openwebui_url']='/'
        return result

def save_settings(data):
    with SETTINGS_LOCK:
        result=settings()
        for key,value in data.items():
            if isinstance(value,dict) and isinstance(result.get(key),dict): result[key].update(value)
            else: result[key]=value
        target=DATA/'settings.json'; temp=target.with_suffix('.tmp')
        temp.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf8'); os.replace(temp,target)
        config._cached_settings=result
        return result

def secret_file(name):
    path=DATA/name
    if not path.exists():
        try:
            with path.open('x',encoding='utf8') as f: f.write(secrets.token_urlsafe(48))
        except FileExistsError: pass
    return path.read_text(encoding='utf8').strip()

app=Flask(__name__,static_folder=str(BASE/'web/static'),template_folder=str(BASE/'web/templates'))
if os.getenv('APP_URL_PREFIX'):
    from werkzeug.middleware.proxy_fix import ProxyFix
    app.wsgi_app=ProxyFix(app.wsgi_app,x_prefix=1)
    app.config.update(SESSION_COOKIE_NAME=os.getenv('SESSION_COOKIE_NAME','anamnesis_session'),SESSION_COOKIE_PATH='/' if os.getenv('BUNDLED_WEBUI')=='1' else os.environ['APP_URL_PREFIX'])
app.secret_key=secret_file('.session-secret'); MCP_TOKEN=secret_file('.agent-token')
app.config.update(MAX_CONTENT_LENGTH=16*1024*1024, SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE='Lax', PERMANENT_SESSION_LIFETIME=timedelta(days=180),SESSION_COOKIE_SECURE=os.getenv('COOKIE_SECURE','0')=='1')
upgrade(config.DB_PATH)
db=Database()
def now(): return datetime.now().strftime('%Y-%m-%d %H:%M:%S')
def norm(word): return ' '.join(str(word).strip().casefold().split())
@contextmanager
def conn():
    connection=db._get_conn()
    try:
        with connection: yield connection
    finally: connection.close()
def body():
    value=request.get_json(silent=True)
    if not isinstance(value,dict): abort(400,description='请求必须是 JSON 对象')
    return value

def migrate():
    with conn() as c:
        c.executescript('''
        CREATE TABLE IF NOT EXISTS schema_migrations(version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS word_keys(key TEXT PRIMARY KEY, word_id INTEGER NOT NULL REFERENCES words(id) ON DELETE CASCADE);
        CREATE TABLE IF NOT EXISTS word_meta(word_id INTEGER PRIMARY KEY REFERENCES words(id) ON DELETE CASCADE, tags TEXT NOT NULL DEFAULT '[]', classification_status TEXT DEFAULT '', classification_error TEXT DEFAULT '');
        CREATE TABLE IF NOT EXISTS groups(id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, tags TEXT NOT NULL DEFAULT '[]', created_at TEXT NOT NULL, updated_at TEXT NOT NULL, learned_at TEXT DEFAULT '');
        CREATE TABLE IF NOT EXISTS group_words(group_id INTEGER NOT NULL REFERENCES groups(id) ON DELETE CASCADE, word_id INTEGER NOT NULL REFERENCES words(id) ON DELETE CASCADE, context_meaning TEXT NOT NULL DEFAULT '', added_at TEXT NOT NULL, PRIMARY KEY(group_id,word_id));
        CREATE INDEX IF NOT EXISTS idx_group_word ON group_words(word_id);
        CREATE TABLE IF NOT EXISTS learned_words(word_id INTEGER PRIMARY KEY REFERENCES words(id) ON DELETE CASCADE, learned_at TEXT NOT NULL);
        CREATE INDEX IF NOT EXISTS idx_learned_date ON learned_words(learned_at);
        CREATE TABLE IF NOT EXISTS jobs(id TEXT PRIMARY KEY, kind TEXT NOT NULL, payload TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'pending', result TEXT, error TEXT DEFAULT '', created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS quiz_sessions(id TEXT PRIMARY KEY, owner TEXT NOT NULL, payload TEXT NOT NULL, created_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS review_operations(id TEXT PRIMARY KEY, result TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS fsrs_cards(word_id INTEGER PRIMARY KEY REFERENCES words(id) ON DELETE CASCADE, card TEXT NOT NULL);
        ''')
        for row in c.execute('SELECT id,word FROM words ORDER BY id').fetchall(): c.execute('INSERT OR IGNORE INTO word_keys VALUES (?,?)',(norm(row['word']),row['id']))
        c.execute('INSERT OR IGNORE INTO learned_words SELECT word_id,MIN(reviewed_at) FROM review_logs GROUP BY word_id')
        c.execute("INSERT OR IGNORE INTO learned_words SELECT id,COALESCE(NULLIF(last_reviewed_at,''),created_at) FROM words WHERE review_count>0")
        c.execute("UPDATE jobs SET status='pending' WHERE status='running'")
        c.execute('INSERT OR IGNORE INTO schema_migrations VALUES (1,?)',(now(),))
        # Tags in the legacy release were embedded in notes, not word_meta.
        import re
        for row in c.execute('SELECT id,notes FROM words').fetchall():
            tags=[]
            marker=re.search(r'\[TAGS\](.*?)\[/TAGS\]',row['notes'] or '',re.S)
            if marker: tags.extend(x.strip() for x in marker[1].split(',') if x.strip())
            for line in (row['notes'] or '').splitlines():
                match=re.match(r'^\s*(?:标签|Tags?)\s*[:：]\s*(.*)',line,re.I)
                if match: tags.extend(x.strip() for x in re.split(r'[,，、;；]',match[1]) if x.strip())
            if tags: c.execute('INSERT OR IGNORE INTO word_meta(word_id,tags) VALUES (?,?)',(row['id'],json.dumps(list(dict.fromkeys(tags)),ensure_ascii=False)))
migrate()

@app.errorhandler(400)
@app.errorhandler(404)
@app.errorhandler(413)
@app.errorhandler(409)
def http_error(error): return jsonify(error=error.description),error.code
@app.errorhandler(403)
@app.errorhandler(401)
@app.errorhandler(429)
def access_error(error): return jsonify(error=error.description),error.code
@app.errorhandler(ValueError)
def value_error(error): return jsonify(error=str(error)),400
@app.errorhandler(AIError)
def ai_error(error): return jsonify(error=str(error)),502

def is_token():
    raw=request.headers.get('Authorization','')
    return raw.startswith('Bearer ') and hmac.compare_digest(raw[7:],MCP_TOKEN)
def local_request(): return request.remote_addr in ('127.0.0.1','::1')
def authed(): return bool(session.get('authenticated')) and session.get('auth_version')==settings().get('auth_version',0) and session.get('expires_at',0)>time.time()
def owner(): return session.get('owner','agent' if is_token() else 'local')

@app.before_request
def security():
    if is_token() and request.path.startswith(('/api/settings','/api/auth','/api/extension')):
        return jsonify(error='Agent Token 不能访问系统配置或认证管理'),403
    if request.method not in ('GET','HEAD','OPTIONS') and not is_token():
        origin=request.headers.get('Origin')
        if origin and origin.rstrip('/')!=request.host_url.rstrip('/'): return jsonify(error='不允许跨站写入'),403
    if request.path.startswith('/static/') or request.path in ('/health','/login','/api/auth/status','/api/auth/login','/api/auth/setup'): return
    if request.path=='/mcp':
        if not is_token(): return jsonify(error='需要 Bearer Agent Token'),401
        return
    if settings().get('password_hash'):
        if not authed() and not is_token():
            if request.path.startswith('/api/'): return jsonify(error='请先登录',need_login=True),401
            return redirect(request.script_root+'/login')
    elif not local_request() and not is_token():
        if request.path.startswith('/api/'): return jsonify(error='请先设置访问密码',need_login=True),401
        return redirect(request.script_root+'/login')
    if not session.get('owner'): session['owner']=secrets.token_hex(16)

@app.after_request
def headers(response):
    if os.getenv('BUNDLED_WEBUI')=='1': response.delete_cookie('anamnesis_session',path=os.getenv('APP_URL_PREFIX','/words'))
    if not request.path.startswith('/static/'): response.headers['Cache-Control']='no-store'
    response.headers['X-Content-Type-Options']='nosniff'; response.headers['Referrer-Policy']='same-origin'
    return response

@app.get('/health')
def health(): return jsonify(ok=True)
@app.get('/')
def index(): return render_template('index.html', appearance=settings()['appearance'])
@app.get('/login')
def login(): return render_template('login.html')
@app.get('/api/auth/status')
def auth_status(): return jsonify(password_set=bool(settings().get('password_hash')), authenticated=authed() or (not settings().get('password_hash') and local_request()), offline_cache_owner=hashlib.sha256(app.secret_key.encode()).hexdigest()[:16], owner_id=owner())

def enter(remember=True):
    session.clear(); session['authenticated']=True; session['auth_version']=settings().get('auth_version',0); session['owner']=secrets.token_hex(16)
    session.permanent=True; session['expires_at']=time.time()+(180 if remember else 30)*86400
LOGIN_ATTEMPTS={}
@app.post('/api/auth/setup')
def setup():
    with LOCK:
        if settings().get('password_hash'): return jsonify(error='密码已设置，请登录'),409
        if not local_request() and os.environ.get('ALLOW_INITIAL_SETUP')!='1': return jsonify(error='首次设置请在本机完成，或在容器中设置 ALLOW_INITIAL_SETUP=1'),403
        password=str(body().get('password',''))
        if len(password)<8: return jsonify(error='密码至少 8 位'),400
        save_settings({'password_hash':generate_password_hash(password),'auth_version':1}); enter()
    return jsonify(ok=True)
@app.post('/api/auth/login')
def do_login():
    key=request.remote_addr; cutoff=time.time()-300; tries=[x for x in LOGIN_ATTEMPTS.get(key,[]) if x>cutoff]
    if len(tries)>=10: return jsonify(error='尝试过于频繁，请五分钟后重试'),429
    data=body(); password_hash=settings().get('password_hash','')
    password=str(data.get('password',''))
    valid=verify_legacy_password(DATA,password) if password_hash=='legacy-nas-password' else bool(password_hash) and check_password_hash(password_hash,password)
    if not valid:
        LOGIN_ATTEMPTS[key]=tries+[time.time()]; return jsonify(error='密码错误'),401
    if password_hash=='legacy-nas-password': save_settings({'password_hash':generate_password_hash(password)})
    LOGIN_ATTEMPTS.pop(key,None); enter(bool(data.get('remember',True))); return jsonify(ok=True)
@app.post('/api/auth/logout')
def logout(): session.clear(); return jsonify(ok=True)
@app.post('/api/auth/change-password')
def change_password():
    data=body(); s=settings()
    old=str(data.get('old_password',''))
    if s.get('password_hash') and not (verify_legacy_password(DATA,old) if s['password_hash']=='legacy-nas-password' else check_password_hash(s['password_hash'],old)): return jsonify(error='原密码错误'),403
    password=str(data.get('new_password',''))
    if len(password)<8: return jsonify(error='密码至少 8 位'),400
    save_settings({'password_hash':generate_password_hash(password),'auth_version':s.get('auth_version',0)+1}); enter(); return jsonify(ok=True)

@app.get('/api/settings')
def get_settings():
    s=settings(); safe={k:v for k,v in s.items() if k not in ('password_hash','auth_version')}
    safe.update(has_key=bool(config.resolve_ai()['key']),has_password=authed(),
                chat_enabled=os.getenv('BUNDLED_WEBUI')=='1' and bool(os.getenv('APP_URL_PREFIX','').strip('/'))); return jsonify(safe)
@app.put('/api/settings')
def put_settings():
    data=body(); updates={k:v for k,v in data.items() if k in DEFAULTS}
    for key in ('auto_decay','manual_tags'):
        if key in updates and type(updates[key]) is not bool: raise ValueError(key+' 必须是布尔值')
    for key in ('api_base','model','proxy_url','openwebui_url'):
        if key in updates and (not isinstance(updates[key],str) or len(updates[key])>4096): raise ValueError(key+' 格式错误')
    if 'study_modes' in updates:
        if not isinstance(updates['study_modes'],dict) or any(not isinstance(k,str) or v not in ('full','meaning_only','choice_only') for k,v in updates['study_modes'].items()): raise ValueError('学习题型配置错误')
    if 'daily_quota' in updates:
        updates['daily_quota']=int(updates['daily_quota'])
        if not 1<=updates['daily_quota']<=200: raise ValueError('每日配额范围为 1–200')
    if 'review_mode' in updates and updates['review_mode'] not in ('mixed','en2cn','cn2en'): raise ValueError('无效的复习方向')
    if 'scheduling_mode' in updates and updates['scheduling_mode'] not in ('ebbinghaus','fsrs'): raise ValueError('无效的调度算法')
    if 'appearance' in updates:
        a=updates['appearance']
        if not isinstance(a,dict): raise ValueError('外观参数格式错误')
        a={k:v for k,v in a.items() if k in DEFAULTS['appearance']}
        for key,lo,hi in [('background_blur',0,30),('background_brightness',20,100),('card_opacity',15,100)]:
            if key in a: a[key]=max(lo,min(hi,int(a[key])))
        if 'background_image_path' in a: a['background_image_path']=compatible_background(a['background_image_path'])
        if 'background_image_path' in a and a['background_image_path'] and not a['background_image_path'].startswith('/api/background/'): raise ValueError('请使用上传的背景图片')
        updates['appearance']=a
    if 'fsrs' in updates: updates['fsrs']={'target_R':max(.7,min(.99,float(updates['fsrs'].get('target_R',.9))))}
    for key in ('api_base','proxy_url','openwebui_url'):
        if key=='openwebui_url' and os.getenv('BUNDLED_WEBUI')=='1': continue
        if updates.get(key) and urlparse(updates[key]).scheme not in ('http','https'): raise ValueError('地址需使用 http 或 https')
    if 'api_key' in data and not isinstance(data['api_key'],str): raise ValueError('API Key 必须是文本')
    key=str(data.get('api_key','')).strip()
    if key or data.get('clear_api_key'):
        if not config.save_apikey('' if data.get('clear_api_key') else key):
            return jsonify(error='API Key 保存失败，请检查 /data/words 文件夹是否可写及 NAS 剩余空间'),500
    try: result=save_settings(updates)
    except OSError:
        return jsonify(error='设置保存失败，请检查 /data/words 文件夹是否可写及 NAS 剩余空间'),500
    return jsonify(ok=True,has_key=bool(config.get_ai_api_key()),saved={k:v for k,v in result.items() if k not in ('password_hash','auth_version')})
@app.post('/api/settings/test-ai')
def test_ai(): return jsonify(ok=True,result=complete('返回 {"ok": true}'))
@app.post('/api/settings/background/upload')
def background_upload():
    file=request.files.get('file')
    if not file: raise ValueError('请选择图片')
    try:
        image=Image.open(file.stream); image.verify(); file.stream.seek(0); image=Image.open(file.stream); image.thumbnail((3840,2160)); image=image.convert('RGB')
    except (UnidentifiedImageError,OSError,Image.DecompressionBombError): raise ValueError('图片无法识别，请使用 JPG、PNG 或 WebP')
    directory=DATA/'backgrounds'; directory.mkdir(exist_ok=True); name=uuid.uuid4().hex+'.jpg'; image.save(directory/name,quality=90)
    path='/api/background/'+name
    if request.form.get('preview') != '1':
        save_settings({'appearance':{'background_type':'custom','background_image_path':path}})
    return jsonify(ok=True,path=path)
@app.get('/api/background/legacy/<name>')
def legacy_background(name): return send_from_directory(DATA/'uploads/background',name)
@app.get('/api/background/<name>')
def background(name): return send_from_directory(DATA/'backgrounds',name)
@app.get('/api/extension/token-info')
def token_info(): return jsonify(token=MCP_TOKEN,server=request.host_url.rstrip('/')+request.script_root,mcp_url=request.host_url.rstrip('/')+request.script_root+'/mcp')
@app.get('/api/study-modes')
def study_modes(): return jsonify(tag_modes=settings()['study_modes'])

def word_dict(word_id,c=None):
    if c is None:
        with conn() as c: return word_dict(word_id,c)
    row=c.execute('SELECT * FROM words WHERE id=?',(word_id,)).fetchone()
    if not row: abort(404,description='单词不存在')
    result=dict(row); meta=c.execute('SELECT * FROM word_meta WHERE word_id=?',(word_id,)).fetchone()
    result['tags']=json.loads(meta['tags']) if meta else []
    result['classification_status']=meta['classification_status'] if meta else ''
    result['classification_error']=meta['classification_error'] if meta else ''
    return result

def list_words_data(search='',group_id=None,tag='',sort='time_desc'):
    order={'time_desc':'w.updated_at DESC,w.id DESC','time_asc':'w.created_at ASC,w.id ASC','alpha_asc':'w.word COLLATE NOCASE ASC','alpha_desc':'w.word COLLATE NOCASE DESC','proficiency_asc':'w.proficiency ASC','proficiency_desc':'w.proficiency DESC','word_asc':'w.word COLLATE NOCASE ASC','word_desc':'w.word COLLATE NOCASE DESC'}.get(sort,'w.updated_at DESC,w.id DESC')
    query='SELECT w.id'+(',gw.context_meaning' if group_id else '')+' FROM words w'; args=[]
    if group_id: query+=' JOIN group_words gw ON gw.word_id=w.id AND gw.group_id=?'; args.append(int(group_id))
    if search: query+=' WHERE (w.word LIKE ? OR w.chinese_meaning LIKE ?)'; args.extend(['%'+search+'%']*2)
    with conn() as c:
        result=[]
        for row in c.execute(query+' ORDER BY '+order,args).fetchall():
            item=word_dict(row['id'],c)
            if tag and tag not in item['tags']: continue
            if group_id: item['context_meaning']=row['context_meaning']
            result.append(item)
        return result

@app.get('/api/words')
def words(): return jsonify(list_words_data(request.args.get('search',''),request.args.get('group_id'),request.args.get('tag',''),request.args.get('sort','time_desc')))
@app.get('/api/words/<int:word_id>')
def get_word(word_id):
    result=word_dict(word_id)
    if request.args.get('group_id'):
        with conn() as c:
            row=c.execute('SELECT context_meaning FROM group_words WHERE group_id=? AND word_id=?',(request.args['group_id'],word_id)).fetchone()
            if row: result['context_meaning']=row[0]
    return jsonify(result)

FIELDS=['word','phonetic','part_of_speech','chinese_meaning','example_sentence','example_translation','notes','source']
def clean_tags(value):
    if not isinstance(value,list): raise ValueError('标签必须是数组')
    return list(dict.fromkeys(str(x).strip()[:40] for x in value if str(x).strip()))[:40]

def save_word_data(data,word_id=None,enqueue_classification=True):
    text=' '.join(str(data.get('word','')).strip().split())
    if not text or len(text)>200: raise ValueError('单词不能为空且不能超过 200 字符')
    with LOCK,conn() as c:
        group_id=data.get('group_id')
        if group_id and not c.execute('SELECT id FROM groups WHERE id=?',(int(group_id),)).fetchone(): raise ValueError('分组不存在')
        match=c.execute('SELECT word_id FROM word_keys WHERE key=?',(norm(text),)).fetchone()
        if word_id and match and match[0]!=word_id: abort(409,description='该单词已经存在，请更新现有记录')
        existing=c.execute('SELECT * FROM words WHERE id=?',(word_id or (match[0] if match else -1),)).fetchone(); updated=bool(existing)
        if match and not word_id and not data.get('update_existing'): return {'exists':True,'existing':word_dict(match[0],c),'error':'单词已存在，是否更新已有内容？'}
        if word_id and not existing: abort(404,description='单词不存在')
        values={key:str(data[key]).replace('\\n','\n') if key in data else (existing[key] if existing else ('manual' if key=='source' else '')) for key in FIELDS}; values['word']=text
        if existing:
            word_id=existing['id']; c.execute('UPDATE words SET '+','.join(k+'=?' for k in FIELDS)+',updated_at=? WHERE id=?',[values[k] for k in FIELDS]+[now(),word_id]); c.execute('DELETE FROM word_keys WHERE word_id=?',(word_id,))
        else:
            word_id=c.execute('INSERT INTO words ('+','.join(FIELDS)+',created_at,updated_at,next_review_at) VALUES ('+','.join('?' for _ in range(len(FIELDS)+3))+')',[values[k] for k in FIELDS]+[now(),now(),now()]).lastrowid
        c.execute('INSERT INTO word_keys VALUES (?,?)',(norm(text),word_id)); c.execute('INSERT OR IGNORE INTO word_meta(word_id) VALUES (?)',(word_id,))
        if 'tags' in data: c.execute('UPDATE word_meta SET tags=? WHERE word_id=?',(json.dumps(clean_tags(data['tags']),ensure_ascii=False),word_id))
        if group_id:
            c.execute('INSERT INTO group_words VALUES (?,?,?,?) ON CONFLICT(group_id,word_id) DO UPDATE SET context_meaning=CASE WHEN ? THEN excluded.context_meaning ELSE group_words.context_meaning END',(int(group_id),word_id,str(data.get('context_meaning','')),now(),'context_meaning' in data))
            c.execute('UPDATE groups SET updated_at=? WHERE id=?',(now(),int(group_id)))
    if enqueue_classification:
        schedule_classification(word_id)
    return {**word_dict(word_id),'updated':updated,'message':'已更新已有单词' if updated else '已录入'}

@app.post('/api/words')
def add_word():
    result=save_word_data(body()); return jsonify(result),409 if result.get('exists') else 200 if result['updated'] else 201
@app.put('/api/words/<int:word_id>')
def update_word(word_id):
    data=body(); data.setdefault('word',word_dict(word_id)['word']); return jsonify(save_word_data(data,word_id))
@app.delete('/api/words/<int:word_id>')
def delete_word(word_id):
    with LOCK,conn() as c: c.execute('DELETE FROM words WHERE id=?',(word_id,))
    return jsonify(ok=True)
@app.get('/api/tags')
def tags():
    counts={}
    for w in list_words_data():
        for tag in w['tags']: counts[tag]=counts.get(tag,0)+1
    return jsonify([{'name':t,'count':n} for t,n in sorted(counts.items())])
@app.route('/api/words/<int:word_id>/tags',methods=['POST','DELETE'])
def set_tags(word_id):
    data=body(); tags=word_dict(word_id)['tags']; values=clean_tags(data.get('tags',[data.get('tag','')]))
    tags=clean_tags(tags+values) if request.method=='POST' else [x for x in tags if x not in values]
    with conn() as c: c.execute('INSERT INTO word_meta(word_id,tags) VALUES (?,?) ON CONFLICT(word_id) DO UPDATE SET tags=excluded.tags',(word_id,json.dumps(tags,ensure_ascii=False)))
    return jsonify(ok=True,tags=tags)

def lookup_data(text,use_ai=False):
    text=text.strip()
    if not text: raise ValueError('请输入单词')
    data=lexicon.build_record(text,local_dict.query(text))
    if use_ai and not config.resolve_ai('lookup')['key']:
        if data: return {'found':True,'data':data,'source':'local','warning':'尚未配置 AI，请先在设置中填写 AI 服务；已保留本地释义'}
        raise AIError('尚未配置 AI，请先在设置中填写 AI 服务')
    if not use_ai:
        if data:return {'found':True,'data':data,'source':'local'}
    else:
        prompt=build_lookup_prompt(text,data)
        try:
            generated=complete(prompt,scene='lookup')
            if not isinstance(generated,dict):raise AIError('AI 返回的词条格式无效')
            if data:
                # Originals stay byte-for-byte intact; AI interpretation is additive.
                addition=generated.get('supplemental_notes') or generated.get('notes') or ''
                if not isinstance(addition,str):raise AIError('AI 补充笔记格式无效')
                if not data.get('chinese_meaning') and isinstance(generated.get('chinese_meaning'),str):
                    data['chinese_meaning']=generated['chinese_meaning'];addition+='\n中文释义由 AI 补充：'+generated['chinese_meaning']
                if not data.get('english_meaning') and isinstance(generated.get('english_meaning'),str):
                    data['english_meaning']=generated['english_meaning'];addition+='\n英文释义由 AI 补充：'+generated['english_meaning']
                if not isinstance(addition,str):raise AIError('AI 补充笔记格式无效')
                for field in ['phonetic','part_of_speech']:
                    if not data.get(field) and isinstance(generated.get(field),str): data[field]=generated[field]
                # Keep translations paired with the exact sentences they describe.
                if not data.get('example_sentence') and not data.get('example_translation'):
                    if all(isinstance(generated.get(k),str) for k in ['example_sentence','example_translation']):
                        data['example_sentence']=generated['example_sentence'];data['example_translation']=generated['example_translation']
                elif not data.get('example_translation') and generated.get('example_sentence')==data.get('example_sentence') and isinstance(generated.get('example_translation'),str):
                    data['example_translation']=generated['example_translation']
                if addition.strip():data['notes']+='\n\nAI 补充（待核对，不改写词典原文）\n'+addition.strip()
                data['source']='local+ai'
            else:
                if not isinstance(generated.get('chinese_meaning'),str) or not generated['chinese_meaning'].strip():raise AIError('AI 未返回有效中文释义')
                data={key:generated.get(key,'') if isinstance(generated.get(key,''),str) else '' for key in FIELDS if key!='source'}
                english=generated.get('english_meaning','')
                if isinstance(english,str) and english:data['notes']='英文释义（AI 生成，待核对）\n'+english+'\n\n'+data['notes']
                data.update(word=text,source='ai')
            return {'found':True,'data':data,'source':data['source']}
        except AIError:
            if data: return {'found':True,'data':data,'source':'local','warning':'AI 不可用，已使用本地完整词条'}
            raise
    return {'found':False,'message':'本地词典未找到该词，可手动填写释义或配置 AI','suggestions':local_dict.suggest_similar(text)}
@app.post('/api/words/lookup')
def lookup():
    data=body(); return jsonify(lookup_data(str(data.get('word','')),data.get('enhance') is True))

@app.get('/api/dictionaries')
def dictionaries():
    return jsonify(**lexicon.status(),primary_ready=local_dict.ready,policy='bilingual-first, local-classification-first, AI-additions-only')

def schedule_classification(word_id):
    w=word_dict(word_id)
    if lexicon.local_tags(w['word']):
        classify_word(word_id)
    elif not w['tags']:
        status='pending' if config.resolve_ai('classification')['key'] else 'unavailable'
        with conn() as c:c.execute("UPDATE word_meta SET classification_status=?,classification_error='' WHERE word_id=?",(status,word_id))
        if status=='pending':enqueue('classify',{'word_id':word_id})

def classify_word(word_id):
    w=word_dict(word_id)
    try:
        local_tags=lexicon.local_tags(w['word'])
        if local_tags:
            tags=clean_tags(w['tags']+local_tags)
            with conn() as c:c.execute("UPDATE word_meta SET tags=?,classification_status='local',classification_error='' WHERE word_id=?",(json.dumps(tags,ensure_ascii=False),word_id))
            return {'tags':tags,'categories':{k:True if k in local_tags else None for k in CATEGORIES},'source':'local','evidence':lexicon.query(w['word'])['classification_evidence']}
        result=complete('独立判断以下每个类别是否适用于该英语单词。难度级别与用途类别允许多个同时为 true，不能强制单选；不确定的为 false。返回 JSON {"categories": {类别名: true/false}}，所有类别必须出现。类别：'+json.dumps(CATEGORIES,ensure_ascii=False)+'；单词资料：'+json.dumps({k:w[k] for k in FIELDS},ensure_ascii=False),scene='classification')
        flags=result.get('categories',result)
        if not isinstance(flags,dict) or not all(k in flags and type(flags[k]) is bool for k in CATEGORIES): raise AIError('分类响应缺少独立布尔判定，请重试')
        tags=clean_tags(w['tags']+[k for k in CATEGORIES if flags[k] is True])
        with conn() as c: c.execute("INSERT INTO word_meta(word_id,tags,classification_status) VALUES (?,?,'done') ON CONFLICT(word_id) DO UPDATE SET tags=excluded.tags,classification_status='done',classification_error=''",(word_id,json.dumps(tags,ensure_ascii=False)))
        return {'tags':tags,'categories':flags}
    except AIError as e:
        with conn() as c: c.execute("UPDATE word_meta SET classification_status='failed',classification_error=? WHERE word_id=?",(str(e),word_id))
        raise
@app.post('/api/words/classify')
def classify():
    data=body(); word_id=data.get('word_id')
    if not word_id:
        with conn() as c: row=c.execute('SELECT word_id FROM word_keys WHERE key=?',(norm(data.get('word','')),)).fetchone()
        if not row: raise ValueError('请先保存单词')
        word_id=row[0]
    return jsonify(classify_word(int(word_id)))

@app.route('/api/groups',methods=['GET','POST'])
def groups():
    if request.method=='POST':
        data=body(); name=str(data.get('name','')).strip()
        if not name: raise ValueError('请输入分组名称')
        with conn() as c: gid=c.execute('INSERT INTO groups(name,tags,created_at,updated_at) VALUES (?,?,?,?)',(name[:100],json.dumps(clean_tags(data.get('tags',[])),ensure_ascii=False),now(),now())).lastrowid
        return jsonify(id=gid,name=name),201
    return jsonify(list_groups_data())

def list_groups_data():
    with conn() as c:
        result=[]
        for row in c.execute('SELECT g.*,COUNT(gw.word_id) AS word_count FROM groups g LEFT JOIN group_words gw ON gw.group_id=g.id GROUP BY g.id ORDER BY g.updated_at DESC,g.id DESC').fetchall():
            item=dict(row); item['tags']=json.loads(item['tags']); result.append(item)
    return result
@app.route('/api/groups/<int:gid>',methods=['PUT','DELETE'])
def group_detail(gid):
    with LOCK,conn() as c:
        if not c.execute('SELECT id FROM groups WHERE id=?',(gid,)).fetchone(): abort(404,description='分组不存在')
        if request.method=='DELETE': c.execute('DELETE FROM groups WHERE id=?',(gid,))
        else:
            data=body()
            if 'name' in data:
                name=str(data['name']).strip()
                if not name: raise ValueError('请输入分组名')
                c.execute('UPDATE groups SET name=? WHERE id=?',(name[:100],gid))
            if 'tags' in data: c.execute('UPDATE groups SET tags=? WHERE id=?',(json.dumps(clean_tags(data['tags']),ensure_ascii=False),gid))
            c.execute('UPDATE groups SET updated_at=? WHERE id=?',(now(),gid))
    return jsonify(ok=True)
@app.route('/api/groups/<int:gid>/words/<int:wid>',methods=['PUT','DELETE'])
def group_word(gid,wid):
    with LOCK,conn() as c:
        if not c.execute('SELECT id FROM groups WHERE id=?',(gid,)).fetchone() or not c.execute('SELECT id FROM words WHERE id=?',(wid,)).fetchone(): abort(404,description='分组或单词不存在')
        if request.method=='DELETE': c.execute('DELETE FROM group_words WHERE group_id=? AND word_id=?',(gid,wid))
        else: c.execute('INSERT INTO group_words VALUES (?,?,?,?) ON CONFLICT(group_id,word_id) DO UPDATE SET context_meaning=excluded.context_meaning',(gid,wid,str(body().get('context_meaning','')),now()))
        c.execute('UPDATE groups SET updated_at=? WHERE id=?',(now(),gid))
    return jsonify(ok=True)

def enqueue(kind,payload):
    job_id=uuid.uuid4().hex
    with conn() as c: c.execute('INSERT INTO jobs(id,kind,payload,created_at,updated_at) VALUES (?,?,?,?,?)',(job_id,kind,json.dumps(payload,ensure_ascii=False),now(),now()))
    return job_id
@app.post('/api/quick-entry')
def quick_entry():
    data=body(); entries=data.get('entries',[])
    if not isinstance(entries,list) or not 1<=len(entries)<=200: raise ValueError('每次可提交 1–200 个词条')
    for item in entries:
        item={'word':item} if isinstance(item,str) else item
        if not isinstance(item,dict) or not str(item.get('word','')).strip(): raise ValueError('每个词条都需要单词')
        gid=item.get('group_id',data.get('group_id'))
        with conn() as c:
            if gid and not c.execute('SELECT id FROM groups WHERE id=?',(int(gid),)).fetchone(): raise ValueError('分组不存在')
    ids=[]
    for item in entries:
        item={'word':item} if isinstance(item,str) else dict(item); item.setdefault('group_id',data.get('group_id')); ids.append(enqueue('quick',item))
    return jsonify(ok=True,job_ids=ids),202
@app.get('/api/jobs')
def jobs():
    with conn() as c:
        result=[]
        for row in c.execute('SELECT * FROM jobs ORDER BY created_at DESC,rowid DESC LIMIT 200').fetchall():
            item=dict(row); item['payload']=json.loads(item['payload']); item['result']=json.loads(item['result']) if item['result'] else None; result.append(item)
    return jsonify(result)
@app.post('/api/jobs/<jid>/retry')
def retry_job(jid):
    with conn() as c:
        cur=c.execute("UPDATE jobs SET status='pending',error='',updated_at=? WHERE id=? AND status='failed'",(now(),jid))
        if not cur.rowcount: raise ValueError('任务不存在或尚未失败')
    return jsonify(ok=True)

def worker(stop_event=None):
    while stop_event is None or not stop_event.is_set():
        job=None
        with LOCK,conn() as c:
            row=c.execute("SELECT * FROM jobs WHERE status='pending' ORDER BY created_at,rowid LIMIT 1").fetchone()
            if row:
                job=dict(row); c.execute("UPDATE jobs SET status='running',updated_at=? WHERE id=?",(now(),job['id']))
        if not job: time.sleep(.7); continue
        try:
            payload=json.loads(job['payload'])
            if job['kind']=='quiz_batch':
                with app.test_request_context('/'):
                    session['owner']=payload['owner']
                    with conn() as c: p=get_quiz(payload['session_id'],c)
                    for index in range(len(p['words'])):
                        with conn() as c:
                            if not c.execute('SELECT 1 FROM quiz_sessions WHERE id=?',(payload['session_id'],)).fetchone(): break
                        quiz_question(payload['session_id'],index)
                    result={'prepared':index+1 if p['words'] else 0}
            elif job['kind']=='classify': result=classify_word(int(payload['word_id']))
            else:
                looked=lookup_data(str(payload['word']),True)
                if not looked['found']: raise ValueError(looked.get('message','查词失败'))
                data=looked['data']; data.update({k:v for k,v in payload.items() if k in ('group_id','context_meaning')}); data['update_existing']=bool(payload.get('update_existing')); result=save_word_data(data)
                if result.get('exists'): raise ValueError('词库已有该词，请在录入面板确认更新，或在快速录入中勾选更新已有词')
            with conn() as c: c.execute("UPDATE jobs SET status='done',result=?,updated_at=? WHERE id=?",(json.dumps(result,ensure_ascii=False),now(),job['id']))
        except Exception as error:
            message=str(error) if isinstance(error,(ValueError,AIError)) else '处理失败，请重试'
            app.logger.warning('Job %s failed (%s)',job['id'],type(error).__name__)
            with conn() as c: c.execute("UPDATE jobs SET status='failed',error=?,updated_at=? WHERE id=?",(message,now(),job['id']))

def learned_today(c): return c.execute('SELECT COUNT(*) FROM learned_words WHERE learned_at LIKE ?',(date.today().isoformat()+'%',)).fetchone()[0]
@app.get('/api/stats/today')
def stats():
    with conn() as c:
        count=learned_today(c); reviewed=c.execute('SELECT COUNT(DISTINCT word_id) FROM review_logs WHERE reviewed_at LIKE ?',(date.today().isoformat()+'%',)).fetchone()[0]
        due=c.execute('SELECT COUNT(*) FROM words WHERE review_count>0 AND next_review_at<=?',(now(),)).fetchone()[0]
    quota=settings()['daily_quota']; return jsonify(today={'new_words_learned':count,'words_reviewed':reviewed},overview=db.get_word_stats(),due_count=due,remaining=max(0,quota-count),daily_quota=quota)
@app.get('/api/stats/overview')
def overview(): return jsonify(db.get_word_stats())
@app.get('/api/review/due')
def due(): return jsonify([w for w in list_words_data(group_id=request.args.get('group_id')) if w['review_count']>0 and w['next_review_at']<=now()])

def make_question(w,training='review',question_source='local'):
    mode=settings()['study_modes'].get((w.get('tags') or [''])[0],'full'); direction=settings()['review_mode']
    if training=='spelling': selected='spell_en'
    elif mode=='choice_only': selected='choice_cn2en' if direction=='cn2en' else 'choice_en2cn'
    elif mode=='meaning_only': selected='recall_en2cn'
    else:
        selected=None
        if direction=='en2cn': selected='choice_en2cn' if w['proficiency']<25 else 'recall_en2cn'
        if direction=='cn2en': selected='choice_cn2en' if w['proficiency']<25 else 'spell_en'
    # Context meaning must participate in ambiguity filtering, not replace the
    # answer after options have already been selected (or always occupy the last slot).
    source=dict(w)
    if w.get('context_meaning'):source['chinese_meaning']=w['context_meaning']
    word=Word.from_dict(source)
    warning=''
    if question_source=='ai' and training!='spelling' and mode!='meaning_only':
        ai_direction=direction if direction in ('en2cn','cn2en') else random.choice(['en2cn','cn2en'])
        try: return ai_quiz.generate(word,ai_direction)
        except AIError as error: warning='AI 出题未通过或请求失败，已使用本地题目：'+str(error)
    q=QuizService(db).generate_question(word,selected)
    q['generation_source']='local'
    if warning:q['generation_warning']=warning
    elif question_source=='ai':q['generation_warning']='当前为拼写或仅释义训练，使用本地题目'
    return q

@app.post('/api/quiz/sessions')
def quiz_create():
    data=body(); training=data.get('training_mode','review'); gid=data.get('group_id')
    if training not in ('new','review','spelling'): raise ValueError('无效的学习模式')
    question_source=data.get('question_source','local')
    if question_source not in ('local','ai'):raise ValueError('无效的出题方式')
    if question_source=='ai' and not config.resolve_ai('quiz')['key']:raise ValueError('请先在设置 → AI 服务中配置 API Key，或选择本地词典出题')
    if settings().get('auto_decay'):
        with LOCK,conn() as c:
            key=int(date.today().strftime('%Y%m%d'))
            c.execute('CREATE TABLE IF NOT EXISTS decay_days(day INTEGER PRIMARY KEY)')
            if not c.execute('SELECT 1 FROM decay_days WHERE day=?',(key,)).fetchone():
                c.execute('UPDATE words SET proficiency=MAX(0,proficiency-3) WHERE review_count>0 AND next_review_at<?',(date.today().isoformat(),))
                c.execute('INSERT INTO decay_days VALUES (?)',(key,))
    with LOCK,conn() as c:
        if gid and not c.execute('SELECT id FROM groups WHERE id=?',(int(gid),)).fetchone(): raise ValueError('分组不存在')
        c.execute('DELETE FROM quiz_sessions WHERE created_at<?',((datetime.now()-timedelta(days=30)).strftime('%Y-%m-%d %H:%M:%S'),))
        quota=max(0,settings()['daily_quota']-learned_today(c)); available=list_words_data(group_id=gid,sort='time_asc')
        if training=='new':
            learned={r[0] for r in c.execute('SELECT word_id FROM learned_words')}; available=[w for w in available if w['id'] not in learned][:quota]
            if not gid and len(available)<quota:
                for entry in WordBookService(db).pick_words_from_books(quota-len(available)):
                    match=c.execute('SELECT word_id FROM word_keys WHERE key=?',(norm(entry.word),)).fetchone()
                    if not match:
                        values=[getattr(entry,k,'wordbook' if k=='source' else '') for k in FIELDS]
                        values[-1]='wordbook'
                        wid=c.execute('INSERT INTO words ('+','.join(FIELDS)+',created_at,updated_at,next_review_at) VALUES ('+','.join('?' for _ in range(len(FIELDS)+3))+')',values+[now(),now(),now()]).lastrowid
                        c.execute('INSERT INTO word_keys VALUES (?,?)',(norm(entry.word),wid)); available.append(word_dict(wid,c))
                    c.execute('UPDATE word_book_entries SET imported=1 WHERE id=?',(entry.id,))
        elif training=='spelling': available=available[:min(200,max(1,int(data.get('count',50))))]
        else: available=[w for w in available if w['review_count']>0 and w['next_review_at']<=now()][:200]
        sid=uuid.uuid4().hex; payload={'words':available,'questions':[],'results':{},'group_id':gid,'training':training,'question_source':question_source}
        c.execute('INSERT INTO quiz_sessions VALUES (?,?,?,?)',(sid,owner(),json.dumps(payload,ensure_ascii=False),now()))
    if available: enqueue('quiz_batch',{'session_id':sid,'owner':owner()})
    return jsonify(session_id=sid,words=available,total=len(available),status='preparing',question_source=question_source,message='整套题目已加入后台队列，可先开始作答' if available else '今日配额已完成，或当前范围内没有可学习单词')

def get_quiz(sid,c):
    row=c.execute('SELECT * FROM quiz_sessions WHERE id=? AND owner=?',(sid,owner())).fetchone()
    if not row: abort(404,description='测验会话已失效，请重新开始')
    return json.loads(row['payload'])

def display_quiz_question(question):
    if (question.get('generation_source', 'local') == 'local'
            and question.get('mode') == 'choice_en2cn' and question.get('type') == 'choice'):
        options = [first_meaning(option) for option in question['options']]
        # Resumed sessions keep the original order and grading record.
        if all(options) and len(set(options)) == len(options):
            return {**question, 'options': options, 'answer': first_meaning(question['answer'])}
    return question
@app.route('/api/quiz/sessions/<sid>',methods=['GET','DELETE'])
def quiz_session(sid):
    with conn() as c:
        p=get_quiz(sid,c)
        if request.method=='DELETE': c.execute('DELETE FROM quiz_sessions WHERE id=?',(sid,))
    ready=sum(q is not None for q in p['questions'])
    return jsonify(ok=True,status='ready' if ready==len(p['words']) else 'preparing',total=len(p['words']),prepared=ready,
                   words=p['words'],results=p['results'],index=p.get('cursor',0),skipped=p.get('skipped',[]),
                   progress=[{'ready':i<len(p['questions']) and p['questions'][i] is not None,'answered':str(i) in p['results'],
                              'skipped':i in p.get('skipped',[]),'source':p['questions'][i].get('generation_source','local') if i<len(p['questions']) and p['questions'][i] else ''} for i in range(len(p['words']))],
                   training=p['training'],question_source=p.get('question_source','local'))

@app.get('/api/quiz/active')
def active_quiz():
    with conn() as c:
        row=c.execute('SELECT id FROM quiz_sessions WHERE owner=? ORDER BY created_at DESC,rowid DESC LIMIT 1',(owner(),)).fetchone()
    return jsonify(session_id=row['id'] if row else None)

@app.put('/api/quiz/sessions/<sid>/cursor')
def quiz_cursor(sid):
    data=body(); index=int(data.get('index',0))
    with LOCK,conn() as c:
        p=get_quiz(sid,c)
        if not 0<=index<=len(p['words']): raise ValueError('进度超出范围')
        p['cursor']=index
        if 'skipped' in data:
            values=data['skipped']
            if not isinstance(values,list) or any(type(i) is not int or not 0<=i<len(p['words']) for i in values): raise ValueError('跳过记录格式错误')
            p['skipped']=list(set(values))
        c.execute('UPDATE quiz_sessions SET payload=? WHERE id=?',(json.dumps(p,ensure_ascii=False),sid))
    return jsonify(ok=True)
@app.get('/api/quiz/sessions/<sid>/question/<int:index>')
def quiz_question(sid,index):
    # Serialize duplicate requests for this question, without holding the global
    # database lock during a slow AI/network call. Session deletion stays responsive.
    with LOCK:
        key=(sid,index)
        question_lock=QUESTION_LOCKS.get(key)
        if question_lock is None:
            question_lock=threading.Lock(); QUESTION_LOCKS[key]=question_lock
    with question_lock:
        with conn() as c:
            p=get_quiz(sid,c)
            if not 0<=index<len(p['words']):abort(404,description='题目不存在')
            if index<len(p['questions']) and p['questions'][index] is not None:
                return jsonify(display_quiz_question(p['questions'][index]))
        question=make_question(p['words'][index],p['training'],p.get('question_source','local'))
        with LOCK,conn() as c:
            p=get_quiz(sid,c)  # A deleted session must not be recreated by a late response.
            while len(p['questions'])<=index:p['questions'].append(None)
            p['questions'][index]=question
            c.execute('UPDATE quiz_sessions SET payload=? WHERE id=?',(json.dumps(p,ensure_ascii=False),sid))
    return jsonify(question)

def record_review(c,wid,rating,mode,gid=None):
    word=word_dict(wid,c); first=not c.execute('SELECT 1 FROM learned_words WHERE word_id=?',(wid,)).fetchone()
    if first and learned_today(c)>=settings()['daily_quota']: abort(409,description='今日新词配额已完成，请结束学习或复习已学单词')
    rs=ReviewService(db); prof=rs.calculate_new_proficiency(word['proficiency'],rating); stage=rs.calculate_new_stage(word['review_stage'],rating); next_time=rs.calculate_next_review(stage)
    if settings()['scheduling_mode']=='fsrs':
        try:
            from fsrs import Scheduler, Card, Rating
            row=c.execute('SELECT card FROM fsrs_cards WHERE word_id=?',(wid,)).fetchone()
            saved=json.loads(row[0]) if row else {}
            card=Card.from_dict(saved) if saved and saved.get('backend')!='ebbinghaus-fallback' else Card()
            scheduler=Scheduler(desired_retention=settings()['fsrs']['target_R']); card,_=scheduler.review_card(card, Rating.Again if rating<=2 else Rating.Hard if rating==3 else Rating.Good if rating==4 else Rating.Easy)
            next_time=card.due.astimezone().replace(tzinfo=None).strftime('%Y-%m-%d %H:%M:%S'); c.execute('INSERT INTO fsrs_cards VALUES (?,?) ON CONFLICT(word_id) DO UPDATE SET card=excluded.card',(wid,json.dumps(card.to_dict())))
        except ImportError:
            # FSRS 是可选依赖；未安装时保持艾宾浩斯结果，不阻断复习或离线同步。
            fallback_card={'version': 1, 'backend': 'ebbinghaus-fallback', 'rating': rating, 'due': next_time}
            c.execute('INSERT INTO fsrs_cards VALUES (?,?) ON CONFLICT(word_id) DO UPDATE SET card=excluded.card',(wid,json.dumps(fallback_card,ensure_ascii=False)))
    c.execute('UPDATE words SET proficiency=?,review_stage=?,review_count=review_count+1,last_reviewed_at=?,next_review_at=?,updated_at=? WHERE id=?',(prof,stage,now(),next_time,now(),wid))
    c.execute('INSERT INTO review_logs(word_id,reviewed_at,rating,review_mode,proficiency_before,proficiency_after,stage_before,stage_after) VALUES (?,?,?,?,?,?,?,?)',(wid,now(),rating,mode,word['proficiency'],prof,word['review_stage'],stage))
    c.execute('INSERT OR IGNORE INTO learned_words VALUES (?,?)',(wid,now()))
    if gid: c.execute('UPDATE groups SET learned_at=? WHERE id=?',(now(),gid))
    return word_dict(wid,c)
@app.post('/api/quiz/sessions/<sid>/judge')
def quiz_judge(sid):
    data=body(); index=int(data.get('index',-1))
    with LOCK,conn() as c:
        p=get_quiz(sid,c)
        if str(index) in p['results']: return jsonify(p['results'][str(index)])
        if not 0<=index<len(p['questions']) or not p['questions'][index]: raise ValueError('请先读取题目')
        q=p['questions'][index]
    answer = str(data.get('answer', ''))
    displayed = display_quiz_question(q)
    if displayed is not q and answer in q['options']:
        answer = displayed['options'][q['options'].index(answer)]
    correct,rating,feedback=QuizService(db).judge_answer(displayed,answer)
    with LOCK,conn() as c:
        p=get_quiz(sid,c)
        if str(index) in p['results']: return jsonify(p['results'][str(index)])
        updated=record_review(c,p['words'][index]['id'],rating,q['mode'],p.get('group_id')); result={'correct':correct,'rating':rating,'feedback':feedback,'proficiency':updated['proficiency']}; p['results'][str(index)]=result
        c.execute('UPDATE quiz_sessions SET payload=? WHERE id=?',(json.dumps(p,ensure_ascii=False),sid))
    return jsonify(result)
@app.post('/api/review/<int:wid>')
def review_word(wid):
    data=body()
    with LOCK,conn() as c: result=record_review(c,wid,max(1,min(5,int(data.get('rating',3)))),str(data.get('mode','mixed')))
    return jsonify(result)
@app.post('/api/session/end')
def session_end():
    from services.learning_service import LearningService
    return jsonify(LearningService(db).end_session().__dict__)
@app.post('/api/words/learn-new')
def learn_new():
    with conn() as c: remaining=max(0,settings()['daily_quota']-learned_today(c)); learned={r[0] for r in c.execute('SELECT word_id FROM learned_words')}
    return jsonify([w for w in list_words_data() if w['id'] not in learned][:min(remaining,int(body().get('count',10)))])

@app.get('/api/reports')
def reports(): return jsonify([{'date':r.date,'summary':r.summary[:100],'created_at':r.created_at} for r in db.get_all_reports(30)])
@app.get('/api/reports/<target_date>')
def report_detail(target_date):
    result=db.get_daily_report(target_date)
    if not result: abort(404,description='报告不存在')
    return jsonify(result.__dict__)
@app.post('/api/reports/generate')
def generate_report():
    target=(request.get_json(silent=True) or {}).get('date',date.today().isoformat()); stats=db.get_review_stats_for_date(target)
    result=complete('根据以下英语学习统计生成中文日报。返回 JSON 字符串字段 summary, weak_words, confused_words, suggestion, trend_analysis, full_report。没有证据的内容不要编造。数据：'+json.dumps(stats,ensure_ascii=False),scene='report')
    from models.daily_report import DailyReport
    report=DailyReport(date=target,**{k:str(result.get(k,'')) for k in ('summary','weak_words','confused_words','suggestion','trend_analysis','full_report')}); db.save_daily_report(report); return jsonify(report.__dict__)
@app.get('/api/wordbooks')
def wordbooks():
    result=[]
    for book in db.get_all_word_books():
        total,imported=db.get_book_entry_count(book.id); result.append({**book.__dict__,'total_words':total,'imported_count':imported})
    return jsonify(result)
@app.post('/api/wordbooks/import')
def import_wordbook():
    import tempfile
    file=request.files.get('file')
    if not file or not file.filename.lower().endswith('.csv'): raise ValueError('请选择 CSV 词书')
    fd,path=tempfile.mkstemp(suffix='.csv'); os.close(fd)
    try:
        name=request.form.get('name') or Path(file.filename).stem
        file.save(path); bid=WordBookService(db).import_from_csv(path,name); return jsonify(ok=bool(bid),book_id=bid,name=name)
    finally: os.unlink(path)
@app.delete('/api/wordbooks/<int:bid>')
def delete_wordbook(bid): return jsonify(ok=db.delete_word_book(bid))
@app.get('/api/words/export')
def export():
    with conn() as c: groups=[dict(r) for r in c.execute('SELECT * FROM groups')]; mappings=[dict(r) for r in c.execute('SELECT * FROM group_words')]
    response=jsonify(version=2,words=list_words_data(),groups=groups,group_words=mappings,exported_at=now()); response.headers['Content-Disposition']='attachment; filename=anamnesis-backup.json'; return response
@app.post('/api/words/import')
def import_backup():
    file=request.files.get('file')
    if not file: raise ValueError('请选择备份文件')
    data=json.load(file); entries=data if isinstance(data,list) else data.get('words',[])
    if not isinstance(entries,list) or len(entries)>100000: raise ValueError('备份词条格式错误')
    for item in entries:
        if not isinstance(item,dict) or not str(item.get('word','')).strip(): raise ValueError('备份含无效词条')
    import sqlite3
    backup=DATA/'backups'; backup.mkdir(exist_ok=True)
    with conn() as source,sqlite3.connect(backup/('before-import-'+uuid.uuid4().hex+'.db')) as target: source.backup(target)
    ids={}; added=updated=skipped=0
    for item in entries:
        record={k:v for k,v in item.items() if k in FIELDS+['tags']}; record['update_existing']=request.form.get('overwrite') in ('true','1'); result=save_word_data(record,enqueue_classification=False)
        if result.get('exists'): ids[item.get('id')]=result['existing']['id']; skipped+=1
        else: ids[item.get('id')]=result['id']; updated+=bool(result['updated']); added+=not result['updated']
    if isinstance(data,dict):
        group_ids={}
        with conn() as c:
            for group in data.get('groups',[]):
                gid=c.execute('INSERT INTO groups(name,tags,created_at,updated_at,learned_at) VALUES (?,?,?,?,?)',(str(group['name']),group.get('tags','[]') if isinstance(group.get('tags','[]'),str) else json.dumps(group['tags']),group.get('created_at',now()),now(),group.get('learned_at',''))).lastrowid; group_ids[group['id']]=gid
            for mapping in data.get('group_words',[]):
                if mapping.get('word_id') in ids and mapping.get('group_id') in group_ids: c.execute('INSERT OR IGNORE INTO group_words VALUES (?,?,?,?)',(group_ids[mapping['group_id']],ids[mapping['word_id']],mapping.get('context_meaning',''),now()))
    return jsonify(ok=True,added=added,updated=updated,skipped=skipped,imported=added+updated)

def run():
    local_dict.add_dictionary(config.get_local_dict_path()); local_dict.build_index_async()
    threading.Thread(target=worker,daemon=True,name='entry-worker').start()
    from waitress import serve
    proxy_options={}
    if os.environ.get('TRUSTED_PROXY','').strip():
        proxy_options={'trusted_proxy':os.environ['TRUSTED_PROXY'].strip(),'trusted_proxy_count':1,'trusted_proxy_headers':{'x-forwarded-for','x-forwarded-host','x-forwarded-proto','x-forwarded-port'}}
    serve(app,host=os.environ.get('HOST','127.0.0.1'),port=int(os.environ.get('PORT','5050')),threads=8,**proxy_options)

import integrations, sys
integrations.register(sys.modules[__name__])
import intake
intake.register(sys.modules[__name__])
import accounts
accounts.register(sys.modules[__name__])
import ai_profiles
ai_profiles.register(sys.modules[__name__])
import platform_features
platform_features.register(sys.modules[__name__])

# 迁移自旧版的义项、专项训练和可选语义检索能力。
from services.practice_service import PracticeService
from services.embedding_service import EmbeddingService

@app.get('/api/words/<int:wid>/meanings')
def meanings(wid): return jsonify(db.get_meanings_by_word_id(wid))

@app.post('/api/words/<int:wid>/meanings')
def add_meaning(wid):
    data=body(); text=str(data.get('meaning','')).strip()
    if not text or len(text)>5000: raise ValueError('义项不能为空且不能超过 5000 字')
    return jsonify(id=db.add_meaning(wid,text,**{k:data.get(k,'') for k in ('example_sentence','example_translation','part_of_speech')}))

@app.post('/api/meanings/<int:mid>/review')
def review_meaning(mid): return jsonify(db.update_meaning_review(mid,max(1,min(5,int(body().get('rating',3))))))

@app.post('/api/search/semantic')
def semantic_search():
    data=body(); query=str(data.get('query','')).strip()
    if not query: raise ValueError('请输入搜索内容')
    items=EmbeddingService(db).semantic_search(query,max(1,min(50,int(data.get('limit',10)))))
    return jsonify(results=[{'word':w.to_dict(),'similarity':round(score,4)} for w,score in items])

@app.post('/api/practice/reading-local')
def reading_local():
    text=str(body().get('text',''))
    if not text or len(text)>100000: raise ValueError('阅读文本需为 1–100000 字符')
    return jsonify(PracticeService(db).review_text(text))
