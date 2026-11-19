from rest_framework import serializers
from .models import Tenant, APIKey


class TenantSerializer(serializers.ModelSerializer):
    class Meta:
        model = Tenant
        fields = ['id', 'name', 'is_active', 'created_at']
        read_only_fields = ['id', 'is_active', 'created_at']


class TenantRegistrationSerializer(serializers.Serializer):
    """
    Serializer for onboarding a new enterprise organization and generating its primary API key.
    """
    name = serializers.CharField(max_length=255, required=True)
    key_name = serializers.CharField(max_length=100, required=False, default="Primary Production Key")

    def validate_name(self, value):
        trimmed = value.strip()
        if Tenant.objects.filter(name__iexact=trimmed).exists():
            raise serializers.ValidationError("An enterprise tenant with this organization name already exists.")
        return trimmed

    def create(self, validated_data):
        tenant = Tenant.objects.create(name=validated_data['name'])
        api_key_obj, raw_key = APIKey.generate_key(
            tenant=tenant,
            name=validated_data.get('key_name', "Primary Production Key")
        )
        return {
            "tenant": tenant,
            "api_key": raw_key,
            "key_prefix": api_key_obj.prefix
        }


class APIKeyCreateSerializer(serializers.Serializer):
    """
    Serializer for generating additional or rotated API keys for an existing tenant.
    """
    name = serializers.CharField(max_length=100, default="Secondary API Key")

    def create(self, validated_data):
        tenant = self.context['tenant']
        api_key_obj, raw_key = APIKey.generate_key(
            tenant=tenant,
            name=validated_data.get('name', "Secondary API Key")
        )
        return {
            "id": api_key_obj.id,
            "name": api_key_obj.name,
            "prefix": api_key_obj.prefix,
            "api_key": raw_key,
            "created_at": api_key_obj.created_at
        }


class APIKeyListSerializer(serializers.ModelSerializer):
    class Meta:
        model = APIKey
        fields = ['id', 'name', 'prefix', 'is_active', 'created_at']
        read_only_fields = fields
