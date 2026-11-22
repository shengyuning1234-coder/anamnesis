"""
学习会话管理 & 统计服务
负责每日学习流程控制、每日统计聚合
"""

from datetime import datetime, date
from typing import List, Optional
from models.word import Word
from models.daily_stats import DailyStats
from models.wordbook import WordBookEntry
from services.database import Database
from services.review_service import ReviewService, get_review_service
from services.wordbook_service import WordBookService, get_wordbook_service


class LearningService:
    """学习会话管理"""

    def __init__(self, db: Database):
        self.db = db
        self.review_service = ReviewService(db)
        self.wordbook_service = WordBookService(db)
        self._session_start: Optional[datetime] = None
        self._daily_quota: int = 20  # 每日新词配额，默认 20
        self._new_words_today = 0
        self._review_words_today = 0

    # ==================== 配额管理 ====================

    @property
    def daily_quota(self) -> int:
        from config import get_daily_quota
        return get_daily_quota()

    @daily_quota.setter
    def daily_quota(self, value: int):
        self._daily_quota = max(1, min(200, value))
        from config import save_learning_settings
        save_learning_settings(daily_quota=self._daily_quota)

    def get_new_words_remaining(self) -> int:
        """今日还可新学几个单词"""
        today_str = date.today().isoformat()
        today_learned = self.db.get_new_words_today(today_str)
        return max(0, self.daily_quota - today_learned)

    # ==================== 学习会话 ====================

    def start_session(self):
        """开始学习会话"""
        self._session_start = datetime.now()
        # 应用自然衰减
        self.review_service.apply_natural_decay()
        # 计算今日已学
        today_str = date.today().isoformat()
        self._new_words_today = self.db.get_new_words_today(today_str)
        self._review_words_today = self.db.get_review_count_today()

    def end_session(self) -> DailyStats:
        """结束学习会话，聚合并保存今日统计"""
        today_str = date.today().isoformat()
        duration = 0
        if self._session_start:
            duration = int((datetime.now() - self._session_start).total_seconds() // 60)

        # 获取今日复习统计
        review_stats = self.db.get_review_stats_for_date(today_str)

        stats = DailyStats(
            date=today_str,
            new_words_learned=self.db.get_new_words_today(today_str),
            words_reviewed=review_stats.get("distinct_words", 0),
            total_reviews=review_stats.get("total", 0),
            ratings_1=review_stats.get("r1", 0),
            ratings_2=review_stats.get("r2", 0),
            ratings_3=review_stats.get("r3", 0),
            ratings_4=review_stats.get("r4", 0),
            ratings_5=review_stats.get("r5", 0),
            avg_rating=round(review_stats.get("avg_r", 0) or 0, 2),
            avg_proficiency_before=round(review_stats.get("avg_before", 0) or 0, 2),
            avg_proficiency_after=round(review_stats.get("avg_after", 0) or 0, 2),
            study_duration_min=duration,
            words_from_book=0,
            report_generated=0,
        )
        self.db.upsert_daily_stats(stats)
        self._session_start = None
        return stats

    # ==================== 新词获取 ====================

    def get_new_words_batch(self, count: int = None) -> List[Word]:
        """
        获取一批新词用于学习
        优先从未复习的已存储单词中取，不够则从词书补充
        """
        if count is None:
            count = min(self.get_new_words_remaining(), 10)

        result = []

        # 1. 先从存储中取从未复习过的单词
        never_reviewed = self.db.get_words_never_reviewed(count)
        result.extend(never_reviewed)

        # 2. 不够则从词书导入
        if len(result) < count:
            needed = count - len(result)
            entries = self.wordbook_service.pick_words_from_books(needed)
            for entry in entries:
                # 检查是否已存在于 words 表
                if self.db.word_exists(entry.word):
                    self.db.mark_entry_imported(entry.id)
                    continue
                # 创建新 Word
                new_word = Word(
                    word=entry.word,
                    phonetic=entry.phonetic,
                    part_of_speech=entry.part_of_speech,
                    chinese_meaning=entry.chinese_meaning,
                    example_sentence=entry.example_sentence,
                    example_translation=entry.example_translation,
                    source="wordbook",
                )
                word_id = self.db.add_word(new_word)
                self.review_service.init_new_word_review(word_id)
                self.db.mark_entry_imported(entry.id)
                # 更新词书导入计数
                book = self.db.get_word_book_by_id(entry.book_id)
                if book:
                    self.db.update_book_imported_count(entry.book_id, book.imported_count + 1)
                # 返回更新后的 word
                result.append(self.db.get_word_by_id(word_id))

        return result[:count]

    # ==================== 统计查询 ====================

    def get_today_stats(self) -> Optional[DailyStats]:
        return self.db.get_daily_stats(date.today().isoformat())

    def get_recent_stats(self, days: int = 7) -> List[DailyStats]:
        return self.db.get_stats_last_n_days(days)

    def get_overall_stats(self) -> dict:
        """获取全局学习概览（SQL聚合，不加载全量单词）"""
        return self.db.get_word_stats()


# 模块级单例
_learning_service: Optional[LearningService] = None


def get_learning_service(db: Database = None) -> LearningService:
    global _learning_service
    if _learning_service is None and db is not None:
        _learning_service = LearningService(db)
    return _learning_service
