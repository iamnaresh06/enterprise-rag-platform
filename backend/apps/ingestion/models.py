import uuid
from django.db import models
from apps.authentication.models import Tenant


class Document(models.Model):
    """
    Enterprise Document Model tracking raw documents, S3 locations,
    and asynchronous Celery processing pipeline states.
    """
    class UploadStatus(models.TextChoices):
        PENDING = 'Pending', 'Pending'
        PROCESSING = 'Processing', 'Processing'
        PROCESSED = 'Processed', 'Processed'
        FAILED = 'Failed', 'Failed'

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
        help_text="Unique document identifier"
    )
    tenant = models.ForeignKey(
        Tenant,
        on_delete=models.CASCADE,
        related_name='documents',
        help_text="Tenant that owns this document"
    )
    filename = models.CharField(
        max_length=255,
        help_text="Original uploaded document filename"
    )
    s3_url = models.CharField(
        max_length=1024,
        help_text="AWS S3 URI (s3://bucket/tenants/{tenant_id}/documents/{doc_id}/{filename})"
    )
    file_size_bytes = models.BigIntegerField(
        default=0,
        help_text="Document file size in bytes"
    )
    upload_status = models.CharField(
        max_length=20,
        choices=UploadStatus.choices,
        default=UploadStatus.PENDING,
        db_index=True,
        help_text="Current state in the asynchronous ingestion pipeline"
    )
    chunk_count = models.IntegerField(
        default=0,
        help_text="Total number of vector chunks extracted and indexed into Pinecone"
    )
    error_message = models.TextField(
        blank=True,
        null=True,
        help_text="Error diagnostics if the background ingestion job fails"
    )
    uploaded_at = models.DateTimeField(
        auto_now_add=True,
        help_text="Timestamp when the upload was initiated"
    )
    processed_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Timestamp when vectorization and Pinecone upsert completed"
    )

    class Meta:
        db_table = 'documents'
        ordering = ['-uploaded_at']
        indexes = [
            models.Index(fields=['tenant', 'upload_status'], name='doc_tenant_status_idx'),
            models.Index(fields=['uploaded_at'], name='doc_uploaded_at_idx'),
        ]

    def __str__(self):
        return f"{self.filename} ({self.tenant.name}) - [{self.upload_status}]"
