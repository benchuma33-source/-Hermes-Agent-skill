#!/usr/bin/env python3
"""
本地 TTS 常驻服务（Breeze TTS 2 / MLX）

    python server.py --config config.json

为什么常驻：模型加载一次要几秒。每次合成都重载的话对话没法用。

设计要点（每条都是踩坑换来的，改之前请看 docs/TROUBLESHOOTING.md）：
  · MLX 要求加载与推理在同一线程 → 全部走单线程 executor
  · 模型会吐精确 3 秒的句中静音 → 分句合成 + 压缩停顿
  · ref_audio 参考音克隆模式会跑飞（生成过 60 秒） → 用 instruct 模式
  · 只监听 127.0.0.1
"""
from __future__ import annotations

import argparse
import io
import json
import logging
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Optional

import numpy as np
import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("voice-tts")

HERE = Path(__file__).resolve().parent

# 模型注册表：短名 → HF 仓库
MODELS = {
    "4bit": "mlx-community/Breeze-TTS-2-mlx-4bit",
    "8bit": "mlx-community/Breeze-TTS-2-mlx-8bit",
    "full": "mlx-community/Breeze-TTS-2-mlx",
}

DEFAULTS = {
    "model": "4bit",
    "voice_instruction": (
        "高冷御姐音：成熟女性的清冷声线，音色醇厚有质感，"
        "语调从容、略带距离感，语速平缓沉稳。"
    ),
    "seed": 77,
    # 0.4 时模型会偶发吐 2~3 秒尾静音，甚至整段跑飞（"你好"生成过 60 秒）。
    # 0.2 稳定得多，音色听不出差别。
    "temperature": 0.2,
    "max_chars": 60,
    "max_utterance_sec": 30,
    "port": 8766,
}

_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="tts")
_model = None
_model_key: Optional[str] = None
_load_error: Optional[str] = None
_cfg: dict = dict(DEFAULTS)
_stats = {"requests": 0, "audio_seconds": 0.0, "synth_seconds": 0.0}

app = FastAPI(title="Local TTS Service")


# ---------------------------------------------------------------------------
def load_config(path: Optional[str]) -> dict:
    cfg = dict(DEFAULTS)
    if path and Path(path).exists():
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
        local = (raw.get("tts") or {}).get("local") or {}
        for k in DEFAULTS:
            if k in local:
                cfg[k] = local[k]
        m = cfg["model"]
        cfg["model_key"] = m if m in MODELS else "4bit"
        cfg["model_id"] = MODELS.get(cfg["model_key"], m)
    else:
        cfg["model_key"] = DEFAULTS["model"]
        cfg["model_id"] = MODELS[DEFAULTS["model"]]
    return cfg


# ---------------------------------------------------------------------------
def _load_model() -> None:
    global _model, _model_key, _load_error
    key = _cfg["model_key"]
    if _model is not None and _model_key == key:
        return
    try:
        from mlx_audio.tts.utils import load_model

        logger.info("加载模型 %s (%s)…", key, _cfg["model_id"])
        t0 = time.time()
        _model = load_model(_cfg["model_id"])
        _model_key = key
        _load_error = None
        logger.info("加载完成，耗时 %.2fs", time.time() - t0)
    except Exception as e:  # noqa: BLE001
        _load_error = str(e)
        _model = None
        logger.exception("模型加载失败")


def _generate(text: str) -> tuple[np.ndarray, int]:
    chunks = []
    sr = 24000
    for r in _model.generate(
        text,
        instruct=_cfg["voice_instruction"],
        seed=_cfg["seed"],
        temperature=_cfg["temperature"],
    ):
        chunks.append(np.asarray(r.audio, dtype=np.float32).reshape(-1))
        if getattr(r, "sample_rate", None):
            sr = int(r.sample_rate)
    if not chunks:
        raise RuntimeError("模型没有产出音频")
    return np.concatenate(chunks), sr


def _split_for_tts(text: str, max_chars: int = 60) -> list[str]:
    """切句。

    必须分句：不分句时长文本内容会丢（实测 100 字只生成出 3.5 秒有声内容），
    而且句中会累积大量静音。
    """
    parts = [s.strip() for s in re.split(r"(?<=[。！？；!?;])", text) if s.strip()]
    out: list[str] = []
    for p in parts:
        if len(p) <= max_chars:
            out.append(p)
            continue
        subs = [s.strip() for s in re.split(r"(?<=[，、,])", p) if s.strip()]
        buf = ""
        for s in subs:
            if len(buf) + len(s) <= max_chars:
                buf += s
            else:
                if buf:
                    out.append(buf)
                buf = s
        if buf:
            out.append(buf)
    final: list[str] = []
    for s in out:
        while len(s) > max_chars:
            final.append(s[:max_chars])
            s = s[max_chars:]
        if s:
            final.append(s)
    return final or [text]


def _compress_pauses(audio: np.ndarray, sr: int, thresh_ratio: float = 0.05,
                     max_pause: float = 0.35, keep: float = 0.20) -> np.ndarray:
    """裁首尾静音 + 把句中超长静音压到 keep 秒。

    模型每段会吐精确 2.95~3.10 秒的空白，听感像「说到一半断了」。
    阈值用相对峰值（5%），固定值在不同音量的句子上会误裁。
    """
    frame = int(sr * 0.02)

    def voiced_mask(a: np.ndarray) -> np.ndarray:
        n = len(a) // frame
        if n == 0:
            return np.array([], dtype=bool)
        rms = np.sqrt(np.mean(a[: n * frame].reshape(n, frame) ** 2, axis=1))
        th = max(rms.max() * thresh_ratio, 0.01)
        return rms > th

    v = voiced_mask(audio)
    idx = np.where(v)[0]
    if len(idx) == 0:
        return audio
    audio = audio[idx[0] * frame: min(len(audio), (idx[-1] + 1) * frame)]

    v = voiced_mask(audio)
    n = len(v)
    if n == 0:
        return audio

    out: list[np.ndarray] = []
    i = 0
    while i < n:
        if v[i]:
            j = i
            while j < n and v[j]:
                j += 1
            out.append(audio[i * frame: min(j * frame, len(audio))])
            i = j
        else:
            j = i
            while j < n and not v[j]:
                j += 1
            if (j - i) * 0.02 > max_pause:
                pad = int(sr * keep / 2)
                mid = (i + j) // 2 * frame
                out.append(audio[max(0, mid - pad): min(len(audio), mid + pad)])
            else:
                out.append(audio[i * frame: min(j * frame, len(audio))])
            i = j
    return np.concatenate(out) if out else audio


def _synthesize_sync(text: str) -> tuple[np.ndarray, int, float]:
    """executor 线程内完成：加载检查 → 分句合成 → 压缩 → 拼接。"""
    _load_model()
    if _model is None:
        raise RuntimeError(_load_error or "模型不可用")

    t0 = time.time()
    sentences = _split_for_tts(text, _cfg["max_chars"])
    logger.info("分句合成：%d 句", len(sentences))

    pieces: list[np.ndarray] = []
    sr = 24000
    for idx, s in enumerate(sentences, 1):
        a, sr = _generate(s)
        raw_dur = len(a) / sr
        a = _compress_pauses(a, sr)
        if len(a) == 0:
            logger.warning("第 %d 句是空音频，跳过", idx)
            continue
        pieces.append(a)
        gap = 0.24 if s and s[-1] in "。！？；.!?;" else 0.12
        pieces.append(np.zeros(int(sr * gap), dtype=np.float32))
        logger.info("  第 %d/%d 句 %.1fs -> %.1fs", idx, len(sentences), raw_dur, len(a) / sr)

    if not pieces:
        raise RuntimeError("所有句子都合成失败")

    audio = np.concatenate(pieces).astype(np.float32)
    if len(audio) / sr > _cfg["max_utterance_sec"]:
        logger.warning("异常偏长 %.1fs，强制裁剪", len(audio) / sr)
        audio = audio[: int(_cfg["max_utterance_sec"] * sr)]
    return audio, sr, time.time() - t0


def _wav_bytes(audio: np.ndarray, sr: int) -> bytes:
    import soundfile as sf

    buf = io.BytesIO()
    sf.write(buf, audio, sr, format="WAV")
    return buf.getvalue()


# ---------------------------------------------------------------------------
class TTSRequest(BaseModel):
    text: str


@app.get("/health")
def health():
    return {
        "ready": _model is not None,
        "model": _model_key,
        "model_id": _cfg.get("model_id"),
        "error": _load_error,
        "stats": _stats,
    }


@app.post("/tts")
def tts(req: TTSRequest):
    if not req.text.strip():
        raise HTTPException(400, "text 为空")
    try:
        audio, sr, synth_sec = _executor.submit(_synthesize_sync, req.text).result()
    except Exception as e:  # noqa: BLE001
        logger.exception("合成失败")
        raise HTTPException(500, str(e)) from e

    dur = len(audio) / sr
    _stats["requests"] += 1
    _stats["audio_seconds"] += dur
    _stats["synth_seconds"] += synth_sec
    logger.info("合成 %.1fs 音频 / 耗时 %.2fs (RTF %.2f)", dur, synth_sec, synth_sec / dur if dur else 0)
    return Response(content=_wav_bytes(audio, sr), media_type="audio/wav")


@app.post("/switch")
def switch(payload: dict):
    key = payload.get("model")
    if key not in MODELS:
        raise HTTPException(400, f"未知模型：{key}")
    _cfg["model_key"] = key
    _cfg["model_id"] = MODELS[key]
    _executor.submit(_load_model).result()
    return {"ok": True, "model": _model_key}


# ---------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default=str(HERE / "config.json"))
    ap.add_argument("--host", default="127.0.0.1")
    args = ap.parse_args()

    global _cfg
    _cfg = load_config(args.config)
    logger.info("配置：模型=%s 端口=%d", _cfg["model_key"], _cfg["port"])

    _executor.submit(_load_model)
    logger.info("服务启动 http://%s:%d", args.host, _cfg["port"])
    uvicorn.run(app, host=args.host, port=_cfg["port"], log_level="warning")


if __name__ == "__main__":
    main()
