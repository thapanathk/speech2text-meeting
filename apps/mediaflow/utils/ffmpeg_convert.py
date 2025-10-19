import asyncio, shlex, uuid
from pathlib import Path
from django.conf import settings

FFMPEG = "ffmpeg"

AUDIO_FILTERS = {
    "fast": 'highpass=f=60,lowpass=f=7900,afftdn=nr=12:nt=w:om=o,dynaudnorm=f=180:g=15,loudnorm=I=-17:TP=-1.5:LRA=11,apad=pad_dur=0.2',
    "mid":  'highpass=f=70,lowpass=f=7800,afftdn=nr=16:nt=w:om=o,dynaudnorm=f=180:g=12,loudnorm=I=-17:TP=-1.5:LRA=10,apad=pad_dur=0.2',
    "max":  'highpass=f=70,lowpass=f=7600,afftdn=nr=22:nt=w:om=o,dynaudnorm=f=200:g=12,loudnorm=I=-18:TP=-2.0:LRA=9,apad=pad_dur=0.2',
}

def _safe_stem(p: Path) -> str:
    s = p.stem.strip().replace(" ", "_")
    return s[:80] or uuid.uuid4().hex[:8]

async def convert_to_wav(input_path, out_dir=None, profile="mid"):
    inp = Path(input_path).resolve()
    out_base = Path(out_dir) if out_dir else settings.CONVERTED_ROOT
    out_base.mkdir(parents=True, exist_ok=True)
    out_wav = out_base / f"{_safe_stem(inp)}.wav"

    af = AUDIO_FILTERS.get(profile, AUDIO_FILTERS["mid"])

    cmd = (
        f'ffmpeg -hide_banner -y -i "{inp}" -ac 1 -ar 16000 -vn -sn -dn '
        f'-af "{af}" -c:a pcm_s16le "{out_wav}"'
    )
    proc = await asyncio.create_subprocess_exec(
        *shlex.split(cmd),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    _, err = await proc.communicate()
    return {
        "ok": proc.returncode == 0,
        "input": str(inp),
        "output": str(out_wav),
        "stderr": err.decode("utf-8", "ignore"),
        "profile": profile if profile in AUDIO_FILTERS else "mid",
    }
