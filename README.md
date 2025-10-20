# 🎙️ Pathumma Speech-to-Text (Django)

ระบบแปลงเสียงเป็นข้อความภาษาไทย พร้อมตัดช่วงผู้พูด (pyannote) และถอดเสียง (Pathumma/Whisper-TH) + UI (Tailwind/Flowbite)

---

## 0) Prerequisites

- Python **3.10+** (แนะนำ 3.11)
- **FFmpeg** ติดตั้งในระบบ และสั่ง `ffmpeg -version` ได้
  - Windows: ดาวน์โหลด FFmpeg แล้วเพิ่มโฟลเดอร์ `bin` เข้า `PATH`
  - macOS: `brew install ffmpeg`
  - Ubuntu/Debian: `sudo apt-get install ffmpeg`
- (ถ้ามี GPU) ติดตั้ง **PyTorch** ให้ตรงกับ CUDA ตามคู่มือที่เว็บไซต์ทางการ

---

## 1) Virtual Environment (venv)

```bash
# ไปยังโฟลเดอร์โปรเจกต์
cd /path/to/project

# สร้าง venv
python -m venv .venv

# เปิดใช้งาน
# macOS/Linux
source .venv/bin/activate
# Windows (PowerShell)
.\.venv\Scripts\Activate.ps1

# อัปเกรด pip + ติดตั้ง dependencies
python.exe -m pip install --upgrade pip
pip install -r requirements.txt
```
> ถ้ามี GPU ให้ติดตั้ง PyTorch ตามคู่มือก่อน แล้วค่อย `pip install -r requirements.txt`

---

## 2) สร้าง Django Secret Key

เลือกวิธีใดวิธีหนึ่ง

```bash
# one-liner
python -c "from django.core.management.utils import get_random_secret_key as g; print(g())"
```

หรือ

```bash
python - <<'PY'
from django.core.management.utils import get_random_secret_key
print(get_random_secret_key())
PY
```

คัดลอกค่าไปใส่ในไฟล์ `.env` (หัวข้อถัดไป)

---

## 3) ขอ Hugging Face Token

1. ล็อกอินที่ https://huggingface.co  
2. ไปที่ **Settings → Access Tokens**  
3. กด **New token** เลือกสิทธิ์ **Read**  
4. คัดลอก token (ขึ้นต้นด้วย `hf_...`)

---

## 4) ตั้งค่าไฟล์ `.env`

สร้างไฟล์ `.env` ที่รากโปรเจกต์ (ระดับเดียวกับ `manage.py`) แล้ววางเนื้อหานี้:

```dotenv
# =============================
# Django
# =============================
DJANGO_SECRET_KEY=ใส่ค่าที่สร้างจากขั้นตอนที่ 2
DEBUG=True

# =============================
# Hugging Face / Models
# =============================
# Token จากขั้นตอนที่ 3
HUGGINGFACE_HUB_TOKEN=hf_xxxxxxxxxxxxxxxxxxxxxxxxxxxxx

# โมเดลสำหรับตัดช่วงผู้พูด (pyannote)
PYANNOTE_MODEL_ID=pyannote/speaker-diarization-3.1

# โมเดลถอดเสียงภาษาไทย (ระบุ repo ที่ใช้งานได้จริง)
PATHUMMA_MODEL_ID=thapana/pathumma-whisper-th

# =============================
# Paths (จะถูกสร้างอัตโนมัติถ้ายังไม่มี)
# =============================
MEDIA_ROOT=data/uploads
CONVERTED_ROOT=data/converted
RESULTS_ROOT=data/results
```

> แนะนำให้ commit ไฟล์ตัวอย่างเป็น `.env.example` และ **อย่า** commit `.env` จริงขึ้น Git

---

## 5) ติดตั้งครั้งแรก (Initial setup)

```bash
python manage.py migrate
# (ถ้าต้องการผู้ใช้แอดมิน)
python manage.py createsuperuser
# ตรวจสอบ FFmpeg
ffmpeg -version
```

---

## 6) รันเซิร์ฟเวอร์

```bash
python manage.py runserver 8000
```

เปิดเบราว์เซอร์: http://127.0.0.1:8000  
หน้า UI สำหรับ Upload → Convert → Diarize → Transcribe

---

## 7) โครงสร้างผลลัพธ์

```
data/
 ├─ uploads/            # ไฟล์ต้นฉบับที่อัปโหลด
 ├─ converted/          # ไฟล์ .wav หลังลด noise
 └─ results/
     ├─ diar/           # JSON ช่วงผู้พูดจาก Pyannote
     └─ transcribe/     # JSON ถอดเสียงตามช่วง
```

---

## 8) Git quick-start

```bash
# เริ่ม repo ครั้งแรก
git init
echo ".env" >> .gitignore
git add .
git commit -m "Initial commit"

# เชื่อมกับ GitHub (แทนที่ YOUR_USERNAME / YOUR_REPO)
git remote add origin https://github.com/YOUR_USERNAME/YOUR_REPO.git
git branch -M main
git push -u origin main
```

> ถ้าใช้ SSH:
> ```bash
> git remote set-url origin git@github.com:YOUR_USERNAME/YOUR_REPO.git
> ```

---

## 9) Troubleshooting

- **`ffmpeg not found`** → ติดตั้ง FFmpeg และเพิ่มลง PATH
- **Hugging Face 401/403** → ตรวจ `HUGGINGFACE_HUB_TOKEN` และสิทธิ์เข้าถึงโมเดล
- **ช้า** → ใช้ GPU, ปรับ `chunk_length_s`, ลด denoise profile
- **ไม่เห็นไฟล์ JSON** → ตรวจ response ของ API และดูใน `data/results/diar` / `data/results/transcribe`
