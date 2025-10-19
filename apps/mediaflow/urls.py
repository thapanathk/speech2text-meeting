from django.urls import path
from .views import (
    convert_one,
    test_page,
    diarize_auto_api,
    diarize_auto_page,
    transcribe_auto_page,
    transcribe_auto_api,
)

urlpatterns = [
    path("", test_page, name="test_page"),
    path("convert", convert_one, name="convert_one"),
    path("diarize_auto", diarize_auto_api, name="diarize_auto_api"),
    path("diarize_auto_ui", diarize_auto_page, name="diarize_auto_page"),
    path("transcribe_auto", transcribe_auto_api, name="transcribe_auto_api"),
    path("transcribe_auto_ui", transcribe_auto_page, name="transcribe_auto_page"),
]