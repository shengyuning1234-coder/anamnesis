#!/bin/sh
set -eu
cd -- "$(dirname -- "$0")"
if [ ! -f .env ]; then
  cp .env.example .env
  printf '%s\n' '已创建 .env。请填写生产域名和现有数据目录，再重新执行此脚本。'
  exit 1
fi
docker compose -f compose.yaml build --pull
docker compose -f compose.yaml up -d --wait --wait-timeout 1200
docker compose -f compose.yaml ps
