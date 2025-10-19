import asyncio
from pathlib import Path
from django.http import JsonResponse, HttpRequest
from django.views.decorators.csrf import csrf_exempt
from django.conf import settings
from django.shortcuts import render
from .utils.io import save_json

from .utils.ffmpeg_convert import convert_to_wav
from .utils.diarize import diarize_auto
from .utils.transcribe import transcribe_segments_with_pathumma

def index(request):
    return render(request, "mediaflow/index.html")

def test_page(request):
    return render(request, "mediaflow/test_page.html")

def diarize_auto_page(request):
    return render(request, "mediaflow/diarize_auto_page.html")

def transcribe_auto_page(request):
    return render(request, "mediaflow/transcribe_auto_page.html")

@csrf_exempt
def convert_one(request: HttpRequest):
    if request.method != "POST":
        return JsonResponse({"error": "POST only"}, status=405)

    f = request.FILES.get("file")
    if not f:
        return JsonResponse({"error": "missing file"}, status=400)

    profile = (request.POST.get("profile") or "fast").lower().strip()
    up = Path(settings.MEDIA_ROOT); up.mkdir(parents=True, exist_ok=True)
    src = up / f.name
    with src.open("wb") as dst:
        for ch in f.chunks():
            dst.write(ch)

    result = asyncio.run(convert_to_wav(src, out_dir=settings.CONVERTED_ROOT, profile=profile))
    if not result["ok"]:
        return JsonResponse({"ok": False, "message": "ffmpeg failed", "detail": result["stderr"][:2000]}, status=500)
    return JsonResponse({"ok": True, "input": result["input"], "output": result["output"], "profile": result["profile"]})

@csrf_exempt
def diarize_auto_api(request: HttpRequest):
    """
    POST multipart/form-data:
      file: (required) ไฟล์เสียงใดๆ (mp3/m4a/wav/…)
      profile: (optional) fast|max (default=fast)
    """
    if request.method != "POST":
        return JsonResponse({"error": "POST only"}, status=405)

    f = request.FILES.get("file")
    if not f:
        return JsonResponse({"error": "missing file"}, status=400)

    profile = (request.POST.get("profile") or "fast").lower().strip()

    up = Path(settings.MEDIA_ROOT); up.mkdir(parents=True, exist_ok=True)
    src = up / f.name
    with src.open("wb") as dst:
        for ch in f.chunks():
            dst.write(ch)

    try:
        res = diarize_auto(src, profile=profile)
        return JsonResponse({"ok": True, **res}, json_dumps_params={"ensure_ascii": False})
    except Exception as e:
        import traceback
        tb = traceback.format_exc()
        return JsonResponse({"ok": False, "error": str(e), "trace": tb[:2000]}, status=500)

@csrf_exempt
def transcribe_auto_api(request: HttpRequest):
    """
    POST multipart/form-data:
      file: (required) ไฟล์เสียงใดๆ
      language: (optional) 'th' (default) หรือปล่อยว่างให้ auto ของโมเดล
    """
    if request.method != "POST":
        return JsonResponse({"error": "POST only"}, status=405)

    f = request.FILES.get("file")
    if not f:
        return JsonResponse({"error": "missing file"}, status=400)

    language = (request.POST.get("language") or "th").strip() or None

    # upload → data/uploads/...
    up = Path(settings.MEDIA_ROOT); up.mkdir(parents=True, exist_ok=True)
    src = up / f.name
    with src.open("wb") as dst:
        for ch in f.chunks():
            dst.write(ch)

    try:
        # 1) diarize (จะสร้าง .json ใน results/diar ให้อัตโนมัติ)
        dia = diarize_auto(src, save=True)

        # 2) transcribe ตามช่วง
        enriched = transcribe_segments_with_pathumma(dia["wav"], dia["segments"], language=language)

        # 3) รวมผล + เซฟเป็น JSON ใน results/transcribe/
        result = {
            "source": str(src),
            "wav": dia["wav"],
            "speakers_count": dia.get("speakers_count"),
            "segments": enriched,
            "diar_json": dia.get("json_path"),  # ลิงก์ไปไฟล์ diar.json ที่สร้างไว้
        }
        trans_json_path = save_json(result, base_name=src.name, tag="trans", subdir="transcribe")

        # 4) ตอบกลับ พร้อม path ไฟล์ที่บันทึกไว้
        return JsonResponse({
            "ok": True,
            "json_path": trans_json_path,
            **result
        }, json_dumps_params={"ensure_ascii": False})

    except Exception as e:
        import traceback
        return JsonResponse({"ok": False, "error": str(e), "trace": traceback.format_exc()[:2000]}, status=500)