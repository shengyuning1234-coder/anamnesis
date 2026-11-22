"""Central identities and revocable sessions, separate from personal learning data."""
import hashlib
import hmac
import json
import secrets
import sqlite3
import threading
import time
import uuid
from contextlib import contextmanager
from flask import request, session, jsonify, redirect, g, abort
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.local import LocalProxy
import tenancy

def register(a):
    @contextmanager
    def central():
        c = sqlite3.connect(tenancy.ROOT / 'accounts.db', timeout=30)
        c.row_factory = sqlite3.Row
        try:
            with c: yield c
        finally: c.close()

    with central() as c:
        c.executescript('''
        CREATE TABLE IF NOT EXISTS users(id TEXT PRIMARY KEY, username TEXT UNIQUE NOT NULL,
          password TEXT NOT NULL, role TEXT NOT NULL, active INTEGER NOT NULL DEFAULT 1,
          allowance INTEGER NOT NULL DEFAULT 100, webui_email TEXT UNIQUE, created_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS devices(id TEXT PRIMARY KEY, user_id TEXT NOT NULL,
          expires REAL NOT NULL, ip TEXT, ua TEXT, created_at TEXT, seen_at TEXT);
        CREATE TABLE IF NOT EXISTS ai_usage(user_id TEXT, day TEXT, calls INTEGER NOT NULL DEFAULT 0,
          own_calls INTEGER NOT NULL DEFAULT 0, PRIMARY KEY(user_id,day));
        CREATE TABLE IF NOT EXISTS preferences(key TEXT PRIMARY KEY,value TEXT NOT NULL);
        ''')
        c.execute('INSERT OR IGNORE INTO users(id,username,password,role,created_at) VALUES (?,?,?,?,?)',
                  ('admin','admin',a.settings().get('password_hash',''),'admin',a.now()))
        c.execute("UPDATE users SET webui_email='words-'||id||'@anamnesis.local' WHERE webui_email IS NULL")
    # Before multi-user support every session in this database belonged to the
    # sole legacy account, even though its browser owner was randomly generated.
    with a.conn() as c: c.execute("UPDATE quiz_sessions SET owner='admin' WHERE owner!='admin'")

    original_db = a.db
    databases = {'admin': original_db}
    workers = set()
    workers_enabled = False
    raw_worker = a.worker
    raw_token = a.MCP_TOKEN

    def personal_db():
        uid = tenancy.profile.get()
        with a.LOCK:
            if uid not in databases:
                databases[uid] = a.Database(tenancy.path('words.db'))
                a.migrate()
        return databases[uid]

    a.DATA = LocalProxy(tenancy.directory)
    a.db = LocalProxy(personal_db)

    def user(uid):
        with central() as c: return c.execute('SELECT * FROM users WHERE id=? AND active=1',(uid,)).fetchone()

    def current():
        sid = session.get('device_id')
        if not sid: return None
        with central() as c:
            row = c.execute('SELECT u.* FROM devices d JOIN users u ON d.user_id=u.id WHERE d.id=? AND d.expires>? AND u.active=1',(sid,time.time())).fetchone()
            if row: c.execute('UPDATE devices SET seen_at=? WHERE id=?',(a.now(),sid))
        return row

    def api_token(uid):
        return raw_token if uid == 'admin' else hmac.new(raw_token.encode(),uid.encode(),'sha256').hexdigest()

    def token_user():
        raw = request.headers.get('Authorization','')
        if not raw.startswith('Bearer '): return None
        with central() as c:
            for row in c.execute('SELECT * FROM users WHERE active=1'):
                if hmac.compare_digest(raw[7:],api_token(row['id'])): return row
        return None

    a.authed = lambda: current() is not None
    a.is_token = lambda: token_user() is not None
    a.owner = lambda: tenancy.profile.get()

    def scoped_worker(uid,stop_event=None):
        token = tenancy.profile.set(uid)
        try:
            personal_db()
            raw_worker(stop_event)
        finally: tenancy.profile.reset(token)
    a.run_profile_jobs=scoped_worker

    def start_worker(uid):
        if not workers_enabled: return
        with a.LOCK:
            if uid in workers: return
            workers.add(uid)
            threading.Thread(target=scoped_worker,args=(uid,),daemon=True,name='jobs-'+uid).start()

    def start_workers():
        nonlocal workers_enabled
        workers_enabled = True
        with central() as c: ids = [r[0] for r in c.execute('SELECT id FROM users WHERE active=1')]
        for uid in ids: start_worker(uid)
    a.worker = start_workers

    def public_user(row):
        return {k:row[k] for k in ('id','username','role','allowance','webui_email','active','created_at')}

    def require_admin():
        row = current()
        if not row or row['role'] != 'admin': abort(403,description='仅管理员可执行此操作')
        return row

    def enter(row,remember=True):
        session.clear()
        sid = secrets.token_urlsafe(32)
        expires = time.time()+(180 if remember else 30)*86400
        with central() as c:
            c.execute('INSERT INTO devices VALUES (?,?,?,?,?,?,?)',(sid,row['id'],expires,request.remote_addr,request.user_agent.string[:1000],a.now(),a.now()))
        session.update(device_id=sid,owner=row['id'],authenticated=True,expires_at=expires)
        session.permanent=True
        tenancy.profile.set(row['id'])

    def password_valid(row,password):
        return a.verify_legacy_password(tenancy.ROOT,password) if row['password']=='legacy-nas-password' else bool(row['password']) and check_password_hash(row['password'],password)

    def gate():
        token = tenancy.profile.set('admin')
        g.profile_token = token
        if request.method not in ('GET','HEAD','OPTIONS'):
            origin = request.headers.get('Origin')
            if origin and origin.rstrip('/') != request.host_url.rstrip('/'): return jsonify(error='不允许跨站写入'),403
        if request.path.startswith('/static/') or request.path in ('/health','/login','/api/auth/status','/api/auth/login','/api/auth/setup','/api/auth/register','/api/internal/agent-token','/api/internal/integration-identity','/manifest.webmanifest','/service-worker.js','/app-icon.svg'): return
        agent = token_user()
        row = agent or current()
        if not row:
            if request.path.startswith('/api/') or request.path=='/mcp': return jsonify(error='请先登录',need_login=True),401
            return redirect(request.script_root+'/login')
        expected=request.headers.get('X-Account-ID')
        if expected and expected!=row['id']: return jsonify(error='账号已在其他页面切换，请刷新后继续',account_changed=True),409
        if agent and request.path.startswith(('/api/settings','/api/auth','/api/admin','/api/extension','/api/devices')): return jsonify(error='Agent Token 不能管理账号或系统配置'),403
        if request.path == '/mcp' and not agent: return jsonify(error='需要 Bearer Agent Token'),401
        tenancy.profile.set(row['id'])
        g.account = row
        personal_db()

    @a.app.after_request
    def account_header(response):
        row=getattr(g,'account',None)
        if row: response.headers['X-Account-ID']=row['id']
        return response

    handlers = a.app.before_request_funcs[None]
    handlers[handlers.index(a.security)] = gate

    @a.app.teardown_request
    def reset_profile(error):
        token = getattr(g,'profile_token',None)
        if token is not None: tenancy.profile.reset(token)

    def status():
        row = current()
        with central() as c:
            configured = bool(c.execute("SELECT password FROM users WHERE id='admin'").fetchone()[0])
            allow = c.execute("SELECT value FROM preferences WHERE key='registration'").fetchone()
        uid = row['id'] if row else ''
        return jsonify(password_set=configured,authenticated=bool(row),user=public_user(row) if row else None,
                       registration_open=bool(allow and allow[0]=='true'),owner_id=uid,
                       offline_cache_owner=hashlib.sha256((a.app.secret_key+uid).encode()).hexdigest()[:24] if uid else None)

    def setup():
        data = a.body()
        with a.LOCK, central() as c:
            row = c.execute("SELECT * FROM users WHERE id='admin'").fetchone()
            if row['password']: return jsonify(error='密码已设置，请登录'),409
            if not a.local_request() and a.os.environ.get('ALLOW_INITIAL_SETUP')!='1': abort(403,description='首次设置请在本机完成')
            password = str(data.get('password',''))
            if len(password)<8: raise ValueError('密码至少 8 位')
            c.execute("UPDATE users SET password=? WHERE id='admin'",(generate_password_hash(password),))
        a.save_settings({'password_hash':generate_password_hash(password)})
        enter(user('admin')); return jsonify(ok=True)

    def login():
        data=a.body(); key=request.remote_addr; cutoff=time.time()-300
        tries=[t for t in a.LOGIN_ATTEMPTS.get(key,[]) if t>cutoff]
        if len(tries)>=10: abort(429,description='尝试过于频繁，请五分钟后重试')
        with central() as c: row=c.execute('SELECT * FROM users WHERE username=? AND active=1',(str(data.get('username','admin')).strip(),)).fetchone()
        if not row or not password_valid(row,str(data.get('password',''))):
            a.LOGIN_ATTEMPTS[key]=tries+[time.time()]; return jsonify(error='账号或密码错误'),401
        a.LOGIN_ATTEMPTS.pop(key,None)
        if row['password']=='legacy-nas-password':
            with central() as c: c.execute('UPDATE users SET password=? WHERE id=?',(generate_password_hash(str(data['password'])),row['id']))
        enter(row,bool(data.get('remember',True))); return jsonify(ok=True)

    def logout():
        with central() as c: c.execute('DELETE FROM devices WHERE id=?',(session.get('device_id',''),))
        session.clear(); return jsonify(ok=True)

    def change_password():
        row=current(); data=a.body()
        if not row or not password_valid(row,str(data.get('old_password',''))): abort(403,description='原密码错误')
        password=str(data.get('new_password',''))
        if len(password)<8: raise ValueError('密码至少 8 位')
        with central() as c:
            c.execute('UPDATE users SET password=? WHERE id=?',(generate_password_hash(password),row['id']))
            c.execute('DELETE FROM devices WHERE user_id=?',(row['id'],))
        enter(user(row['id'])); return jsonify(ok=True)

    for name,view in [('auth_status',status),('setup',setup),('do_login',login),('logout',logout),('change_password',change_password)]: a.app.view_functions[name]=view

    def create_user(data):
        import re
        username=str(data.get('username','')).strip(); password=str(data.get('password',''))
        if not re.fullmatch(r'[A-Za-z0-9_.-]{3,40}',username): raise ValueError('账号需为 3–40 位字母、数字、点、下划线或短横线')
        if len(password)<8: raise ValueError('密码至少 8 位')
        uid=uuid.uuid4().hex
        with central() as c:
            default=c.execute("SELECT value FROM preferences WHERE key='default_allowance'").fetchone()
            allowance=int(default[0]) if default else 100
            try: c.execute('INSERT INTO users(id,username,password,role,allowance,webui_email,created_at) VALUES (?,?,?,?,?,?,?)',(uid,username,generate_password_hash(password),'user',allowance,'words-'+uid+'@anamnesis.local',a.now()))
            except sqlite3.IntegrityError: raise ValueError('账号已存在')
        token=tenancy.profile.set(uid)
        try: personal_db()
        finally: tenancy.profile.reset(token)
        start_worker(uid)
        return user(uid)

    @a.app.post('/api/auth/register')
    def registration():
        with central() as c: flag=c.execute("SELECT value FROM preferences WHERE key='registration'").fetchone()
        if not flag or flag[0]!='true': abort(403,description='暂未开放注册，请联系管理员')
        row=create_user(a.body()); enter(row); return jsonify(ok=True),201

    @a.app.route('/api/admin/users',methods=['GET','POST'])
    def users():
        require_admin()
        if request.method=='POST': return jsonify(user=public_user(create_user(a.body()))),201
        with central() as c: return jsonify([public_user(r) for r in c.execute('SELECT * FROM users ORDER BY created_at')])

    @a.app.route('/api/admin/users/<uid>',methods=['PUT','DELETE'])
    def manage_user(uid):
        require_admin()
        row=user(uid)
        if not row: abort(404,description='用户不存在')
        if uid=='admin' and request.method=='DELETE': raise ValueError('不能停用旧版管理员')
        data=a.body() if request.method=='PUT' else {}
        with central() as c:
            if request.method=='DELETE':
                c.execute('UPDATE users SET active=0 WHERE id=?',(uid,))
                c.execute('DELETE FROM devices WHERE user_id=?',(uid,))
            if 'password' in data:
                if len(str(data['password']))<8: raise ValueError('密码至少 8 位')
                c.execute('UPDATE users SET password=? WHERE id=?',(generate_password_hash(str(data['password'])),uid))
                c.execute('DELETE FROM devices WHERE user_id=?',(uid,))
            if 'allowance' in data:
                allowance=int(data['allowance'])
                if not 0<=allowance<=1000000: raise ValueError('AI 额度需为 0–1000000 次/日')
                c.execute('UPDATE users SET allowance=? WHERE id=?',(allowance,uid))
            if 'webui_email' in data:
                email=str(data['webui_email']).strip().lower()
                if not __import__('re').fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+',email): raise ValueError('请输入有效的 OpenWebUI 账号邮箱')
                try: c.execute('UPDATE users SET webui_email=? WHERE id=?',(email,uid))
                except sqlite3.IntegrityError: raise ValueError('该 OpenWebUI 账号已绑定其他用户')
        return jsonify(ok=True)

    @a.app.route('/api/admin/policy',methods=['GET','PUT'])
    def policy():
        require_admin()
        with central() as c:
            if request.method=='PUT':
                data=a.body()
                if 'registration' in data:
                    if type(data['registration']) is not bool: raise ValueError('注册开关需为布尔值')
                    c.execute('INSERT OR REPLACE INTO preferences VALUES (?,?)',('registration',json.dumps(data['registration'])))
                if 'default_allowance' in data:
                    value=int(data['default_allowance'])
                    if not 0<=value<=1000000: raise ValueError('默认额度范围为 0–1000000')
                    c.execute('INSERT OR REPLACE INTO preferences VALUES (?,?)',('default_allowance',str(value)))
            result={r[0]:json.loads(r[1]) for r in c.execute('SELECT * FROM preferences')}
        return jsonify(registration=result.get('registration',False),default_allowance=result.get('default_allowance',100))

    @a.app.get('/api/devices')
    def devices():
        row=current()
        with central() as c:
            items=[dict(r) for r in c.execute('SELECT id,ip,ua,created_at,seen_at,expires FROM devices WHERE user_id=? AND expires>? ORDER BY seen_at DESC',(row['id'],time.time()))]
        for item in items: item['current']=item['id']==session.get('device_id')
        return jsonify(items)

    @a.app.delete('/api/devices/<sid>')
    def revoke(sid):
        row=current()
        with central() as c: c.execute('DELETE FROM devices WHERE id=? AND user_id=?',(sid,row['id']))
        if sid==session.get('device_id'): session.clear()
        return jsonify(ok=True)

    def token_info():
        return jsonify(token=api_token(tenancy.profile.get()),server=request.host_url.rstrip('/')+request.script_root,mcp_url=request.host_url.rstrip('/')+request.script_root+'/mcp')
    a.app.view_functions['token_info']=token_info

    @a.app.get('/api/auth/bridge')
    def bridge():
        # Only the bundled gateway knows the secret; cookies alone cannot expose identities.
        secret=a.os.environ.get('GATEWAY_AUTH_SECRET','')
        if not secret or not hmac.compare_digest(request.headers.get('X-Gateway-Secret',''),secret): abort(403)
        row=current()
        if not row: abort(401)
        return jsonify(id=row['id'],email=row['webui_email'] or ('words-'+row['id']+'@anamnesis.local'),name=row['username'],role=row['role'])

    @a.app.get('/api/internal/integration-identity')
    def integration_identity():
        secret=a.os.environ.get('GATEWAY_AUTH_SECRET','')
        if not a.local_request() or not secret or not hmac.compare_digest(request.headers.get('X-Gateway-Secret',''),secret): abort(403)
        row=user('admin')
        if not row: abort(503)
        return jsonify(email=row['webui_email'],name=row['username'],role='admin')

    @a.app.post('/api/internal/agent-token')
    def internal_agent_token():
        secret=a.os.environ.get('GATEWAY_AUTH_SECRET','')
        if not a.local_request() or not secret or not hmac.compare_digest(request.headers.get('X-Gateway-Secret',''),secret): abort(403)
        email=str(a.body().get('email','')).strip().lower()
        with central() as c:
            row=next((r for r in c.execute('SELECT * FROM users WHERE active=1') if email==(r['webui_email'] or ('words-'+r['id']+'@anamnesis.local'))),None)
        if not row: abort(403,description='此对话账号没有绑定有效的平台用户')
        return jsonify(token=api_token(row['id']))

    def reserve_ai(own=False):
        uid=tenancy.profile.get(); row=user(uid)
        if not row: raise a.AIError('账号不可用')
        day=a.date.today().isoformat()
        with a.LOCK,central() as c:
            c.execute('INSERT OR IGNORE INTO ai_usage VALUES (?,?,0,0)',(uid,day))
            used=c.execute('SELECT calls FROM ai_usage WHERE user_id=? AND day=?',(uid,day)).fetchone()[0]
            if not own and row['role']!='admin' and used>=row['allowance']: raise a.AIError('今日平台 AI 额度已用完，可在设置中使用个人 API Key')
            c.execute('UPDATE ai_usage SET '+('own_calls' if own else 'calls')+'='+('own_calls' if own else 'calls')+'+1 WHERE user_id=? AND day=?',(uid,day))

    @a.app.get('/api/ai/usage')
    def usage():
        uid=tenancy.profile.get(); row=user(uid)
        with central() as c: used=c.execute('SELECT calls,own_calls FROM ai_usage WHERE user_id=? AND day=?',(uid,a.date.today().isoformat())).fetchone()
        return jsonify(platform_calls=used[0] if used else 0,own_calls=used[1] if used else 0,allowance=row['allowance'],unlimited=row['role']=='admin')
    a.config.reserve_ai=reserve_ai
