#!/usr/bin/env bash
# 环境自检：把能出错的地方一次查完。
set -uo pipefail

RED=$'\033[31m'; GREEN=$'\033[32m'; YELLOW=$'\033[33m'; BOLD=$'\033[1m'; NC=$'\033[0m'
PASS=0; FAIL=0; WARN=0
ok()   { echo "  ${GREEN}PASS${NC}  $*"; PASS=$((PASS+1)); }
bad()  { echo "  ${RED}FAIL${NC}  $*"; FAIL=$((FAIL+1)); }
warn() { echo "  ${YELLOW}WARN${NC}  $*"; WARN=$((WARN+1)); }

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
CFG="service/config.json"
PY=".venv/bin/python"

echo "${BOLD}=== 环境 ===${NC}"
command -v python3 >/dev/null && ok "python3: $(python3 -V 2>&1)" || bad "缺少 python3"
[ -x "$PY" ] && ok "venv: $PY" || bad "缺少 .venv（先跑 scripts/install.sh）"
command -v ffmpeg >/dev/null && ok "ffmpeg: $(ffmpeg -version 2>/dev/null | head -1 | cut -d' ' -f3)" || bad "缺少 ffmpeg"
command -v curl >/dev/null && ok "curl 可用" || bad "缺少 curl"

echo
echo "${BOLD}=== 配置 ===${NC}"
if [ -f "$CFG" ]; then
  ok "找到 $CFG"
  TTS_MODE=$("$PY" -c "import json;print(json.load(open('$CFG'))['tts']['mode'])" 2>/dev/null)
  ASR_MODE=$("$PY" -c "import json;print(json.load(open('$CFG'))['asr']['mode'])" 2>/dev/null)
  ok "tts.mode = $TTS_MODE"
  ok "asr.mode = $ASR_MODE"

  # key 是否为空
  if [ "$TTS_MODE" = "api" ]; then
    K=$("$PY" - <<'EOF' 2>/dev/null
import json,os,sys
sys.path.insert(0,'service')
from importlib.machinery import SourceFileLoader
m=SourceFileLoader('tts','service/tts').load_module()
cfg=m.load_config()
print(cfg.get('tts',{}).get('api',{}).get('api_key',''))
EOF
)
    [ -n "$K" ] && ok "TTS API key 已配置" || bad "TTS API key 为空"
  fi

  if [ "$ASR_MODE" = "api" ]; then
    K=$("$PY" - <<'EOF' 2>/dev/null
import sys
sys.path.insert(0,'service')
from importlib.machinery import SourceFileLoader
m=SourceFileLoader('asr','service/asr').load_module()
cfg=m.load_config()
print(cfg.get('asr',{}).get('api',{}).get('api_key',''))
EOF
)
    [ -n "$K" ] && ok "ASR API key 已配置" || bad "ASR API key 为空"
  fi
else
  bad "缺少 ${CFG}（cp service/config.example.json service/config.json）"
  TTS_MODE=""; ASR_MODE=""
fi

echo
echo "${BOLD}=== 本地模型（仅 local 模式需要）${NC}"
if [ "$TTS_MODE" = "local" ]; then
  HF_CACHE="$HOME/.cache/huggingface/hub"
  if ls -d "$HF_CACHE"/models--mlx-community--Breeze-TTS-2-* >/dev/null 2>&1; then
    for d in "$HF_CACHE"/models--mlx-community--Breeze-TTS-2-*; do
      SZ=$(python3 -c "import os,sys;b='$d/blobs';n=sum(os.path.getsize(os.path.join(b,f)) for f in os.listdir(b) if not f.endswith('.incomplete'));print(f'{n/1e9:.1f}GB')" 2>/dev/null || echo "?")
      ok "已下载: $(basename "$d" | sed 's/models--mlx-community--//')  ($SZ)"
    done
  else
    warn "未发现已下载模型（首次运行会自动下载 3~8 GB）"
    echo "         国内建议先: export HF_ENDPOINT=https://hf-mirror.com"
  fi

  PORT=$("$PY" -c "import json;print(json.load(open('$CFG'))['tts']['local'].get('port',8766))" 2>/dev/null || echo 8766)
  if curl -s --max-time 3 "http://127.0.0.1:$PORT/health" >/dev/null 2>&1; then
    ok "常驻服务在跑（:${PORT}）"
  else
    warn "常驻服务未运行（tts 首次调用会自动拉起）"
  fi
fi

echo
echo "${BOLD}=== Hermes 配置 ===${NC}"
if command -v hermes >/dev/null; then
  ok "hermes CLI 可用"
  H_TTS=$(hermes config 2>/dev/null | grep -A2 '^tts:' | grep 'provider:' | head -1 | awk '{print $2}')
  H_STT=$(hermes config 2>/dev/null | grep -A2 '^stt:' | grep 'provider:' | head -1 | awk '{print $2}')
  [ "$H_TTS" = "voice" ] && ok "tts.provider = voice" || warn "tts.provider = ${H_TTS:-未设置}"
  [ "$H_STT" = "voice" ] && ok "stt.provider = voice" || warn "stt.provider = ${H_STT:-未设置}"

  # voice_compatible 必须是 false
  VC=$(hermes config 2>/dev/null | grep -A6 'voice_compatible' | grep 'voice_compatible' | head -1 | awk '{print $2}')
  if [ "$VC" = "True" ] || [ "$VC" = "true" ]; then
    bad "tts.providers.voice.voice_compatible = true —— 会输出 Ogg/Opus，macOS 播不完"
    echo "         修：hermes config set tts.providers.voice.voice_compatible false --force"
  fi
else
  warn "找不到 hermes CLI"
fi

SKILL="$HOME/.hermes/skills/software-development/spoken-summary-reply/SKILL.md"
[ -f "$SKILL" ] && ok "skill 已安装" || warn "skill 未安装"

echo
echo "${BOLD}=== 结果 ===${NC}"
echo "  通过 $PASS / 警告 $WARN / 失败 $FAIL"
[ "$FAIL" -eq 0 ] && exit 0 || exit 1
