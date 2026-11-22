#!/bin/zsh
set -e
cd -- "${0:A:h}"
if curl -fsS --max-time 2 http://127.0.0.1:5050/words/health >/dev/null 2>&1; then
  print '内置对话版本已运行：http://127.0.0.1:5050/words/'
  exit 0
fi
if [[ ! -x .venv-macos/bin/python ]]; then
  python3 -m venv .venv-macos
fi
if ! .venv-macos/bin/python -c 'import flask, PIL, fsrs, jsonschema, waitress, bs4, mdict_utils, nltk' >/dev/null 2>&1; then
  .venv-macos/bin/python -m pip install -r '英语单词/requirements.txt'
fi
print '忆溯启动中，请访问 http://127.0.0.1:5050 ，按 Ctrl+C 停止。'
.venv-macos/bin/python -u '英语单词/web_server.py'
