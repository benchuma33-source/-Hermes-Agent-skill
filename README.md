# Hermes Voice Dual-Track

给 [Hermes Agent](https://github.com/NousResearch/hermes-agent) 加一套**语音双轨输出**：
先听摘要，再看详情。

```
🔊 朗读这段（2~4 句口语摘要，15 秒内）
────────────────────────────
📄 详细内容（表格、代码、路径 —— 只看，不念）
```

表格和代码念出来很难听。这个项目让 AI 先给一段人能听懂的口头摘要，
完整细节照常显示在下面。

---

## 它解决什么问题

语音助手最大的败笔是**什么都念**：

> "文件路径是杠 Volumes 杠 ANTX 杠 AI 语音对话生成架构 杠 breeze 杠 service，
> 实时率是零点八二，详见 R-E-A-D-M-E 点 M-D 的踩坑章节第一条..."

而它真正的价值是让你**在做别的事的时候也能跟上进度**。

所以正确的做法是分层：

| 层 | 内容 | 处理 |
|---|---|---|
| 语音层 | 结论、状态、下一步 | 朗读 |
| 文字层 | 表格、代码、路径、数据 | 只看 |

---

## 两种 TTS 后端

| 模式 | 后端 | 特点 |
|---|---|---|
| **local** | Breeze TTS 2 (MLX) | 完全离线、免费、Apple Silicon 专用 |
| **api** | 任意 OpenAI 兼容 / DashScope | 跨平台、要联网、按量计费 |

ASR 同理，支持本地 mlx-whisper 或云端 API。

**两种后端共用同一套 skill 和调用约定**，改一个配置文件就能切换。

---

## 快速开始

```bash
git clone https://github.com/benchuma33-source/hermes-voice-dual-track ~/hermes-voice
cd ~/hermes-voice
./scripts/install.sh
```

安装脚本会：
1. 检查依赖（Python、ffmpeg、可选 MLX）
2. 创建虚拟环境
3. 复制 skill 到 `~/.hermes/skills/`
4. 生成配置模板
5. 提示你填 API key（如果选 API 模式）

然后编辑 `service/config.json`，选 `local` 或 `api`。

详细步骤见 [docs/SETUP.md](docs/SETUP.md)。

---

## 手动安装（想自己控制的话）

### 1. 依赖

```bash
# macOS
brew install ffmpeg

# Python 3.10+
python3 -m venv .venv
.venv/bin/pip install -r service/requirements.txt
```

本地 TTS 还要（仅 Apple Silicon）：

```bash
.venv/bin/pip install mlx-audio
```

### 2. 配置

```bash
cp service/config.example.json service/config.json
vim service/config.json      # 选模式、填 key
```

### 3. 启动本地 TTS 服务（仅 local 模式需要）

```bash
.venv/bin/python service/server.py --config service/config.json
```

### 4. 接到 Hermes

```bash
hermes config set tts.provider voice
hermes config set tts.providers.voice.type command --force
hermes config set tts.providers.voice.command '"/abs/path/to/service/tts" {input_path} {output_path}' --force
hermes config set tts.providers.voice.voice_compatible false --force

hermes config set stt.provider voice
hermes config set stt.providers.voice.type command --force
hermes config set stt.providers.voice.command '"/abs/path/to/service/asr" {input_path}' --force
hermes config set stt.providers.voice.output_format txt --force
```

**注意 `voice_compatible` 必须是 `false`。**

设成 `true` 会让 Hermes 输出 Ogg/Opus，而 macOS 的 Opus 播放有毛病——
`afplay` 播 1 秒就"成功"退出，还以为播完了。这个坑踩过，见
[docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md#1-oggopus-在-macos-上播不完)。

### 5. 装 skill

```bash
cp -r skills/spoken-summary-reply ~/.hermes/skills/software-development/
```

---

## 配置说明

`service/config.json`：

```json
{
  "tts": {
    "mode": "local",
    "local": {
      "model": "mlx-community/Breeze-TTS-2-mlx-4bit",
      "voice_instruction": "高冷御姐音：成熟女性的清冷声线...",
      "seed": 77,
      "temperature": 0.2,
      "max_chars": 60
    },
    "api": {
      "provider": "openai",
      "base_url": "https://api.openai.com/v1",
      "api_key": "${OPENAI_API_KEY}",
      "model": "gpt-4o-mini-tts",
      "voice": "alloy",
      "format": "mp3"
    }
  },
  "asr": {
    "mode": "api",
    "api": {
      "provider": "dashscope",
      "model": "qwen3-asr-flash",
      "api_key": "${DASHSCOPE_API_KEY}"
    }
  }
}
```

`${VAR}` 会从环境变量或 `~/.hermes/.env` 读取，**不要把 key 写进文件**。

完整字段见 [docs/CONFIG.md](docs/CONFIG.md)。

---

## 支持的 API 服务

### TTS

| 服务 | provider | 说明 |
|---|---|---|
| OpenAI | `openai` | 标准 `/audio/speech` |
| 任意 OpenAI 兼容 | `openai` | 填你的 `base_url` 即可 |
| 阿里 DashScope | `dashscope` | `qwen3-tts-flash` |

### ASR

| 服务 | provider | 说明 |
|---|---|---|
| 阿里 DashScope | `dashscope` | `qwen3-asr-flash`，中文强 |
| OpenAI | `openai` | `whisper-1`，标准 `/audio/transcriptions` |
| 任意 OpenAI 兼容 | `openai` | 填 `base_url` |

---

## 它长什么样

实际输出（`> 🔊` 开头那段会被朗读，`---` 之后只显示）：

```
> 🔊 老师，语音服务接好了。合成用本地模型，识别走千问接口。
>    中间踩了四个坑，主要是音频格式的问题，细节在下面。

---

## 已完成

| 组件 | 状态 | 耗时 |
|---|---|---|
| TTS  | 完成 | 0.82 RTF |
| ASR  | 完成 | 1.26s / 8s 音频 |

文件位置：~/.hermes/config.yaml
```

---

## 项目结构

```
hermes-voice-dual-track/
├── README.md
├── LICENSE
├── .gitignore
├── skills/
│   └── spoken-summary-reply/
│       └── SKILL.md          输出规范（AI 读的）
├── service/
│   ├── server.py             本地 TTS 常驻服务
│   ├── tts                   TTS 统一入口（本地/API 自动分流）
│   ├── asr                   ASR 统一入口
│   ├── config.example.json   配置模板
│   └── requirements.txt
├── scripts/
│   ├── install.sh            一键安装
│   └── doctor.sh             环境自检
└── docs/
    ├── SETUP.md              详细安装
    ├── CONFIG.md             全部配置项
    └── TROUBLESHOOTING.md    踩过的坑
```

---

## 已知限制

- **本地模式**仅 Apple Silicon（MLX）。Intel Mac / Linux 请用 API 模式。
- **Breeze TTS 2 权重是非商业许可**。自己用没问题，商用请换模型或改用 API 模式。
- 首次启动要下模型（3~8 GB），国内建议用镜像：

  ```bash
  export HF_ENDPOINT=https://hf-mirror.com
  ```

- ASR 走 API 时断网不可用（TTS 本地模式仍可用）。
- skill 是**软约束**——AI 理论上可能忘记生成摘要。忘了就是没声音，很容易发现。

---

## License

MIT。见 [LICENSE](LICENSE)。

Breeze TTS 2 的**模型权重**另有许可，与本仓库的代码许可无关，使用前请自行确认。
