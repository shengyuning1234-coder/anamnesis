"""
艾宾浩斯复习调度服务
基于遗忘曲线控制复习间隔和熟练度变化
"""

from datetime import datetime, timedelta
from typing import List, Tuple
from models.word import Word
from models.review_log import ReviewLog
from services.database import Database


class ReviewService:
    """艾宾浩斯遗忘曲线复习调度"""

    # 艾宾浩斯复习间隔（从阶段 1 开始）
    # 阶段 0 = 未开始 → 首次复习立即（或 20 分钟→1 小时→...）
    # 实际使用更实用的间隔：
    #   阶段 1: 1 天（学习后第二天）
    #   阶段 2: 2 天
    #   阶段 3: 4 天
    #   阶段 4: 7 天
    #   阶段 5: 15 天
    #   阶段 6: 30 天
    #   阶段 7: 60 天（完全掌握）
    INTERVALS_DAYS = [0, 1, 2, 4, 7, 15, 30, 60]

    # 评分 → 熟练度变化
    RATING_PROFICIENCY_DELTA = {
        1: -15,   # 完全忘记：-15
        2: -5,    # 困难：-5
        3: +5,    # 模糊：+5
        4: +12,   # 基本掌握：+12
        5: +20,   # 完全掌握：+20
    }

    # 评分 → 阶段变化
    RATING_STAGE_DELTA = {
        1: -3,    # 完全忘记 → 回退 3 阶段
        2: -1,    # 困难 → 回退 1 阶段
        3: 0,     # 模糊 → 维持
        4: +1,    # 基本掌握 → 前进 1
        5: +2,    # 完全掌握 → 前进 2（加速）
    }

    MAX_STAGE = 7
    MIN_PROFICIENCY = 0
    MAX_PROFICIENCY = 100

    REVIEW_MODES = ["en2cn", "cn2en", "mixed"]

    def __init__(self, db: Database):
        self.db = db

    # ==================== 核心逻辑 ====================

    @classmethod
    def clamp_proficiency(cls, value: int) -> int:
        return max(cls.MIN_PROFICIENCY, min(cls.MAX_PROFICIENCY, value))

    @classmethod
    def clamp_stage(cls, value: int) -> int:
        return max(0, min(cls.MAX_STAGE, value))

    def calculate_new_proficiency(self, current: int, rating: int) -> int:
        """根据评分计算新熟练度"""
        delta = self.RATING_PROFICIENCY_DELTA.get(rating, 0)
        return self.clamp_proficiency(current + delta)

    def calculate_new_stage(self, current_stage: int, rating: int) -> int:
        """根据评分计算新阶段"""
        delta = self.RATING_STAGE_DELTA.get(rating, 0)
        new_stage = current_stage + delta
        # 如果评分 >=4 且当前阶段为 0，直接进入阶段 1
        if current_stage == 0 and rating >= 3:
            new_stage = max(new_stage, 1)
        return self.clamp_stage(new_stage)

    def calculate_next_review(self, stage: int, from_time: datetime = None) -> str:
        """计算下次复习时间"""
        if from_time is None:
            from_time = datetime.now()
        days = self.INTERVALS_DAYS[min(stage, self.MAX_STAGE)]
        if days == 0:
            days = 1  # 至少 1 天后
        next_time = from_time + timedelta(days=days)
        return next_time.strftime("%Y-%m-%d %H:%M:%S")

    # ==================== 复习操作 ====================

    def review_word(self, word_id: int, rating: int, mode: str = "en2cn") -> Word:
        """
        复习一个单词
        - rating: 1-5
        - mode: en2cn / cn2en / mixed
        返回更新后的 Word
        """
        word = self.db.get_word_by_id(word_id)
        if word is None:
            raise ValueError(f"单词不存在: id={word_id}")

        now = datetime.now()
        now_str = now.strftime("%Y-%m-%d %H:%M:%S")

        # 记录复习前状态
        proficiency_before = word.proficiency
        stage_before = word.review_stage

        # 计算新值
        new_proficiency = self.calculate_new_proficiency(proficiency_before, rating)
        new_stage = self.calculate_new_stage(stage_before, rating)
        new_review_count = word.review_count + 1
        next_review = self.calculate_next_review(new_stage, now)

        # 更新单词
        word.proficiency = new_proficiency
        word.review_count = new_review_count
        word.review_stage = new_stage
        word.last_reviewed_at = now_str
        word.next_review_at = next_review
        word.updated_at = now_str
        self.db.update_word(word)

        # 写复习日志
        log = ReviewLog(
            word_id=word_id,
            reviewed_at=now_str,
            rating=rating,
            review_mode=mode,
            proficiency_before=proficiency_before,
            proficiency_after=new_proficiency,
            stage_before=stage_before,
            stage_after=new_stage,
        )
        self.db.add_review_log(log)

        return word

    # ==================== 初始化复习 ====================

    def init_new_word_review(self, word_id: int):
        """
        新单词加入复习队列
        设为立即可复习（next_review_at = now，立即出现在待复习列表）
        """
        word = self.db.get_word_by_id(word_id)
        if word is None:
            return
        now = datetime.now()
        word.next_review_at = now.strftime("%Y-%m-%d %H:%M:%S")
        word.updated_at = now.strftime("%Y-%m-%d %H:%M:%S")
        self.db.update_word(word)

    # ==================== 查询 ====================

    def get_today_review_list(self) -> List[Word]:
        """获取今日待复习单词列表"""
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        return self.db.get_words_due_for_review(now)

    def get_review_count_today(self) -> int:
        """今日已复习数量"""
        return self.db.get_review_count_today()

    def apply_natural_decay(self) -> int:
        """
        对超过复习时间未复习的单词进行熟练度自然衰减
        返回衰减的单词数
        """
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        overdue_words = self.db.get_words_due_for_review(now)
        count = 0
        for w in overdue_words:
            if w.proficiency > 0:
                # 每超过 1 天减 1 分，最少减到 0
                try:
                    due_time = datetime.strptime(w.next_review_at, "%Y-%m-%d %H:%M:%S")
                    overdue_days = (datetime.now() - due_time).days
                    decay = min(overdue_days, w.proficiency)
                except (ValueError, TypeError):
                    decay = 1
                if decay > 0:
                    w.proficiency = self.clamp_proficiency(w.proficiency - decay)
                    w.updated_at = now
                    self.db.update_word(w)
                    count += 1
        return count


# 模块级单例
_review_service: ReviewService = None


def get_review_service(db: Database = None) -> ReviewService:
    global _review_service
    if _review_service is None and db is not None:
        _review_service = ReviewService(db)
    return _review_service
