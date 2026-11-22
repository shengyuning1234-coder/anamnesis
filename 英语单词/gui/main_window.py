"""
主窗口 —— 英语单词背诵记忆系统（含学习 & 报告模块）
"""

import tkinter as tk
from tkinter import ttk, messagebox
from datetime import date
from services.database import Database
from services.local_dict import local_dict
from services.learning_service import LearningService, get_learning_service
from services.review_service import ReviewService, get_review_service
from gui.word_list import WordListPanel
from gui.add_word_dialog import AddWordDialog
from gui.settings_dialog import SettingsDialog
from gui.wordbook_dialog import WordBookDialog
from gui.quiz_panel import QuizPanel
from gui.report_panel import ReportPanel
from config import get_local_dict_path, get_daily_quota, save_learning_settings
from models.word import Word


class MainWindow(tk.Tk):
    """主窗口"""

    def __init__(self):
        super().__init__()

        self.title("📚 英语单词背诵记忆系统")
        self.geometry("1050x750")
        self.minsize(900, 600)

        # 数据库 & 服务
        self.db = Database()
        self.learning_service = get_learning_service(self.db)
        self.review_service = get_review_service(self.db)

        # 加载配置
        self.learning_service.daily_quota = get_daily_quota()

        # 加载本地词典（后台建索引）
        self._init_local_dicts()

        self._build_ui()
        self._center_window()

    def _init_local_dicts(self):
        """加载本地 MDX 词典"""
        local_dict.add_dictionary(get_local_dict_path())
        local_dict.build_index_async()

    # ============================================================
    #  UI 构建
    # ============================================================

    def _build_ui(self):
        # ===== 顶部工具栏 =====
        toolbar = ttk.Frame(self)
        toolbar.pack(fill=tk.X, padx=10, pady=(10, 0))

        ttk.Label(
            toolbar, text="📚 英语单词背诵记忆系统",
            font=("Microsoft YaHei", 15, "bold"),
        ).pack(side=tk.LEFT)

        # 右侧按钮
        self.quota_label = ttk.Label(toolbar, text="", font=("", 10), foreground="#2c3e50")
        self.quota_label.pack(side=tk.RIGHT, padx=5)

        ttk.Button(
            toolbar, text="⚙️ 设置", command=self._open_settings,
        ).pack(side=tk.RIGHT, padx=3)

        ttk.Button(
            toolbar, text="📚 词书", command=self._open_wordbook,
        ).pack(side=tk.RIGHT, padx=3)

        self.count_label = ttk.Label(toolbar, text="", font=("", 10))
        self.count_label.pack(side=tk.RIGHT, padx=10)

        self._update_stats()

        ttk.Separator(self, orient=tk.HORIZONTAL).pack(fill=tk.X, padx=10, pady=5)

        # ===== Tab 导航 =====
        self.notebook = ttk.Notebook(self)
        self.notebook.pack(fill=tk.BOTH, expand=True)

        # ---- Tab 1: 单词本 ----
        self.word_list = WordListPanel(self.notebook, self.db, on_edit=self._edit_word)
        self.notebook.add(self.word_list, text="  📖 单词本  ")
        self.word_list.add_btn.config(command=self._add_word)

        # ---- Tab 2: 学习 ----
        self.learn_frame = ttk.Frame(self.notebook)
        self.notebook.add(self.learn_frame, text="  📝 学习  ")

        self._build_learn_tab()

        # ---- Tab 3: 报告 ----
        self.report_panel = ReportPanel(self.notebook, self.db)
        self.notebook.add(self.report_panel, text="  📊 报告  ")

        # 切换 Tab 事件
        self.notebook.bind("<<NotebookTabChanged>>", self._on_tab_change)

    def _build_learn_tab(self):
        """构建学习 Tab"""
        # 顶部信息栏
        info_frame = ttk.Frame(self.learn_frame)
        info_frame.pack(fill=tk.X, padx=10, pady=5)

        self.learn_info_label = ttk.Label(
            info_frame, text="", font=("Microsoft YaHei", 10),
            foreground="#2c3e50",
        )
        self.learn_info_label.pack(side=tk.LEFT)

        # 每日配额设置
        quota_frame = ttk.Frame(info_frame)
        quota_frame.pack(side=tk.RIGHT)

        ttk.Label(quota_frame, text="每日新词：").pack(side=tk.LEFT)
        self.quota_var = tk.IntVar(value=self.learning_service.daily_quota)
        ttk.Spinbox(
            quota_frame, from_=1, to=200, textvariable=self.quota_var,
            width=5, command=self._on_quota_change,
        ).pack(side=tk.LEFT)

        ttk.Button(
            quota_frame, text="📥 开始学新词", command=self._start_learn_new_words,
        ).pack(side=tk.LEFT, padx=(10, 0))

        self.start_review_btn = ttk.Button(
            quota_frame, text="🔄 开始复习", command=self._start_review,
        )
        self.start_review_btn.pack(side=tk.LEFT, padx=(5, 0))

        ttk.Separator(self.learn_frame, orient=tk.HORIZONTAL).pack(fill=tk.X, padx=10)

        # 内容区
        self.learn_content = ttk.Frame(self.learn_frame)
        self.learn_content.pack(fill=tk.BOTH, expand=True)

        # 默认显示学习状态
        self._show_learn_status()

    def _show_learn_status(self):
        """显示学习状态页"""
        for w in self.learn_content.winfo_children():
            w.destroy()

        status_frame = ttk.Frame(self.learn_content)
        status_frame.pack(expand=True, fill=tk.BOTH, padx=40, pady=30)

        # 获取统计数据
        today = date.today().isoformat()
        stats = self.db.get_daily_stats(today)
        due_count = len(self.review_service.get_today_review_list())
        remaining = self.learning_service.get_new_words_remaining()

        lines = []
        lines.append(f"📅 日期：{today}")
        lines.append(f"📖 每日新词配额：{self.learning_service.daily_quota} 个")
        lines.append(f"📥 今日已学新词：{stats.new_words_learned if stats else 0} 个（剩余 {remaining}）")
        lines.append(f"🔄 今日已复习：{stats.words_reviewed if stats else 0} 个")
        lines.append(f"⏰ 待复习：{due_count} 个")
        lines.append("")

        for line in lines:
            ttk.Label(
                status_frame, text=line, font=("Microsoft YaHei", 12),
            ).pack(anchor=tk.W, pady=3)

        ttk.Label(
            status_frame, text="💡 点击「开始复习」进入多级测验（选择题/回忆/拼写/释义/综合）",
            font=("Microsoft YaHei", 10), foreground="gray",
        ).pack(anchor=tk.W, pady=(15, 0))

        if stats and stats.study_duration_min > 0:
            self.learn_info_label.config(
                text=f"📊 今日已学 {stats.new_words_learned} 词 | 复习 {stats.words_reviewed} 词 | 时长 {stats.study_duration_min} 分钟"
            )
        else:
            self.learn_info_label.config(text="📊 今日尚未开始学习")

    # ============================================================
    #  学习 & 复习操作
    # ============================================================

    def _start_review(self):
        """开始复习（使用多级测验引擎）"""
        self.learning_service.start_session()

        due_words = self.review_service.get_today_review_list()
        if not due_words:
            messagebox.showinfo("提示", "今日没有需要复习的单词。\n所有单词都在复习计划中！")
            return

        self.notebook.select(self.learn_frame)
        for w in self.learn_content.winfo_children():
            w.destroy()

        self.quiz_panel = QuizPanel(self.learn_content, self.db, due_words)
        self.quiz_panel.pack(fill=tk.BOTH, expand=True)
        self.quiz_panel.bind("<<QuizFinished>>", self._on_review_finished)

        self.learn_info_label.config(text="📝 复习测验中...")
        self.start_review_btn.config(state=tk.DISABLED)

    def _start_learn_new_words(self):
        """开始学习新词"""
        self.learning_service.start_session()

        remaining = self.learning_service.get_new_words_remaining()
        if remaining <= 0:
            messagebox.showinfo("提示", f"今日新词配额（{self.learning_service.daily_quota}）已用完！\n可调整配额继续学习。")
            return

        # 获取新词
        new_words = self.learning_service.get_new_words_batch(remaining)
        if not new_words:
            messagebox.showinfo("提示", "当前无可学习的新词。\n请先录入单词或导入词书！")
            return

        # 对于从词书新导入的词，打开编辑对话框确认
        from_wordbook = [w for w in new_words if w.source == "wordbook"]
        if from_wordbook:
            for w in from_wordbook[:5]:  # 最多确认 5 个
                dialog = AddWordDialog(self, self.db, edit_word=w)
                self.wait_window(dialog)

        # 将新词加入复习队列
        for w in new_words:
            if w.review_count == 0:
                self.review_service.init_new_word_review(w.id)

        # 刷新状态
        self.word_list.refresh()
        self._update_stats()
        self._show_learn_status()

        messagebox.showinfo(
            "新词就绪",
            f"已准备 {len(new_words)} 个新词。\n"
            f"它们已加入复习队列，请点击「开始复习」进行首次复习。"
        )

    # ============================================================
    #  事件处理
    # ============================================================

    def _on_review_finished(self, event):
        """复习完成"""
        self.start_review_btn.config(state=tk.NORMAL)
        self.word_list.refresh()
        self._update_stats()
        self._show_learn_status()
        if messagebox.askyesno("复习完成", "是否生成今日学习报告？"):
            self._generate_report_inline()

    def _on_tab_change(self, event):
        """Tab 切换"""
        current = self.notebook.select()
        tab_id = self.notebook.index(current)
        if tab_id == 0:
            self.word_list.refresh()
            self._update_stats()
        elif tab_id == 1:
            self._show_learn_status()
            self._update_stats()
        elif tab_id == 2:
            self.report_panel.refresh()

    def _on_quota_change(self):
        """每日配额变更"""
        try:
            new_quota = int(self.quota_var.get())
            self.learning_service.daily_quota = new_quota
            save_learning_settings(daily_quota=new_quota)
            self._show_learn_status()
        except (ValueError, tk.TclError):
            pass

    # ============================================================
    #  对话框
    # ============================================================

    def _add_word(self):
        dialog = AddWordDialog(self, self.db)
        self.wait_window(dialog)
        self._refresh()

    def _edit_word(self, word: Word):
        dialog = AddWordDialog(self, self.db, edit_word=word)
        self.wait_window(dialog)
        self._refresh()

    def _open_settings(self):
        SettingsDialog(self)

    def _open_wordbook(self):
        WordBookDialog(self, self.db)
        self._refresh()

    def _generate_report_inline(self):
        """内联生成报告"""
        from services.report_service import get_report_service
        rs = get_report_service(self.db)
        today = date.today().isoformat()
        report = rs.generate_daily_report(today)
        if report:
            self.notebook.select(self.report_panel)
            self.report_panel.refresh()

    # ============================================================
    #  工具方法
    # ============================================================

    def _refresh(self):
        self.word_list.refresh()
        self._update_stats()

    def _update_stats(self):
        count = self.db.get_total_count()
        overview = self.learning_service.get_overall_stats()
        avg = overview.get("avg_proficiency", 0)
        self.count_label.config(text=f"📊 {count}词 | 均熟{avg}")
        self.quota_label.config(text=f"📥 {self.learning_service.daily_quota}词/日")

    def _center_window(self):
        self.update_idletasks()
        w = self.winfo_width()
        h = self.winfo_height()
        sw = self.winfo_screenwidth()
        sh = self.winfo_screenheight()
        x = (sw - w) // 2
        y = (sh - h) // 2
        self.geometry(f"+{x}+{y}")
