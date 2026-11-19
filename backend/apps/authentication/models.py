import uuid
import hashlib
import secrets
from django.db import models


class Tenant(models.Model):
    """
    Enterprise Tenant Model representing an isolated organizational customer.
    All documents, vectors, and API keys are strictly partitioned by tenant.
    """
    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
        help_text="Globally unique tenant identifier used for partitioning"
    )
    name = models.CharField(
        max_length=255,
        unique=True,
        help_text="Legal organization or corporate tenant name"
    )
    is_active = models.BooleanField(
        default=True,
        help_text="Flag indicating whether this tenant is permitted to make API requests"
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        help_text="Timestamp when the tenant was provisioned"
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        help_text="Timestamp when the tenant record was last updated"
    )

    class Meta:
        db_table = 'tenants'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['name'], name='tenant_name_idx'),
        ]

    def __str__(self):
        return f"{self.name} ({self.id})"


class APIKey(models.Model):
    """
    Cryptographically secure API Key representation.
    Raw keys are NEVER persisted; only a one-way SHA-256 hash is stored.
    """
    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False
    )
    tenant = models.ForeignKey(
        Tenant,
        on_delete=models.CASCADE,
        related_name='api_keys',
        help_text="Associated enterprise tenant"
    )
    name = models.CharField(
        max_length=100,
        default="Default API Key",
        help_text="Descriptive label for key auditing and rotation"
    )
    key_hash = models.CharField(
        max_length=64,
        unique=True,
        db_index=True,
        help_text="SHA-256 digest of the raw plaintext API key"
    )
    prefix = models.CharField(
        max_length=16,
        help_text="Safe non-secret prefix for UI display (e.g., sk_live_8f3d...)"
    )
    is_active = models.BooleanField(
        default=True,
        help_text="Allows instant revocation without deleting records"
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        help_text="Key generation timestamp"
    )

    class Meta:
        db_table = 'api_keys'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['key_hash'], name='apikey_hash_idx'),
            models.Index(fields=['tenant', 'is_active'], name='apikey_tenant_active_idx'),
        ]

    def __str__(self):
        return f"{self.tenant.name} - {self.name} [{self.prefix}...]"

    @classmethod
    def hash_key(cls, raw_key: str) -> str:
        """
        Computes SHA-256 hexadecimal digest of raw plaintext key.
        """
        return hashlib.sha256(raw_key.strip().encode('utf-8')).hexdigest()

    @classmethod
    def generate_key(cls, tenant: Tenant, name: str = "Production API Key") -> tuple['APIKey', str]:
        """
        Generates a cryptographically strong API key.
        Returns:
            tuple: (APIKey instance, raw_key_string)
            Note: raw_key_string is only available at generation time!
        """
        # Format: sk_live_<48-character-hex-entropy>
        entropy = secrets.token_hex(24)
        raw_key = f"sk_live_{entropy}"
        key_hash = cls.hash_key(raw_key)
        prefix = raw_key[:12]

        instance = cls.objects.create(
            tenant=tenant,
            name=name,
            key_hash=key_hash,
            prefix=prefix,
            is_active=True
        )
        return instance, raw_key
