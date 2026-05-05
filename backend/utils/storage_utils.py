import os
import logging
from abc import ABC, abstractmethod
from typing import Optional

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
        # For local storage, we assume files are already in the right place
        return True

    def download_file(self, remote_path: str, local_path: str) -> bool:
        return True

    def delete_file(self, remote_path: str) -> bool:
        if os.path.exists(remote_path):
            os.remove(remote_path)
            return True
        return False

    def get_url(self, remote_path: str) -> Optional[str]:
        return None

class S3StorageBackend(StorageBackend):
    def __init__(self):
        try:
            import boto3
            from botocore.config import Config
            
            self.s3 = boto3.client(
                "s3",
                endpoint_url=os.getenv("S3_ENDPOINT"),
                aws_access_key_id=os.getenv("S3_ACCESS_KEY"),
                aws_secret_access_key=os.getenv("S3_SECRET_KEY"),
                region_name=os.getenv("S3_REGION", "us-east-1"),
                config=Config(signature_version="s3v4")
            )
            self.bucket = os.getenv("S3_BUCKET")
        except ImportError:
            logger.error("boto3 not installed. S3 storage will not work.")
            self.s3 = None

    def upload_file(self, local_path: str, remote_path: str) -> bool:
        if not self.s3: return False
        try:
            self.s3.upload_file(local_path, self.bucket, remote_path)
            return True
        except Exception as e:
            logger.error(f"S3 upload failed: {e}")
            return False

    def download_file(self, remote_path: str, local_path: str) -> bool:
        if not self.s3: return False
        try:
            self.s3.download_file(self.bucket, remote_path, local_path)
            return True
        except Exception as e:
            logger.error(f"S3 download failed: {e}")
            return False

    def delete_file(self, remote_path: str) -> bool:
        if not self.s3: return False
        try:
            self.s3.delete_object(Bucket=self.bucket, Key=remote_path)
            return True
        except Exception as e:
            logger.error(f"S3 delete failed: {e}")
            return False

    def get_url(self, remote_path: str) -> Optional[str]:
        if not self.s3: return None
        try:
            return self.s3.generate_presigned_url(
                "get_object",
                Params={"Bucket": self.bucket, "Key": remote_path},
                ExpiresIn=3600
            )
        except Exception as e:
            logger.error(f"S3 URL generation failed: {e}")
            return None

def get_storage_backend() -> StorageBackend:
    if os.getenv("S3_BUCKET"):
        return S3StorageBackend()
    return LocalStorageBackend()
