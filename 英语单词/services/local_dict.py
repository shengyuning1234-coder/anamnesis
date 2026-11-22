"""
本地 MDX 词典查询服务 —— 牛津英汉双解词典
启动时构建正向索引，查询返回结构化字段
"""

import os
import re
import threading
import difflib
import random
from functools import lru_cache
from typing import Optional, Dict, List
from bs4 import BeautifulSoup
from mdict_utils.reader import MDX


class LocalDictService:
    """本地词典服务（单例）"""

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._initialized = True
        self._mdx: Optional[MDX] = None
        self._forward: Dict[str, str] = {}
        self._all_keys: List[str] = []
        self._indexed = False
        self._indexing = False

    def add_dictionary(self, mdx_path: str) -> bool:
        if not os.path.isfile(mdx_path):
            print(f"[LocalDict] 文件不存在: {mdx_path}")
            return False
        try:
            self._mdx = MDX(mdx_path)
            print(f"[LocalDict] 已加载: {os.path.basename(mdx_path)}")
            return True
        except Exception as e:
            print(f"[LocalDict] 加载失败: {e}")
            return False

    def build_index(self):
        if self._indexed or self._indexing or not self._mdx:
            return
        self._indexing = True
        print("[LocalDict] 构建索引中...")
        t0 = __import__("time").time()
        count = 0
        for key, value in self._mdx.items():
            try:
                headword = key.decode("utf-8", errors="ignore").strip()
                html = value.decode("utf-8", errors="ignore")
                hw_lower = headword.lower()
                if hw_lower not in self._forward:
                    self._forward[hw_lower] = html
                    self._all_keys.append(headword)
                count += 1
            except Exception:
                continue
        self._indexed = True
        self._indexing = False
        elapsed = __import__("time").time() - t0
        print(f"[LocalDict] 索引完成 ({elapsed:.1f}s) - {len(self._forward)} 词条")

    def build_index_async(self):
        if self._indexed or self._indexing:
            return
        threading.Thread(target=self.build_index, daemon=True).start()

    # ==================== HTML 解析 ====================

    @staticmethod
    def _parse_entry(html: str) -> dict:
        """解析牛津词典 HTML，返回结构化字段"""
        soup = BeautifulSoup(html, "html.parser")
        result = {
            "phonetic": "",
            "part_of_speech": "",
            "chinese_meaning": "",
            "english_meaning": "",
            "examples": [],
            "collocations": "",
            "synonyms": "",
            "word_origin": "",
        }

        # 音标（英式）
        phon_el = soup.select_one(".phons_br .phon")
        if phon_el:
            result["phonetic"] = phon_el.get_text(strip=True)

        # 词性
        pos_el = soup.select_one(".pos")
        if pos_el:
            pos_text = pos_el.get_text(strip=True)
            # 去掉紧随的标签信息（如 formal）
            labels = soup.select_one(".webtop .labels")
            if labels:
                label_text = labels.get_text(" ", strip=True)
                pos_text += f" ({label_text})"
            result["part_of_speech"] = pos_text

        # 释义 —— 只取定义区的中文，不含例句翻译
        sense = soup.select_one("li.sense") or soup.select_one(".sense_single li")
        if sense:
            def_el = sense.select_one(".def")
            if def_el:
                result["english_meaning"] = def_el.get_text(strip=True)
            # 中文释义（只取 deft 下的 chn.simple，避免例句翻译混入）
            deft = sense.select_one("deft")
            if deft:
                chns = deft.select("chn.simple")
                if chns:
                    result["chinese_meaning"] = "；".join(
                        c.get_text(strip=True) for c in chns
                    )

        # Preserve all dictionary senses rather than silently taking only the first.
        definitions = []
        for deft in soup.select('deft'):
            text = '；'.join(c.get_text(strip=True) for c in deft.select('chn.simple'))
            if text and text not in definitions:
                definitions.append(text)
        if definitions:
            result['chinese_meaning'] = '\n'.join(definitions)

        # Retain source sense pairs; never pair independently numbered dictionaries.
        pairs=[];related=[]
        for sense in soup.select('li.sense'):
            definition=sense.select_one('.def')
            chinese=sense.select_one('deft')
            en=definition.get_text(' ',strip=True) if definition else ''
            zh='；'.join(c.get_text(strip=True) for c in chinese.select('chn.simple')) if chinese else ''
            pair={'chinese':zh,'english':en}
            phrase=sense.find_parent(class_='idm-g') or sense.find_parent(class_='pv-g')
            if phrase:
                heading=phrase.select_one('.idm, .pv')
                pair['phrase']=heading.get_text(' ',strip=True) if heading else '词典相关短语'
                if (en or zh) and pair not in related:related.append(pair)
            elif (en or zh) and pair not in pairs:pairs.append(pair)
        result['senses']=pairs
        result['related_senses']=related
        if pairs:
            result['chinese_meaning']='\n'.join(dict.fromkeys(p['chinese'] for p in pairs if p['chinese']))
            result['english_meaning']='\n'.join(dict.fromkeys(p['english'] for p in pairs if p['english']))
        elif related:
            result['chinese_meaning']=''
            result['english_meaning']=''
        positions=list(dict.fromkeys(p.get_text(' ',strip=True) for p in soup.select('.pos')))
        if positions:result['part_of_speech']=' / '.join(positions)

        # 例句 —— 单独解析，去重
        seen_examples = set()
        for li in soup.select("ul.examples li"):
            x_el = li.select_one(".x")
            xt_el = li.select_one("xt chn.simple")
            if x_el:
                # 获取英文例句（排除内嵌的 xt 标签内容）
                en_parts = []
                for child in x_el.children:
                    if hasattr(child, "name") and child.name == "xt":
                        continue
                    en_parts.append(child.get_text(strip=True) if hasattr(child, "get_text") else str(child).strip())
                en = " ".join(p for p in en_parts if p).strip()
                xt_text = xt_el.get_text(strip=True) if xt_el else ""
                if en and en not in seen_examples:
                    seen_examples.add(en)
                    result["examples"].append((en, xt_text))

        # 搭配
        colloc_div = soup.select_one(".unbox[unbox='snippet'] .body")
        if colloc_div:
            parts = []
            for span in colloc_div.select("span.unbox"):
                label = span.get_text(strip=True)
                ul = span.find_next_sibling("ul")
                if ul:
                    items = [li.get_text(strip=True) for li in ul.select("li")]
                    parts.append(f"{label}: {', '.join(items)}")
            result["collocations"] = "; ".join(parts)

        # 近义词
        xrefs = soup.select_one(".xrefs")
        if xrefs:
            links = [a.get_text(strip=True) for a in xrefs.select("a.Ref")]
            result["synonyms"] = ", ".join(links) if links else ""

        # 词源
        origin_div = soup.select_one(".unbox[unbox='wordorigin'] .body")
        if origin_div:
            result["word_origin"] = origin_div.get_text(" ", strip=True)[:200]

        return result

    # ==================== 查询 ====================

    def query(self, word: str) -> Optional[dict]:
        """查询单词，返回结构化字段，失败返回 None"""
        if not self._indexed:
            return None
        word_lower = word.strip().lower()
        html = self._forward.get(word_lower)
        if not html:
            return None
        seen = set()
        while html.strip().startswith('@@@LINK='):
            target = html.strip()[8:].strip('\x00\r\n ').lower()
            if target in seen or len(seen)>=8: return None
            seen.add(target); html = self._forward.get(target)
            if not html: return None
        return self._parse_entry(html)

    def suggest_similar(self, word: str, limit: int = 5) -> List[str]:
        """拼写纠错：找相似词条"""
        if not self._indexed:
            return []
        word_lower = word.strip().lower()
        if word_lower and len(word_lower) > 1:
            prefix = word_lower[0]
            candidates = [k for k in self._all_keys if k.lower().startswith(prefix)]
        else:
            candidates = self._all_keys
        matches = difflib.get_close_matches(word, candidates, n=limit, cutoff=0.7)
        if not matches:
            matches = difflib.get_close_matches(
                word_lower, [k.lower() for k in candidates], n=limit, cutoff=0.7
            )
        return matches[:limit]

    def distractors(self, word: str, count: int = 3, meaning: str = '', pos: str = ''):
        """Offline bilingual candidates with family/synonym/ambiguity exclusions."""
        from services.distractors import choose
        return choose(word, meaning, pos, count)

    @property
    def ready(self) -> bool:
        return self._indexed


local_dict = LocalDictService()
