#!/bin/zsh
set -e
cd -- "${0:A:h}"
if ! docker info >/dev/null 2>&1; then
  print '请先启动 Docker Desktop，再重新运行此文件。'
  exit 1
fi
if [[ ! -f '.local/chat-runtime/.env' ]]; then
  python3 - <<'PY'
from pathlib import Path
import secrets
p = Path('.local/chat-runtime/.env')
p.parent.mkdir(parents=True, exist_ok=True)
with p.open('x') as f:
    f.write('CHAT_POSTGRES_PASSWORD=' + secrets.token_urlsafe(32) + '\n')
p.chmod(0o600)
PY
fi
docker compose --env-file .local/chat-runtime/.env -f compose.macos-chat.yaml up -d
print '内置对话启动中：http://127.0.0.1:5050/words/?tab=chat'
print '首次启动请稍候。后台服务不会随终端关闭而退出。'
