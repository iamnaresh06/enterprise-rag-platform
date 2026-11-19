import pytest
import uuid
from rest_framework import status


@pytest.mark.django_db
class TestAuthenticationPipeline:

    def test_public_health_probe(self, api_client):
        """Verifies public probe is accessible without authentication."""
        response = api_client.get('/api/v1/health/')
        assert response.status_code == status.HTTP_200_OK
        assert response.data['status'] == 'healthy'

    def test_tenant_registration_success(self, api_client):
        """Verifies organization onboarding and initial API key provisioning."""
        unique_name = f"GlobalEnterprise_{uuid.uuid4().hex[:6]}"
        payload = {"name": unique_name, "key_name": "Root Production Key"}
        response = api_client.post('/api/v1/auth/tenants/', payload, format='json')

        assert response.status_code == status.HTTP_201_CREATED
        assert 'api_key' in response.data
        assert response.data['api_key'].startswith('sk_live_')
        assert response.data['tenant']['name'] == unique_name

    def test_tenant_duplicate_name_fails(self, api_client, sample_tenant):
        """Rejects registration when tenant name already exists."""
        response = api_client.post('/api/v1/auth/tenants/', {"name": sample_tenant.name}, format='json')
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_unauthenticated_request_rejected(self, api_client):
        """Rejects request with 401 when X-API-Key is omitted."""
        response = api_client.get('/api/v1/documents/')
        assert response.status_code == status.HTTP_401_UNAUTHORIZED
        assert response.json()['error']['code'] == 'AUTHENTICATION_REQUIRED'

    def test_malformed_key_rejected(self, api_client):
        """Rejects request with 401 when key does not follow sk_live_ format."""
        response = api_client.get('/api/v1/documents/', HTTP_X_API_KEY='invalid_key_string')
        assert response.status_code == status.HTTP_401_UNAUTHORIZED
        assert response.json()['error']['code'] == 'INVALID_KEY_FORMAT'

    def test_unknown_key_rejected(self, api_client):
        """Rejects validly formatted but non-existent key with 401."""
        fake_key = f"sk_live_{uuid.uuid4().hex}{uuid.uuid4().hex}"
        response = api_client.get('/api/v1/documents/', HTTP_X_API_KEY=fake_key)
        assert response.status_code == status.HTTP_401_UNAUTHORIZED
        assert response.json()['error']['code'] == 'INVALID_API_KEY'

    def test_revoked_key_forbidden(self, api_client, auth_credentials):
        """Rejects revoked/inactive API key with 403 Forbidden."""
        auth_credentials['api_key_obj'].is_active = False
        auth_credentials['api_key_obj'].save()

        response = api_client.get('/api/v1/documents/', **auth_credentials['headers'])
        assert response.status_code == status.HTTP_403_FORBIDDEN
        assert response.json()['error']['code'] == 'API_KEY_REVOKED'

    def test_suspended_tenant_forbidden(self, api_client, auth_credentials):
        """Rejects requests from suspended organizations with 403 Forbidden."""
        auth_credentials['tenant'].is_active = False
        auth_credentials['tenant'].save()

        response = api_client.get('/api/v1/documents/', **auth_credentials['headers'])
        assert response.status_code == status.HTTP_403_FORBIDDEN
        assert response.json()['error']['code'] == 'TENANT_SUSPENDED'

    def test_create_and_list_secondary_keys(self, api_client, auth_credentials):
        """Verifies authenticated tenant can provision and list additional API keys."""
        # Create secondary key
        create_res = api_client.post(
            '/api/v1/auth/keys/',
            {"name": "Secondary Ingestion Key"},
            format='json',
            **auth_credentials['headers']
        )
        assert create_res.status_code == status.HTTP_201_CREATED
        assert 'api_key' in create_res.data['key_details']

        # List keys
        list_res = api_client.get('/api/v1/auth/keys/', **auth_credentials['headers'])
        assert list_res.status_code == status.HTTP_200_OK
        assert len(list_res.data) >= 2
        # Ensure secret hash is NEVER exposed in listing
        for key_info in list_res.data:
            assert 'key_hash' not in key_info
            assert 'prefix' in key_info
