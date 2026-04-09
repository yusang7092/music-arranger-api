from fastapi import APIRouter, UploadFile, File, BackgroundTasks, HTTPException, Depends
from app.models.schemas import ArrangeRequest, ArrangeStatus
from app.core.supabase import supabase

router = APIRouter(prefix="/arrange", tags=["arrange"])


async def _process_arrangement(
    arrangement_id: str,
    file_path: str,
    request: ArrangeRequest,
) -> None:
    """Background task: run audio processing and AI arrangement pipeline."""
    # TODO: implement full pipeline
    # 1. audio_processor.extract_notes_basic_pitch / separate_stems_demucs
    # 2. ai_arranger.arrange_quick / arrange_thorough
    # 3. score_generator.generate_score
    # 4. upload results to Supabase Storage
    # 5. update arrangement row status -> "done" or "error"
    pass


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
        .select("id, status, scores")
        .eq("id", arrangement_id)
        .single()
        .execute()
    )

    if not response.data:
        raise HTTPException(status_code=404, detail="Arrangement not found")

    data = response.data
    return ArrangeStatus(
        id=data["id"],
        status=data["status"],
        scores=data.get("scores"),
    )
