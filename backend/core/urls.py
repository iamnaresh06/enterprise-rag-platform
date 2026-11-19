"""
Core URL Configuration for Multi-Tenant Enterprise Agentic RAG Platform.
"""
from django.contrib import admin
from django.urls import path, include
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status


class HealthCheckView(APIView):
    """
    Public Liveness and Readiness Probe for load balancers and orchestrators.
    """
    authentication_classes = []
    permission_classes = []

    def get(self, request, *args, **kwargs):
        return Response(
            {
                "status": "healthy",
                "service": "enterprise-agentic-rag-microservice",
                "version": "1.0.0-PROD",
            },
            status=status.HTTP_200_OK
        )


from django.http import HttpResponse


class APIRootView(APIView):
    """
    Public Service Discovery & Landing Endpoint.
    """
    authentication_classes = []
    permission_classes = []

    def get(self, request, *args, **kwargs):
        return Response(
            {
                "service": "Enterprise Multi-Tenant Agentic RAG Platform",
                "version": "1.0.0-PROD",
                "status": "online",
                "documentation": "See docs/POSTMAN_COLLECTION.json for API specifications.",
                "available_endpoints": {
                    "health_check": "/api/v1/health/",
                    "admin_portal": "/admin/",
                    "authentication": {
                        "register_tenant": "POST /api/v1/auth/tenants/",
                        "manage_keys": "GET, POST /api/v1/auth/keys/",
                    },
                    "documents": {
                        "upload": "POST /api/v1/documents/upload/",
                        "list": "GET /api/v1/documents/",
                        "detail": "GET, DELETE /api/v1/documents/<uuid:pk>/",
                    },
                    "rag_query": {
                        "ask": "POST /api/v1/query/",
                    },
                },
            },
            status=status.HTTP_200_OK
        )


urlpatterns = [
    # Root Service Discovery & Favicon
    path('', APIRootView.as_view(), name='api-root'),
    path('favicon.ico', lambda request: HttpResponse(status=204)),

    # Admin Portal
    path('admin/', admin.site.urls),
    
    # Public health probe
    path('api/v1/health/', HealthCheckView.as_view(), name='api-health'),

    # Enterprise Domain Microservice Endpoints
    path('api/v1/auth/', include('apps.authentication.urls')),
    path('api/v1/documents/', include('apps.ingestion.urls')),
    path('api/v1/query/', include('apps.rag_engine.urls')),
]

