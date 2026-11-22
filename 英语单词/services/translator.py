"""
免费翻译服务 —— 使用 MyMemory API（无需 Key）
将英文释义翻译为中文
"""

import json
import urllib.request
import urllib.parse
import urllib.error
from typing import Optional


class TranslatorService:
    """免费在线翻译（MyMemory，不限量、无需 Key）"""

    API_URL = "https://api.mymemory.translated.net/get"

    @staticmethod
    def translate_en_to_zh(text: str) -> Optional[str]:
        """英文翻译为中文，成功返回译文，失败返回 None"""
        if not text or not text.strip():
            return None

        try:
            params = urllib.parse.urlencode({
                "q": text[:500],
                "langpair": "en|zh",
            })
            url = f"{TranslatorService.API_URL}?{params}"
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})

            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode())

            if data.get("responseStatus", 0) != 200:
                return None
            return data.get("responseData", {}).get("translatedText", "") or None

        except Exception as e:
            print(f"[Translator] 异常: {e}")
            return None

    @staticmethod
    def translate_meaning(english_meaning: str) -> str:
        """逐行翻译英文释义，保持换行结构"""
        if not english_meaning:
            return ""
        lines = [l.strip() for l in english_meaning.split("\n") if l.strip()]
        result = []
        for line in lines:
            zh = TranslatorService.translate_en_to_zh(line)
            result.append(zh if zh else line)
        return "\n".join(result)
