from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from .models import APIKey
from .serializers import (
    TenantRegistrationSerializer,
    TenantSerializer,
    APIKeyCreateSerializer,
    APIKeyListSerializer
)
from .permissions import HasValidTenant


class TenantRegistrationView(APIView):
    """
    POST /api/v1/auth/tenants/
    Registers a new corporate tenant and generates their primary API key.
    Publicly accessible endpoint (or restricted via platform admin token).
    """
    authentication_classes = []
    permission_classes = []

    def post(self, request, *args, **kwargs):
        serializer = TenantRegistrationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        result = serializer.save()

        tenant_data = TenantSerializer(result['tenant']).data

        return Response(
            {
                "message": "Enterprise tenant registered successfully.",
                "tenant": tenant_data,
                "api_key": result['api_key'],
                "warning": "Store this API key safely in your secret manager. It will never be shown again!"
            },
            status=status.HTTP_201_CREATED
        )


class APIKeyManagementView(APIView):
    """
    GET /api/v1/auth/keys/  -> List all active keys for the authenticated tenant.
    POST /api/v1/auth/keys/ -> Provision an additional API key for the tenant.
    Requires authenticated X-API-Key.
    """
    permission_classes = [HasValidTenant]

    def get(self, request, *args, **kwargs):
        keys = APIKey.objects.filter(tenant=request.tenant).order_by('-created_at')
        serializer = APIKeyListSerializer(keys, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

    def post(self, request, *args, **kwargs):
        serializer = APIKeyCreateSerializer(data=request.data, context={'tenant': request.tenant})
        serializer.is_valid(raise_exception=True)
        result = serializer.save()

        return Response(
            {
                "message": "New enterprise API key created.",
                "key_details": result,
                "warning": "Store this API key securely. It cannot be recovered once this response is closed."
            },
            status=status.HTTP_201_CREATED
        )
