import os
import boto3
from botocore.exceptions import ClientError, NoCredentialsError
from pathlib import Path
from django.conf import settings


class S3StorageService:
    """
    Enterprise S3 Object Storage Service enforcing tenant path isolation:
    s3://{bucket}/tenants/{tenant_id}/documents/{document_id}/{filename}
    """

    def __init__(self):
        self.bucket_name = getattr(settings, 'AWS_STORAGE_BUCKET_NAME', 'enterprise-rag-tenants-documents')
        self.region_name = getattr(settings, 'AWS_S3_REGION_NAME', 'us-east-1')
        self.access_key = getattr(settings, 'AWS_ACCESS_KEY_ID', '')
        self.secret_key = getattr(settings, 'AWS_SECRET_ACCESS_KEY', '')

        # Check if actual AWS credentials are provided
        self.use_mock_storage = not (self.access_key and self.secret_key and not self.access_key.startswith('mock_'))
        
        if not self.use_mock_storage:
            self.s3_client = boto3.client(
                's3',
                aws_access_key_id=self.access_key,
                aws_secret_access_key=self.secret_key,
                region_name=self.region_name
            )
        else:
            self.s3_client = None
            self.local_storage_root = settings.BASE_DIR / 'media' / 's3_storage'
            self.local_storage_root.mkdir(parents=True, exist_ok=True)

    def generate_s3_key(self, tenant_id: str, document_id: str, filename: str) -> str:
        """
        Constructs the canonical tenant-partitioned object key.
        """
        clean_filename = os.path.basename(filename)
        return f"tenants/{tenant_id}/documents/{document_id}/{clean_filename}"

    def upload_file(self, file_obj, tenant_id: str, document_id: str, filename: str) -> str:
        """
        Streams and uploads a document to S3 within the tenant's isolated directory prefix.
        Returns:
            str: Canonical S3 URI (s3://bucket/key)
        """
        s3_key = self.generate_s3_key(tenant_id, document_id, filename)

        if not self.use_mock_storage:
            try:
                # Seek to beginning if file was previously read
                if hasattr(file_obj, 'seek'):
                    file_obj.seek(0)

                self.s3_client.upload_fileobj(
                    file_obj,
                    self.bucket_name,
                    s3_key,
                    ExtraArgs={'ServerSideEncryption': 'AES256'}  # Enforce AES-256 at-rest encryption
                )
                return f"s3://{self.bucket_name}/{s3_key}"
            except (ClientError, NoCredentialsError) as e:
                raise RuntimeError(f"AWS S3 Upload failed for key {s3_key}: {str(e)}") from e
        else:
            # Local enterprise mock storage for development/testing without live AWS credentials
            destination_path = self.local_storage_root / s3_key
            destination_path.parent.mkdir(parents=True, exist_ok=True)

            if hasattr(file_obj, 'seek'):
                file_obj.seek(0)
            
            with open(destination_path, 'wb') as dest:
                if hasattr(file_obj, 'read'):
                    content = file_obj.read()
                    if isinstance(content, str):
                        content = content.encode('utf-8')
                    dest.write(content)
                else:
                    dest.write(file_obj)

            return f"s3://{self.bucket_name}/{s3_key}"

    def download_file_bytes(self, s3_url: str) -> bytes:
        """
        Retrieves file bytes from S3 or local mock storage given an S3 URI.
        """
        # Parse bucket and key from s3://bucket/key
        if not s3_url.startswith('s3://'):
            raise ValueError(f"Invalid S3 URI format: {s3_url}")

        parts = s3_url.replace('s3://', '').split('/', 1)
        if len(parts) != 2:
            raise ValueError(f"Malformed S3 URI: {s3_url}")

        bucket, key = parts

        if not self.use_mock_storage:
            try:
                response = self.s3_client.get_object(Bucket=bucket, Key=key)
                return response['Body'].read()
            except ClientError as e:
                raise RuntimeError(f"Failed to download object from S3 ({s3_url}): {str(e)}") from e
        else:
            local_path = self.local_storage_root / key
            if not local_path.exists():
                raise FileNotFoundError(f"Mock S3 file not found on disk: {local_path}")
            with open(local_path, 'rb') as f:
                return f.read()
