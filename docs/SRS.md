# Software Requirements Specification (SRS)
## Multi-Tenant Enterprise Agentic RAG Microservice

---

### Document Information
- **System Name:** Multi-Tenant Enterprise Agentic RAG Platform (`enterprise_rag_platform`)
- **Version:** 1.0.0-PROD
- **Target Audience:** Enterprise B2B Customers, Security Reviewers, Senior Engineering Staff, Systems Architects
- **Status:** Approved for Implementation

---

## 1. Executive Summary & Purpose

The **Multi-Tenant Enterprise Agentic RAG Platform** is an enterprise-grade Software-as-a-Service (SaaS) backend designed to empower corporate tenants to ingest proprietary unstructured knowledge (HR policies, compliance standards, technical manuals, internal wikis) and execute contextual, natural-language semantic searches using an AI Agent.

Unlike consumer RAG implementations, this system strictly enforces **Cryptographic Tenant Isolation**, ensuring that no enterprise tenant can ever query, retrieve, or infer the existence of another tenant's indexed documents. The platform is architected around asynchronous batch ingestion, idempotent vectorization, and deterministic retrieval filtering powered by a Service Layer architecture in Django REST Framework, Celery, Redis, MySQL, AWS S3, and Pinecone Vector Database.

---

## 2. Business & Operational Objectives

1. **Strict Multi-Tenant Isolation:** Complete logical separation of client data at storage (S3), relational metadata (MySQL), and semantic representation (Pinecone Vector DB) levels.
2. **Sub-2-Second P95 Query Latency:** Ensure retrieval and prompt assembly respond in under 2000ms under standard enterprise load.
3. **Decoupled Heavy Ingestion:** Asynchronous document parsing and vector generation to prevent thread exhaustion on API gateways.
4. **Auditability & Traceability:** Every LLM response must cite the precise internal document ID, chunk index, and page/source snippet.
5. **Zero-Trust API Key Authentication:** Secure, hashed API keys with sub-millisecond validation and tenant scoping.

---

## 3. User & System Actors

| Actor | Role Description | Authentication Method |
| :--- | :--- | :--- |
| **Tenant Admin** | Provisions API keys, reviews tenant document ingestion logs, configures tenant metadata. | Admin Portal / Scoped API Key |
| **Enterprise Client App** | B2B consumer system (e.g., Slack bot, internal portal, CRM) making programmatic API calls. | Header-based Bearer API Key (`X-API-Key`) |
| **Ingestion Worker** | Asynchronous Celery worker executing PDF parsing, chunking, embedding generation, and vector indexing. | Internal IAM / Service Credentials |
| **RAG Agent Service** | Internal reasoning and retrieval engine assembling vector filters and invoking the LLM. | Internal Service Layer |

---

## 4. Functional Requirements (FR)

### Module 1: Tenant & Authentication Management
* **FR-1.1 Tenant Provisioning:** The system must record enterprise tenants with unique UUID identifiers, organization names, status flags (`ACTIVE`, `SUSPENDED`), and resource quotas.
* **FR-1.2 API Key Generation & Hashing:** 
  * The system must generate high-entropy cryptographic API keys (`sk_live_[32-random-alphanumeric]`).
  * Raw API keys are displayed **only once** upon generation.
  * Only a one-way cryptographic hash (`SHA-256`) is stored in the database to prevent database-compromise key exposure.
* **FR-1.3 API Key Invalidation:** Tenant admins must have the ability to revoke or rotate API keys with immediate invalidation across all microservice instances.
* **FR-1.4 Tenant Identification Middleware:** A custom HTTP middleware must intercept all incoming `/api/v1/*` requests, extract `X-API-Key`, compute its SHA-256 hash in constant time, identify the associated `Tenant`, and attach the validated `Tenant` entity to `request.tenant`.

### Module 2: Document Ingestion Pipeline (Pipeline A)
* **FR-2.1 Document Submission:** Expose `POST /api/v1/documents/upload/` accepting multipart/form-data with file attachments (`.pdf`, `.docx`, `.txt`).
* **FR-2.2 Pre-flight Validation:** 
  * Validate MIME types using magic byte inspection (not solely file extensions).
  * Enforce maximum file size limits (default 25 MB per file).
  * Sanitize file names to prevent directory traversal or object-storage collision.
* **FR-2.3 Object Storage Persistence:** Persist raw document artifacts in AWS S3 utilizing strict tenant-scoped directory partitioning: `s3://{bucket}/tenants/{tenant_id}/documents/{document_uuid}/{filename}`.
* **FR-2.4 Ingestion Job Enqueueing:** Create a `Document` record in MySQL with `upload_status = 'Pending'` and dispatch an asynchronous Celery task `process_document_ingestion(document_id)`.
* **FR-2.5 Chunking & Embeddings:**
  * Celery task extracts text via LangChain document loaders.
  * Apply `RecursiveCharacterTextSplitter` configured for semantic cohesion (`chunk_size=500`, `chunk_overlap=50`).
  * Generate 384-dimensional dense vector embeddings using `sentence-transformers/all-MiniLM-L6-v2`.
* **FR-2.6 Vector DB Upsert with Multi-Tenant Metadata:**
  * Vectors must be upserted to Pinecone accompanied by immutable payload metadata:
    ```json
    {
      "tenant_id": "<uuid>",
      "document_id": "<uuid>",
      "filename": "HR_Policy_2026.pdf",
      "chunk_index": 12,
      "text": "..."
    }
    ```
  * Update MySQL document status to `Processed` (or `Failed` with error diagnostics if exception occurs).

### Module 3: Agentic RAG Retrieval & Inference (Pipeline B)
* **FR-3.1 Query Submission:** Expose `POST /api/v1/query/` accepting JSON payloads containing `{ "query": "..." }`.
* **FR-3.2 Query Vectorization:** Transform the user query using the identical `sentence-transformers/all-MiniLM-L6-v2` embedding model.
* **FR-3.3 Deterministic Metadata Filter Construction:**
  * Vector search query MUST inject a mandatory top-level filter:
    ```json
    { "tenant_id": { "$eq": "<request.tenant.id>" } }
    ```
  * System must reject any vector search execution that lacks a validated `tenant_id` filter.
* **FR-3.4 Retrieval & Context Assembly:** Retrieve Top-K (default $K=4$) cosine-similarity chunks. Filter out candidates below a relevance score threshold ($\ge 0.5$).
* **FR-3.5 Standardized Prompt Formulation (MCP-Compliant):** Format system instructions, retrieved context chunks, and user query into a structured context window:
  ```markdown
  [CONTEXT]
  Document: HR_Policy_2026.pdf (Chunk #12)
  Content: Employees are entitled to 25 days of annual leave...
  [/CONTEXT]
  [QUESTION]
  How many vacation days do I get?
  ```
* **FR-3.6 Grounded Answer Generation:** Query the LLM with instructions to answer strictly from the provided context. If the answer cannot be deduced from the retrieved documents, the model must explicitly return a standardized fallback: `"The provided documents do not contain sufficient information to answer this inquiry."`
* **FR-3.7 Citation Reporting:** Return a JSON response containing the synthesized `answer` and an array of `citations` listing document IDs, filenames, chunk indexes, and confidence scores.

---

## 5. Non-Functional Requirements (NFR)

### NFR-1: Security & Cryptographic Integrity
* **Data Isolation:** Logical segregation must be verified at every tier. A tenant must never receive search results containing vectors with a different `tenant_id`.
* **Timing-Attack Resistance:** API key validation must use constant-time comparison algorithms (`hmac.compare_digest`).
* **Encryption Standards:** TLS 1.3 in transit; AES-256 for AWS S3 and Pinecone at rest.
* **Least Privilege:** S3 IAM policies restrict workers to tenant path prefixes; Celery tasks receive only primary keys.

### NFR-2: Performance & Scalability
* **Stateless Application Tier:** The Django API container must be entirely stateless, allowing horizontal autoscaling behind an Application Load Balancer (ALB).
* **Asynchronous Offloading:** Web worker request latency for uploads must remain $< 250\text{ms}$ by delegating parsing and embedding generation to Celery workers.
* **Concurrent Worker Scaling:** Celery workers can be scaled independently of web workers to accommodate variable document ingestion workloads.

### NFR-3: Reliability & Fault Tolerance
* **Idempotent Ingestion:** Re-uploading a document or re-running a failed task replaces existing chunk vectors for that `document_id` without creating duplicates.
* **Dead-Letter Queue (DLQ):** Failed Celery tasks must retry up to 3 times with exponential backoff before being routed to a Redis-backed DLQ for manual inspection.

### NFR-4: Maintainability & Extensibility
* **Service-Oriented Architecture:** Business logic resides inside dedicated service classes (`IngestionService`, `RagService`, `PineconeVectorService`), not in Django views or models.
* **Configurable Model Providers:** Vector embedding models and LLM providers must be swappable via dependency injection without altering core pipeline controllers.

---

## 6. External Interface Specifications

### 6.1 Authentication Header
All protected API endpoints require:
```http
X-API-Key: sk_live_YOUR_TENANT_API_KEY_HERE
```

### 6.2 Endpoint Summary Table

| Method | Endpoint | Description | Auth Required |
| :--- | :--- | :--- | :--- |
| `POST` | `/api/v1/auth/tenants/` | Register new tenant and generate initial API key | Superadmin |
| `POST` | `/api/v1/auth/keys/` | Generate additional API key for existing tenant | Superadmin / Tenant Admin |
| `POST` | `/api/v1/documents/upload/` | Upload document for async ingestion & indexing | Valid `X-API-Key` |
| `GET` | `/api/v1/documents/` | List tenant documents and processing statuses | Valid `X-API-Key` |
| `GET` | `/api/v1/documents/{id}/` | Get processing details for a specific document | Valid `X-API-Key` |
| `POST` | `/api/v1/query/` | Execute Agentic RAG question answering | Valid `X-API-Key` |
| `GET` | `/api/v1/health/` | Microservice liveness & readiness probe | None |

---

## 7. Error Handling & Standardized Response Schema

All API error responses adhere to RFC 7807 (Problem Details for HTTP APIs):
```json
{
  "error": {
    "code": "AUTHENTICATION_FAILED",
    "message": "Invalid or inactive API key provided.",
    "details": {},
    "timestamp": "2026-09-25T12:00:00Z"
  }
}
```

Standard HTTP status mappings:
- `200 OK`: Successful synchronous retrieval/query.
- `202 Accepted`: File accepted and asynchronous ingestion enqueued.
- `400 Bad Request`: Validation failure (malformed JSON, invalid file type).
- `401 Unauthorized`: Missing or malformed `X-API-Key`.
- `403 Forbidden`: Inactive API key or tenant suspended.
- `404 Not Found`: Requested document or resource does not exist under the tenant.
- `429 Too Many Requests`: Tenant rate limit exceeded.
- `500 Internal Server Error`: Unhandled system failure.
