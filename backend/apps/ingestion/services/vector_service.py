import os
import json
import logging
from typing import List, Dict, Any
from pathlib import Path
from django.conf import settings

logger = logging.getLogger(__name__)


class PineconeVectorService:
    """
    Enterprise Vector Service interfacing with Pinecone Vector Database.
    Guarantees strict tenant isolation by embedding 'tenant_id' in every vector payload.
    Supports persistent disk-backed storage for local testing when Pinecone credentials are mock.
    """

    def __init__(self):
        self.api_key = getattr(settings, 'PINECONE_API_KEY', '')
        self.index_name = getattr(settings, 'PINECONE_INDEX_NAME', 'enterprise-rag-index')
        self.dimension = getattr(settings, 'EMBEDDING_DIMENSION', 384)

        self.use_mock = not (self.api_key and not self.api_key.startswith('mock_'))
        self.index = None

        # Persistent storage file for mock vector operations across processes
        self.mock_store_path = settings.BASE_DIR / 'media' / 'mock_pinecone_vectors.json'

        if not self.use_mock:
            try:
                from pinecone import Pinecone
                pc = Pinecone(api_key=self.api_key)
                self.index = pc.Index(self.index_name)
            except Exception as e:
                logger.warning(f"Could not connect to live Pinecone index '{self.index_name}': {e}. Falling back to mock vector store.")
                self.use_mock = True

    def _load_mock_vectors(self) -> Dict[str, Dict[str, Any]]:
        """Loads vectors from local persistent disk storage."""
        if not self.mock_store_path.exists():
            return {}
        try:
            with open(self.mock_store_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            logger.warning(f"Could not read mock vector file: {e}")
            return {}

    def _save_mock_vectors(self, store: Dict[str, Dict[str, Any]]):
        """Saves vectors to local persistent disk storage."""
        self.mock_store_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            with open(self.mock_store_path, 'w', encoding='utf-8') as f:
                json.dump(store, f)
        except Exception as e:
            logger.error(f"Could not save mock vector file: {e}")

    def upsert_chunks(
        self,
        tenant_id: str,
        document_id: str,
        filename: str,
        chunks: List[str],
        embeddings: List[List[float]]
    ) -> int:
        """
        Upserts chunk vectors and tenant metadata to Pinecone in batches.
        Returns:
            int: Number of vectors successfully indexed.
        """
        if len(chunks) != len(embeddings):
            raise ValueError("Chunks length and embeddings length must match exactly.")

        total_chunks = len(chunks)
        batch_size = 100

        for i in range(0, total_chunks, batch_size):
            batch_chunks = chunks[i:i + batch_size]
            batch_embeddings = embeddings[i:i + batch_size]

            vectors_to_upsert = []
            for j, (chunk_text, embedding) in enumerate(zip(batch_chunks, batch_embeddings)):
                chunk_index = i + j
                vector_id = f"{document_id}#{chunk_index}"
                
                # Payload metadata enforcing multi-tenancy and citation lineage
                metadata = {
                    "tenant_id": str(tenant_id),
                    "doc_id": str(document_id),
                    "filename": filename,
                    "chunk_index": chunk_index,
                    "text": chunk_text
                }

                vectors_to_upsert.append({
                    "id": vector_id,
                    "values": embedding,
                    "metadata": metadata
                })

            if not self.use_mock and self.index:
                try:
                    self.index.upsert(vectors=vectors_to_upsert)
                except Exception as e:
                    raise RuntimeError(f"Pinecone vector upsert failed: {str(e)}") from e
            else:
                store = self._load_mock_vectors()
                for item in vectors_to_upsert:
                    store[item["id"]] = item
                self._save_mock_vectors(store)

        logger.info(f"Successfully upserted {total_chunks} vectors for document {document_id} (Tenant: {tenant_id})")
        return total_chunks

    def query_vectors(
        self,
        tenant_id: str,
        query_vector: List[float],
        top_k: int = 4,
        document_id: str = None
    ) -> List[Dict[str, Any]]:
        """
        Executes a vector similarity query strictly constrained by the tenant_id metadata filter
        and optional document_id filter.
        """
        # Strict Multi-Tenant Filter - REQUIRED for zero data leakage
        metadata_filter = {
            "tenant_id": {"$eq": str(tenant_id)}
        }
        if document_id:
            metadata_filter["doc_id"] = {"$eq": str(document_id)}

        if not self.use_mock and self.index:
            try:
                response = self.index.query(
                    vector=query_vector,
                    top_k=top_k,
                    filter=metadata_filter,
                    include_metadata=True
                )
                
                matches = []
                for match in response.get('matches', []):
                    retrieved_tenant = match.get('metadata', {}).get('tenant_id')
                    if retrieved_tenant != str(tenant_id):
                        logger.critical(f"DATA LEAKAGE ATTEMPT DETECTED: Expected {tenant_id}, got {retrieved_tenant}")
                        continue
                    
                    matches.append({
                        "id": match['id'],
                        "score": match['score'],
                        "metadata": match.get('metadata', {})
                    })
                return matches
            except Exception as e:
                raise RuntimeError(f"Pinecone vector query failed: {str(e)}") from e
        else:
            # Persistent mock cosine similarity search for testing
            import numpy as np
            matches = []
            q_vec = np.array(query_vector)
            q_norm = np.linalg.norm(q_vec)

            store = self._load_mock_vectors()
            for vec_id, data in store.items():
                meta = data["metadata"]
                if meta.get("tenant_id") == str(tenant_id):
                    # Filter by specific document if requested
                    if document_id and meta.get("doc_id") != str(document_id):
                        continue

                    d_vec = np.array(data["values"])
                    d_norm = np.linalg.norm(d_vec)
                    score = float(np.dot(q_vec, d_vec) / (q_norm * d_norm)) if (q_norm > 0 and d_norm > 0) else 0.0
                    matches.append({
                        "id": vec_id,
                        "score": score,
                        "metadata": meta
                    })

            # Sort descending by similarity score
            matches.sort(key=lambda x: x["score"], reverse=True)
            return matches[:top_k]

    def get_header_chunks(self, tenant_id: str, document_id: str = None) -> List[Dict[str, Any]]:
        """
        Retrieves chunk #0 (document title / author / candidate header) for the tenant's documents.
        Essential for entity, identity, author, and contact queries.
        """
        if not self.use_mock and self.index:
            try:
                metadata_filter = {
                    "tenant_id": {"$eq": str(tenant_id)},
                    "chunk_index": {"$eq": 0}
                }
                if document_id:
                    metadata_filter["doc_id"] = {"$eq": str(document_id)}

                # Query with zero vector to fetch metadata matches
                zero_vector = [0.0] * 384
                response = self.index.query(
                    vector=zero_vector,
                    top_k=5,
                    filter=metadata_filter,
                    include_metadata=True
                )
                return [
                    {"id": m['id'], "score": 0.95, "metadata": m.get('metadata', {})}
                    for m in response.get('matches', [])
                ]
            except Exception as e:
                logger.warning(f"Could not retrieve header chunks from Pinecone: {e}")
                return []
        else:
            store = self._load_mock_vectors()
            headers = []
            for vec_id, data in store.items():
                meta = data.get("metadata", {})
                if meta.get("tenant_id") == str(tenant_id):
                    if document_id and meta.get("doc_id") != str(document_id):
                        continue
                    if meta.get("chunk_index") == 0:
                        headers.append({
                            "id": vec_id,
                            "score": 0.95,
                            "metadata": meta
                        })
            return headers
