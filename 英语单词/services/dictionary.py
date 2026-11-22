"""
在线词典查询服务 —— 使用免费 Dictionary API（英文释义）
"""

import json
import urllib.request
import urllib.error
from typing import Optional
from models.word import Word
from config import DICT_API_URL


class DictionaryService:
    """在线词典查询（英英词典）"""

    @staticmethod
    def query(word: str) -> Optional[Word]:
        """
        在线查询单词释义（英文）
        成功返回 Word 对象，失败返回 None
        """
        try:
            url = DICT_API_URL.format(word=word.strip())
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode())

            if not data or not isinstance(data, list):
                return None

            entry = data[0]
            result = Word(word=word.strip())

            # ---- 音标 ----
            phonetics = entry.get("phonetics", [])
            if phonetics:
                result.phonetic = phonetics[0].get("text", "") or entry.get("phonetic", "")

            # ---- 收集所有词性 ----
            meanings = entry.get("meanings", [])
            all_parts = []
            meaning_lines = []
            example_lines = []

            for m in meanings:
                pos = m.get("partOfSpeech", "")
                if pos:
                    all_parts.append(pos)

                defs = m.get("definitions", [])
                for i, d in enumerate(defs):
                    definition = d.get("definition", "")
                    if definition:
                        prefix = f"  {i+1}. " if len(defs) > 1 else "  · "
                        meaning_lines.append(f"[{pos}] {prefix}{definition}")

                    # 尝试拿例句
                    example = d.get("example", "")
                    if example and example not in example_lines:
                        example_lines.append(example)

            result.part_of_speech = " / ".join(all_parts) if all_parts else ""
            result.chinese_meaning = "\n".join(meaning_lines) if meaning_lines else ""
            result.example_sentence = "\n".join(example_lines[:3]) if example_lines else ""  # 最多3个例句

            result.source = "online"
            return result

        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None
            print(f"[DictionaryService] HTTP {e.code}: {str(e)[:100]}")
            return None
        except urllib.error.URLError as e:
            print(f"[DictionaryService] 网络错误: {e.reason}")
            return None
        except Exception as e:
            print(f"[DictionaryService] 查询异常: {e}")
            return None
