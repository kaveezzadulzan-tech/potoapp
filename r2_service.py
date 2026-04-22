"""
r2_service.py
-------------
Cloudflare R2 storage using boto3 (S3-compatible).

Setup (one-time, ~5 minutes):
  1. Go to dash.cloudflare.com → R2 Object Storage → Create bucket
     Name it: fieldcam-photos
  2. R2 → Manage R2 API Tokens → Create API Token
     Permissions: Object Read & Write
     Copy: Access Key ID + Secret Access Key
  3. Get your Account ID from the R2 dashboard URL or Overview page
  4. Set these environment variables in Render:
       R2_ACCOUNT_ID      = your cloudflare account ID
       R2_ACCESS_KEY_ID   = your R2 access key
       R2_SECRET_KEY      = your R2 secret key
       R2_BUCKET_NAME     = fieldcam-photos
"""

import os
import io
import boto3
from botocore.config import Config

# ── Config from environment ────────────────────────────────────────────────────
R2_ACCOUNT_ID    = os.environ.get('R2_ACCOUNT_ID', '')
R2_ACCESS_KEY_ID = os.environ.get('R2_ACCESS_KEY_ID', '')
R2_SECRET_KEY    = os.environ.get('R2_SECRET_KEY', '')
R2_BUCKET_NAME   = os.environ.get('R2_BUCKET_NAME', 'fieldcam-photos')
R2_CONFIGURED    = all([R2_ACCOUNT_ID, R2_ACCESS_KEY_ID, R2_SECRET_KEY])


def _get_client():
    return boto3.client(
        's3',
        endpoint_url=f'https://{R2_ACCOUNT_ID}.r2.cloudflarestorage.com',
        aws_access_key_id=R2_ACCESS_KEY_ID,
        aws_secret_access_key=R2_SECRET_KEY,
        config=Config(signature_version='s3v4'),
        region_name='auto',
    )


def upload_to_r2(file_bytes: bytes, key: str, mime_type: str = 'image/jpeg') -> bool:
    """
    Upload raw bytes to R2 under the given key.
    Key format: project_name/folder_name/filename
    Returns True on success, False on failure.
    """
    if not R2_CONFIGURED:
        return False
    try:
        client = _get_client()
        client.put_object(
            Bucket=R2_BUCKET_NAME,
            Key=key,
            Body=file_bytes,
            ContentType=mime_type,
        )
        return True
    except Exception as e:
        print(f'R2 upload failed: {e}')
        return False


def download_from_r2(key: str) -> bytes | None:
    """Download a file from R2 by key. Returns bytes or None on failure."""
    if not R2_CONFIGURED:
        return None
    try:
        client   = _get_client()
        response = client.get_object(Bucket=R2_BUCKET_NAME, Key=key)
        return response['Body'].read()
    except Exception as e:
        print(f'R2 download failed: {e}')
        return None


def delete_from_r2(key: str) -> bool:
    """Delete a file from R2 by key."""
    if not R2_CONFIGURED:
        return False
    try:
        client = _get_client()
        client.delete_object(Bucket=R2_BUCKET_NAME, Key=key)
        return True
    except Exception as e:
        print(f'R2 delete failed: {e}')
        return False


def download_folder_from_r2(keys: list[str]) -> dict[str, bytes]:
    """
    Download multiple files from R2.
    Returns dict of {key: bytes} for successful downloads.
    """
    if not R2_CONFIGURED:
        return {}
    client  = _get_client()
    results = {}
    for key in keys:
        try:
            response   = client.get_object(Bucket=R2_BUCKET_NAME, Key=key)
            results[key] = response['Body'].read()
        except Exception as e:
            print(f'R2 download failed for {key}: {e}')
    return results
