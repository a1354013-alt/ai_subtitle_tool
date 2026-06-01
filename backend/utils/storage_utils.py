import logging
import os
import shutil
from abc import ABC, abstractmethod
from typing import Optional

from .. import settings

logger = logging.getLogger(__name__)


class StorageBackend(ABC):
    @abstractmethod
    def upload_file(self, local_path: str, remote_path: str) -> bool:
        pass

    @abstractmethod
    def download_file(self, remote_path: str, local_path: str) -> bool:
        pass

    @abstractmethod
    def delete_file(self, remote_path: str) -> bool:
        pass

    @abstractmethod
    def get_url(self, remote_path: str) -> Optional[str]:
        pass


class LocalStorageBackend(StorageBackend):
    def upload_file(self, local_path: str, remote_path: str) -> bool:
        # For local storage, files are usually already in the right place.
        return True

    def download_file(self, remote_path: str, local_path: str) -> bool:
        if not os.path.exists(remote_path):
            return False
        parent = os.path.dirname(os.path.abspath(local_path))
        if parent:
            os.makedirs(parent, exist_ok=True)
        shutil.copy2(remote_path, local_path)
        return True

    def delete_file(self, remote_path: str) -> bool:
        if os.path.exists(remote_path):
            os.remove(remote_path)
            return True
        return False

    def get_url(self, remote_path: str) -> Optional[str]:
        return None


class S3StorageBackend(StorageBackend):
    """
    S3 Storage Backend (EXPERIMENTAL)

    Configuration environment variables:
    - STORAGE_BACKEND=s3: Required to enable S3 backend
    - S3_BUCKET: Required when S3 backend is enabled
    - S3_ENDPOINT: Custom endpoint URL (optional)
    - S3_ACCESS_KEY: AWS/S3 access key
    - S3_SECRET_KEY: AWS/S3 secret key
    - S3_REGION: AWS region (default: us-east-1)
    """

    def __init__(self):
        logger.warning("S3 Storage Backend is EXPERIMENTAL and may change in future releases")
        if not os.getenv("S3_BUCKET"):
            raise ValueError("STORAGE_BACKEND=s3 requires S3_BUCKET to be set")
        try:
            import boto3
            from botocore.config import Config
        except ImportError:
            raise RuntimeError("STORAGE_BACKEND=s3 requires boto3 to be installed") from None

        self.bucket = os.getenv("S3_BUCKET")
        self.s3 = boto3.client(
            "s3",
            endpoint_url=os.getenv("S3_ENDPOINT"),
            aws_access_key_id=os.getenv("S3_ACCESS_KEY"),
            aws_secret_access_key=os.getenv("S3_SECRET_KEY"),
            region_name=os.getenv("S3_REGION", "us-east-1"),
            config=Config(signature_version="s3v4"),
        )

    def upload_file(self, local_path: str, remote_path: str) -> bool:
        try:
            self.s3.upload_file(local_path, self.bucket, remote_path)
            return True
        except Exception as e:
            logger.error("S3 upload failed: %s", e)
            return False

    def download_file(self, remote_path: str, local_path: str) -> bool:
        try:
            parent = os.path.dirname(os.path.abspath(local_path))
            if parent:
                os.makedirs(parent, exist_ok=True)
            self.s3.download_file(self.bucket, remote_path, local_path)
            return True
        except Exception as e:
            logger.error("S3 download failed: %s", e)
            return False

    def delete_file(self, remote_path: str) -> bool:
        try:
            self.s3.delete_object(Bucket=self.bucket, Key=remote_path)
            return True
        except Exception as e:
            logger.error("S3 delete failed: %s", e)
            return False

    def get_url(self, remote_path: str) -> Optional[str]:
        try:
            return self.s3.generate_presigned_url(
                "get_object",
                Params={"Bucket": self.bucket, "Key": remote_path},
                ExpiresIn=3600,
            )
        except Exception as e:
            logger.error("S3 URL generation failed: %s", e)
            return None


def get_storage_backend() -> StorageBackend:
    backend = (settings.STORAGE_BACKEND or "local").strip().lower()
    if backend == "local":
        return LocalStorageBackend()
    if backend == "s3":
        return S3StorageBackend()
    raise ValueError("Invalid STORAGE_BACKEND value. Expected 'local' or 's3'.")
