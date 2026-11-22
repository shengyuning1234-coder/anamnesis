"""
词书导入对话框
"""

import os
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from typing import List
from services.database import Database
from services.wordbook_service import WordBookService
from models.wordbook import WordBook, WordBookEntry


class WordBookDialog(tk.Toplevel):
    """词书管理对话框"""

    def __init__(self, parent, db: Database):
        super().__init__(parent)
        self.db = db
        self.wordbook_service = WordBookService(db)

        self.title("📚 词书管理")
        self.geometry("620x480")
        self.minsize(500, 380)
        self.transient(parent)
        self.grab_set()

        self._build_ui()
        self._refresh_book_list()

    def _build_ui(self):
        pad = {"padx": 15, "pady": 5}

        # 标题
        header = ttk.Frame(self)
        header.pack(fill=tk.X, **pad)
        ttk.Label(
            header, text="📚 导入标准词书",
            font=("Microsoft YaHei", 13, "bold"),
        ).pack(side=tk.LEFT)
        ttk.Button(
            header, text="📥 导入 CSV 词书", command=self._import_csv,
        ).pack(side=tk.RIGHT)

        ttk.Label(
            self,
            text="支持 CSV 格式词书（UTF-8/GBK），列：word, phonetic, part_of_speech, chinese_meaning...",
            foreground="gray", font=("", 9),
        ).pack(fill=tk.X, **pad)

        ttk.Separator(self, orient=tk.HORIZONTAL).pack(fill=tk.X, padx=15, pady=3)

        # 词书列表
        list_frame = ttk.Frame(self)
        list_frame.pack(fill=tk.BOTH, expand=True, padx=15, pady=5)

        columns = ("name", "total", "imported", "progress")
        self.tree = ttk.Treeview(
            list_frame, columns=columns, show="headings",
            selectmode="browse", height=10,
        )
        self.tree.heading("name", text="词书名称", anchor=tk.W)
        self.tree.heading("total", text="总词数", anchor=tk.CENTER)
        self.tree.heading("imported", text="已导入", anchor=tk.CENTER)
        self.tree.heading("progress", text="进度", anchor=tk.CENTER)

        self.tree.column("name", width=250, minwidth=120)
        self.tree.column("total", width=80, anchor=tk.CENTER)
        self.tree.column("imported", width=80, anchor=tk.CENTER)
        self.tree.column("progress", width=80, anchor=tk.CENTER)

        vsb = ttk.Scrollbar(list_frame, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscrollcommand=vsb.set)
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        vsb.pack(side=tk.RIGHT, fill=tk.Y)

        # 底部按钮
        btn_frame = ttk.Frame(self)
        btn_frame.pack(fill=tk.X, padx=15, pady=(5, 12))

        ttk.Button(
            btn_frame, text="🗑 删除选中词书", command=self._delete_book,
        ).pack(side=tk.LEFT)

        ttk.Button(
            btn_frame, text="📤 预览词书内容", command=self._preview_book,
        ).pack(side=tk.LEFT, padx=5)

        ttk.Button(
            btn_frame, text="关闭", command=self.destroy,
        ).pack(side=tk.RIGHT)

    def _refresh_book_list(self):
        self.tree.delete(*self.tree.get_children())
        books = self.db.get_all_word_books()
        for b in books:
            total, imported = self.db.get_book_entry_count(b.id)
            pct = f"{imported}/{total}" if total else "0/0"
            progress = f"{int(imported/total*100)}%" if total else "0%"
            self.tree.insert("", tk.END, iid=str(b.id), values=(b.name, total, imported, progress))

    def _import_csv(self):
        file_path = filedialog.askopenfilename(
            title="选择 CSV 词书文件",
            filetypes=[
                ("CSV 文件", "*.csv"),
                ("所有文件", "*.*"),
            ],
        )
        if not file_path:
            return

        # 解析预览
        field_names, rows = self.wordbook_service.parse_csv(file_path)
        if not rows:
            messagebox.showerror("错误", f"无法解析文件或文件无有效数据：\n{file_path}")
            return

        book_name = os.path.splitext(os.path.basename(file_path))[0]

        # 确认对话框
        preview_lines = []
        for i, row in enumerate(rows[:5]):
            preview_lines.append(
                f"  {row.get('word','')} — {row.get('chinese_meaning','')[:30]}"
            )

        msg = (
            f"将导入词书：{book_name}\n"
            f"共 {len(rows)} 个单词\n\n"
            f"预览（前5条）：\n" + "\n".join(preview_lines) +
            f"\n\n{'...' if len(rows) > 5 else ''}"
            f"\n\n列映射：{', '.join(field_names)}"
        )

        if not messagebox.askyesno("确认导入", msg):
            return

        book_id = self.wordbook_service.import_from_csv(file_path, book_name)
        if book_id:
            messagebox.showinfo("成功", f"词书「{book_name}」导入成功！\n共 {len(rows)} 个单词。")
            self._refresh_book_list()
        else:
            messagebox.showerror("失败", "导入失败，请检查文件格式。")

    def _delete_book(self):
        selection = self.tree.selection()
        if not selection:
            messagebox.showwarning("提示", "请先选中一个词书")
            return

        book_id = int(selection[0])
        book = self.db.get_word_book_by_id(book_id)
        if not book:
            return

        if messagebox.askyesno("确认删除", f"确定删除词书「{book.name}」及其所有词条吗？"):
            self.db.delete_word_book(book_id)
            self._refresh_book_list()

    def _preview_book(self):
        selection = self.tree.selection()
        if not selection:
            messagebox.showwarning("提示", "请先选中一个词书")
            return

        book_id = int(selection[0])
        book = self.db.get_word_book_by_id(book_id)
        if not book:
            return

        # 取前 20 条未导入的
        entries = self.db.get_unimported_entries(book_id, 20)
        lines = [f"词书：{book.name}", f"未导入词条预览（前{len(entries)}条）：", ""]
        for e in entries:
            lines.append(f"  {e.word} — {e.chinese_meaning[:40]}")
        if not entries:
            lines.append("  （全部已导入）")

        messagebox.showinfo("词书预览", "\n".join(lines))
