"""专项学习、阅读取词和写作反馈。"""
import re
from services.ai_client import complete, AIError

class PracticeService:
    def __init__(self, db): self.db = db

    def review_text(self, text: str) -> dict:
        tokens = list(dict.fromkeys(re.findall(r"[A-Za-z][A-Za-z'-]*", text.lower())))
        known, unknown = [], []
        for token in tokens:
            word = self.db.find_word_by_text(token)
            item = {'word': token, 'id': word.id if word else None, 'meaning': word.chinese_meaning if word else ''}
            (known if word else unknown).append(item)
        return {'tokens': len(tokens), 'known': known, 'unknown': unknown,
                'coverage': round(len(known) / len(tokens) * 100, 1) if tokens else 0}

    def writing_feedback(self, word: str, meaning: str, sentence: str) -> dict:
        if not sentence.strip(): raise ValueError('请输入句子')
        try:
            result = complete('检查目标词在句子中的使用。只返回 JSON：correct(布尔), feedback(中文建议), rewrite(英文改写)。目标词：%s；义项：%s；句子：%s' % (word, meaning, sentence))
            return {'ai': True, 'correct': bool(result.get('correct')), 'feedback': str(result.get('feedback', '')), 'rewrite': str(result.get('rewrite', sentence))}
        except (AIError, ValueError, TypeError):
            used = bool(re.search(r'(?<!\\w)' + re.escape(word) + r'(?!\\w)', sentence, re.I))
            return {'ai': False, 'correct': used, 'feedback': '已检查目标词是否出现；配置可用 AI 后可获得语法批改。', 'rewrite': sentence}

    def scenario(self, words, scene):
        names = [w.word if hasattr(w, 'word') else str(w) for w in words[:5]]
        return {'scene': scene, 'words': names, 'prompt': '场景：%s。请用以下词写 2—3 句英文：%s。' % (scene, ', '.join(names))}
