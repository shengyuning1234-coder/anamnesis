"""
单词列表面板 —— 用 Treeview 展示所有单词
"""

import tkinter as tk
from tkinter import ttk, messagebox
from typing import List, Callable
from models.word import Word
from services.database import Database


class WordListPanel(ttk.Frame):
    """单词列表 Treeview 面板"""

    COLUMNS = ("word", "phonetic", "pos", "meaning", "proficiency", "review", "source", "date")
    COLUMN_HEADERS = {
        "word": "单词",
        "phonetic": "音标",
        "pos": "词性",
        "meaning": "中文释义",
        "proficiency": "熟练度",
        "review": "复习",
        "source": "来源",
        "date": "日期",
    }

    def __init__(self, parent, db: Database, on_edit: Callable = None):
        super().__init__(parent)
        self.db = db
        self.on_edit = on_edit
        self.all_words: List[Word] = []
        self._build_ui()
        self.refresh()

    def _build_ui(self):
        # 搜索栏
        search_frame = ttk.Frame(self)
        search_frame.pack(fill=tk.X, padx=10, pady=(10, 5))

        ttk.Label(search_frame, text="🔍 搜索：").pack(side=tk.LEFT)
        self.search_var = tk.StringVar()
        self.search_var.trace_add("write", lambda *a: self._do_search())
        search_entry = ttk.Entry(search_frame, textvariable=self.search_var, width=30)
        search_entry.pack(side=tk.LEFT, padx=5)

        # 统计标签
        self.stats_label = ttk.Label(search_frame, text="共 0 个单词")
        self.stats_label.pack(side=tk.RIGHT, padx=10)

        # ===== 主内容区（上下分割） =====
        main_pw = ttk.PanedWindow(self, orient=tk.VERTICAL)
        main_pw.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

        # ---- 上半部分：Treeview 列表 ----
        tree_frame = ttk.Frame(main_pw)
        main_pw.add(tree_frame, weight=3)

        style = ttk.Style()
        style.configure("Word.Treeview", rowheight=32, font=("Microsoft YaHei", 10))

        self.tree = ttk.Treeview(
            tree_frame,
            columns=self.COLUMNS,
            show="headings",
            style="Word.Treeview",
            selectmode="browse",
        )

        # 列宽与标题
        col_widths = {
            "word": 110, "phonetic": 100, "pos": 60, "meaning": 180,
            "proficiency": 65, "review": 55, "source": 55, "date": 90,
        }
        for col in self.COLUMNS:
            self.tree.heading(col, text=self.COLUMN_HEADERS[col], anchor=tk.W)
            self.tree.column(col, width=col_widths.get(col, 80), minwidth=40, anchor=tk.W)

        # 滚动条
        vsb = ttk.Scrollbar(tree_frame, orient=tk.VERTICAL, command=self.tree.yview)
        hsb = ttk.Scrollbar(tree_frame, orient=tk.HORIZONTAL, command=self.tree.xview)
        self.tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)

        self.tree.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        hsb.grid(row=1, column=0, sticky="ew")
        tree_frame.rowconfigure(0, weight=1)
        tree_frame.columnconfigure(0, weight=1)

        # 选中变化 → 更新详情面板
        self.tree.bind("<<TreeviewSelect>>", lambda e: self._show_detail())
        # 双击编辑
        self.tree.bind("<Double-1>", lambda e: self._on_double_click())

        # ---- 下半部分：详情面板 ----
        detail_frame = ttk.LabelFrame(main_pw, text="📋 单词详情", padding=5)
        main_pw.add(detail_frame, weight=2)

        self.detail_text = tk.Text(
            detail_frame, height=6, font=("Microsoft YaHei", 10),
            wrap=tk.WORD, relief=tk.FLAT, borderwidth=0,
            state=tk.DISABLED,
        )
        detail_scroll = ttk.Scrollbar(detail_frame, orient=tk.VERTICAL, command=self.detail_text.yview)
        self.detail_text.configure(yscrollcommand=detail_scroll.set)

        self.detail_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        detail_scroll.pack(side=tk.RIGHT, fill=tk.Y)

        # 配置详情文本样式
        self.detail_text.tag_configure("header", font=("Microsoft YaHei", 12, "bold"), foreground="#1a5276")
        self.detail_text.tag_configure("label", font=("Microsoft YaHei", 10, "bold"), foreground="#2c3e50")
        self.detail_text.tag_configure("content", font=("Microsoft YaHei", 10), lmargin2=10)
        self.detail_text.tag_configure("notes_label", font=("Microsoft YaHei", 10, "bold"), foreground="#7d3c98")
        self.detail_text.tag_configure("notes_content", font=("Microsoft YaHei", 9), foreground="#555555", lmargin2=10)

        # 操作按钮栏（含主窗口的录入按钮）
        btn_frame = ttk.Frame(self)
        btn_frame.pack(fill=tk.X, padx=10, pady=(3, 8))

        self.add_btn = ttk.Button(btn_frame, text="➕ 录入新单词")
        self.add_btn.pack(side=tk.LEFT, padx=(0, 5))

        ttk.Button(btn_frame, text="✏️ 编辑", command=self._edit_selected).pack(side=tk.LEFT, padx=(0, 5))
        ttk.Button(btn_frame, text="🗑️ 删除", command=self._delete_selected).pack(side=tk.LEFT, padx=(0, 5))
        ttk.Button(btn_frame, text="🔄 刷新", command=self.refresh).pack(side=tk.RIGHT)

        ttk.Label(btn_frame, text="💡 双击单词可编辑 | 选中后点删除可移除", foreground="gray",
                  font=("", 8)).pack(side=tk.RIGHT, padx=(0, 15))

    def _do_search(self):
        """根据搜索框内容过滤"""
        keyword = self.search_var.get().strip()
        if keyword:
            words = self.db.search_words(keyword)
        else:
            words = self.db.get_all_words()
        self._populate(words)

    def refresh(self, keyword: str = ""):
        """刷新列表"""
        self.all_words = self.db.get_all_words()
        self._populate(self.all_words)
        self.stats_label.config(text=f"共 {len(self.all_words)} 个单词")

    def _populate(self, words: List[Word]):
        """填充 Treeview（截断过长的文本）"""
        for item in self.tree.get_children():
            self.tree.delete(item)

        def _truncate(text: str, max_len: int = 40) -> str:
            """截断文本，换行转空格"""
            t = text.replace("\n", " ").replace("\r", " ")
            return t if len(t) <= max_len else t[:max_len-2] + "…"

        for w in words:
            source_map = {"local+ai": "📖+🤖", "local": "📖本地", "online": "🌐在线", "ai": "🤖AI", "manual": "✍手动", "wordbook": "📚词书"}
            # 熟练度显示
            prof_text = f"{w.proficiency}%"
            review_text = f"{w.review_stage}/7"
            values = (
                w.word,
                w.phonetic,
                w.part_of_speech,
                _truncate(w.chinese_meaning, 50),
                prof_text,
                review_text,
                source_map.get(w.source, w.source),
                w.created_at[:10],
            )
            self.tree.insert("", tk.END, iid=str(w.id), values=values)

    def _show_detail(self):
        """在详情面板显示选中单词的完整信息"""
        word = self.get_selected_word()
        dt = self.detail_text
        dt.configure(state=tk.NORMAL)
        dt.delete("1.0", tk.END)

        if not word:
            dt.insert(tk.END, "👆 点击上方列表中的单词查看详情", "content")
            dt.configure(state=tk.DISABLED)
            return

        # 标题行：单词 + 音标 + 来源
        source_icon = {"local+ai": "📖+🤖", "local": "📖", "online": "🌐", "ai": "🤖", "manual": "✍", "wordbook": "📚"}.get(word.source, "")
        header_text = f"{word.word}  {word.phonetic}  {source_icon}\n"
        dt.insert(tk.END, header_text, "header")

        # 学习进度
        if word.proficiency > 0 or word.review_count > 0:
            dt.insert(tk.END, f"📊 熟练度: {word.proficiency}/100  |  阶段: {word.review_stage}/7  |  复习: {word.review_count}次", "notes_label")
            if word.next_review_at:
                dt.insert(tk.END, f"  |  下次复习: {word.next_review_at[:10]}", "notes_content")
            dt.insert(tk.END, "\n")

        # 词性
        if word.part_of_speech:
            dt.insert(tk.END, f"词性：{word.part_of_speech}\n", "label")

        # 中文释义
        if word.chinese_meaning:
            dt.insert(tk.END, "释义：\n", "label")
            dt.insert(tk.END, f"{word.chinese_meaning}\n", "content")

        # 例句 + 翻译
        if word.example_sentence:
            dt.insert(tk.END, "例句：\n", "label")
            examples = word.example_sentence.split("\n")
            translations = word.example_translation.split("\n") if word.example_translation else []
            for i, ex in enumerate(examples):
                if ex.strip():
                    dt.insert(tk.END, f"  {ex.strip()}\n", "content")
                    if i < len(translations) and translations[i].strip():
                        dt.insert(tk.END, f"  → {translations[i].strip()}\n", "notes_content")

        # 笔记（搭配/近反义词等）
        if word.notes:
            dt.insert(tk.END, f"\n{word.notes}\n", "notes_content")

        dt.configure(state=tk.DISABLED)

    def get_selected_word(self) -> Word:
        """获取当前选中的 Word 对象"""
        sel = self.tree.selection()
        if not sel:
            return None
        return self.db.get_word_by_id(int(sel[0]))

    def _on_double_click(self):
        """双击行 → 编辑"""
        self._edit_selected()

    def _edit_selected(self):
        word = self.get_selected_word()
        if not word:
            messagebox.showinfo("提示", "请先选中一个单词")
            return
        if self.on_edit:
            self.on_edit(word)

    def _delete_selected(self):
        """删除选中单词"""
        word = self.get_selected_word()
        if not word:
            messagebox.showinfo("提示", "请先选中一个单词")
            return
        if messagebox.askyesno("确认删除", f"确定删除单词「{word.word}」吗？"):
            self.db.delete_word(word.id)
            self.refresh()
