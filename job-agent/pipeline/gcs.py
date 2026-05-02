"""
Google Cloud Storage helper.

Set GCS_BUCKET to enable PDF uploads.
Authentication uses Application Default Credentials (ADC) on GCP VMs,
or GOOGLE_APPLICATION_CREDENTIALS pointing to a service-account JSON on
non-GCP machines (e.g. your laptop running the agent).

If GCS_BUCKET is not set, all functions are no-ops and return the
local path unchanged — backward compatible with local/SQLite dev.
"""

import os
import logging
import datetime

logger = logging.getLogger(__name__)

GCS_BUCKET = os.getenv("GCS_BUCKET", "")


def _client():
    from google.cloud import storage
    return storage.Client()


def upload_pdf(local_path: str, filename: str) -> str:
    """
    Upload a compiled PDF to GCS.

    Returns the gs:// URI on success, or the original local_path if
    GCS_BUCKET is not configured or the upload fails.
    """
    if not GCS_BUCKET:
        return local_path
    try:
        client = _client()
        bucket = client.bucket(GCS_BUCKET)
        blob = bucket.blob(f"resumes/{filename}")
        blob.upload_from_filename(local_path, content_type="application/pdf")
        gcs_uri = f"gs://{GCS_BUCKET}/resumes/{filename}"
        logger.info("Uploaded PDF to GCS: %s", gcs_uri)
        return gcs_uri
    except Exception as e:
        logger.warning("GCS upload failed (%s) — keeping local path", e)
        return local_path


def get_signed_url(gcs_uri: str, expiry_minutes: int = 30) -> str:
    """
    Generate a short-lived signed URL for a GCS object.

    Returns the original gcs_uri unchanged if it is not a gs:// URI
    or if signing fails.
    """
    if not gcs_uri or not gcs_uri.startswith("gs://"):
        return gcs_uri
    try:
        path = gcs_uri[5:]  # strip gs://
        bucket_name, _, object_name = path.partition("/")
        client = _client()
        blob = client.bucket(bucket_name).blob(object_name)
        url = blob.generate_signed_url(
            expiration=datetime.timedelta(minutes=expiry_minutes),
            method="GET",
            version="v4",
        )
        return url
    except Exception as e:
        logger.warning("GCS signed URL failed: %s", e)
        return gcs_uri


def is_gcs_uri(path: str) -> bool:
    return bool(path and path.startswith("gs://"))
