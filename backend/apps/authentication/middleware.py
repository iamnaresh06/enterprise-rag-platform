import hmac
import hashlib
from datetime import datetime, timezone
from django.http import JsonResponse
from django.utils.deprecation import MiddlewareMixin
from django.conf import settings
from .models import APIKey, Tenant


class TenantAuthMiddleware(MiddlewareMixin):
    """
    Enterprise Custom Middleware for API Key Authentication & Tenant Identification.

    Security Responsibilities:
    1. Intercepts incoming HTTP requests to protected API endpoints.
    2. Extracts and validates the 'X-API-Key' header.
    3. Computes the SHA-256 digest and performs constant-time verification using hmac.compare_digest.
    4. Enforces Tenant and APIKey active status checks.
    5. Binds 'request.tenant' and 'request.api_key' to the request context for downstream services.
    6. Returns standardized RFC 7807 JSON error envelopes for unauthenticated / unauthorized requests.
    """

    # Paths exempted from API key authentication (public probes, admin, registration, static assets)
    EXEMPT_PATHS = [
        '/api/v1/health/',
        '/api/v1/auth/tenants/',
        '/admin/',
        '/static/',
        '/media/',
    ]

    def process_request(self, request):
        """
        Intercepts and evaluates request headers before routing to views.
        """
        # 1. Initialize tenant context
        request.tenant = None
        request.api_key = None

        # 2. Check path exemption
        path = request.path_info
        for exempt_prefix in self.EXEMPT_PATHS:
            if path.startswith(exempt_prefix):
                return None

        # Only enforce API key authentication on /api/ routes
        if not path.startswith('/api/'):
            return None

        # 3. Extract API Key from request headers
        raw_key = request.headers.get('X-API-Key') or request.META.get('HTTP_X_API_KEY')

        if not raw_key:
            return self._build_error_response(
                status_code=401,
                error_code='AUTHENTICATION_REQUIRED',
                message="Missing 'X-API-Key' header. All enterprise API requests must supply an authorized API key."
            )

        raw_key = raw_key.strip()

        # 4. Syntactic validation: enterprise keys start with 'sk_live_'
        if not raw_key.startswith('sk_live_') or len(raw_key) < 32:
            return self._build_error_response(
                status_code=401,
                error_code='INVALID_KEY_FORMAT',
                message="The provided API key does not conform to enterprise key specifications (expected 'sk_live_...')."
            )

        # 5. Cryptographic hash calculation (SHA-256)
        computed_hash = hashlib.sha256(raw_key.encode('utf-8')).hexdigest()

        # 6. Database lookup using indexed key_hash with eager tenant fetch to prevent N+1 queries
        try:
            api_key = APIKey.objects.select_related('tenant').get(key_hash=computed_hash)
        except APIKey.DoesNotExist:
            return self._build_error_response(
                status_code=401,
                error_code='INVALID_API_KEY',
                message="The provided API key is unrecognized or invalid."
            )

        # 7. Constant-time digest verification to protect against timing side-channel attacks
        if not hmac.compare_digest(api_key.key_hash, computed_hash):
            return self._build_error_response(
                status_code=401,
                error_code='KEY_VERIFICATION_FAILED',
                message="Cryptographic verification of API key failed."
            )

        # 8. Check API Key active status
        if not api_key.is_active:
            return self._build_error_response(
                status_code=403,
                error_code='API_KEY_REVOKED',
                message="This API key has been revoked by your tenant administrator."
            )

        # 9. Check Tenant organizational status
        if not api_key.tenant.is_active:
            return self._build_error_response(
                status_code=403,
                error_code='TENANT_SUSPENDED',
                message="The enterprise organization associated with this key is currently suspended or inactive."
            )

        # 10. Bind authenticated entities to the request context
        request.tenant = api_key.tenant
        request.api_key = api_key

        return None

    @staticmethod
    def _build_error_response(status_code: int, error_code: str, message: str) -> JsonResponse:
        """
        Constructs an enterprise-standard RFC 7807 error envelope.
        """
        payload = {
            "error": {
                "code": error_code,
                "message": message,
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
        }
        return JsonResponse(payload, status=status_code)
