"""
多级测验面板 —— 选择题/回忆/拼写/释义/综合
根据熟练度自动分层
"""

import tkinter as tk
from tkinter import ttk, messagebox
import random
from typing import List, Optional, Dict
from models.word import Word
from services.database import Database
from services.quiz_service import QuizService
from services.review_service import ReviewService, get_review_service
from services.learning_service import LearningService, get_learning_service


class QuizPanel(ttk.Frame):
    """多模式测验面板"""

    # 熟练度配色
    PROF_COLORS = {range(0, 25): "#e74c3c", range(25, 50): "#e67e22",
                   range(50, 75): "#2ecc71", range(75, 101): "#27ae60"}

    def __init__(self, parent, db: Database, words: List[Word] = None):
        super().__init__(parent)
        self.db = db
        self.quiz_service = QuizService(db)
        self.review_service = get_review_service(db)
        self.learning_service = get_learning_service(db)

        self.words: List[Word] = words or []
        self.current_index = 0
        self.current_question: dict = None
        self.quiz_result = {"total": 0, "correct": 0, "ratings": []}

        self._build_ui()
        if self.words:
            self._start_quiz()

    # ==================== UI ====================

    def _build_ui(self):
        # 顶部进度
        top = ttk.Frame(self)
        top.pack(fill=tk.X, padx=10, pady=(8, 4))

        self.mode_label = ttk.Label(top, text="", font=("", 11, "bold"), foreground="#2c3e50")
        self.mode_label.pack(side=tk.LEFT)

        self.progress_label = ttk.Label(top, text="", font=("", 10))
        self.progress_label.pack(side=tk.RIGHT)

        self.prof_label = ttk.Label(top, text="", font=("", 9), foreground="gray")
        self.prof_label.pack(side=tk.RIGHT, padx=10)

        ttk.Separator(self, orient=tk.HORIZONTAL).pack(fill=tk.X, padx=10)

        # 题目区
        card = ttk.Frame(self)
        card.pack(fill=tk.BOTH, expand=True, padx=30, pady=15)

        self.prompt_label = ttk.Label(
            card, text="", font=("Microsoft YaHei", 16, "bold"),
            anchor=tk.CENTER, wraplength=550,
        )
        self.prompt_label.pack(pady=(10, 5))

        self.hint_label = ttk.Label(
            card, text="", font=("", 10), foreground="#888",
            anchor=tk.CENTER, wraplength=500,
        )
        self.hint_label.pack(pady=3)

        self.extra_label = ttk.Label(
            card, text="", font=("", 9), foreground="#aaa",
            anchor=tk.CENTER, wraplength=500,
        )
        self.extra_label.pack(pady=3)

        # 动态区（选项/输入/结果）
        self.dynamic_frame = ttk.Frame(card)
        self.dynamic_frame.pack(fill=tk.BOTH, expand=True, pady=10)

        # 按钮区
        btn_frame = ttk.Frame(self)
        btn_frame.pack(fill=tk.X, padx=10, pady=(0, 10))

        self.skip_btn = ttk.Button(btn_frame, text="⏭ 跳过", command=self._next_question)
        self.skip_btn.pack(side=tk.LEFT)

        self.quit_btn = ttk.Button(btn_frame, text="🏁 结束", command=self._finish)
        self.quit_btn.pack(side=tk.RIGHT)

    # ==================== 题目流程 ====================

    def _start_quiz(self):
        self.current_index = 0
        self.quiz_result = {"total": 0, "correct": 0, "ratings": []}
        self._show_question()

    def _show_question(self):
        """显示当前题目"""
        for w in self.dynamic_frame.winfo_children():
            w.destroy()

        if self.current_index >= len(self.words):
            self._finish()
            return

        word = self.words[self.current_index]
        mode = self.quiz_service.get_mode_for_word(word)
        self.current_question = self.quiz_service.generate_question(word, mode)

        # 更新标题
        mode_name = self.quiz_service.MODES.get(mode, ("?", ""))[0]
        self.mode_label.config(text=mode_name)

        # 进度
        self.progress_label.config(
            text=f"📊 {self.current_index + 1}/{len(self.words)}"
        )

        # 熟练度色标
        prof = word.proficiency
        color = "#888"
        for r, c in self.PROF_COLORS.items():
            if prof in r:
                color = c
                break
        self.prof_label.config(text=f"熟练度 {prof}", foreground=color)

        # 题目内容
        q = self.current_question
        self.prompt_label.config(text=q.get("prompt", ""))
        self.hint_label.config(text=q.get("hint", ""))
        self.extra_label.config(text=q.get("extra", ""))

        # 根据题型构建交互区
        qtype = q.get("type", "recall")
        if qtype == "choice":
            self._build_choice_ui(q)
        elif qtype == "recall":
            self._build_recall_ui(q)
        elif qtype in ("spell", "type_cn", "type_multi_cn", "fill_blank", "synonym_antonym"):
            self._build_input_ui(q)
        else:
            self._build_recall_ui(q)

    def _build_choice_ui(self, q: dict):
        """选择题：4 个按钮"""
        options = q.get("options", [])
        for i, opt in enumerate(options):
            btn = ttk.Button(
                self.dynamic_frame,
                text=f"{chr(65+i)}. {opt}",
                command=lambda o=opt: self._on_choice(o),
            )
            btn.pack(fill=tk.X, pady=3, ipady=5)

    def _build_recall_ui(self, q: dict):
        """回忆模式：先隐藏答案，用户点显示"""
        # 显示"点击查看答案"
        reveal_btn = ttk.Button(
            self.dynamic_frame,
            text="👁 点击查看答案",
            command=lambda: self._reveal_recall_answer(q),
        )
        reveal_btn.pack(pady=10)

    def _build_input_ui(self, q: dict):
        """输入模式：文本框 + 提交"""
        qtype = q.get("type", "")
        if qtype == "spell":
            placeholder = "在此输入英文单词..."
        elif qtype in ("type_cn", "type_multi_cn"):
            placeholder = "在此输入中文释义..."
        else:
            placeholder = "在此输入答案..."

        self.input_text = tk.Text(
            self.dynamic_frame, height=3, font=("Microsoft YaHei", 12),
            wrap=tk.WORD, relief=tk.SUNKEN, borderwidth=1,
        )
        self.input_text.pack(fill=tk.X, pady=5)
        self.input_text.insert("1.0", "")
        self.input_text.focus_set()

        # 提示词
        if placeholder:
            self.input_text.insert("1.0", placeholder)
            self.input_text.config(foreground="gray")
            self.input_text.bind("<FocusIn>", lambda e: self._clear_placeholder(placeholder))
            self.input_text.bind("<FocusOut>", lambda e: self._restore_placeholder(placeholder))

        ttk.Button(
            self.dynamic_frame, text="✅ 提交", command=self._on_submit_input,
        ).pack(pady=8)

        self.feedback_label = ttk.Label(
            self.dynamic_frame, text="", font=("", 11),
        )
        self.feedback_label.pack(pady=5)

    def _clear_placeholder(self, placeholder: str):
        if self.input_text.get("1.0", "end-1c").strip() == placeholder:
            self.input_text.delete("1.0", tk.END)
            self.input_text.config(foreground="black")

    def _restore_placeholder(self, placeholder: str):
        if not self.input_text.get("1.0", "end-1c").strip():
            self.input_text.insert("1.0", placeholder)
            self.input_text.config(foreground="gray")

    # ==================== 答题处理 ====================

    def _on_choice(self, selected: str):
        q = self.current_question
        correct = selected == q.get("answer", "")
        rating = 5 if correct else 1
        self._record_answer(correct, rating)
        self._show_feedback_choice(correct, q.get("answer", ""))

    def _show_feedback_choice(self, correct: bool, answer: str):
        """选择题反馈 + 自动下一题"""
        for w in self.dynamic_frame.winfo_children():
            w.destroy()

        if correct:
            ttk.Label(
                self.dynamic_frame, text="✅ 正确！", font=("", 14, "bold"),
                foreground="green",
            ).pack(pady=10)
        else:
            ttk.Label(
                self.dynamic_frame, text=f"❌ 正确答案：{answer}",
                font=("", 12), foreground="red",
            ).pack(pady=10)

        ttk.Button(
            self.dynamic_frame, text="▶ 下一题", command=self._next_question,
        ).pack(pady=10)

    def _reveal_recall_answer(self, q: dict):
        """回忆模式：显示答案 + 自评按钮"""
        for w in self.dynamic_frame.winfo_children():
            w.destroy()

        answer = q.get("answer", "")
        ttk.Label(
            self.dynamic_frame,
            text=f"📖 {answer}",
            font=("Microsoft YaHei", 13), wraplength=500,
        ).pack(pady=10)

        ttk.Label(
            self.dynamic_frame, text="你记住了吗？", font=("", 10),
        ).pack(pady=5)

        btns = ttk.Frame(self.dynamic_frame)
        btns.pack(pady=8)
        ttk.Button(
            btns, text="✅ 记得", command=lambda: self._on_recall_result(True),
        ).pack(side=tk.LEFT, padx=5)
        ttk.Button(
            btns, text="❌ 忘了", command=lambda: self._on_recall_result(False),
        ).pack(side=tk.LEFT, padx=5)

    def _on_recall_result(self, remembered: bool):
        rating = 5 if remembered else 2
        self._record_answer(remembered, rating)
        self._next_question()

    def _on_submit_input(self):
        """处理文本输入提交"""
        q = self.current_question
        user_answer = self.input_text.get("1.0", "end-1c").strip()

        # 去掉占位符
        placeholders = ["在此输入英文单词...", "在此输入中文释义...", "在此输入答案..."]
        if user_answer in placeholders:
            user_answer = ""

        if not user_answer:
            self.feedback_label.config(text="请输入答案", foreground="orange")
            return

        # 禁用提交按钮防重复
        for child in self.dynamic_frame.winfo_children():
            if isinstance(child, ttk.Button):
                child.config(state=tk.DISABLED)

        self.feedback_label.config(text="⏳ 评判中...", foreground="gray")
        self.update()

        correct, rating, feedback = self.quiz_service.judge_answer(q, user_answer)
        self._record_answer(correct, rating)

        # 显示反馈
        color = "green" if correct else "red"
        icon = "✅" if correct else "❌"
        self.feedback_label.config(
            text=f"{icon} {feedback}", foreground=color,
        )

        # 显示参考答案（如果错误）
        if not correct:
            ref = q.get("reference", q.get("answer", ""))
            if ref:
                ttk.Label(
                    self.dynamic_frame,
                    text=f"参考答案：{ref[:200]}",
                    font=("", 9), foreground="#888", wraplength=500,
                ).pack(pady=3)

        ttk.Button(
            self.dynamic_frame, text="▶ 下一题", command=self._next_question,
        ).pack(pady=8)

    # ==================== 记录 & 导航 ====================

    def _record_answer(self, correct: bool, rating: int):
        self.quiz_result["total"] += 1
        if correct:
            self.quiz_result["correct"] += 1
        self.quiz_result["ratings"].append(rating)

        # 同步写入复习记录
        word = self.words[self.current_index]
        mode = self.current_question.get("mode", "mixed")
        try:
            self.review_service.review_word(word.id, rating, mode)
        except Exception as e:
            print(f"[Quiz] review error: {e}")

    def _next_question(self):
        self.current_index += 1
        self._show_question()

    def _finish(self):
        """结束测验"""
        total = self.quiz_result["total"]
        correct = self.quiz_result["correct"]
        ratings = self.quiz_result["ratings"]
        avg = sum(ratings) / len(ratings) if ratings else 0

        msg = (
            f"🎉 测验完成！\n\n"
            f"总题数：{total}\n"
            f"正确：{correct}  错误：{total - correct}\n"
            f"正确率：{int(correct/total*100) if total else 0}%\n"
            f"平均评分：{avg:.1f}/5"
        )
        messagebox.showinfo("测验结果", msg)
        self.event_generate("<<QuizFinished>>")
