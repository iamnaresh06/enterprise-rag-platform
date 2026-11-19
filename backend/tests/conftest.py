import pytest
import uuid
from rest_framework.test import APIClient
from apps.authentication.models import Tenant, APIKey


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def sample_tenant(db):
    unique_name = f"TestCorp_{uuid.uuid4().hex[:6]}"
    return Tenant.objects.create(name=unique_name, is_active=True)


@pytest.fixture
def auth_credentials(sample_tenant):
    api_key_obj, raw_key = APIKey.generate_key(
        tenant=sample_tenant,
        name="Automated Test Key"
    )
    return {
        "tenant": sample_tenant,
        "api_key_obj": api_key_obj,
        "raw_key": raw_key,
        "headers": {"HTTP_X_API_KEY": raw_key}
    }


@pytest.fixture
def secondary_tenant(db):
    unique_name = f"IsolatedCorp_{uuid.uuid4().hex[:6]}"
    tenant = Tenant.objects.create(name=unique_name, is_active=True)
    api_key_obj, raw_key = APIKey.generate_key(tenant=tenant, name="Secondary Key")
    return {
        "tenant": tenant,
        "api_key_obj": api_key_obj,
        "raw_key": raw_key,
        "headers": {"HTTP_X_API_KEY": raw_key}
    }
