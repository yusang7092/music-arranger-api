import json
from fastapi import APIRouter, UploadFile, File, Form, BackgroundTasks, HTTPException
from app.models.schemas import ArrangeRequest, ArrangeStatus, ScoreResult, ReviseRequest, RevisionStatus
from app.core.supabase import supabase

router = APIRouter(prefix="/arrange", tags=["arrange"])

# 수정 작업 상태 추적 (in-memory, 단일 인스턴스 서버)
_revision_tasks: dict[str, dict] = {}   # key: f"{arrangement_id}:{instrument_kr}"

# 편곡 진행도 추적
_progress: dict[str, dict] = {}  # key: arrangement_id, value: {progress, stage}


def _set_progress(arrangement_id: str, progress: int, stage: str) -> None:
    _progress[arrangement_id] = {"progress": progress, "stage": stage}


async def _process_arrangement(
    arrangement_id: str,
    file_path: str,
    request: ArrangeRequest,
) -> None:
    import os
    from app.services import audio_processor, ai_arranger, score_generator

    n = len(request.instruments) or 1

    try:
        # 1. 상태 → processing
        _set_progress(arrangement_id, 3, "시작 중...")
        supabase.table("arrangements").update(
            {"status": "processing"}
        ).eq("id", arrangement_id).execute()

        # 2. 음표 추출 / 스템 분리
        original_filename = request.original_filename or ""
        if request.mode == "quick":
            _set_progress(arrangement_id, 10, "음원에서 음표 추출 중")
            notes_data = await audio_processor.extract_notes_basic_pitch(file_path)
            _set_progress(arrangement_id, 40, "AI 편곡 중")
            arrangement = await ai_arranger.arrange_quick(notes_data, request.instruments, original_filename, request.target_instrument)
        else:  # thorough
            _set_progress(arrangement_id, 8, "스템 분리 중 (보컬·악기 분리)")
            stems_data = await audio_processor.separate_stems_demucs(file_path)
            _set_progress(arrangement_id, 38, "각 파트 음표 추출 중")
            stems_notes = await audio_processor.extract_notes_from_stems(stems_data)
            _set_progress(arrangement_id, 58, "AI 편곡 중")
            arrangement = await ai_arranger.arrange_thorough(stems_notes, request.instruments, original_filename, request.target_instrument)

        _set_progress(arrangement_id, 70, "편곡 완료 — 악보 저장 중")

        # 3. AI 편곡 결과 JSON을 Storage에 저장 (수정 요청 시 재활용)
        try:
            from app.core.supabase import supabase as sb
            arrangement_json_bytes = json.dumps(arrangement).encode()
            arrangement_json_key = f"scores/{arrangement_id}/arrangement.json"
            sb.storage.from_("scores").upload(
                arrangement_json_key,
                arrangement_json_bytes,
                {"content-type": "application/json", "x-upsert": "true"},
            )
        except Exception:
            pass  # 저장 실패해도 악보 생성은 계속

        # 4. 악기별 악보 생성 + Storage 업로드
        score_records = []
        instruments_in_arrangement = arrangement.get("instruments", {})

        # target_instrument만 악보 생성 (지정 없으면 전체)
        target_kr = request.target_instrument
        score_instruments = [request.target_instrument] if target_kr else [
            inst_spec.split("_")[0] for inst_spec in request.instruments
        ]
        n_score = len(score_instruments) or 1

        for idx, inst_kr in enumerate(score_instruments):
            inst_progress = 70 + int((idx / n_score) * 25)
            inst_spec = next((s for s in request.instruments if s.split("_")[0] == inst_kr), inst_kr)

            _set_progress(arrangement_id, inst_progress, f"{inst_kr} 악보 생성 중 ({idx + 1}/{n_score})")

            from app.services.ai_arranger import INSTRUMENT_MAP
            inst_en = INSTRUMENT_MAP.get(inst_kr, inst_kr)

            inst_arrangement = instruments_in_arrangement.get(inst_en, {})
            if not inst_arrangement:
                for key, val in instruments_in_arrangement.items():
                    if inst_kr.lower() in key.lower() or key.lower() in inst_en.lower():
                        inst_arrangement = val
                        break

            arrangement_for_gen = {
                "tempo": arrangement.get("tempo", 120),
                "time_signature": arrangement.get("time_signature", "4/4"),
                "notes": inst_arrangement.get("notes", []) if isinstance(inst_arrangement, dict) else []
            }

            pdf_bytes, png_bytes = await score_generator.generate_score(
                arrangement_for_gen, inst_en
            )

            from app.core.supabase import supabase as sb

            pdf_url = ""
            png_url = ""

            if pdf_bytes:
                pdf_key = f"scores/{arrangement_id}/{inst_en}_score.pdf"
                sb.storage.from_("scores").upload(
                    pdf_key, pdf_bytes, {"content-type": "application/pdf"}
                )
                pdf_url = sb.storage.from_("scores").get_public_url(pdf_key)

            if png_bytes:
                # verovio는 SVG를 반환하므로 .svg로 저장 (브라우저 직접 렌더링)
                is_svg = png_bytes[:5] == b"<?xml" or png_bytes[:4] == b"<svg"
                ext = "svg" if is_svg else "png"
                ct = "image/svg+xml" if is_svg else "image/png"
                png_key = f"scores/{arrangement_id}/{inst_en}_score.{ext}"
                sb.storage.from_("scores").upload(
                    png_key, png_bytes, {"content-type": ct, "x-upsert": "true"}
                )
                png_url = sb.storage.from_("scores").get_public_url(png_key)

            score_records.append({
                "arrangement_id": arrangement_id,
                "instrument": inst_kr,
                "pdf_url": pdf_url,
                "png_url": png_url,
            })

        _set_progress(arrangement_id, 97, "마무리 중...")

        if score_records:
            supabase.table("scores").insert(score_records).execute()

        _set_progress(arrangement_id, 100, "완료")
        supabase.table("arrangements").update(
            {"status": "done"}
        ).eq("id", arrangement_id).execute()

    except Exception as e:
        _set_progress(arrangement_id, 0, f"오류: {str(e)[:60]}")
        supabase.table("arrangements").update(
            {"status": "error"}
        ).eq("id", arrangement_id).execute()
        raise
    finally:
        import os
        if os.path.exists(file_path):
            os.remove(file_path)


@router.post("", status_code=202)
async def start_arrangement(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    arrangement_id: str = Form(""),
    instruments: list[str] = Form([]),
    mode: str = Form("quick"),
    original_filename: str = Form(""),
    target_instrument: str = Form(""),
):
    """
    Upload an audio file and start the arrangement pipeline.

    - Saves the uploaded file temporarily.
    - Queues a background task that runs audio processing + AI arrangement.
    - Returns the arrangement_id immediately (202 Accepted).
    """
    if not arrangement_id:
        raise HTTPException(status_code=400, detail="arrangement_id is required")

    import tempfile, os, shutil

    suffix = os.path.splitext(file.filename or "audio.mp3")[1]
    tmp_file = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
    try:
        shutil.copyfileobj(file.file, tmp_file)
        tmp_file.flush()
        tmp_path = tmp_file.name
    finally:
        tmp_file.close()

    # 오디오 파일을 Supabase Storage에 백업 (service role key로 RLS 우회)
    try:
        import re as _re
        safe_name = _re.sub(r'[^\w.\-]', '_', original_filename or file.filename or "audio.mp3")
        safe_name = _re.sub(r'_+', '_', safe_name)
        storage_key = f"audio/{arrangement_id}/{safe_name}"
        with open(tmp_path, "rb") as f:
            audio_bytes = f.read()
        supabase.storage.from_("audio-files").upload(
            storage_key, audio_bytes,
            {"content-type": file.content_type or "audio/mpeg", "x-upsert": "true"}
        )
        audio_url = supabase.storage.from_("audio-files").get_public_url(storage_key)
        supabase.table("arrangements").update({"audio_url": audio_url}).eq("id", arrangement_id).execute()
    except Exception as e:
        pass  # 저장 실패해도 편곡은 계속

    request = ArrangeRequest(
        arrangement_id=arrangement_id,
        instruments=instruments,
        mode=mode,
        original_filename=original_filename,
        target_instrument=target_instrument,
    )
    background_tasks.add_task(_process_arrangement, arrangement_id, tmp_path, request)

    return {"arrangement_id": arrangement_id, "status": "pending"}


@router.get("/{arrangement_id}/status", response_model=ArrangeStatus)
async def get_arrangement_status(arrangement_id: str):
    """
    Query Supabase for the current status of an arrangement job.
    Returns ArrangeStatus with optional score URLs when done.
    """
    response = (
        supabase.table("arrangements")
        .select("id, status")
        .eq("id", arrangement_id)
        .single()
        .execute()
    )

    if not response.data:
        raise HTTPException(status_code=404, detail="Arrangement not found")

    scores_response = (
        supabase.table("scores")
        .select("*")
        .eq("arrangement_id", arrangement_id)
        .execute()
    )

    scores = None
    if scores_response.data:
        scores = [
            ScoreResult(
                instrument=s["instrument"],
                pdf_url=s.get("pdf_url"),
                png_url=s.get("png_url"),
            )
            for s in scores_response.data
        ]

    data = response.data
    prog = _progress.get(arrangement_id, {})
    return ArrangeStatus(
        id=data["id"],
        status=data["status"],
        scores=scores,
        progress=prog.get("progress", 0),
        stage=prog.get("stage", ""),
    )


# ─── 악기별 수정 ───────────────────────────────────────────────

async def _revise_instrument(arrangement_id: str, instrument_kr: str, feedback: str) -> None:
    """특정 악기 악보를 피드백 기반으로 수정하는 백그라운드 태스크."""
    from app.services import ai_arranger, score_generator
    from app.core.supabase import supabase as sb
    import time

    task_key = f"{arrangement_id}:{instrument_kr}"

    try:
        # 1. 저장된 arrangement.json 로드
        json_key = f"scores/{arrangement_id}/arrangement.json"
        json_bytes = sb.storage.from_("scores").download(json_key)
        arrangement = json.loads(json_bytes)

        # 2. 악기 이름 매핑
        from app.services.ai_arranger import INSTRUMENT_MAP
        inst_en = INSTRUMENT_MAP.get(instrument_kr, instrument_kr)

        # 3. 현재 음표 추출
        current_notes = (
            arrangement.get("instruments", {})
            .get(inst_en, {})
            .get("notes", [])
        )
        tempo = arrangement.get("tempo", 120)
        time_sig = arrangement.get("time_signature", "4/4")

        # 4. AI 수정
        revised_notes = await ai_arranger.revise_instrument(
            current_notes, instrument_kr, inst_en, feedback, tempo, time_sig
        )

        # 5. 악보 재생성
        revised_arrangement = {"tempo": tempo, "time_signature": time_sig, "notes": revised_notes}
        pdf_bytes, png_bytes = await score_generator.generate_score(revised_arrangement, inst_en)

        # 6. 새 파일 업로드 (타임스탬프로 구분)
        ts = int(time.time())
        pdf_url = ""
        png_url = ""

        if pdf_bytes:
            pdf_key = f"scores/{arrangement_id}/{inst_en}_revised_{ts}.pdf"
            sb.storage.from_("scores").upload(pdf_key, pdf_bytes, {"content-type": "application/pdf"})
            pdf_url = sb.storage.from_("scores").get_public_url(pdf_key)

        if png_bytes:
            png_key = f"scores/{arrangement_id}/{inst_en}_revised_{ts}.png"
            sb.storage.from_("scores").upload(png_key, png_bytes, {"content-type": "image/png"})
            png_url = sb.storage.from_("scores").get_public_url(png_key)

        # 7. scores 테이블 업데이트
        sb.table("scores").update({
            "pdf_url": pdf_url,
            "png_url": png_url,
        }).eq("arrangement_id", arrangement_id).eq("instrument", instrument_kr).execute()

        # 8. arrangement.json도 수정된 음표로 업데이트
        try:
            if inst_en in arrangement.get("instruments", {}):
                arrangement["instruments"][inst_en]["notes"] = revised_notes
            updated_json = json.dumps(arrangement).encode()
            sb.storage.from_("scores").upload(
                json_key, updated_json, {"content-type": "application/json", "x-upsert": "true"}
            )
        except Exception:
            pass

        _revision_tasks[task_key] = {
            "status": "done",
            "score": {"instrument": instrument_kr, "pdf_url": pdf_url, "png_url": png_url},
        }

    except Exception as e:
        _revision_tasks[task_key] = {"status": "error", "score": None, "error": str(e)}


@router.post("/{arrangement_id}/revise", status_code=202)
async def request_revision(
    arrangement_id: str,
    body: ReviseRequest,
    background_tasks: BackgroundTasks,
):
    """특정 악기 악보 수정 요청. 즉시 202 반환 후 백그라운드에서 처리."""
    task_key = f"{arrangement_id}:{body.instrument}"
    _revision_tasks[task_key] = {"status": "revising", "score": None}
    background_tasks.add_task(_revise_instrument, arrangement_id, body.instrument, body.feedback)
    return {"status": "revising"}


@router.get("/{arrangement_id}/revise/{instrument}/status", response_model=RevisionStatus)
async def get_revision_status(arrangement_id: str, instrument: str):
    """악기별 수정 작업 상태 조회."""
    task_key = f"{arrangement_id}:{instrument}"
    task = _revision_tasks.get(task_key)
    if not task:
        return RevisionStatus(status="idle")
    score = None
    if task.get("score"):
        score = ScoreResult(**task["score"])
    return RevisionStatus(
        status=task["status"],
        score=score,
        error=task.get("error"),
    )
