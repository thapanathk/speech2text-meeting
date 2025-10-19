import os
import io
import re
import torch
import soundfile as sf
from pathlib import Path
from typing import List, Dict, Optional, Any
from subprocess import Popen, PIPE
from transformers import pipeline

# ---- Device & dtype ---------------------------------------------------------
HAS_CUDA = torch.cuda.is_available()
DEVICE = 0 if HAS_CUDA else -1            # transformers: 0 = CUDA:0, -1 = CPU
DTYPE = torch.float16 if HAS_CUDA else torch.float32


# ---- Pipeline loader ---------------------------------------------------------
def _require_model_id() -> str:
    mid = os.getenv("PATHUMMA_MODEL_ID")
    if not mid:
        raise RuntimeError("Missing PATHUMMA_MODEL_ID in .env (required for Pathumma transcription).")
    return mid


def _load_pipeline():
    """
    โหลด Pathumma (Whisper-TH) ด้วย transformers.pipeline
    - บังคับภาษาไทย
    - รองรับ token (กรณี private/จำกัดสิทธิ์)
    """
    # กันเผื่อเคยตั้ง offline เอาไว้
    os.environ.pop("HF_HUB_OFFLINE", None)

    model_id = _require_model_id()
    token = os.getenv("HUGGINGFACE_HUB_TOKEN")

    print(f"[INFO] Loading ASR pipeline: {model_id} (device={'cuda' if HAS_CUDA else 'cpu'}, dtype={DTYPE})")
    asr = pipeline(
        task="automatic-speech-recognition",
        model=model_id,
        torch_dtype=DTYPE,
        device=DEVICE,
        token=token,  # ถ้า transformers เก่า: ใช้ use_auth_token=token
    )
    # บังคับ decoder ไทย
    asr.model.config.forced_decoder_ids = asr.tokenizer.get_decoder_prompt_ids(
        language="th", task="transcribe"
    )
    return asr


_asr_pipeline = None
def _get_pipe():
    global _asr_pipeline
    if _asr_pipeline is None:
        _asr_pipeline = _load_pipeline()
    return _asr_pipeline


# ---- Segments prep (รวม/เติม padding/ซอย) -----------------------------------
def prepare_asr_segments(
    raw: List[Dict],
    pad_head: float = 0.25,
    pad_tail: float = 0.35,
    min_len:  float = 1.5,
    merge_gap: float = 0.30,
    max_len: float = 18.0,
) -> List[Dict]:
    if not raw:
        return []

    raw = sorted(raw, key=lambda x: (x["start"], x["end"]))

    # รวม speaker เดียวกันที่ติดกัน/ห่างกันน้อย
    merged: List[Dict] = []
    for s in raw:
        if not merged:
            merged.append(dict(s))
            continue
        last = merged[-1]
        if s.get("speaker") == last.get("speaker") and (float(s["start"]) - float(last["end"])) <= merge_gap:
            last["end"] = max(float(last["end"]), float(s["end"]))
        else:
            merged.append(dict(s))

    # รวมจนพอขั้นต่ำ แล้วเติม padding และซอยตาม max_len
    asr_ready: List[Dict] = []
    i = 0
    while i < len(merged):
        cur = dict(merged[i])
        while (
            i + 1 < len(merged)
            and merged[i + 1].get("speaker") == cur.get("speaker")
            and (float(merged[i + 1]["start"]) - float(cur["end"])) <= merge_gap
            and (float(merged[i + 1]["end"]) - float(cur["start"])) < max(min_len, max_len)
        ):
            cur["end"] = float(merged[i + 1]["end"])
            i += 1
        asr_ready.append(cur)
        i += 1

    final: List[Dict] = []
    for s in asr_ready:
        start = max(0.0, float(s["start"]) - pad_head)
        end = float(s["end"]) + pad_tail
        dur = max(0.02, end - start)
        if dur <= max_len:
            final.append({**s, "start": start, "end": end})
        else:
            # ซอยเป็นชิ้นย่อย (มี overlap)
            stride = max_len - 0.3
            cur = start
            while cur < end:
                sub_end = min(end, cur + max_len)
                final.append({**s, "start": round(cur, 3), "end": round(sub_end, 3)})
                if sub_end >= end:
                    break
                cur = sub_end - 0.3

    return final


# ---- Helper: ดึง text จากผลลัพธ์หลายรูปแบบของ transformers.pipeline ----------
def _extract_text(out: Any) -> str:
    """
    รองรับ:
    - dict: {"text": "..."} หรือ {"chunks": [{"text": ...}, ...]}
    - list[dict]: [{"text": ...}, ...]
    - str: "..."
    - อื่น ๆ -> ""
    """
    if out is None:
        return ""
    if isinstance(out, str):
        return out.strip()
    if isinstance(out, dict):
        if isinstance(out.get("text"), str):
            return out["text"].strip()
        chunks = out.get("chunks")
        if isinstance(chunks, list):
            texts = [str(c.get("text", "")).strip() for c in chunks]
            return " ".join(t for t in texts if t)
        return ""
    if isinstance(out, list):
        texts = []
        for item in out:
            if isinstance(item, dict) and "text" in item:
                texts.append(str(item["text"]).strip())
            elif isinstance(item, str):
                texts.append(item.strip())
        return " ".join(t for t in texts if t)
    return ""


# ---- Helper: ลดการซ้ำคำ ------------------------------------------------------
def _squash_repeats(text: str, max_repeat: int = 2) -> str:
    tokens = text.split()
    out, last, cnt = [], None, 0
    for t in tokens:
        if t == last:
            cnt += 1
        else:
            last, cnt = t, 1
        if cnt <= max_repeat:
            out.append(t)
    rough = " ".join(out)
    rough = re.sub(r"(\S{2,20})\1{2,}", r"\1\1", rough)
    return rough


# ---- Main: Transcribe by segments -------------------------------------------
def transcribe_segments_with_pathumma(
    wav_path: str | Path,
    segments: List[Dict],
    language: Optional[str] = "th",
) -> List[Dict]:
    """
    อ่านช่วงเสียงด้วย ffmpeg (stream) → ส่งเข้า Pathumma ในหน่วยความจำ
    - วาง -ss หลัง -i เพื่อ seek แม่น
    - ใช้ silenceremove แบบพอดี + fallback แบบไม่ตัดเงียบ
    - ตั้ง chunk_length/stride ให้โมเดลจัดการภายใน
    - post-process กันวนคำ
    """
    wav_path = Path(wav_path).resolve()
    pipe = _get_pipe()
    enriched: List[Dict] = []

    def _ffmpeg_read_chunk(start: float, dur: float, use_silence: bool) -> bytes:
        cmd = [
            "ffmpeg", "-hide_banner", "-loglevel", "error",
            "-i", str(wav_path),
            "-ss", f"{start:.3f}", "-t", f"{dur:.3f}",
            "-ac", "1", "-ar", "16000",
        ]
        if use_silence:
            cmd += [
                "-af",
                "silenceremove=start_periods=1:start_threshold=-35dB:start_duration=0.2:"
                "stop_periods=1:stop_threshold=-35dB:stop_duration=0.2",
            ]
        cmd += ["-f", "wav", "pipe:1"]
        p = Popen(cmd, stdout=PIPE, stderr=PIPE)
        wav_bytes, _ = p.communicate()
        return wav_bytes or b""

    def _decode_arr(arr):
        return pipe(
            arr,
            chunk_length_s=12,
            stride_length_s=(2, 2),
            return_timestamps=False,
            generate_kwargs={
                "num_beams": 5,
                "temperature": 0.0,
                "no_repeat_ngram_size": 3,
                "repetition_penalty": 1.1,
                "length_penalty": 0.1,
            },
        )

    for seg in prepare_asr_segments(
        segments,
        pad_head=0.30, pad_tail=0.40,
        min_len=1.5, merge_gap=0.30, max_len=18.0,
    ):
        start = float(seg["start"])
        end = float(seg["end"])
        dur = max(0.02, end - start)

        text = ""
        try:
            # pass 1: ตัดเงียบ
            wav_bytes = _ffmpeg_read_chunk(start, dur, use_silence=True)
            if wav_bytes:
                data, _ = sf.read(io.BytesIO(wav_bytes), dtype="float32")
                out = _decode_arr(data)
                text = _extract_text(out)
        except Exception as e:
            text = f"[ERROR: {e}]"

        # fallback: ไม่ตัดเงียบ
        if len(text) < 3 or text.startswith("[ERROR"):
            try:
                wav_bytes2 = _ffmpeg_read_chunk(start, dur, use_silence=False)
                if wav_bytes2:
                    data2, _ = sf.read(io.BytesIO(wav_bytes2), dtype="float32")
                    out2 = _decode_arr(data2)
                    text2 = _extract_text(out2)
                    if len(text2) > len(text):
                        text = text2
            except Exception:
                pass

        text = _squash_repeats(text, max_repeat=2)

        enriched.append({
            "start": float(start),
            "end": float(end),
            "speaker": str(seg.get("speaker", "-")),
            "text": str(text or ""),
        })

    return enriched
