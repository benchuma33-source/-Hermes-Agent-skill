# 踩过的坑

这些都是实际调试出来的，不是猜的。按"症状 → 原因 → 解法"组织。

如果你遇到没列在这里的问题，先跑 `./scripts/doctor.sh`。

---

## 1. Ogg/Opus 在 macOS 上播不完

**症状**

语音听起来说三四个字就断了，但音频文件本身是完整的（用 `ffprobe` 看时长正常）。
更迷惑的是 `afplay` 返回码是 0，从脚本层面完全看不出错误。

**验证方法**

```bash
F=你的文件.ogg
echo "文件时长: $(ffprobe -v error -show_entries format=duration -of csv=p=0 $F)"
SECONDS=0; afplay $F; echo "实际播放: ${SECONDS}s"
```

如果两个数差很远（比如文件 23 秒、播放 1 秒），就是这个坑。

**原因**

macOS 的 Opus 支持一直有毛病。`afplay` 播 Opus 时会提前结束且不报错。

**解法**

让 Hermes 输出标准格式，不要 Ogg：

```bash
hermes config set tts.providers.voice.voice_compatible false --force
```

`voice_compatible: true` 会让 Hermes 按"聊天软件语音气泡"的规格输出 Ogg/Opus。
Telegram 这类平台需要它，**本机播放不需要**。

---

## 2. 模型在句子中间吐出精确 3 秒的静音

**症状**

一段 100 字的文本，生成的音频 9.76 秒，但其中 5.5 秒是空白，
断成"说几秒 → 静 3 秒 → 再说几秒"。

**验证方法**

```bash
python - <<'EOF'
import soundfile as sf, numpy as np
a, sr = sf.read('你的文件.wav')
if a.ndim > 1: a = a[:, 0]
f = int(sr * 0.02); n = len(a) // f
rms = np.sqrt(np.mean(a[:n*f].reshape(n, f) ** 2, axis=1))
th = max(rms.max() * 0.05, 0.01); v = rms > th
print(f"有声占比 {v.sum() / n * 100:.1f}%  正常应 > 80%")
EOF
```

低于 60% 就是这个问题。

**原因**

模型生成完内容后继续吐静音帧，每段都是精确的 2.95~3.10 秒。
文本越长累积越多。

**解法**

代码里已经处理了（`server.py` 的 `_split_for_tts` + `_compress_pauses`）：

1. **分句合成** —— 按 `。！？；` 切，每句不超过 60 字。
   不分句的话长文本内容还会丢（实测 100 字只生成出 3.5 秒有声内容）。
2. **压缩停顿** —— 超过 0.35 秒的静音压到 0.2 秒。

**关键**：阈值必须用**相对峰值**（5%），不能用固定值。
不同句子音量差好几倍，固定阈值会误裁或裁不干净。

---

## 3. `ref_audio` 参考音克隆模式会跑飞

**症状**

"今天天气不错。"用参考音模式生成过 **60 秒**（几乎全是静音），
换 `instruct` 模式只要 1.12 秒。

而且完全可重现——同样的 seed、同样的文本，每次都是 60 秒。

**原因**

不确定是模型 bug 还是 MLX 实现问题。总之 `ref_audio + ref_text`
这条路在当前版本不稳定。

**解法**

用 `instruct` 模式，靠文字描述控制音色：

```json
"voice_instruction": "高冷御姐音：成熟女性的清冷声线，音色醇厚有质感，语调从容、略带距离感，语速平缓沉稳。"
```

配合固定 `seed` 和低 `temperature`，音色足够稳定，且不会跑飞。

想换音色就改这段文字，重启服务即可。

---

## 4. temperature 0.4 会偶发吐长尾静音

**症状**

同样一句话，有时正常（0.04 秒尾静音），有时带 2.9 秒空白，偶尔跑飞到 60 秒。

**验证**

```python
for temp in [0.4, 0.2, 0.0]:
    # 比较同一文本的尾静音长度
```

实测数据（4bit）：

| temperature | "老师，现在测试一下通过命令行调用合成。" |
|---|---|
| 0.4 | 7.12s，尾静音 2.92s |
| 0.2 | 9.60s，尾静音 0.04s |
| 0.0 | 6.64s，尾静音 0.04s |

**解法**

`temperature: 0.2`。音色差异听不出来，稳定性明显更好。

代码里还有 `max_utterance_sec: 30` 硬上限兜底。

---

## 5. 千问 ASR 的端点很刁

试了四种调用方式，只有一种能用：

| 方式 | 结果 |
|---|---|
| `POST /compatible-mode/v1/audio/transcriptions` | ❌ 404，端点不存在 |
| `POST /compatible-mode/v1/chat/completions` + `input_audio` | ❌ 400 `dedicated task asr does not support this input` |
| `POST /api/v1/services/audio/asr/transcription` | ❌ 只收公网 URL，本地文件不行 |
| `POST /api/v1/services/aigc/multimodal-generation/generation` + data URL | ✅ 可用 |

**能用的写法**

```json
{
  "model": "qwen3-asr-flash",
  "input": {
    "messages": [{
      "role": "user",
      "content": [{"audio": "data:audio/wav;base64,<BASE64>"}]
    }]
  }
}
```

返回值取 `output.choices[0].message.content[0].text`。

**另外**：`qwen-audio-3.0-asr-flash` 和 `fun-asr-flash` 会报
`AllocationQuota.FreeTierOnly`（免费额度耗尽），不是接口问题。

---

## 6. Python 的 SSL 证书不全，urllib 报错

**症状**

```
ssl.SSLCertVerificationError: certificate verify failed:
unable to get local issuer certificate
```

但同一台机器上 `curl` 访问正常。

**原因**

某些 Python 环境（尤其是 homebrew/china 镜像装的）没有正确的 CA 包。

**解法**

`asr` 和 `tts` 里所有外部 HTTP 请求都用 `curl` 子进程，不用 `urllib`。
这是刻意的，别"优化"回 urllib。

---

## 7. 分句后变慢

**症状**

完整版模型 + 40 字分句，RTF 1.5~2.8，比实时慢，播报会卡。

**原因**

每句都要单独跑一次模型，固定开销约 0.8 秒/次。

**解法**

| 配置 | RTF |
|---|---|
| full + 分句 40 字 | 1.5 ~ 2.8 |
| 4bit + 分句 60 字 | **0.71** |

两件事一起做：
1. **换 4bit**（最大单点收益，快 3 倍，音质听不出差别）
2. **分句粒度别太小**（60 字比 40 字少约 1/3 调用次数）

RTF < 1 就能边合成边播，实际感受几乎不等。

---

## 8. 下载模型卡住或极慢

**症状**

`huggingface.co` 超时，或者速度只有 2 KB/s（7.6 GB 要下 34 天）。

**解法**

用国内镜像：

```bash
export HF_ENDPOINT=https://hf-mirror.com
```

实测速度 3.4 MB/s。不需要代理。

**注意**：如果之前下了一半，`blobs/` 里会留残缺文件，
`du -sh` 看模型目录可能显示 1.2 MB（因为 snapshots 里是符号链接，
`du` 不跟随）。用 `du -shL` 或看 `blobs/` 里实际文件大小。

---

## 9. 蓝牙耳机播放报 -66681

**症状**

```
AudioQueueStart failed (-66681)
```

连以前能播的 wav 也播不了。

**原因**

默认音频输出是蓝牙设备，且掉线/休眠了。

**解法**

```bash
system_profiler SPAudioDataType | grep -A3 "Default Output Device: Yes"
```

看是不是 `Transport: Bluetooth`。切到内置扬声器或有线即可，
不是代码问题。

---

## 10. skill 没生效

**症状**

回复里没有摘要块，也没声音。

**原因**

1. skill 没装到正确位置
2. 或者 AI 忘了遵守（skill 是软约束）

**解法**

```bash
ls ~/.hermes/skills/software-development/spoken-summary-reply/SKILL.md
```

在的话就是 AI 忘了。直接说「读一下」提醒它。
如果经常忘，可以把规则同时写进 memory（权重更高，但占每轮 token）。
