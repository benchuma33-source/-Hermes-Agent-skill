# 配置项

全部字段。文件是 `service/config.json`。

---

## `tts`

### `tts.mode`

| 值 | 说明 |
|---|---|
| `local` | 本机常驻服务（Breeze TTS 2 / MLX），仅 Apple Silicon |
| `api` | 云端接口 |

### `tts.local`（local 模式）

| 字段 | 默认 | 说明 |
|---|---|---|
| `model` | `4bit` | `4bit`(3GB,快) / `8bit`(4.6GB) / `full`(7.6GB,慢2-4倍) |
| `voice_instruction` | 高冷御姐音… | 文字描述控制音色，改这个换声音 |
| `seed` | `77` | 固定随机种子，保证音色稳定 |
| `temperature` | `0.2` | **别超过 0.3**，高了会吐长静音甚至跑飞 |
| `max_chars` | `60` | 每句最多多少字。太小变慢，太大会丢内容 |
| `max_utterance_sec` | `30` | 单次合成硬上限，防止跑飞 |
| `port` | `8766` | 常驻服务端口 |

**换音色**：改 `voice_instruction`，重启服务。

**模型对比**（实测，同一段 130 字文本）：

| 模型 | RTF | 说明 |
|---|---|---|
| `4bit` | 0.71 | 默认，音质与 full 听不出差别 |
| `full` | 1.5~2.8 | 理论最好，但明显慢 |

### `tts.api`（api 模式）

| 字段 | 默认 | 说明 |
|---|---|---|
| `provider` | `openai` | `openai` / `dashscope` |
| `base_url` | `https://api.openai.com/v1` | 兼容接口可改成自己的 |
| `api_key` | `${OPENAI_API_KEY}` | 写 `${变量名}`，值放环境变量 |
| `model` | `gpt-4o-mini-tts` | |
| `voice` | `alloy` | 各家音色名不同 |
| `format` | `mp3` | mp3 / wav / opus / aac / flac |
| `speed` | `1.0` | 部分服务支持 |
| `instructions` | — | 部分模型支持（如 gpt-4o-mini-tts） |

**DashScope 特殊**：`provider: "dashscope"` 会走原生接口
（`/api/v1/services/aigc/multimodal-generation/generation`），
因为 OpenAI 兼容的 `/audio/speech` 在 DashScope 上是 404。

---

## `asr`

### `asr.mode`

| 值 | 说明 |
|---|---|
| `local` | 本机模型（mlx-whisper / faster-whisper） |
| `api` | 云端接口 |

### `asr.local`

| 字段 | 默认 | 说明 |
|---|---|---|
| `engine` | `mlx-whisper` | `mlx-whisper`(Apple Silicon 最快) / `faster-whisper`(跨平台) |
| `model` | `mlx-community/whisper-large-v3-turbo` | mlx-whisper 用 |
| `size` | `base` | faster-whisper 用：tiny/base/small/medium/large-v3 |
| `language` | `null` | `null` = 自动检测，或写 `zh` / `en` |

### `asr.api`

| 字段 | 默认 | 说明 |
|---|---|---|
| `provider` | `dashscope` | `dashscope` / `openai` |
| `base_url` | `https://dashscope.aliyuncs.com` | |
| `api_key` | `${DASHSCOPE_API_KEY}` | |
| `model` | `qwen3-asr-flash` | 或 `whisper-1`（openai） |

---

## 环境变量

`config.json` 里写 `${VAR}`，运行时按顺序查找：

1. 进程环境变量
2. `~/.hermes/.env` 里的 `VAR=值`

找不到就是空字符串，测试时会报「api_key 为空」。

---

## 常见组合

### 全本地（离线、免费、仅 Apple Silicon）

```json
{
  "tts": { "mode": "local", "local": { "model": "4bit" } },
  "asr": { "mode": "local", "local": { "engine": "mlx-whisper" } }
}
```

### 本地合成 + 云端识别（**推荐**）

中文识别用云端准确率高，合成用本地省延迟和费用：

```json
{
  "tts": { "mode": "local" },
  "asr": { "mode": "api", "api": { "provider": "dashscope" } }
}
```

### 全云端（Linux / Intel Mac / 无显卡）

```json
{
  "tts": { "mode": "api", "api": { "provider": "openai" } },
  "asr": { "mode": "api", "api": { "provider": "openai" } }
}
```

---

## 调优

**嫌慢**

1. `tts.local.model` 改 `4bit`
2. `max_chars` 从 60 提到 80（减少调用次数，但每句更长）

**嫌音色不稳**

1. `temperature` 降到 0.1
2. `seed` 固定不变
3. 别用参考音克隆模式（会跑飞，见 TROUBLESHOOTING）

**嫌停顿不自然**

`max_chars` 调小到 40，句子更短，停顿更多但更自然。
代价是慢一些。
