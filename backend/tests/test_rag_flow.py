import pytest
from rest_framework import status
from django.core.files.uploadedfile import SimpleUploadedFile
from apps.ingestion.models import Document


@pytest.mark.django_db
class TestRagPipelineAndMultiTenancy:

    def test_document_upload_success(self, api_client, auth_credentials):
        """Tests document upload returns 202 Accepted and stores document record."""
        file_content = b"Enterprise Compliance Handbook 2026. Data retention is 7 years."
        uploaded_file = SimpleUploadedFile("Compliance_2026.txt", file_content, content_type="text/plain")

        response = api_client.post(
            '/api/v1/documents/upload/',
            {'file': uploaded_file},
            format='multipart',
            **auth_credentials['headers']
        )

        assert response.status_code == status.HTTP_202_ACCEPTED
        assert response.data['document']['filename'] == "Compliance_2026.txt"
        assert response.data['document']['upload_status'] in ['Pending', 'Processed']

        # Verify DB persistence
        doc_id = response.data['document']['id']
        assert Document.objects.filter(id=doc_id, tenant=auth_credentials['tenant']).exists()

    def test_invalid_file_extension_rejected(self, api_client, auth_credentials):
        """Rejects executable or unsupported file types with 400 Bad Request."""
        malicious_file = SimpleUploadedFile("malware.exe", b"MZ\x90\x00", content_type="application/octet-stream")

        response = api_client.post(
            '/api/v1/documents/upload/',
            {'file': malicious_file},
            format='multipart',
            **auth_credentials['headers']
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_document_listing_isolation(self, api_client, auth_credentials, secondary_tenant):
        """Verifies each tenant can only view their own uploaded documents."""
        # Tenant A uploads
        file_a = SimpleUploadedFile("DocA.txt", b"Content for Tenant A", content_type="text/plain")
        api_client.post('/api/v1/documents/upload/', {'file': file_a}, format='multipart', **auth_credentials['headers'])

        # Tenant B uploads
        file_b = SimpleUploadedFile("DocB.txt", b"Content for Tenant B", content_type="text/plain")
        api_client.post('/api/v1/documents/upload/', {'file': file_b}, format='multipart', **secondary_tenant['headers'])

        # Tenant A lists documents
        res_a = api_client.get('/api/v1/documents/', **auth_credentials['headers'])
        assert res_a.status_code == status.HTTP_200_OK
        filenames_a = [d['filename'] for d in res_a.data['documents']]
        assert "DocA.txt" in filenames_a
        assert "DocB.txt" not in filenames_a

        # Tenant B lists documents
        res_b = api_client.get('/api/v1/documents/', **secondary_tenant['headers'])
        assert res_b.status_code == status.HTTP_200_OK
        filenames_b = [d['filename'] for d in res_b.data['documents']]
        assert "DocB.txt" in filenames_b
        assert "DocA.txt" not in filenames_b

    def test_idor_protection_on_document_details(self, api_client, auth_credentials, secondary_tenant):
        """Guarantees Tenant B cannot inspect Tenant A's document details via IDOR."""
        file_a = SimpleUploadedFile("Confidential_A.txt", b"Confidential M&A details", content_type="text/plain")
        upload_res = api_client.post(
            '/api/v1/documents/upload/',
            {'file': file_a},
            format='multipart',
            **auth_credentials['headers']
        )
        doc_id = upload_res.data['document']['id']

        # Tenant B attempts to fetch Tenant A's document by ID
        trespass_res = api_client.get(f'/api/v1/documents/{doc_id}/', **secondary_tenant['headers'])
        assert trespass_res.status_code == status.HTTP_404_NOT_FOUND

    def test_rag_query_and_strict_cross_tenant_isolation(self, api_client, auth_credentials, secondary_tenant):
        """
        Critical Multi-Tenant Isolation Test:
        Tenant A ingests proprietary documentation.
        Both tenants submit the exact same query.
        Tenant A receives grounded answer + citations.
        Tenant B receives fallback answer + ZERO citations.
        """
        # 1. Tenant A uploads policy
        policy_text = b"Acme Vacation Policy 2026: All engineers receive 40 paid vacation days per calendar year."
        policy_file = SimpleUploadedFile("Vacation_Policy.txt", policy_text, content_type="text/plain")
        upload_res = api_client.post(
            '/api/v1/documents/upload/',
            {'file': policy_file},
            format='multipart',
            **auth_credentials['headers']
        )
        assert upload_res.status_code == status.HTTP_202_ACCEPTED

        query_payload = {"query": "How many vacation days do engineers receive?", "top_k": 3}

        # 2. Tenant A executes query
        res_a = api_client.post('/api/v1/query/', query_payload, format='json', **auth_credentials['headers'])
        assert res_a.status_code == status.HTTP_200_OK
        assert res_a.data['retrieved_chunk_count'] > 0
        assert len(res_a.data['citations']) > 0
        assert "Vacation_Policy.txt" in res_a.data['citations'][0]['filename']
        assert res_a.data['tenant_id'] == str(auth_credentials['tenant'].id)

        # 3. Tenant B executes the EXACT SAME query
        res_b = api_client.post('/api/v1/query/', query_payload, format='json', **secondary_tenant['headers'])
        assert res_b.status_code == status.HTTP_200_OK
        # Zero Data Leakage Assertions
        assert res_b.data['retrieved_chunk_count'] == 0
        assert len(res_b.data['citations']) == 0
        assert "sufficient information" in res_b.data['answer'].lower()

    def test_empty_query_rejected(self, api_client, auth_credentials):
        """Rejects empty or whitespace-only query string with 400 Bad Request."""
        response = api_client.post(
            '/api/v1/query/',
            {"query": "   "},
            format='json',
            **auth_credentials['headers']
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST
