# 安装

## 前置条件

| 需要 | 版本 | 说明 |
|---|---|---|
| Hermes Agent | ≥ 0.21 | `hermes --version` |
| Python | ≥ 3.10 | |
| ffmpeg | 任意 | 音频转码，**必需** |
| Apple Silicon Mac | — | 仅本地 TTS 需要；API 模式跨平台 |

---

## 第 1 步：跑安装脚本

```bash
git clone <this-repo> ~/hermes-voice
cd ~/hermes-voice
chmod +x scripts/*.sh
./scripts/install.sh
```

脚本会做：检查环境 → 建 venv → 装依赖 → 复制 skill → 生成配置模板。

---

## 第 2 步：选模式

```bash
cp service/config.example.json service/config.json
```

编辑 `service/config.json`，先决定 TTS 用哪种：

### 选项 A：local（本地，仅 Apple Silicon）

```json
"tts": {
  "mode": "local",
  "local": { "model": "4bit" }
}
```

- 完全离线、免费
- 首次要下模型 3~8 GB
- 需要 `mlx-audio`（install.sh 已装）

国内下载模型先设镜像：

```bash
export HF_ENDPOINT=https://hf-mirror.com
```

### 选项 B：api（云端，跨平台）

```json
"tts": {
  "mode": "api",
  "api": {
    "provider": "openai",
    "base_url": "https://api.openai.com/v1",
    "api_key": "${OPENAI_API_KEY}",
    "model": "gpt-4o-mini-tts",
    "voice": "alloy"
  }
}
```

`${OPENAI_API_KEY}` 会从环境变量或 `~/.hermes/.env` 读。
**不要把真实 key 写进 config.json**（`.gitignore` 已排除，但习惯要养成）。

---

## 第 3 步：启动本地服务（仅 local 模式）

```bash
.venv/bin/python service/server.py --config service/config.json
```

首次会下载模型并编译，等几十秒。日志里出现
`服务启动 http://127.0.0.1:8766` 就好了。

**平时不用手动起** —— `tts` 命令连不上会自动拉起一次。

---

## 第 4 步：接到 Hermes

把 `<ABS>` 换成仓库的绝对路径：

```bash
ABS=$(pwd)

hermes config set tts.provider voice
hermes config set tts.providers.voice.type command --force
hermes config set tts.providers.voice.command "\"$ABS/service/tts\" {input_path} {output_path}" --force
hermes config set tts.providers.voice.voice_compatible false --force

hermes config set stt.provider voice
hermes config set stt.providers.voice.type command --force
hermes config set stt.providers.voice.command "\"$ABS/service/asr\" {input_path}" --force
hermes config set stt.providers.voice.output_format txt --force
```

**`voice_compatible` 必须是 `false`。**
设成 `true` 会让 Hermes 输出 Ogg/Opus，macOS 上播不完
（见 [TROUBLESHOOTING.md](TROUBLESHOOTING.md#1-oggopus-在-macos-上播不完)）。

---

## 第 5 步：自检

```bash
./scripts/doctor.sh
```

全 PASS 就能用了。有 FAIL 按提示修。

---

## 第 6 步：试一下

在 Hermes 里：

```
/voice on
```

然后按住 `ctrl+b` 说话。第一次会弹麦克风权限，允许。

回复会变成两段：`> 🔊` 开头那段被朗读，`---` 之后是文字详情。

---

## 卸载

```bash
hermes config set tts.provider edge
hermes config set stt.provider local
rm -rf ~/.hermes/skills/software-development/spoken-summary-reply
rm -rf ~/hermes-voice
```

模型缓存在 `~/.cache/huggingface/hub/`，想省空间可以手动删
`models--mlx-community--Breeze-TTS-2-*`。

---

## 下一步

- 配置项全部字段 → [CONFIG.md](CONFIG.md)
- 出问题了 → [TROUBLESHOOTING.md](TROUBLESHOOTING.md)
