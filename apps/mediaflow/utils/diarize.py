import os
import asrpro.compat  # noqa: F401
import torch
import soundfile as sf
from functools import lru_cache
from pathlib import Path
from typing import List, Dict
from django.conf import settings
from .hf_auth import hf_login_from_env
from .ffmpeg_convert import convert_to_wav
from .io import save_json

MODEL_ID = os.getenv("PYANNOTE_MODEL_ID", "pyannote/speaker-diarization-3.1")

def _run_async(coro):
    import asyncio
    return asyncio.run(coro)

def _to_cuda_if_available(pipe):
    try:
        import torch
        if torch.cuda.is_available():
            major, minor = torch.cuda.get_device_capability(0)
            if f"sm_{major}{minor}" in set(torch.cuda.get_arch_list()):
                pipe.to("cuda")
    except Exception:
        pass
    return pipe

@lru_cache(maxsize=1)
def _get_pipeline():
    ok = hf_login_from_env()
    token = os.getenv("HUGGINGFACE_HUB_TOKEN")
    if not token and not ok:
        raise RuntimeError("Missing HUGGINGFACE_HUB_TOKEN in .env (required for pyannote).")
    from pyannote.audio import Pipeline
    try:
        pipe = Pipeline.from_pretrained(MODEL_ID, use_auth_token=token)
    except Exception as e:
        # Handle YAML deserialization errors by retrying with alternative options
        error_msg = str(e)
        if "Could not import module" in error_msg or "pipeline" in error_msg.lower():
            # Try loading without auth token as fallback
            try:
                pipe = Pipeline.from_pretrained(MODEL_ID, use_auth_token=None)
            except Exception as retry_error:
                raise RuntimeError(f"Failed to load pyannote pipeline '{MODEL_ID}': {error_msg}. "
                                   f"Retry also failed: {retry_error}")
        else:
            raise
    if pipe is None: raise RuntimeError(f"Pipeline.load returned None for '{MODEL_ID}'.")
    return _to_cuda_if_available(pipe)

def diarize_auto(audio_path: str | Path, *, profile: str = "mid", save: bool = True) -> Dict:
    audio_path = Path(audio_path).resolve()

    conv = _run_async(convert_to_wav(audio_path, profile=profile))
    if not conv.get("ok"):
        raise RuntimeError(f"ffmpeg failed: {conv.get('stderr','')}")
    wav_path = Path(conv["output"]).resolve()

    pipe = _get_pipeline()
    waveform, sample_rate = sf.read(str(wav_path), dtype="float32", always_2d=True)
    file_input = {
        "waveform": torch.from_numpy(waveform.T),
        "sample_rate": sample_rate,
        "uri": wav_path.stem,
    }
    try:
        diar = pipe(file_input, batch_size=1)
    except TypeError:
        diar = pipe(file_input)

    segments, speakers = [], set()
    for turn, _, spk in diar.itertracks(yield_label=True):
        s = str(spk); speakers.add(s)
        segments.append({"start": round(float(turn.start), 3),
                         "end": round(float(turn.end), 3),
                         "speaker": s})
    segments.sort(key=lambda x: (x["start"], x["end"]))

    segments = clean_diar_segments(segments, min_turn=0.60, merge_gap=0.25, collar=0.05)

    result = {
        "wav": str(wav_path),
        "segments": segments,
        "speakers_count": len({s["speaker"] for s in segments}),
        "profile": profile,
        "model": MODEL_ID,
        "source": str(audio_path),
    }
    if save:
        result["json_path"] = save_json(result, base_name=audio_path.name, tag="diar", subdir="diar")
    return result

def clean_diar_segments(segs: List[Dict], min_turn=0.50, merge_gap=0.20, collar=0.05) -> List[Dict]:
    if not segs: return []
    segs = sorted(segs, key=lambda x: (x["start"], x["end"]))
    merged = []
    for s in segs:
        if not merged: merged.append(dict(s)); continue
        last = merged[-1]
        if s["speaker"] == last["speaker"] and s["start"] - last["end"] <= merge_gap:
            last["end"] = max(last["end"], s["end"])
        else:
            merged.append(dict(s))
    for i, s in enumerate(merged):
        s["start"] = max(0.0, s["start"] - collar)
        s["end"]   = s["end"] + collar
        if i > 0: s["start"] = max(s["start"], merged[i-1]["end"])
    i = 1
    while 0 < i < len(merged)-1:
        prev, cur, nxt = merged[i-1], merged[i], merged[i+1]
        if (cur["end"] - cur["start"]) < min_turn and prev["speaker"] == nxt["speaker"] != cur["speaker"]:
            prev["end"] = nxt["end"]; merged.pop(i+1); merged.pop(i); i -= 1
        else: i += 1
    cleaned = []
    for s in merged:
        if not cleaned: cleaned.append(s); continue
        last = cleaned[-1]; gap = s["start"] - last["end"]
        if s["speaker"] == last["speaker"] or gap <= merge_gap:
            last["end"] = max(last["end"], s["end"])
        else: cleaned.append(s)
    for s in cleaned:
        s["start"] = round(float(s["start"]), 3)
        s["end"]   = round(float(s["end"]), 3)
    return cleaned
