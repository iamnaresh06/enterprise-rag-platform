import os
from rest_framework import serializers
from .models import Document

ALLOWED_EXTENSIONS = {'.pdf', '.txt', '.md', '.markdown', '.docx'}
MAX_FILE_SIZE_BYTES = 25 * 1024 * 1024  # 25 MB enterprise limit


class DocumentUploadSerializer(serializers.Serializer):
    """
    Validates file uploads for enterprise document ingestion.
    """
    file = serializers.FileField(required=True)

    def validate_file(self, file_obj):
        # 1. File size enforcement
        if file_obj.size > MAX_FILE_SIZE_BYTES:
            raise serializers.ValidationError(
                f"File size exceeds maximum enterprise threshold of {MAX_FILE_SIZE_BYTES / (1024 * 1024)} MB."
            )

        # 2. File extension & format verification
        _, ext = os.path.splitext(file_obj.name.lower())
        if ext not in ALLOWED_EXTENSIONS:
            raise serializers.ValidationError(
                f"Unsupported document format '{ext}'. Allowed enterprise extensions are: {', '.join(sorted(ALLOWED_EXTENSIONS))}."
            )

        return file_obj


class DocumentDetailSerializer(serializers.ModelSerializer):
    """
    Detailed serializer representing document metadata and pipeline status.
    """
    class Meta:
        model = Document
        fields = [
            'id',
            'filename',
            's3_url',
            'file_size_bytes',
            'upload_status',
            'chunk_count',
            'error_message',
            'uploaded_at',
            'processed_at'
        ]
        read_only_fields = fields
