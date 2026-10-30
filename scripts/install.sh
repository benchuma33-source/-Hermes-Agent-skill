#!/usr/bin/env bash
# 一键安装。会创建 venv、装依赖、复制 skill、生成配置模板。
set -euo pipefail

RED=$'\033[31m'; GREEN=$'\033[32m'; YELLOW=$'\033[33m'; BOLD=$'\033[1m'; NC=$'\033[0m'
ok()   { echo "${GREEN}✓${NC} $*"; }
warn() { echo "${YELLOW}!${NC} $*"; }
die()  { echo "${RED}✗${NC} $*" >&2; exit 1; }
step() { echo; echo "${BOLD}== $* ==${NC}"; }

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

step "1/5 检查环境"

command -v python3 >/dev/null || die "缺少 python3"
PY_VER=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3,10) else 1)' \
  || die "需要 Python 3.10+，当前 $PY_VER"
ok "Python $PY_VER"

if command -v ffmpeg >/dev/null; then
  ok "ffmpeg 已安装"
else
  warn "缺少 ffmpeg —— 音频转码会失败"
  echo "    macOS:  brew install ffmpeg"
  echo "    Ubuntu: sudo apt install ffmpeg"
  read -r -p "   继续安装? [y/N] " ans
  [[ "${ans:-n}" =~ ^[Yy]$ ]] || exit 1
fi

ARCH=$(uname -m); OS=$(uname -s)
if [ "$OS" = "Darwin" ] && [ "$ARCH" = "arm64" ]; then
  ok "Apple Silicon —— 支持本地 TTS"
else
  warn "非 Apple Silicon（$OS/$ARCH）—— 只能用 API 模式"
fi

step "2/5 创建虚拟环境"

if [ -d .venv ]; then
  ok "已有 .venv"
else
  python3 -m venv .venv
  ok "已创建 .venv"
fi

step "3/5 安装依赖"

.venv/bin/pip install --quiet --upgrade pip
.venv/bin/pip install --quiet -r service/requirements.txt
ok "依赖安装完成"

step "4/5 复制 skill"

SKILL_DST="$HOME/.hermes/skills/software-development/spoken-summary-reply"
mkdir -p "$(dirname "$SKILL_DST")"
cp -r skills/spoken-summary-reply "$SKILL_DST"
ok "skill 已装到 $SKILL_DST"

step "5/5 生成配置"

if [ -f service/config.json ]; then
  ok "已存在 service/config.json，跳过"
else
  cp service/config.example.json service/config.json
  ok "已生成 service/config.json"
  warn "请编辑它选择模式：tts.mode = local 或 api"
fi

chmod +x service/tts service/asr

echo
echo "${BOLD}安装完成。${NC}"
echo
echo "下一步："
echo "  1. 编辑 ${BOLD}service/config.json${NC} 选模式（local 或 api）"
echo "  2. 跑 ${BOLD}./scripts/doctor.sh${NC} 自检"
echo "  3. 按 ${BOLD}docs/SETUP.md${NC} 第 4 步接到 Hermes"
echo
