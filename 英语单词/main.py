#!/usr/bin/env python3
"""
英语单词背诵记忆系统 — 启动入口

使用方法：
    python3 main.py
"""

import sys
import os

# 确保项目根目录在 sys.path 中
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from gui.main_window import MainWindow


def main():
    app = MainWindow()
    app.mainloop()


if __name__ == "__main__":
    main()
