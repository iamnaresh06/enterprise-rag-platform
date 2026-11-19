import uuid
import logging
from django.shortcuts import get_object_or_404
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from apps.authentication.permissions import HasValidTenant
from .models import Document
from .serializers import DocumentUploadSerializer, DocumentDetailSerializer
from .services.s3_service import S3StorageService
from .tasks import process_document_ingestion

logger = logging.getLogger(__name__)


class DocumentUploadView(APIView):
    """
    POST /api/v1/documents/upload/
    Accepts multipart/form-data with a file payload.
    Streams document to S3 and enqueues Celery background ingestion task.
    Returns 202 Accepted immediately for non-blocking I/O.
    """
    permission_classes = [HasValidTenant]

    def post(self, request, *args, **kwargs):
        serializer = DocumentUploadSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        file_obj = serializer.validated_data['file']
        tenant = request.tenant
        document_id = uuid.uuid4()

        # 1. Stream upload to AWS S3 under isolated tenant path
        s3_service = S3StorageService()
        try:
            s3_url = s3_service.upload_file(
                file_obj=file_obj,
                tenant_id=str(tenant.id),
                document_id=str(document_id),
                filename=file_obj.name
            )
        except Exception as e:
            logger.error(f"Failed to persist file to S3: {e}", exc_info=True)
            return Response(
                {
                    "error": {
                        "code": "STORAGE_FAILURE",
                        "message": f"Document persistence to object storage failed: {str(e)}"
                    }
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

        # 2. Create document entity in MySQL
        document = Document.objects.create(
            id=document_id,
            tenant=tenant,
            filename=file_obj.name,
            s3_url=s3_url,
            file_size_bytes=file_obj.size,
            upload_status=Document.UploadStatus.PENDING
        )

        # 3. Enqueue asynchronous background parsing and vectorization task
        try:
            process_document_ingestion.delay(str(document.id))
            celery_enqueued = True
        except Exception as e:
            logger.warning(
                f"Celery task dispatch failed (broker may be offline): {e}. "
                f"Document {document.id} saved in Pending status."
            )
            celery_enqueued = False

        return Response(
            {
                "message": "Document accepted for asynchronous ingestion & vectorization.",
                "document": DocumentDetailSerializer(document).data,
                "celery_enqueued": celery_enqueued
            },
            status=status.HTTP_202_ACCEPTED
        )


class DocumentListView(APIView):
    """
    GET /api/v1/documents/
    Lists all documents belonging exclusively to the authenticated tenant.
    """
    permission_classes = [HasValidTenant]

    def get(self, request, *args, **kwargs):
        documents = Document.objects.filter(tenant=request.tenant).order_by('-uploaded_at')
        serializer = DocumentDetailSerializer(documents, many=True)
        return Response(
            {
                "tenant_id": str(request.tenant.id),
                "total_documents": len(serializer.data),
                "documents": serializer.data
            },
            status=status.HTTP_200_OK
        )


class DocumentDetailView(APIView):
    """
    GET /api/v1/documents/{id}/
    Retrieves the status, chunk count, and diagnostics of a specific document.
    Enforces strict tenant scoping to prevent IDOR vulnerabilities.

    DELETE /api/v1/documents/{id}/
    Deletes the document record and cleans up tenant-scoped resources.
    """
    permission_classes = [HasValidTenant]

    def get(self, request, pk, *args, **kwargs):
        document = get_object_or_404(Document, id=pk, tenant=request.tenant)
        serializer = DocumentDetailSerializer(document)
        return Response(serializer.data, status=status.HTTP_200_OK)

    def delete(self, request, pk, *args, **kwargs):
        document = get_object_or_404(Document, id=pk, tenant=request.tenant)
        document.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

