from rest_framework.permissions import BasePermission
from rest_framework.exceptions import AuthenticationFailed, PermissionDenied


class HasValidTenant(BasePermission):
    """
    DRF Permission class ensuring that the request has a valid, active Tenant
    attached by the TenantAuthMiddleware.
    """
    message = "Enterprise tenant authentication is required to access this resource."

    def has_permission(self, request, view):
        tenant = getattr(request, 'tenant', None)
        if not tenant:
            raise AuthenticationFailed({
                "code": "AUTHENTICATION_REQUIRED",
                "message": self.message
            })

        if not tenant.is_active:
            raise PermissionDenied({
                "code": "TENANT_INACTIVE",
                "message": "Tenant organization is suspended."
            })

        return True
