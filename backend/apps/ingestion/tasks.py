import logging
from celery import shared_task
from .services.processing_service import DocumentProcessingService

logger = logging.getLogger(__name__)


@shared_task(
    bind=True,
    max_retries=3,
    default_retry_delay=10,
    name="apps.ingestion.tasks.process_document_ingestion"
)
def process_document_ingestion(self, document_id: str):
    """
    Celery background task orchestrating asynchronous document parsing,
    LangChain chunking, HuggingFace vector embedding, and Pinecone upsert.

    Retries up to 3 times with exponential backoff on transient network failures.
    """
    logger.info(f"[Task ID: {self.request.id}] Starting ingestion for Document ID: {document_id}")

    try:
        service = DocumentProcessingService()
        indexed_chunks = service.process_document(document_id)
        logger.info(f"[Task ID: {self.request.id}] Successfully ingested {indexed_chunks} chunks for Document {document_id}")
        return {
            "status": "success",
            "document_id": document_id,
            "indexed_chunks": indexed_chunks
        }
    except Exception as exc:
        retry_count = self.request.retries
        backoff_countdown = 10 * (2 ** retry_count)  # 10s, 20s, 40s exponential backoff
        logger.warning(
            f"[Task ID: {self.request.id}] Ingestion failed for Document {document_id}: {exc}. "
            f"Attempt {retry_count + 1} of {self.max_retries}. Retrying in {backoff_countdown}s..."
        )

        if retry_count < self.max_retries:
            raise self.retry(exc=exc, countdown=backoff_countdown)
        else:
            logger.error(
                f"[Task ID: {self.request.id}] Max retries reached for Document {document_id}. "
                f"Marking as permanently Failed."
            )
            return {
                "status": "failed",
                "document_id": document_id,
                "error": str(exc)
            }
