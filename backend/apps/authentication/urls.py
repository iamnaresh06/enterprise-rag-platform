from django.urls import path
from .views import TenantRegistrationView, APIKeyManagementView

app_name = 'authentication'

urlpatterns = [
    path('tenants/', TenantRegistrationView.as_view(), name='tenant-register'),
    path('keys/', APIKeyManagementView.as_view(), name='api-keys'),
]
