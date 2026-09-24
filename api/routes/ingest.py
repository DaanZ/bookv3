"""Feeding the pipeline: pricing a PDF, uploading it, and the job queue. The owner's."""

import os

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile

from api import estimate as estimating
from api import jobs
from api.deps import admin

# A book PDF; anything larger than this is very unlikely to be one.
MAX_UPLOAD_BYTES = 200 * 1024 * 1024

router = APIRouter()


@router.get("/api/ingest/jobs")
def get_jobs(profile: dict = Depends(admin)):
    has_key = bool(os.environ.get("OPENROUTER_API_KEY") or os.environ.get("OPENAI_API_KEY"))
    rows = jobs.list_jobs()
    # What a failed job could resume from — parts already bought, and not re-bought.
    for row in rows:
        if row.get("status") == "failed":
            row["partsBought"] = jobs.partial_parts(row["id"])
    # The models a failed job could be retried with. Sent here rather than fetched
    # separately because the reason a job failed is usually the model, and the retry
    # should not need an estimate round-trip to offer an alternative.
    return {
        "jobs": rows,
        "hasKey": has_key,
        "models": estimating.CANDIDATE_MODELS,
        "proven": sorted(estimating.PROVEN_MODELS),
    }


async def _read_pdf_upload(file: UploadFile) -> bytes:
    """The same checks for both the estimate and the real upload.

    PDF and EPUB. The extension decides how it will be read, and the first bytes decide
    whether to believe it — an EPUB is a zip, so it opens `PK`.
    """
    name = (file.filename or "book.pdf").lower()
    if not name.endswith((".pdf", ".epub")):
        raise HTTPException(status_code=400, detail="Only PDF and EPUB files can be ingested.")

    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="That file is empty.")
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="That file is larger than 200MB.")

    expected, label = (b"PK", "EPUB") if name.endswith(".epub") else (b"%PDF", "PDF")
    if not data.startswith(expected):
        raise HTTPException(status_code=400, detail=f"That file is not a {label}.")
    return data


@router.post("/api/ingest/estimate")
async def estimate_upload(
    file: UploadFile = File(...),
    chunks: int | None = None,
    profile: dict = Depends(admin),
):
    """Price a PDF without running anything.

    The file is read into a temporary path, measured and thrown away — nothing is queued
    and no LLM is called, so this is safe to run on a machine with no API key. The
    browser sends the file again when the estimate is accepted; that second transfer is
    the price of never leaving an unconfirmed PDF sitting in next/.
    """
    import tempfile

    data = await _read_pdf_upload(file)

    # The suffix is not cosmetic: `read_pdf_pages` dispatches on it, so a hardcoded
    # ".pdf" here handed every EPUB to pypdf and it failed as a corrupt PDF.
    suffix = ".epub" if (file.filename or "").lower().endswith(".epub") else ".pdf"
    handle, path = tempfile.mkstemp(suffix=suffix)
    try:
        with os.fdopen(handle, "wb") as temp:
            temp.write(data)
        try:
            result = estimating.estimate_pdf(path, chunks)
        except ValueError as ex:
            raise HTTPException(status_code=400, detail=str(ex))
        except Exception as ex:
            raise HTTPException(status_code=400, detail=f"This file could not be read as a PDF: {ex}")
    finally:
        try:
            os.remove(path)
        except OSError:
            pass

    return {"filename": file.filename, "bytes": len(data), **result}


@router.post("/api/ingest/upload")
async def upload(
    file: UploadFile = File(...),
    chunks: int | None = None,
    model: str | None = None,
    cost: float | None = None,
    profile: dict = Depends(admin),
):
    """Take a PDF and queue it for the pipeline. The owner's, like everything that
    changes what is on the shelf rather than what somebody has read of it."""
    data = await _read_pdf_upload(file)
    name = file.filename or "book.pdf"
    try:
        return jobs.public(jobs.submit(name, data, chunks, model, {"cost": cost}))
    except ValueError as ex:
        raise HTTPException(status_code=400, detail=str(ex))


@router.delete("/api/ingest/jobs")
def clear_jobs(profile: dict = Depends(admin)):
    """Clear finished and failed jobs from the list; the books they made are kept."""
    return {"cleared": jobs.clear_finished()}


@router.post("/api/ingest/jobs/{job_id}/resume")
def resume_job(job_id: str, model: str | None = None, profile: dict = Depends(admin)):
    """Run a failed job again from the parts it already bought.

    The alternative was re-buying the whole book: "One Nation Under Blackmail" is 39
    parts and died at 20, so nineteen paid-for summaries were thrown away because there
    was nowhere to put them.
    """
    job, error = jobs.resume(job_id, model)
    if error == "No such job.":
        raise HTTPException(status_code=404, detail=error)
    if error:
        raise HTTPException(status_code=409, detail=error)
    return job


@router.delete("/api/ingest/jobs/{job_id}")
def remove_job(job_id: str, profile: dict = Depends(admin)):
    """Remove one settled job. A running job has to finish or fail first."""
    removed = jobs.remove(job_id)
    if removed is None:
        raise HTTPException(status_code=404, detail="No such job.")
    if removed is False:
        raise HTTPException(status_code=409, detail="That job is still running.")
    return {"removed": True}
