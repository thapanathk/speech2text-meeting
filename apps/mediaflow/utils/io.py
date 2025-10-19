import json, re, time
from pathlib import Path
from django.conf import settings

SAFE = re.compile(r"[^a-zA-Z0-9._-]+")

def safe_stem(name: str) -> str:
    stem = Path(name).stem
    return SAFE.sub("_", stem)[:120] or "audio"

def save_json(payload: dict, base_name: str, tag: str, subdir: str) -> str:
    stem = Path(base_name).stem
    ts = time.strftime("%Y%m%d-%H%M%S")
    outdir = (settings.RESULTS_ROOT / subdir)
    outdir.mkdir(parents=True, exist_ok=True)
    outpath = outdir / f"{stem}_{tag}_{ts}.json"
    outpath.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return str(outpath)
