"""
词书导入服务 —— CSV 词书解析与导入
"""

import csv
import os
from typing import List, Optional, Tuple
from models.wordbook import WordBook, WordBookEntry
from services.database import Database


class WordBookService:
    """词书导入与管理"""

    # CSV 列名映射（兼容多种格式）
    COLUMN_ALIASES = {
        "word": ["word", "单词", "英文", "english", "词汇"],
        "phonetic": ["phonetic", "音标", "phonetics", "pronunciation"],
        "part_of_speech": ["part_of_speech", "词性", "pos", "partofspeech", "词类"],
        "chinese_meaning": ["chinese_meaning", "中文释义", "释义", "meaning", "中文", "chinese"],
        "example_sentence": ["example_sentence", "例句", "example", "sentence"],
        "example_translation": ["example_translation", "例句翻译", "翻译", "translation"],
    }

    def __init__(self, db: Database):
        self.db = db

    # ==================== CSV 解析 ====================

    @classmethod
    def detect_encoding(cls, file_path: str) -> str:
        """检测 CSV 文件编码"""
        # 按优先级尝试常见编码
        for enc in ["utf-8", "utf-8-sig", "gbk", "gb2312", "latin-1"]:
            try:
                with open(file_path, "r", encoding=enc) as f:
                    f.read(1024)
                return enc
            except (UnicodeDecodeError, UnicodeError):
                continue
        return "utf-8"  # fallback

    @classmethod
    def parse_csv(cls, file_path: str) -> Tuple[Optional[List[str]], List[dict]]:
        """
        解析 CSV 词书文件
        返回 (列名列表, 词条字典列表)
        """
        encoding = cls.detect_encoding(file_path)
        rows = []

        with open(file_path, "r", encoding=encoding, errors="replace") as f:
            # 尝试嗅探分隔符
            sample = f.read(8192)
            f.seek(0)
            dialect = csv.Sniffer().sniff(sample, delimiters=",;\t|")

            reader = csv.DictReader(f, dialect=dialect)
            if reader.fieldnames is None:
                return None, []

            headers = [h.strip() for h in reader.fieldnames]
            mapped_headers = cls._map_headers(headers)

            for row in reader:
                entry = {}
                for original, mapped in mapped_headers.items():
                    value = row.get(original, "").strip()
                    # 用 | 分隔的例句/翻译转换为换行
                    if mapped in ("example_sentence", "example_translation") and "|" in value:
                        value = "\n".join(v.strip() for v in value.split("|") if v.strip())
                    entry[mapped] = value
                # 只保留有 word 的行
                if entry.get("word"):
                    rows.append(entry)

        field_names = ["word", "phonetic", "part_of_speech", "chinese_meaning",
                       "example_sentence", "example_translation"]
        return field_names, rows

    @classmethod
    def _map_headers(cls, headers: List[str]) -> dict:
        """将 CSV 列名映射到标准字段名"""
        mapping = {}
        for h in headers:
            h_lower = h.lower().strip()
            for standard, aliases in cls.COLUMN_ALIASES.items():
                if h_lower in aliases or h_lower.replace(" ", "_") in aliases:
                    mapping[h] = standard
                    break
            if h not in mapping:
                # 尝试模糊匹配
                for standard, aliases in cls.COLUMN_ALIASES.items():
                    for alias in aliases:
                        if alias in h_lower or h_lower in alias:
                            mapping[h] = standard
                            break
                    if h in mapping:
                        break
        return mapping

    # ==================== 导入 ====================

    def import_from_csv(self, file_path: str, book_name: str = None) -> Optional[int]:
        """
        从 CSV 导入词书
        返回词书 id，失败返回 None
        """
        if book_name is None:
            book_name = os.path.splitext(os.path.basename(file_path))[0]

        # 检查是否已导入过同名词书
        existing_id = self.db.get_book_id_by_name(book_name)
        if existing_id:
            print(f"[WordBook] 词书 '{book_name}' 已存在，跳过")
            return existing_id

        field_names, rows = self.parse_csv(file_path)
        if not rows:
            print(f"[WordBook] 文件无有效数据: {file_path}")
            return None

        # 创建词书
        book = WordBook(
            name=book_name,
            description=f"从 {os.path.basename(file_path)} 导入",
            total_words=len(rows),
            imported_count=0,
        )
        book_id = self.db.add_word_book(book)

        # 批量插入条目（分批，每批 500 条）
        entries = []
        for row in rows:
            entries.append(WordBookEntry(
                book_id=book_id,
                word=row.get("word", ""),
                phonetic=row.get("phonetic", ""),
                part_of_speech=row.get("part_of_speech", ""),
                chinese_meaning=row.get("chinese_meaning", ""),
                example_sentence=row.get("example_sentence", ""),
                example_translation=row.get("example_translation", ""),
                imported=0,
            ))
            if len(entries) >= 500:
                self.db.add_word_book_entries(entries)
                entries = []
        if entries:
            self.db.add_word_book_entries(entries)

        print(f"[WordBook] 导入完成: '{book_name}' ({len(rows)} 词)")
        return book_id

    # ==================== 从词书挑词 ====================

    def pick_words_from_books(self, count: int = 10) -> List[WordBookEntry]:
        """
        从所有词书中挑选未导入的单词
        优先从导入进度最高的词书选取（集中突破）
        """
        books = self.db.get_all_word_books()
        if not books:
            return []

        # 按未导入数量降序排列
        books_with_remaining = []
        for b in books:
            total, imported = self.db.get_book_entry_count(b.id)
            remaining = total - imported
            if remaining > 0:
                books_with_remaining.append((b.id, remaining))

        if not books_with_remaining:
            return []

        # 从剩余最多的词书开始取
        books_with_remaining.sort(key=lambda x: -x[1])
        result = []
        for book_id, _ in books_with_remaining:
            needed = count - len(result)
            if needed <= 0:
                break
            entries = self.db.get_unimported_entries(book_id, needed)
            result.extend(entries)

        return result[:count]


# 模块级单例
_wordbook_service: Optional[WordBookService] = None


def get_wordbook_service(db: Database = None) -> WordBookService:
    global _wordbook_service
    if _wordbook_service is None and db is not None:
        _wordbook_service = WordBookService(db)
    return _wordbook_service
