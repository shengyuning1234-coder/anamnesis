"""可选的 OpenAI 兼容 Embedding 搜索；无 API 时自动返回空结果。"""
import hashlib, json, math, urllib.request
from config import _load_apikey, _load_settings

def _embed(text):
    key = _load_apikey(); settings = _load_settings()
    if not key: return None
    try:
        req = urllib.request.Request(settings.get('api_base','').rstrip('/') + '/embeddings', data=json.dumps({'model': settings.get('embedding_model', 'text-embedding-3-small'), 'input': text[:1500]}).encode(), headers={'Content-Type':'application/json','Authorization':'Bearer '+key})
        with urllib.request.urlopen(req, timeout=20) as response: return response.read()
    except Exception: return None

def _vector(text):
    raw = _embed(text)
    if not raw: return None
    try: return json.loads(raw)['data'][0]['embedding']
    except (KeyError, IndexError, TypeError, ValueError): return None

def _cosine(a,b):
    dot=sum(x*y for x,y in zip(a,b)); na=math.sqrt(sum(x*x for x in a)); nb=math.sqrt(sum(x*x for x in b))
    return dot/(na*nb) if na and nb else 0

class EmbeddingService:
    def __init__(self, db): self.db=db
    def _text(self,w): return '%s - %s' % (w.word, w.chinese_meaning)
    def semantic_search(self, query, limit=10):
        q=_vector(query)
        if not q: return []
        result=[]
        for w in self.db.get_all_words():
            h=hashlib.sha256(self._text(w).encode()).hexdigest(); v=self.db.get_word_embedding(w.id,h)
            if v: result.append((w,_cosine(q,v)))
        return sorted(result,key=lambda x:x[1],reverse=True)[:limit]
    def get_or_compute_embedding(self,w):
        text=self._text(w); h=hashlib.sha256(text.encode()).hexdigest(); v=self.db.get_word_embedding(w.id,h)
        if v is None and (v:=_vector(text)): self.db.save_word_embedding(w.id,v,h)
        return v
