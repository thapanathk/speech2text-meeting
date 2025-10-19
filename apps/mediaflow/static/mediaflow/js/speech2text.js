document.addEventListener("DOMContentLoaded", () => {
    // ===== helpers
    const $ = (s, el = document) => el.querySelector(s);
    const pad = n => String(n).padStart(2, "0");
    const tlabel = s => `${Math.floor(s / 60)}:${pad(Math.floor(s % 60))}`;
    function showToast(type, msg) {
        const palette = {
            ok: { bg: 'bg-green-100', fg: 'text-green-700', icon: '✓' },
            err: { bg: 'bg-red-100', fg: 'text-red-700', icon: '!' },
            pending: { bg: 'bg-yellow-100', fg: 'text-yellow-700', icon: '⏳' },
        };
        const p = palette[type] || palette.ok;

        const el = document.createElement('div');
        el.className = `flex items-center w-full max-w-xs p-4 bg-white rounded-lg shadow border border-slate-200`;
        el.innerHTML = `
    <div class="inline-flex items-center justify-center w-8 h-8 ${p.fg} ${p.bg} rounded-lg me-3">${p.icon}</div>
    <div class="text-sm font-medium flex-1 ${p.fg.replace('text-', 'text-')}">${msg}</div>
    <button class="text-slate-400 hover:text-slate-600">✕</button>
  `;
        el.lastElementChild.onclick = () => el.remove();
        document.getElementById('toastArea').appendChild(el);

        // pending อยู่นานหน่อย, อย่างอื่น 4s
        setTimeout(() => el.remove(), type === 'pending' ? 8000 : 4000);
    }


    // ===== elements
    const dropzone = $('#dropzone'), fileInput = $('#audioFile'), fileHint = $('#fileHint');
    const btnSend = $('#btnSend'), badgeStatus = $('#badgeStatus');
    const steps = ["upload", "convert", "diarize", "transcribe", "done"];
    const progress = $('#progressBar'), progressInd = $('#progressInd'), statusEl = $('#status');
    const modal = $('#confirmModal'), btnOk = $('#btnOk'), btnCancel = $('#btnCancel'), etaText = $('#etaText');
    const countdownEl = $('#countdown');
    const audio = $('#audioPlayer'), seek = $('#seek'), curTime = $('#curTime'), totalTime = $('#totalTime');
    const btnPlay = $('#btnPlay'), btnBack = $('#btnBack'), btnFwd = $('#btnFwd'), vol = $('#vol');
    const chatBox = $('#chatBox'), downloadBtn = $('#downloadBtn');

    // ===== drag & drop
    ['dragenter', 'dragover'].forEach(evt => {
        dropzone.addEventListener(evt, e => { e.preventDefault(); dropzone.classList.add('ring-2', 'ring-indigo-300') });
    });
    ['dragleave', 'drop'].forEach(evt => {
        dropzone.addEventListener(evt, e => { e.preventDefault(); dropzone.classList.remove('ring-2', 'ring-indigo-300') });
    });
    dropzone.addEventListener('drop', e => {
        if (e.dataTransfer?.files?.length) {
            const dt = new DataTransfer();[...e.dataTransfer.files].forEach(f => dt.items.add(f));
            fileInput.files = dt.files; fileHint.textContent = fileInput.files[0].name; previewAudio(); toggleSend(true);
        }
    });
    fileInput.addEventListener('change', () => {
        fileHint.textContent = fileInput.files[0]?.name || 'รองรับ .mp3 .m4a .wav .flac .ogg .aac';
        previewAudio(); toggleSend(!!fileInput.files.length);
    });
    function toggleSend(on) { btnSend.disabled = !on; btnSend.classList.toggle('opacity-60', !on); btnSend.classList.toggle('cursor-not-allowed', !on); }

    // ===== audio
    function previewAudio() {
        if (!fileInput.files.length) return;
        const url = URL.createObjectURL(fileInput.files[0]);
        audio.src = url; audio.classList.remove('hidden');
        audio.addEventListener('loadedmetadata', () => {
            seek.max = audio.duration || 0; totalTime.textContent = tlabel(audio.duration || 0);
        }, { once: true });
    }
    audio.addEventListener('timeupdate', () => {
        seek.value = audio.currentTime || 0; curTime.textContent = tlabel(audio.currentTime || 0);
    });
    seek.addEventListener('input', () => audio.currentTime = +seek.value);
    btnPlay.onclick = () => { if (audio.paused) { audio.play(); btnPlay.textContent = 'Pause'; } else { audio.pause(); btnPlay.textContent = 'Play'; } };
    btnBack.onclick = () => audio.currentTime = Math.max(0, (audio.currentTime || 0) - 10);
    btnFwd.onclick = () => audio.currentTime = Math.min(audio.duration || 0, (audio.currentTime || 0) + 10);
    vol.oninput = () => audio.volume = +vol.value;

    // ===== steps
    function setStepState(key, state) {
        const li = document.querySelector(`.step[data-step="${key}"]`); if (!li) return;
        const circle = li.querySelector("div.w-7"), bar = li.querySelector(".h-1");
        circle.className = "w-7 h-7 flex items-center justify-center rounded-full border-2";
        if (state === "active") { circle.classList.add("border-indigo-600", "bg-indigo-50", "text-indigo-600", "font-semibold"); if (bar) bar.className = "mx-2 h-1 bg-indigo-400 flex-1 rounded"; }
        else if (state === "done") { circle.classList.add("border-emerald-600", "bg-emerald-50", "text-emerald-700", "font-semibold"); if (bar) bar.className = "mx-2 h-1 bg-emerald-400 flex-1 rounded"; circle.innerHTML = "✓"; }
        else { circle.classList.add("border-slate-300", "bg-white"); if (bar) bar.className = "mx-2 h-1 bg-slate-200 flex-1 rounded"; circle.innerHTML = (steps.indexOf(key) + 1); }
    }
    function setAllIdle() { steps.forEach(s => setStepState(s, "idle")); progress.style.width = "0%"; }

    // ===== ETA (เผื่อเวลา) + countdown
    function estimateETA(durationSec) {
        const base = Math.max(60, Math.round(durationSec || 180));     // ขั้นต่ำ 1 นาที
        const rtFactor = navigator.hardwareConcurrency >= 8 ? 0.75 : 1.25; // เครื่องแรงเร็วกว่า
        const overhead = 25;    // startup / I/O
        const bufferPct = 0.30; // เผื่อ 30%
        return Math.round((base * rtFactor + overhead) * (1 + bufferPct));
    }
    function openModal() { modal.classList.remove('hidden'); }
    function closeModal() { modal.classList.add('hidden'); }

    let countdownTimer = null, countdownStartMs = 0, countdownTotal = 0;
    function startCountdown(totalSec) {
        stopCountdown(); countdownTotal = totalSec; countdownStartMs = Date.now();
        tickCountdown(); countdownTimer = setInterval(tickCountdown, 1000);
    }
    function tickCountdown() {
        const elapsed = Math.floor((Date.now() - countdownStartMs) / 1000);
        const remain = Math.max(0, countdownTotal - elapsed);
        const m = Math.floor(remain / 60), s = remain % 60;
        countdownEl.textContent = `${m}:${pad(s)}`;
    }
    function stopCountdown() { clearInterval(countdownTimer); countdownTimer = null; countdownEl.textContent = "00:00"; }

    // ===== Confirm modal
    document.getElementById('uploadForm').addEventListener('submit', e => {
        e.preventDefault();
        if (!fileInput.files.length) { showToast('err', 'กรุณาเลือกไฟล์'); return; }
        const tmp = new Audio(); tmp.src = URL.createObjectURL(fileInput.files[0]);
        tmp.addEventListener('loadedmetadata', () => {
            const eta = estimateETA(tmp.duration || 180);
            etaText.textContent = `${Math.floor(eta / 60)}:${pad(eta % 60)}`; openModal();
        });
    });
    document.getElementById('btnCancel').onclick = () => closeModal();
    document.getElementById('btnOk').onclick = async () => { closeModal(); await runPipeline(); };

    // ===== normalize segments from API (รองรับหลายรูปแบบ)
    function getSegmentsFromResponse(json, audioDurSec) {
        const candidates = [json?.segments, json?.data?.segments, json?.result?.segments, json?.diarization?.segments];
        for (const segs of candidates) {
            if (Array.isArray(segs) && segs.length) {
                return segs.map((s, i) => ({
                    start: typeof s.start === 'number' ? s.start : NaN,
                    end: typeof s.end === 'number' ? s.end : NaN,
                    speaker: s.speaker || `SPEAKER_${String(i % 2).padStart(2, '0')}`,
                    text: (s.text ?? s.utterance ?? s.sentence ?? '').toString()
                }));
            }
        }
        const bigText =
            (typeof json?.text === 'string' && json.text.trim()) ? json.text :
                (Array.isArray(json?.lines) ? json.lines.join('\n') : '');

        if (bigText) return textToBubbles(bigText, audioDurSec);
        return [];
    }

    function textToBubbles(text, audioDurSec) {
        let chunks = text.split(/\n{2,}|\r{2,}/).map(s => s.trim()).filter(Boolean);
        if (chunks.length <= 1) {
            chunks = text
                .split(/([.!?]|[。！？]|[…]|[ฯ]|[\u0E2F])\s+/)
                .reduce((acc, cur, idx, arr) => {
                    if (idx % 2 === 0) {
                        const sent = (cur + (arr[idx + 1] || '')).trim();
                        if (sent) acc.push(sent);
                    }
                    return acc;
                }, []);
        }
        if (chunks.length === 0) chunks = [text.trim()];

        const total = Number.isFinite(audioDurSec) && audioDurSec > 0 ? audioDurSec : NaN;
        const step = Number.isFinite(total) ? total / chunks.length : NaN;

        return chunks.map((t, i) => ({
            start: Number.isFinite(step) ? Math.max(0, i * step) : NaN,
            end: Number.isFinite(step) ? Math.max(0, (i + 1) * step) : NaN,
            speaker: `SPEAKER_${String(i % 2).padStart(2, '0')}`,
            text: t
        }));
    }

    // ===== pipeline
    async function runPipeline() {
        const data = new FormData();
        data.append('file', fileInput.files[0]);

        // 🔄 reset UI for new run
        btnSend.disabled = true;
        downloadBtn.classList.add('hidden');
        chatBox.innerHTML = `<div class="text-slate-400 text-sm">กำลังประมวลผลไฟล์ใหม่…</div>`;
        // reset player
        try { audio.pause(); } catch (e) { }
        audio.currentTime = 0;
        if (btnPlay) btnPlay.textContent = 'Play';
        stopCountdown?.(); // ถ้ามีฟังก์ชันนี้อยู่แล้ว

        // steps/progress
        setAllIdle();
        setStepState("upload", "active");
        statusEl.textContent = "กำลังอัปโหลด...";
        progressInd.classList.remove('hidden');
        progress.style.width = "10%";

        // 🟡 แจ้งเตือนกำลังประมวลผล
        showToast('pending', 'กำลังประมวลผล...');

        // ETA countdown
        const tmp = new Audio();
        tmp.src = URL.createObjectURL(fileInput.files[0]);
        tmp.addEventListener('loadedmetadata', () =>
            startCountdown(estimateETA(tmp.duration || 180))
        );

        try {
            setTimeout(() => { setStepState("upload", "done"); setStepState("convert", "active"); statusEl.textContent = "Convert (denoise: mid)…"; progress.style.width = "30%"; }, 400);
            setTimeout(() => { setStepState("convert", "done"); setStepState("diarize", "active"); statusEl.textContent = "Diarize (pyannote)…"; progress.style.width = "55%"; }, 900);
            setTimeout(() => { setStepState("diarize", "done"); setStepState("transcribe", "active"); statusEl.textContent = "Transcribe (Pathumma)…"; progress.style.width = "80%"; }, 1600);

            const res = await fetch("/tools/transcribe_auto", { method: "POST", body: data });
            const txt = await res.text();
            let json; try { json = JSON.parse(txt); } catch (e) { throw new Error("API ตอบกลับไม่ใช่ JSON: " + txt.slice(0, 300)); }

            console.log("API /tools/transcribe_auto =>", json);
            if (!json.ok) throw new Error(json.error || "ถอดเสียงไม่สำเร็จ");

            const segs = getSegmentsFromResponse(json, audio.duration || 0);
            if (!segs.length) {
                chatBox.innerHTML = `<div class="text-slate-500 text-sm">ไม่มี segments ในผลลัพธ์ (ลองดู console).</div>`;
            } else {
                renderTranscript(segs);
            }

            setStepState("transcribe", "done");
            setStepState("done", "done");
            statusEl.textContent = "เสร็จสิ้น ✅";
            progressInd.classList.add('hidden');
            progress.style.width = "100%";
            downloadBtn.classList.remove('hidden');
            stopCountdown();

            showToast('ok', 'ถอดเสียงสำเร็จ');
        } catch (e) {
            progressInd.classList.add('hidden');
            statusEl.innerHTML = `<span class="text-red-600">❌ Error:</span> ${e.message}`;
            stopCountdown();
            showToast('err', e.message);
        } finally {
            btnSend.disabled = false;
        }
    }


    // ===== transcript renderer (ชิดซ้ายทั้งหมด + click-to-seek)
    function renderTranscript(segments) {
        // 1) กรองช่วงที่ไม่ใช้: ไม่มีข้อความ หรือเป็น ERROR
        const clean = (segments || []).filter(s => {
            const t = (s.text || "").trim();
            if (!t) return false;
            // ตัดพวก [ERROR: ...], ERROR:, [ERROR], <error ...> ทั้งหมด
            if (/^\s*\[?\s*error[\s:]/i.test(t) || /^error[\s:]/i.test(t)) return false;
            return true;
        });

        const fullText = clean.map(s => s.text).join(" ").trim();
        downloadBtn.onclick = () => {
            const text = exportTextFromSegments(segments);
            const content = text || "[no usable text]";
            const blob = new Blob(["\ufeff" + content], { type: "text/plain;charset=utf-8" }); // \ufeff เผื่อเปิดใน Excel/Notepad++
            const url = URL.createObjectURL(blob);
            const a = document.createElement("a");
            // ตั้งชื่อไฟล์ตามเวลา
            const ts = new Date().toISOString().slice(0, 19).replace(/[:T]/g, "-");
            a.href = url;
            a.download = `transcription-${ts}.txt`;
            a.click();
            URL.revokeObjectURL(url);
        };


        chatBox.innerHTML = "";
        if (!clean.length) {
            chatBox.innerHTML = `<div class="text-slate-400 text-sm">ไม่มีข้อความที่ใช้งานได้</div>`;
            return;
        }

        // 2) กำหนดโทนสีต่อ speaker (ทั้งหมดยังคง “ชิดซ้าย”)
        const palette = [
            { bg: "bg-indigo-50", border: "border-indigo-200", head: "text-indigo-700" },
            { bg: "bg-emerald-50", border: "border-emerald-200", head: "text-emerald-700" },
            { bg: "bg-rose-50", border: "border-rose-200", head: "text-rose-700" },
            { bg: "bg-amber-50", border: "border-amber-200", head: "text-amber-700" },
            { bg: "bg-cyan-50", border: "border-cyan-200", head: "text-cyan-700" },
            { bg: "bg-violet-50", border: "border-violet-200", head: "text-violet-700" },
        ];
        const colorOf = {}; let idx = 0;
        const getTheme = (spk) => {
            if (!colorOf[spk]) colorOf[spk] = palette[idx++ % palette.length];
            return colorOf[spk];
        };

        let prevSpk = null;
        clean.forEach(s => {
            const spk = s.speaker || "SPEAKER";
            const theme = getTheme(spk);
            const hasTime = Number.isFinite(s.start) && Number.isFinite(s.end);
            const header = hasTime
                ? `${spk} • ${tlabel(s.start || 0)}–${tlabel(s.end || 0)}`
                : `${spk}`;
            const mtCls = (prevSpk === spk) ? "mt-1.5" : "mt-3";

            const wrap = document.createElement("div");
            wrap.className = `flex justify-start ${mtCls}`;
            wrap.innerHTML = `
      <button data-start="${Number.isFinite(s.start) ? s.start : 0}"
        class="bubble text-left rounded-2xl px-4 py-3 shadow-sm border ${theme.border} ${theme.bg} hover:bg-white transition">
        <div class="text-xs font-semibold ${theme.head} mb-1">${header}</div>
        <div class="text-[15px] leading-7 text-slate-800">${(s.text || '').replace(/</g, '&lt;')}</div>
      </button>
    `;
            chatBox.appendChild(wrap);
            prevSpk = spk;
        });

        chatBox.scrollTop = chatBox.scrollHeight;

        // คลิกที่บับเบิลเพื่อ seek
        chatBox.querySelectorAll('button[data-start]').forEach(b => {
            b.onclick = () => {
                const t = parseFloat(b.dataset.start || "0");
                if (!isNaN(t)) { audio.currentTime = t; audio.play(); btnPlay.textContent = 'Pause'; }
            };
        });
    }

    function fmtTime(sec) {
        if (!Number.isFinite(sec) || sec < 0) return "--:--";
        const h = Math.floor(sec / 3600);
        const m = Math.floor((sec % 3600) / 60);
        const s = Math.floor(sec % 60);
        return (h ? String(h).padStart(2, "0") + ":" : "") +
            String(m).padStart(2, "0") + ":" +
            String(s).padStart(2, "0");
    }

    // ทำข้อความสำหรับดาวน์โหลด (ข้าม ERROR/ว่าง)
    function exportTextFromSegments(segments) {
        const lines = [];
        (segments || []).forEach((s) => {
            const txt = (s.text || "").trim();
            if (!txt) return;
            if (/^\s*\[?\s*error[\s:]/i.test(txt) || /^error[\s:]/i.test(txt)) return;

            const speaker = (s.speaker || "SPEAKER").toUpperCase();
            const t1 = fmtTime(Number(s.start));
            const t2 = fmtTime(Number(s.end));
            lines.push(`[${t1} - ${t2}] ${speaker}: ${txt}`);
        });
        return lines.join("\n");
    }


});
