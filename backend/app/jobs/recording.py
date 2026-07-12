"""process_recording — assemble the browser-uploaded interview recording.

The candidate's browser records mixed mic+agent audio with MediaRecorder and
uploads ~15s chunks to kandidly-recordings/{id}/chunks/ (api/candidate.py).
Chunks from a single MediaRecorder session byte-concatenate into one valid
stream (the container header lives in chunk 0); the Safari fallback uploads a
single mp4 blob, which ffmpeg reads the same way.

Pipeline: concat chunks → head-trim so audio t=0 ≈ interviews.started_at (the
transcript's zero point; the recorder starts at room connect, a few seconds
earlier) → transcode to mono 32 kbps Opus/OGG → extract waveform peaks →
write audio.ogg + StoredFile, set audio_recording_id/audio_waveform → delete
chunks. Idempotent: no-op once audio_recording_id is set, so the deferred
safety-net enqueue from finalize_interview is harmless.
"""

from __future__ import annotations

import array
import asyncio
import hashlib
import json
import tempfile
from datetime import datetime
from pathlib import Path

import structlog

from app.core import storage
from app.core.ids import new_id
from app.db.models import Application, Interview, StoredFile
from app.db.session import SessionLocal

log = structlog.get_logger(__name__)

_PEAK_BINS = 1024
_PCM_RATE = 8000  # peak-extraction sample rate; plenty for a visual waveform
_MAX_HEAD_TRIM_S = 30.0  # clock-skew guard on the started_at alignment trim


def compute_peaks(
    pcm: bytes, bins: int = _PEAK_BINS, rate: int = _PCM_RATE
) -> tuple[list[int], float]:
    """Max-abs peaks (0–100 ints, one per bin) over s16le mono PCM, plus the
    duration in seconds. Same waveform math as the seed's _gen_wav."""
    samples = array.array("h")
    samples.frombytes(pcm[: (len(pcm) // 2) * 2])
    n = len(samples)
    if n == 0:
        return [], 0.0
    duration = n / rate
    per = max(1, n // bins)
    peaks: list[int] = []
    for k in range(bins):
        window = samples[k * per : (k + 1) * per]
        if not window:
            peaks.append(0)
            continue
        loudest = max(max(window), -min(window))
        peaks.append(min(100, int(loudest * 100 / 32767)))
    return peaks, duration


async def _run_ffmpeg(*args: str) -> bytes:
    proc = await asyncio.create_subprocess_exec(
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "error",
        *args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    out, err = await proc.communicate()
    if proc.returncode != 0:
        raise RuntimeError(f"ffmpeg failed ({proc.returncode}): {err.decode(errors='replace')[:500]}")
    return out


def _head_trim_seconds(manifest: dict, interview_started_at: datetime | None) -> float:
    """Seconds to trim from the recording head so t=0 matches started_at."""
    client_started = manifest.get("started_at")
    if not client_started or interview_started_at is None:
        return 0.0
    try:
        delta = (interview_started_at - datetime.fromisoformat(client_started)).total_seconds()
    except ValueError:
        return 0.0
    return delta if 0 < delta <= _MAX_HEAD_TRIM_S else 0.0


async def process_recording(ctx: dict, interview_id: str) -> None:
    async with SessionLocal() as db:
        interview = await db.get(Interview, interview_id)
        if interview is None or interview.audio_recording_id is not None:
            return  # idempotent
        started_at = interview.started_at
        application = await db.get(Application, interview.application_id)
        candidate_id = application.candidate_id  # stored_files.created_by is NOT NULL

    manifest_key = storage.recording_manifest_key(interview_id)  # type: ignore[arg-type]
    keys = await storage.list_keys(storage.BUCKET_RECORDINGS, f"{interview_id}/chunks/")
    chunk_keys = sorted(k for k in keys if k != manifest_key)
    if not chunk_keys:
        log.info("recording_no_chunks", interview_id=interview_id)
        return

    manifest: dict = {}
    if manifest_key in keys:
        try:
            manifest = json.loads(
                await storage.get_object(storage.BUCKET_RECORDINGS, manifest_key)
            )
        except Exception:  # noqa: BLE001
            log.warning("recording_manifest_unreadable", interview_id=interview_id)
    offset = _head_trim_seconds(manifest, started_at)

    with tempfile.TemporaryDirectory(prefix="kndl-rec-") as tmp:
        raw = Path(tmp) / "raw.bin"
        with raw.open("wb") as fh:
            for key in chunk_keys:
                fh.write(await storage.get_object(storage.BUCKET_RECORDINGS, key))
        out = Path(tmp) / "audio.ogg"
        # -ss after -i = decode-accurate trim; re-encoding also repairs the
        # missing duration/cues metadata MediaRecorder streams lack.
        trim = ["-ss", f"{offset:.3f}"] if offset else []
        await _run_ffmpeg(
            "-y", "-i", str(raw), *trim, "-vn", "-c:a", "libopus", "-b:a", "32k", "-ac", "1",
            str(out),
        )
        pcm = await _run_ffmpeg(
            "-i", str(out), "-f", "s16le", "-ac", "1", "-ar", str(_PCM_RATE), "-"
        )
        data = out.read_bytes()

    peaks, duration = compute_peaks(pcm)
    if not data or duration <= 0:
        log.warning("recording_empty_output", interview_id=interview_id)
        return

    final_key = storage.recording_key(interview_id, "ogg")  # type: ignore[arg-type]
    await storage.put_object(storage.BUCKET_RECORDINGS, final_key, data, "audio/ogg")

    async with SessionLocal() as db:
        interview = await db.get(Interview, interview_id)
        if interview is None or interview.audio_recording_id is not None:
            return  # double-enqueue race — the other run won
        stored = StoredFile(
            id=new_id(),
            bucket=storage.BUCKET_RECORDINGS,
            key=final_key,
            mime="audio/ogg",
            bytes=len(data),
            sha256=hashlib.sha256(data).hexdigest(),
            created_by=candidate_id,
        )
        db.add(stored)
        await db.flush()
        interview.audio_recording_id = stored.id
        interview.audio_waveform = {
            "version": 1,
            "peaks": peaks,
            "bins": len(peaks),
            "duration_seconds": int(round(duration)),
        }
        await db.commit()

    for key in keys:
        try:
            await storage.delete_object(storage.BUCKET_RECORDINGS, key)
        except Exception:  # noqa: BLE001
            log.warning("recording_chunk_delete_failed", interview_id=interview_id, key=key)

    log.info(
        "recording_processed",
        interview_id=interview_id,
        chunks=len(chunk_keys),
        duration_s=round(duration, 1),
        head_trim_s=offset,
    )
