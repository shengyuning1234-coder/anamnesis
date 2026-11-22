"""
复习卡片面板 —— 艾宾浩斯间隔复习
支持 en2cn / cn2en / mixed 三种模式
"""

import tkinter as tk
from tkinter import ttk, messagebox
import random
from typing import List, Optional
from models.word import Word
from services.database import Database
from services.review_service import ReviewService, get_review_service
from services.learning_service import LearningService, get_learning_service


class ReviewPanel(ttk.Frame):
    """复习卡片面板"""

    RATING_LABELS = {
        1: ("⭐", "完全忘记"),
        2: ("⭐⭐", "很困难"),
        3: ("⭐⭐⭐", "有点模糊"),
        4: ("⭐⭐⭐⭐", "基本掌握"),
        5: ("⭐⭐⭐⭐⭐", "完全掌握"),
    }

    def __init__(self, parent, db: Database):
        super().__init__(parent)
        self.db = db
        self.review_service = get_review_service(db)
        self.learning_service = get_learning_service(db)

        self.review_list: List[Word] = []
        self.current_index = 0
        self.mode: str = "mixed"  # en2cn / cn2en / mixed
        self.show_answer = False

        self._build_ui()
        self._load_review_list()

    # ==================== UI 构建 ====================

    def _build_ui(self):
        # 顶部工具栏
        toolbar = ttk.Frame(self)
        toolbar.pack(fill=tk.X, padx=10, pady=(10, 5))

        ttk.Label(toolbar, text="📝 单词复习", font=("Microsoft YaHei", 14, "bold")).pack(side=tk.LEFT)

        self.progress_label = ttk.Label(toolbar, text="", font=("", 10))
        self.progress_label.pack(side=tk.RIGHT, padx=10)

        self.mode_label = ttk.Label(toolbar, text="", foreground="blue")
        self.mode_label.pack(side=tk.RIGHT, padx=5)

        ttk.Separator(self, orient=tk.HORIZONTAL).pack(fill=tk.X, padx=10)

        # 主体：卡片区
        card_frame = ttk.Frame(self)
        card_frame.pack(fill=tk.BOTH, expand=True, padx=40, pady=20)

        # 提示文字
        self.hint_label = ttk.Label(
            card_frame, text="", font=("Microsoft YaHei", 11),
            foreground="gray", anchor=tk.CENTER,
        )
        self.hint_label.pack(pady=(0, 15))

        # 大号单词显示
        self.word_label = ttk.Label(
            card_frame, text="", font=("Microsoft YaHei", 28, "bold"),
            anchor=tk.CENTER, wraplength=500,
        )
        self.word_label.pack(pady=10)

        # 音标
        self.phonetic_label = ttk.Label(
            card_frame, text="", font=("Microsoft YaHei", 13),
            foreground="#666", anchor=tk.CENTER,
        )
        self.phonetic_label.pack(pady=3)

        # 释义（答案区）
        self.answer_frame = ttk.LabelFrame(card_frame, text="📖 答案", padding=10)
        self.answer_frame.pack(fill=tk.X, pady=(15, 10))

        self.answer_text = tk.Text(
            self.answer_frame, height=5, font=("Microsoft YaHei", 11),
            wrap=tk.WORD, relief=tk.FLAT, borderwidth=0,
            state=tk.DISABLED,
        )
        self.answer_text.pack(fill=tk.X)

        # 熟练度指标
        self.prof_label = ttk.Label(
            card_frame, text="", font=("Microsoft YaHei", 10),
            foreground="green",
        )
        self.prof_label.pack(pady=3)

        # 按钮区
        btn_frame = ttk.Frame(card_frame)
        btn_frame.pack(pady=15)

        self.show_btn = ttk.Button(
            btn_frame, text="👁 显示答案", command=self._reveal_answer,
        )
        self.show_btn.pack(side=tk.LEFT, padx=5)

        # 评分按钮（初始隐藏）
        self.rating_frame = ttk.Frame(card_frame)
        self.rating_frame.pack(pady=10)
        self.rating_buttons = {}

        for rating in range(1, 6):
            label, desc = self.RATING_LABELS[rating]
            btn = ttk.Button(
                self.rating_frame,
                text=f"{label}\n{desc}",
                command=lambda r=rating: self._submit_rating(r),
                width=14,
            )
            btn.pack(side=tk.LEFT, padx=3)
            self.rating_buttons[rating] = btn
            btn.pack_forget()  # 初始隐藏

        # 底部：模式切换
        bottom_frame = ttk.Frame(self)
        bottom_frame.pack(fill=tk.X, padx=10, pady=(0, 10))

        ttk.Label(bottom_frame, text="复习模式：").pack(side=tk.LEFT)
        self.mode_var = tk.StringVar(value="mixed")
        for text, val in [("英→中", "en2cn"), ("中→英", "cn2en"), ("混合", "mixed")]:
            ttk.Radiobutton(
                bottom_frame, text=text, value=val, variable=self.mode_var,
                command=self._on_mode_change,
            ).pack(side=tk.LEFT, padx=5)

        self.skip_btn = ttk.Button(
            bottom_frame, text="⏭ 跳过", command=self._next_word,
        )
        self.skip_btn.pack(side=tk.RIGHT, padx=5)

        self.quit_btn = ttk.Button(
            bottom_frame, text="🏁 结束复习", command=self._finish_review,
        )
        self.quit_btn.pack(side=tk.RIGHT, padx=5)

    # ==================== 复习逻辑 ====================

    def _load_review_list(self):
        """加载今日待复习列表"""
        self.review_list = self.review_service.get_today_review_list()
        self.current_index = 0
        self._update_progress()
        if self.review_list:
            self._show_card()
        else:
            self._show_empty()

    def _show_empty(self):
        """无复习内容时显示"""
        self.word_label.config(text="🎉")
        self.hint_label.config(text="今日没有需要复习的单词！")
        self.phonetic_label.config(text="")
        self.prof_label.config(text="")
        self.show_btn.pack_forget()
        self._hide_ratings()
        self.answer_text.config(state=tk.NORMAL)
        self.answer_text.delete("1.0", tk.END)
        self.answer_text.insert("1.0", "所有单词都已完成复习计划。\n去学习新单词吧！")
        self.answer_text.config(state=tk.DISABLED)
        self.progress_label.config(text="✅ 全部完成")
        ttk.Button(
            self.answer_frame, text="📥 学习新词",
            command=self._learn_new_words,
        ).pack(pady=5)

    def _show_card(self):
        """显示当前卡片"""
        if self.current_index >= len(self.review_list):
            self._show_empty()
            return

        word = self.review_list[self.current_index]
        self.show_answer = False
        self._hide_ratings()
        self.show_btn.pack(side=tk.LEFT, padx=5)

        # 根据模式决定显示英文还是中文
        actual_mode = self.mode
        if actual_mode == "mixed":
            actual_mode = random.choice(["en2cn", "cn2en"])

        if actual_mode == "en2cn":
            self.word_label.config(text=word.word)
            self.hint_label.config(text="🤔 请回忆中文意思")
            self._build_answer(word, show_en=False, show_cn=True)
        else:
            self.word_label.config(text=word.chinese_meaning.replace("\n", "；")[:50])
            self.hint_label.config(text="✏️ 请回忆英文拼写")
            self._build_answer(word, show_en=True, show_cn=False)

        self.phonetic_label.config(text=word.phonetic if word.phonetic else "")
        self.prof_label.config(
            text=f"📊 熟练度: {word.proficiency}/100  |  阶段: {word.review_stage}/7  |  复习: {word.review_count}次"
        )

        self._update_progress()

    def _build_answer(self, word: Word, show_en: bool, show_cn: bool):
        """构建答案文本"""
        self.answer_text.config(state=tk.NORMAL)
        self.answer_text.delete("1.0", tk.END)

        if show_en:
            self.answer_text.insert(tk.END, f"📝 {word.word}\n")
        if word.phonetic:
            self.answer_text.insert(tk.END, f"🔊 {word.phonetic}\n")
        if word.part_of_speech:
            self.answer_text.insert(tk.END, f"📌 {word.part_of_speech}\n")
        if show_cn:
            self.answer_text.insert(tk.END, f"📖 {word.chinese_meaning}\n")
        if word.example_sentence:
            self.answer_text.insert(tk.END, f"\n💬 例句：\n{word.example_sentence}")
        if word.example_translation:
            self.answer_text.insert(tk.END, f"\n{word.example_translation}")
        if word.notes:
            self.answer_text.insert(tk.END, f"\n\n📝 笔记：{word.notes}")

        self.answer_text.config(state=tk.DISABLED)

    def _reveal_answer(self):
        """显示答案"""
        self.show_answer = True
        self.show_btn.pack_forget()
        self._show_ratings()

    def _show_ratings(self):
        for btn in self.rating_buttons.values():
            btn.pack(side=tk.LEFT, padx=3)

    def _hide_ratings(self):
        for btn in self.rating_buttons.values():
            btn.pack_forget()

    def _submit_rating(self, rating: int):
        """提交评分并进入下一词"""
        if self.current_index >= len(self.review_list):
            return

        word = self.review_list[self.current_index]

        # 执行复习
        self.review_service.review_word(word.id, rating, self.mode)

        # 更新列表中该词的引用
        updated = self.db.get_word_by_id(word.id)
        if updated:
            self.review_list[self.current_index] = updated

        self.current_index += 1
        self._show_card()

    def _next_word(self):
        """跳过当前词（不减分，下次继续）"""
        if self.current_index >= len(self.review_list):
            return
        self.current_index += 1
        self._show_card()

    def _on_mode_change(self):
        """切换复习模式"""
        self.mode = self.mode_var.get()
        if self.mode == "en2cn":
            self.mode_label.config(text="模式：英→中", foreground="blue")
        elif self.mode == "cn2en":
            self.mode_label.config(text="模式：中→英", foreground="green")
        else:
            self.mode_label.config(text="模式：混合", foreground="purple")

        # 刷新当前卡片
        if self.review_list and self.current_index < len(self.review_list):
            self._show_card()

    def _update_progress(self):
        total = len(self.review_list)
        if total == 0:
            self.progress_label.config(text="")
            return
        done = self.current_index
        self.progress_label.config(
            text=f"📊 {done}/{total}  ({int(done/total*100) if total else 0}%)"
        )

    def _learn_new_words(self):
        """触发学习新词"""
        self.event_generate("<<LearnNewWords>>")

    def _finish_review(self):
        """结束复习"""
        from services.learning_service import get_learning_service
        ls = get_learning_service(self.db)
        stats = ls.end_session()
        messagebox.showinfo(
            "复习完成",
            f"今日复习结束！\n"
            f"复习单词：{stats.words_reviewed} 个\n"
            f"复习次数：{stats.total_reviews} 次\n"
            f"平均评分：{stats.avg_rating:.1f}/5\n"
            f"学习时长：{stats.study_duration_min} 分钟",
        )
        self.event_generate("<<ReviewFinished>>")

    def refresh(self):
        """外部调用刷新"""
        self._load_review_list()
