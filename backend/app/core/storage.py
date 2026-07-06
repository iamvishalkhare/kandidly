"""S3-compatible object storage (SPEC §6.3). All access via backend-issued
presigned URLs; buckets are private. Uses aioboto3.

Bucket names (SPEC §6.3):
  kandidly-resumes / kandidly-snapshots / kandidly-selfies /
  kandidly-recordings / kandidly-reports
"""

from __future__ import annotations

from uuid import UUID

import aioboto3

from app.core.config import settings

BUCKET_RESUMES = "kandidly-resumes"
BUCKET_SNAPSHOTS = "kandidly-snapshots"
BUCKET_SELFIES = "kandidly-selfies"
BUCKET_RECORDINGS = "kandidly-recordings"
BUCKET_REPORTS = "kandidly-reports"

PRESIGN_TTL = 600  # 10 minutes (SPEC §16.6)


def _session() -> aioboto3.Session:
    return aioboto3.Session()


def _client_kwargs(public: bool = False) -> dict:
    # Presigned URLs are signed against the request host, so URLs handed to a
    # browser must use the browser-reachable endpoint (e.g. localhost:9000),
    # not the in-cluster one (minio:9000).
    endpoint = settings.s3_endpoint
    if public and settings.s3_public_endpoint:
        endpoint = settings.s3_public_endpoint
    return {
        "endpoint_url": endpoint,
        "aws_access_key_id": settings.s3_access_key,
        "aws_secret_access_key": settings.s3_secret_key,
        "region_name": settings.s3_region,
    }


async def put_object(bucket: str, key: str, body: bytes, content_type: str) -> None:
    async with _session().client("s3", **_client_kwargs()) as s3:
        await s3.put_object(Bucket=bucket, Key=key, Body=body, ContentType=content_type)


async def get_object(bucket: str, key: str) -> bytes:
    async with _session().client("s3", **_client_kwargs()) as s3:
        obj = await s3.get_object(Bucket=bucket, Key=key)
        return await obj["Body"].read()


async def delete_object(bucket: str, key: str) -> None:
    async with _session().client("s3", **_client_kwargs()) as s3:
        await s3.delete_object(Bucket=bucket, Key=key)


async def presign_get(bucket: str, key: str, ttl: int = PRESIGN_TTL, public: bool = False) -> str:
    async with _session().client("s3", **_client_kwargs(public=public)) as s3:
        return await s3.generate_presigned_url(
            "get_object", Params={"Bucket": bucket, "Key": key}, ExpiresIn=ttl
        )


def resume_key(application_id: UUID, uid: UUID, ext: str) -> str:
    return f"{application_id}/{uid}.{ext.lstrip('.')}"


def snapshot_key(interview_id: UUID, epoch_ms: int) -> str:
    return f"{interview_id}/{epoch_ms}.webp"


def selfie_key(application_id: UUID) -> str:
    return f"{application_id}/reference.webp"


def recording_key(interview_id: UUID, ext: str = "ogg") -> str:
    return f"{interview_id}/audio.{ext.lstrip('.')}"


def report_key(interview_id: UUID) -> str:
    return f"{interview_id}/report.html"
