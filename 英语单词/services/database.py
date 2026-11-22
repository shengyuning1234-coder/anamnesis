"""
SQLite 数据库存储层 —— 单词 + 学习系统的增删改查
"""

import sqlite3
import os
import json
from datetime import datetime, date
from typing import List, Optional, Tuple
from models.word import Word
from models.review_log import ReviewLog
from models.daily_stats import DailyStats
from models.daily_report import DailyReport
from models.wordbook import WordBook, WordBookEntry
from config import DB_PATH


class ClosingConnection(sqlite3.Connection):
    def __exit__(self, *args):
        try: return super().__exit__(*args)
        finally: self.close()


class Database:
    def __init__(self, db_path: str = None):
        self.db_path = db_path or DB_PATH
        self._ensure_dir()
        self._create_all_tables()
        self._migrate()

    def _ensure_dir(self):
        """确保数据库文件所在目录存在"""
        dir_name = os.path.dirname(self.db_path)
        if dir_name and not os.path.exists(dir_name):
            os.makedirs(dir_name)

    def _get_conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=30, factory=ClosingConnection)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    # ============================================================
    #  建表 & 迁移
    # ============================================================

    def _create_all_tables(self):
        """创建所有表"""
        with self._get_conn() as conn:
            # 单词主表
            conn.execute("""
                CREATE TABLE IF NOT EXISTS words (
                    id               INTEGER PRIMARY KEY AUTOINCREMENT,
                    word             TEXT NOT NULL,
                    phonetic         TEXT DEFAULT '',
                    part_of_speech   TEXT DEFAULT '',
                    chinese_meaning  TEXT DEFAULT '',
                    example_sentence TEXT DEFAULT '',
                    example_translation TEXT DEFAULT '',
                    notes            TEXT DEFAULT '',
                    source           TEXT DEFAULT 'manual',
                    proficiency      INTEGER DEFAULT 0,
                    review_count     INTEGER DEFAULT 0,
                    review_stage     INTEGER DEFAULT 0,
                    last_reviewed_at TEXT DEFAULT '',
                    next_review_at   TEXT DEFAULT '',
                    created_at       TEXT DEFAULT '',
                    updated_at       TEXT DEFAULT ''
                )
            """)
            # 复习日志
            conn.execute("""
                CREATE TABLE IF NOT EXISTS review_logs (
                    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
                    word_id            INTEGER NOT NULL,
                    reviewed_at        TEXT DEFAULT '',
                    rating             INTEGER DEFAULT 0,
                    review_mode        TEXT DEFAULT 'en2cn',
                    proficiency_before INTEGER DEFAULT 0,
                    proficiency_after  INTEGER DEFAULT 0,
                    stage_before       INTEGER DEFAULT 0,
                    stage_after        INTEGER DEFAULT 0,
                    FOREIGN KEY (word_id) REFERENCES words(id) ON DELETE CASCADE
                )
            """)
            # 每日统计
            conn.execute("""
                CREATE TABLE IF NOT EXISTS daily_stats (
                    id                    INTEGER PRIMARY KEY AUTOINCREMENT,
                    date                  TEXT UNIQUE NOT NULL,
                    new_words_learned     INTEGER DEFAULT 0,
                    words_reviewed        INTEGER DEFAULT 0,
                    total_reviews         INTEGER DEFAULT 0,
                    ratings_1             INTEGER DEFAULT 0,
                    ratings_2             INTEGER DEFAULT 0,
                    ratings_3             INTEGER DEFAULT 0,
                    ratings_4             INTEGER DEFAULT 0,
                    ratings_5             INTEGER DEFAULT 0,
                    avg_rating            REAL DEFAULT 0,
                    avg_proficiency_before REAL DEFAULT 0,
                    avg_proficiency_after  REAL DEFAULT 0,
                    study_duration_min    INTEGER DEFAULT 0,
                    words_from_book       INTEGER DEFAULT 0,
                    report_generated      INTEGER DEFAULT 0
                )
            """)
            # AI 每日报告
            conn.execute("""
                CREATE TABLE IF NOT EXISTS daily_reports (
                    id              INTEGER PRIMARY KEY AUTOINCREMENT,
                    date            TEXT UNIQUE NOT NULL,
                    summary         TEXT DEFAULT '',
                    weak_words      TEXT DEFAULT '',
                    confused_words  TEXT DEFAULT '',
                    suggestion      TEXT DEFAULT '',
                    trend_analysis  TEXT DEFAULT '',
                    full_report     TEXT DEFAULT '',
                    created_at      TEXT DEFAULT ''
                )
            """)
            # 词书
            conn.execute("""
                CREATE TABLE IF NOT EXISTS word_books (
                    id             INTEGER PRIMARY KEY AUTOINCREMENT,
                    name           TEXT NOT NULL,
                    description    TEXT DEFAULT '',
                    total_words    INTEGER DEFAULT 0,
                    imported_count INTEGER DEFAULT 0,
                    created_at     TEXT DEFAULT ''
                )
            """)
            # 词书条目
            conn.execute("""
                CREATE TABLE IF NOT EXISTS word_book_entries (
                    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
                    book_id             INTEGER NOT NULL,
                    word                TEXT NOT NULL,
                    phonetic            TEXT DEFAULT '',
                    part_of_speech      TEXT DEFAULT '',
                    chinese_meaning     TEXT DEFAULT '',
                    example_sentence    TEXT DEFAULT '',
                    example_translation TEXT DEFAULT '',
                    imported            INTEGER DEFAULT 0,
                    FOREIGN KEY (book_id) REFERENCES word_books(id) ON DELETE CASCADE
                )
            """)
            # 压缩摘要快照（每日一行精简 JSON）
            conn.execute("""
                CREATE TABLE IF NOT EXISTS compressed_snapshots (
                    date       TEXT PRIMARY KEY,
                    snapshot   TEXT DEFAULT '',
                    compressed INTEGER DEFAULT 0
                )
            """)
            # 滚动压缩摘要（旧数据聚合文本）
            conn.execute("""
                CREATE TABLE IF NOT EXISTS compressed_summaries (
                    id         INTEGER PRIMARY KEY AUTOINCREMENT,
                    summary    TEXT DEFAULT '',
                    created_at TEXT DEFAULT ''
                )
            """)
            conn.execute("""CREATE TABLE IF NOT EXISTS word_meanings (
                id INTEGER PRIMARY KEY AUTOINCREMENT, word_id INTEGER NOT NULL,
                meaning TEXT NOT NULL DEFAULT '', example_sentence TEXT DEFAULT '',
                example_translation TEXT DEFAULT '', part_of_speech TEXT DEFAULT '',
                meaning_order INTEGER DEFAULT 0, unlocked INTEGER DEFAULT 0,
                proficiency INTEGER DEFAULT 0, review_count INTEGER DEFAULT 0,
                review_stage INTEGER DEFAULT 0, last_reviewed_at TEXT DEFAULT '',
                next_review_at TEXT DEFAULT '', created_at TEXT DEFAULT '', updated_at TEXT DEFAULT '',
                FOREIGN KEY(word_id) REFERENCES words(id) ON DELETE CASCADE)
            """)
            conn.execute("""CREATE TABLE IF NOT EXISTS word_confusions (
                id INTEGER PRIMARY KEY AUTOINCREMENT, word_id INTEGER NOT NULL,
                confused_with_id INTEGER NOT NULL, confused_word TEXT DEFAULT '',
                trigger_count INTEGER DEFAULT 1, last_triggered_at TEXT DEFAULT '',
                UNIQUE(word_id, confused_with_id),
                FOREIGN KEY(word_id) REFERENCES words(id) ON DELETE CASCADE,
                FOREIGN KEY(confused_with_id) REFERENCES words(id) ON DELETE CASCADE)
            """)
            conn.execute("""CREATE TABLE IF NOT EXISTS word_embeddings (
                word_id INTEGER PRIMARY KEY, vector TEXT NOT NULL, input_hash TEXT DEFAULT '',
                updated_at TEXT DEFAULT '', FOREIGN KEY(word_id) REFERENCES words(id) ON DELETE CASCADE)
            """)
            conn.commit()

    def _migrate(self):
        """兼容旧数据库：为 words 表添加缺失列"""
        migrations = [
            ("proficiency", "INTEGER DEFAULT 0"),
            ("review_count", "INTEGER DEFAULT 0"),
            ("review_stage", "INTEGER DEFAULT 0"),
            ("last_reviewed_at", "TEXT DEFAULT ''"),
            ("next_review_at", "TEXT DEFAULT ''"),
            ("notes", "TEXT DEFAULT ''"),
        ]
        with self._get_conn() as conn:
            for col, col_def in migrations:
                try:
                    conn.execute(f"ALTER TABLE words ADD COLUMN {col} {col_def}")
                except sqlite3.OperationalError:
                    pass
            conn.commit()

    def _execute(self, sql: str, params=()):
        """兼容服务层的短查询接口；调用方负责关闭连接时使用。"""
        conn = self._get_conn()
        return conn.execute(sql, params)

    def find_word_by_text(self, word: str):
        return self.get_word_by_id(self._find_word_id(word)) if self._find_word_id(word) else None

    def _find_word_id(self, word: str):
        with self._get_conn() as conn:
            row = conn.execute("SELECT id FROM words WHERE LOWER(word)=LOWER(?) LIMIT 1", (word.strip(),)).fetchone()
            return row["id"] if row else None

    def record_confusion(self, word_id: int, confused_with_id: int, confused_word: str = ""):
        with self._get_conn() as conn:
            conn.execute("""INSERT INTO word_confusions(word_id,confused_with_id,confused_word,trigger_count,last_triggered_at)
                VALUES (?,?,?,?,?) ON CONFLICT(word_id,confused_with_id) DO UPDATE SET
                trigger_count=trigger_count+1, confused_word=excluded.confused_word, last_triggered_at=excluded.last_triggered_at""",
                (word_id, confused_with_id, confused_word, 1, datetime.now().strftime('%Y-%m-%d %H:%M:%S')))

    def get_word_embedding(self, word_id: int, input_hash: str = ""):
        with self._get_conn() as conn:
            row = conn.execute("SELECT vector,input_hash FROM word_embeddings WHERE word_id=?", (word_id,)).fetchone()
            if not row or (input_hash and row["input_hash"] != input_hash): return None
            return json.loads(row["vector"])

    def save_word_embedding(self, word_id: int, vector, input_hash: str = ""):
        with self._get_conn() as conn:
            conn.execute("INSERT INTO word_embeddings(word_id,vector,input_hash,updated_at) VALUES (?,?,?,?) ON CONFLICT(word_id) DO UPDATE SET vector=excluded.vector,input_hash=excluded.input_hash,updated_at=excluded.updated_at",
                         (word_id, json.dumps(vector), input_hash, datetime.now().strftime('%Y-%m-%d %H:%M:%S')))

    def get_ordered_meaning_texts(self, word_id: int, fallback: str = ""):
        with self._get_conn() as conn:
            rows = conn.execute("SELECT meaning FROM word_meanings WHERE word_id=? ORDER BY meaning_order,id", (word_id,)).fetchall()
            return [r["meaning"] for r in rows] or [fallback]

    def get_meanings_by_word_id(self, word_id: int):
        with self._get_conn() as conn:
            return [dict(r) for r in conn.execute("SELECT * FROM word_meanings WHERE word_id=? ORDER BY meaning_order,id", (word_id,)).fetchall()]

    def add_meaning(self, word_id: int, meaning: str, **fields):
        with self._get_conn() as conn:
            order = conn.execute("SELECT COALESCE(MAX(meaning_order),-1)+1 FROM word_meanings WHERE word_id=?", (word_id,)).fetchone()[0]
            stamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            columns = {r[1] for r in conn.execute('PRAGMA table_info(word_meanings)')}
            if 'meaning_index' in columns:
                # Preserve the legacy unique (word_id,meaning_index) index.
                index = conn.execute('SELECT COALESCE(MAX(meaning_index),0)+1 FROM word_meanings WHERE word_id=?',(word_id,)).fetchone()[0]
                return conn.execute('INSERT INTO word_meanings(word_id,meaning_index,chinese_meaning,meaning,meaning_order,example_sentence,example_translation,part_of_speech,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?,?,?)',
                                    (word_id,index,meaning.strip(),meaning.strip(),order,fields.get('example_sentence',''),fields.get('example_translation',''),fields.get('part_of_speech',''),stamp,stamp)).lastrowid
            cur = conn.execute("INSERT INTO word_meanings(word_id,meaning,example_sentence,example_translation,part_of_speech,meaning_order,unlocked,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?,?)",
                               (word_id, meaning.strip(), fields.get('example_sentence',''), fields.get('example_translation',''), fields.get('part_of_speech',''), order, int(fields.get('unlocked', 0)), stamp, stamp))
            return cur.lastrowid

    def update_meaning_review(self, meaning_id: int, rating: int):
        with self._get_conn() as conn:
            row = conn.execute("SELECT proficiency,review_stage FROM word_meanings WHERE id=?", (meaning_id,)).fetchone()
            if not row: raise ValueError('义项不存在')
            prof=max(0,min(100,row['proficiency']+{1:-15,2:-5,3:5,4:12,5:20}.get(rating,0)))
            stage=max(0,min(7,row['review_stage']+{1:-3,2:-1,3:0,4:1,5:2}.get(rating,0)))
            stamp=datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            conn.execute("UPDATE word_meanings SET unlocked=1,proficiency=?,review_stage=?,review_count=review_count+1,last_reviewed_at=?,updated_at=? WHERE id=?", (prof,stage,stamp,stamp,meaning_id))
            return dict(conn.execute("SELECT * FROM word_meanings WHERE id=?", (meaning_id,)).fetchone())

    # ============================================================
    #  单词 CRUD（含学习字段）
    # ============================================================

    def add_word(self, word: Word) -> int:
        """添加单词，返回新记录的 id"""
        with self._get_conn() as conn:
            cursor = conn.execute("""
                INSERT INTO words (word, phonetic, part_of_speech, chinese_meaning,
                                   example_sentence, example_translation, notes, source,
                                   proficiency, review_count, review_stage,
                                   last_reviewed_at, next_review_at,
                                   created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                word.word, word.phonetic, word.part_of_speech,
                word.chinese_meaning, word.example_sentence,
                word.example_translation, word.notes, word.source,
                word.proficiency, word.review_count, word.review_stage,
                word.last_reviewed_at, word.next_review_at,
                word.created_at, word.updated_at,
            ))
            conn.commit()
            return cursor.lastrowid

    def delete_word(self, word_id: int) -> bool:
        """根据 id 删除单词（级联删除复习日志）"""
        with self._get_conn() as conn:
            cursor = conn.execute("DELETE FROM words WHERE id = ?", (word_id,))
            conn.commit()
            return cursor.rowcount > 0

    def update_word(self, word: Word) -> bool:
        """更新单词（含学习字段）"""
        with self._get_conn() as conn:
            cursor = conn.execute("""
                UPDATE words
                SET word=?, phonetic=?, part_of_speech=?, chinese_meaning=?,
                    example_sentence=?, example_translation=?, notes=?,
                    source=?, proficiency=?, review_count=?, review_stage=?,
                    last_reviewed_at=?, next_review_at=?, updated_at=?
                WHERE id=?
            """, (
                word.word, word.phonetic, word.part_of_speech,
                word.chinese_meaning, word.example_sentence,
                word.example_translation, word.notes, word.source,
                word.proficiency, word.review_count, word.review_stage,
                word.last_reviewed_at, word.next_review_at, word.updated_at,
                word.id,
            ))
            conn.commit()
            return cursor.rowcount > 0

    def get_word_by_id(self, word_id: int) -> Optional[Word]:
        """根据 id 查询单词"""
        with self._get_conn() as conn:
            row = conn.execute("SELECT * FROM words WHERE id = ?", (word_id,)).fetchone()
            return Word.from_dict(dict(row)) if row else None

    def search_words(self, keyword: str = "") -> List[Word]:
        """搜索单词（按英文或中文模糊匹配）"""
        with self._get_conn() as conn:
            if keyword:
                like = f"%{keyword}%"
                rows = conn.execute(
                    "SELECT * FROM words WHERE word LIKE ? OR chinese_meaning LIKE ? ORDER BY updated_at DESC",
                    (like, like)
                ).fetchall()
            else:
                rows = conn.execute("SELECT * FROM words ORDER BY updated_at DESC").fetchall()
            return [Word.from_dict(dict(r)) for r in rows]

    def get_all_words(self) -> List[Word]:
        return self.search_words()

    def word_exists(self, word: str) -> bool:
        with self._get_conn() as conn:
            row = conn.execute(
                "SELECT id FROM words WHERE LOWER(word) = LOWER(?)", (word,)
            ).fetchone()
            return row is not None

    def get_total_count(self) -> int:
        with self._get_conn() as conn:
            row = conn.execute("SELECT COUNT(*) as cnt FROM words").fetchone()
            return row["cnt"] if row else 0

    # ============================================================
    #  学习系统专用查询
    # ============================================================

    def get_words_due_for_review(self, before_date: str = None, limit: int = 200) -> List[Word]:
        """获取到期待复习的单词（从未复习的 + next_review_at <= 现在），最多 limit 条"""
        if before_date is None:
            before_date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with self._get_conn() as conn:
            rows = conn.execute(
                """SELECT * FROM words
                   WHERE review_count = 0
                      OR next_review_at = ''
                      OR next_review_at <= ?
                   ORDER BY review_count ASC, next_review_at ASC
                   LIMIT ?""",
                (before_date, limit)
            ).fetchall()
            return [Word.from_dict(dict(r)) for r in rows]

    def get_low_proficiency_words(self, threshold: int = 30, limit: int = 20) -> List[Word]:
        """获取低熟练度单词"""
        with self._get_conn() as conn:
            rows = conn.execute(
                "SELECT * FROM words WHERE proficiency < ? ORDER BY proficiency ASC LIMIT ?",
                (threshold, limit)
            ).fetchall()
            return [Word.from_dict(dict(r)) for r in rows]

    def get_new_words_today(self, today: str = None) -> int:
        """首次完成学习的词数；录入单词不消耗学习配额。"""
        if today is None:
            today = date.today().isoformat()
        with self._get_conn() as conn:
            if conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='learned_words'").fetchone():
                return conn.execute('SELECT COUNT(*) FROM learned_words WHERE learned_at LIKE ?',(f'{today}%',)).fetchone()[0]
            row = conn.execute(
                "SELECT COUNT(*) as cnt FROM (SELECT word_id, MIN(reviewed_at) AS first_review FROM review_logs GROUP BY word_id) WHERE first_review LIKE ?",
                (f"{today}%",)
            ).fetchone()
            return row["cnt"] if row else 0

    def get_words_never_reviewed(self, limit: int = 20) -> List[Word]:
        """获取从未复习过的单词"""
        with self._get_conn() as conn:
            rows = conn.execute(
                "SELECT * FROM words WHERE review_count = 0 ORDER BY created_at ASC LIMIT ?",
                (limit,)
            ).fetchall()
            return [Word.from_dict(dict(r)) for r in rows]

    def get_review_count_today(self, today: str = None) -> int:
        """今日复习单词数（去重）"""
        if today is None:
            today = date.today().isoformat()
        with self._get_conn() as conn:
            row = conn.execute(
                "SELECT COUNT(DISTINCT word_id) as cnt FROM review_logs WHERE reviewed_at LIKE ?",
                (f"{today}%",)
            ).fetchone()
            return row["cnt"] if row else 0

    # ============================================================
    #  复习日志 CRUD
    # ============================================================

    def add_review_log(self, log: ReviewLog) -> int:
        with self._get_conn() as conn:
            cursor = conn.execute("""
                INSERT INTO review_logs (word_id, reviewed_at, rating, review_mode,
                                         proficiency_before, proficiency_after,
                                         stage_before, stage_after)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                log.word_id, log.reviewed_at, log.rating, log.review_mode,
                log.proficiency_before, log.proficiency_after,
                log.stage_before, log.stage_after,
            ))
            conn.commit()
            return cursor.lastrowid

    def get_review_logs_by_word(self, word_id: int, limit: int = 20) -> List[ReviewLog]:
        with self._get_conn() as conn:
            rows = conn.execute(
                "SELECT * FROM review_logs WHERE word_id = ? ORDER BY reviewed_at DESC LIMIT ?",
                (word_id, limit)
            ).fetchall()
            return [ReviewLog.from_dict(dict(r)) for r in rows]

    def get_today_review_logs(self, today: str = None) -> List[ReviewLog]:
        if today is None:
            today = date.today().isoformat()
        with self._get_conn() as conn:
            rows = conn.execute(
                "SELECT * FROM review_logs WHERE reviewed_at LIKE ? ORDER BY reviewed_at ASC",
                (f"{today}%",)
            ).fetchall()
            return [ReviewLog.from_dict(dict(r)) for r in rows]

    def get_review_stats_for_date(self, target_date: str) -> dict:
        """获取某日复习统计摘要，用于 AI 报告"""
        with self._get_conn() as conn:
            row = conn.execute("""
                SELECT
                    COUNT(*) as total,
                    SUM(CASE WHEN rating=1 THEN 1 ELSE 0 END) as r1,
                    SUM(CASE WHEN rating=2 THEN 1 ELSE 0 END) as r2,
                    SUM(CASE WHEN rating=3 THEN 1 ELSE 0 END) as r3,
                    SUM(CASE WHEN rating=4 THEN 1 ELSE 0 END) as r4,
                    SUM(CASE WHEN rating=5 THEN 1 ELSE 0 END) as r5,
                    AVG(rating) as avg_r,
                    AVG(proficiency_before) as avg_before,
                    AVG(proficiency_after) as avg_after,
                    COUNT(DISTINCT word_id) as distinct_words
                FROM review_logs WHERE reviewed_at LIKE ?
            """, (f"{target_date}%",)).fetchone()
            if row and row["total"]:
                return dict(row)
            return {"total": 0, "r1": 0, "r2": 0, "r3": 0, "r4": 0, "r5": 0,
                    "avg_r": 0, "avg_before": 0, "avg_after": 0, "distinct_words": 0}

    def get_recent_week_stats(self) -> List[dict]:
        """获取最近 7 天的每日统计摘要"""
        with self._get_conn() as conn:
            rows = conn.execute("""
                SELECT date, new_words_learned, words_reviewed, total_reviews,
                       avg_rating, avg_proficiency_before, avg_proficiency_after
                FROM daily_stats
                ORDER BY date DESC LIMIT 7
            """).fetchall()
            return [dict(r) for r in reversed(rows)]

    # ============================================================
    #  每日统计 CRUD
    # ============================================================

    def upsert_daily_stats(self, stats: DailyStats) -> bool:
        """插入或更新每日统计"""
        with self._get_conn() as conn:
            conn.execute("""
                INSERT INTO daily_stats (date, new_words_learned, words_reviewed,
                    total_reviews, ratings_1, ratings_2, ratings_3, ratings_4, ratings_5,
                    avg_rating, avg_proficiency_before, avg_proficiency_after,
                    study_duration_min, words_from_book, report_generated)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(date) DO UPDATE SET
                    new_words_learned=excluded.new_words_learned,
                    words_reviewed=excluded.words_reviewed,
                    total_reviews=excluded.total_reviews,
                    ratings_1=excluded.ratings_1,
                    ratings_2=excluded.ratings_2,
                    ratings_3=excluded.ratings_3,
                    ratings_4=excluded.ratings_4,
                    ratings_5=excluded.ratings_5,
                    avg_rating=excluded.avg_rating,
                    avg_proficiency_before=excluded.avg_proficiency_before,
                    avg_proficiency_after=excluded.avg_proficiency_after,
                    study_duration_min=excluded.study_duration_min,
                    words_from_book=excluded.words_from_book,
                    report_generated=excluded.report_generated
            """, (
                stats.date, stats.new_words_learned, stats.words_reviewed,
                stats.total_reviews, stats.ratings_1, stats.ratings_2,
                stats.ratings_3, stats.ratings_4, stats.ratings_5,
                stats.avg_rating, stats.avg_proficiency_before,
                stats.avg_proficiency_after, stats.study_duration_min,
                stats.words_from_book, stats.report_generated,
            ))
            conn.commit()
            return True

    def get_daily_stats(self, target_date: str) -> Optional[DailyStats]:
        with self._get_conn() as conn:
            row = conn.execute(
                "SELECT * FROM daily_stats WHERE date = ?", (target_date,)
            ).fetchone()
            return DailyStats.from_dict(dict(row)) if row else None

    def get_stats_last_n_days(self, n: int = 7) -> List[DailyStats]:
        with self._get_conn() as conn:
            rows = conn.execute(
                "SELECT * FROM daily_stats ORDER BY date DESC LIMIT ?", (n,)
            ).fetchall()
            return [DailyStats.from_dict(dict(r)) for r in reversed(rows)]

    # ============================================================
    #  AI 报告 CRUD
    # ============================================================

    def save_daily_report(self, report: DailyReport) -> int:
        with self._get_conn() as conn:
            cursor = conn.execute("""
                INSERT INTO daily_reports (date, summary, weak_words, confused_words,
                    suggestion, trend_analysis, full_report, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(date) DO UPDATE SET
                    summary=excluded.summary,
                    weak_words=excluded.weak_words,
                    confused_words=excluded.confused_words,
                    suggestion=excluded.suggestion,
                    trend_analysis=excluded.trend_analysis,
                    full_report=excluded.full_report,
                    created_at=excluded.created_at
            """, (
                report.date, report.summary, report.weak_words,
                report.confused_words, report.suggestion,
                report.trend_analysis, report.full_report, report.created_at,
            ))
            conn.commit()
            return cursor.lastrowid

    def get_daily_report(self, target_date: str) -> Optional[DailyReport]:
        with self._get_conn() as conn:
            row = conn.execute(
                "SELECT * FROM daily_reports WHERE date = ?", (target_date,)
            ).fetchone()
            return DailyReport.from_dict(dict(row)) if row else None

    def get_all_reports(self, limit: int = 30) -> List[DailyReport]:
        with self._get_conn() as conn:
            rows = conn.execute(
                "SELECT * FROM daily_reports ORDER BY date DESC LIMIT ?", (limit,)
            ).fetchall()
            return [DailyReport.from_dict(dict(r)) for r in rows]

    # ============================================================
    #  词书 CRUD
    # ============================================================

    def add_word_book(self, book: WordBook) -> int:
        with self._get_conn() as conn:
            cursor = conn.execute("""
                INSERT INTO word_books (name, description, total_words, imported_count, created_at)
                VALUES (?, ?, ?, ?, ?)
            """, (book.name, book.description, book.total_words, book.imported_count, book.created_at))
            conn.commit()
            return cursor.lastrowid

    def get_all_word_books(self) -> List[WordBook]:
        with self._get_conn() as conn:
            rows = conn.execute("SELECT * FROM word_books ORDER BY created_at DESC").fetchall()
            return [WordBook.from_dict(dict(r)) for r in rows]

    def get_word_book_by_id(self, book_id: int) -> Optional[WordBook]:
        with self._get_conn() as conn:
            row = conn.execute("SELECT * FROM word_books WHERE id = ?", (book_id,)).fetchone()
            return WordBook.from_dict(dict(row)) if row else None

    def delete_word_book(self, book_id: int) -> bool:
        with self._get_conn() as conn:
            cursor = conn.execute("DELETE FROM word_books WHERE id = ?", (book_id,))
            conn.commit()
            return cursor.rowcount > 0

    def update_book_imported_count(self, book_id: int, count: int):
        with self._get_conn() as conn:
            conn.execute("UPDATE word_books SET imported_count = ? WHERE id = ?", (count, book_id))
            conn.commit()

    # ---- 词书条目 ----

    def add_word_book_entries(self, entries: List[WordBookEntry]) -> int:
        """批量插入词书条目，返回插入数"""
        with self._get_conn() as conn:
            data = [(e.book_id, e.word, e.phonetic, e.part_of_speech,
                     e.chinese_meaning, e.example_sentence, e.example_translation, e.imported)
                    for e in entries]
            conn.executemany("""
                INSERT INTO word_book_entries (book_id, word, phonetic, part_of_speech,
                    chinese_meaning, example_sentence, example_translation, imported)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, data)
            conn.commit()
            return len(data)

    def get_unimported_entries(self, book_id: int, limit: int = 20) -> List[WordBookEntry]:
        """获取词书中尚未导入学习的条目"""
        with self._get_conn() as conn:
            rows = conn.execute(
                "SELECT * FROM word_book_entries WHERE book_id = ? AND imported = 0 LIMIT ?",
                (book_id, limit)
            ).fetchall()
            return [WordBookEntry.from_dict(dict(r)) for r in rows]

    def get_book_entry_count(self, book_id: int) -> Tuple[int, int]:
        """返回 (总数, 已导入数)"""
        with self._get_conn() as conn:
            total = conn.execute(
                "SELECT COUNT(*) as cnt FROM word_book_entries WHERE book_id=?", (book_id,)
            ).fetchone()["cnt"]
            imported = conn.execute(
                "SELECT COUNT(*) as cnt FROM word_book_entries WHERE book_id=? AND imported=1", (book_id,)
            ).fetchone()["cnt"]
            return total, imported

    def mark_entry_imported(self, entry_id: int):
        with self._get_conn() as conn:
            conn.execute("UPDATE word_book_entries SET imported=1 WHERE id=?", (entry_id,))
            conn.commit()

    def get_book_id_by_name(self, name: str) -> Optional[int]:
        with self._get_conn() as conn:
            row = conn.execute("SELECT id FROM word_books WHERE name = ?", (name,)).fetchone()
            return row["id"] if row else None

    # ============================================================
    #  压缩摘要
    # ============================================================

    def save_compressed_snapshot(self, date_str: str, snapshot: str):
        with self._get_conn() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO compressed_snapshots (date, snapshot, compressed) VALUES (?, ?, 0)",
                (date_str, snapshot),
            )
            conn.commit()

    def get_compressed_snapshots(self, limit: int = 7) -> list:
        with self._get_conn() as conn:
            rows = conn.execute(
                "SELECT * FROM compressed_snapshots WHERE compressed=0 ORDER BY date DESC LIMIT ?",
                (limit,)
            ).fetchall()
            return [dict(r) for r in reversed(rows)]

    def mark_snapshot_compressed(self, date_str: str):
        with self._get_conn() as conn:
            conn.execute("UPDATE compressed_snapshots SET compressed=1 WHERE date=?", (date_str,))
            conn.commit()

    def save_compressed_summary(self, summary: str):
        from datetime import datetime
        with self._get_conn() as conn:
            conn.execute(
                "INSERT INTO compressed_summaries (summary, created_at) VALUES (?, ?)",
                (summary, datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
            )
            conn.commit()

    def get_compressed_summaries(self, limit: int = 5) -> list:
        with self._get_conn() as conn:
            rows = conn.execute(
                "SELECT summary FROM compressed_summaries ORDER BY id DESC LIMIT ?", (limit,)
            ).fetchall()
            return [r["summary"] for r in reversed(rows)]

    # ============================================================
    #  轻量级查询（用于测验/统计优化）
    # ============================================================

    def get_random_words_except(self, exclude_id: int, count: int) -> List[Word]:
        """随机获取 N 个单词（排除指定 ID），用于选择题干扰项"""
        with self._get_conn() as conn:
            rows = conn.execute(
                "SELECT * FROM words WHERE id != ? ORDER BY RANDOM() LIMIT ?",
                (exclude_id, count)
            ).fetchall()
            return [Word.from_dict(dict(r)) for r in rows]

    def get_word_stats(self) -> dict:
        """使用 SQL 聚合获取全局统计（避免加载全部单词到内存）"""
        with self._get_conn() as conn:
            row = conn.execute("""
                SELECT
                    COUNT(*) as total,
                    COALESCE(AVG(proficiency), 0) as avg_prof,
                    SUM(CASE WHEN proficiency >= 80 THEN 1 ELSE 0 END) as mastered,
                    SUM(CASE WHEN proficiency >= 30 AND proficiency < 80 THEN 1 ELSE 0 END) as learning,
                    SUM(CASE WHEN proficiency < 30 AND review_count > 0 THEN 1 ELSE 0 END) as weak,
                    COALESCE(SUM(review_count), 0) as total_reviews
                FROM words
            """).fetchone()
            if row:
                return {
                    "total_words": row["total"],
                    "avg_proficiency": round(row["avg_prof"], 1),
                    "mastered": row["mastered"] or 0,
                    "learning": row["learning"] or 0,
                    "weak": row["weak"] or 0,
                    "total_reviews": row["total_reviews"] or 0,
                }
            return {"total_words": 0, "avg_proficiency": 0, "mastered": 0, "learning": 0, "weak": 0, "total_reviews": 0}
