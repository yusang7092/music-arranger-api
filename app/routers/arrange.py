from fastapi import APIRouter, UploadFile, File, BackgroundTasks, HTTPException, Depends
from app.models.schemas import ArrangeRequest, ArrangeStatus, ScoreResult
from app.core.supabase import supabase

router = APIRouter(prefix="/arrange", tags=["arrange"])


async def _process_arrangement(
    arrangement_id: str,
    file_path: str,
    request: ArrangeRequest,
) -> None:
    import os
    from app.services import audio_processor, ai_arranger, score_generator

    try:
        # 1. 상태 → processing
        supabase.table("arrangements").update(
            {"status": "processing"}
        ).eq("id", arrangement_id).execute()

        # 2. 음표 추출 / 스템 분리
        if request.mode == "quick":
            notes_data = await audio_processor.extract_notes_basic_pitch(file_path)
            arrangement = await ai_arranger.arrange_quick(notes_data, request.instruments)
        else:  # thorough
            stems_data = await audio_processor.separate_stems_demucs(file_path)
            stems_notes = await audio_processor.extract_notes_from_stems(stems_data)
            arrangement = await ai_arranger.arrange_thorough(stems_notes, request.instruments)

        # 3. 악기별 악보 생성 + Storage 업로드
        score_records = []
        instruments_in_arrangement = arrangement.get("instruments", {})

        for inst_spec in request.instruments:
            # "바이올린_2" → "바이올린", 2
            parts = inst_spec.split("_")
            inst_kr = parts[0]
            count = int(parts[1]) if len(parts) > 1 else 1

            from app.services.ai_arranger import INSTRUMENT_MAP
            inst_en = INSTRUMENT_MAP.get(inst_kr, inst_kr)

            # AI 편곡 결과에서 해당 악기 데이터 가져오기
            inst_arrangement = instruments_in_arrangement.get(inst_en, {})
            if not inst_arrangement:
                # 영어명 매핑 실패 시 첫 번째 키 사용
                for key, val in instruments_in_arrangement.items():
                    if inst_kr.lower() in key.lower() or key.lower() in inst_en.lower():
                        inst_arrangement = val
                        break

            # 악보 생성
            arrangement_for_gen = {
                "tempo": arrangement.get("tempo", 120),
                "time_signature": arrangement.get("time_signature", "4/4"),
                "notes": inst_arrangement.get("notes", []) if isinstance(inst_arrangement, dict) else []
            }

            pdf_bytes, png_bytes = await score_generator.generate_score(
                arrangement_for_gen, inst_en
            )

            # Supabase Storage 업로드
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
                png_key = f"scores/{arrangement_id}/{inst_en}_score.png"
                sb.storage.from_("scores").upload(
                    png_key, png_bytes, {"content-type": "image/png"}
                )
                png_url = sb.storage.from_("scores").get_public_url(png_key)

            score_records.append({
                "arrangement_id": arrangement_id,
                "instrument": inst_kr,
                "pdf_url": pdf_url,
                "png_url": png_url,
            })

        # 4. scores 테이블에 삽입
        if score_records:
            supabase.table("scores").insert(score_records).execute()

        # 5. 상태 → done
        supabase.table("arrangements").update(
            {"status": "done"}
        ).eq("id", arrangement_id).execute()

    except Exception as e:
        # 에러 시 상태 업데이트
        supabase.table("arrangements").update(
            {"status": "error"}
        ).eq("id", arrangement_id).execute()
        raise
    finally:
        # 임시 파일 정리
        import os
        if os.path.exists(file_path):
            os.remove(file_path)


@router.post("", status_code=202)
async def start_arrangement(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    arrangement_id: str = "",
    instruments: list[str] = [],
    mode: str = "quick",
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

    request = ArrangeRequest(
        arrangement_id=arrangement_id,
        instruments=instruments,
        mode=mode,
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
    return ArrangeStatus(
        id=data["id"],
        status=data["status"],
        scores=scores,
    )
