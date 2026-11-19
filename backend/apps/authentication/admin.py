from django.contrib import admin, messages
from django.utils.html import format_html
from .models import Tenant, APIKey


class APIKeyInline(admin.TabularInline):
    model = APIKey
    extra = 0
    fields = ('prefix', 'name', 'is_active', 'created_at')
    readonly_fields = ('prefix', 'created_at')
    can_delete = True


@admin.register(Tenant)
class TenantAdmin(admin.ModelAdmin):
    list_display = ('name', 'status_badge', 'api_key_count', 'id', 'created_at')
    list_filter = ('is_active', 'created_at')
    search_fields = ('name', 'id')
    readonly_fields = ('id', 'created_at', 'updated_at')
    inlines = [APIKeyInline]
    actions = ['activate_tenants', 'terminate_tenants', 'provision_api_key_action']

    @admin.display(description="Status")
    def status_badge(self, obj):
        if obj.is_active:
            return format_html('<span style="color: #10b981; font-weight: 600;">● Active</span>')
        return format_html('<span style="color: #ef4444; font-weight: 600;">● Suspended</span>')

    @admin.display(description="Active Keys")
    def api_key_count(self, obj):
        return obj.api_keys.filter(is_active=True).count()

    @admin.action(description="Activate selected tenants")
    def activate_tenants(self, request, queryset):
        count = queryset.update(is_active=True)
        self.message_user(request, f"Activated {count} tenant(s).", messages.SUCCESS)

    @admin.action(description="Terminate / Suspend selected tenants")
    def terminate_tenants(self, request, queryset):
        count = queryset.update(is_active=False)
        self.message_user(request, f"Terminated/Suspended {count} tenant(s). Their API requests will now be rejected.", messages.WARNING)

    @admin.action(description="Generate & Issue a new API Key for selected tenant(s)")
    def provision_api_key_action(self, request, queryset):
        for tenant in queryset:
            api_key_obj, raw_key = APIKey.generate_key(tenant=tenant, name="Admin Generated Key")
            self.message_user(
                request,
                f"Generated new API Key for '{tenant.name}': {raw_key} (Copy this now! It cannot be shown again.)",
                messages.INFO
            )


@admin.register(APIKey)
class APIKeyAdmin(admin.ModelAdmin):
    list_display = ('prefix', 'name', 'tenant', 'status_badge', 'created_at')
    list_filter = ('is_active', 'created_at', 'tenant')
    search_fields = ('prefix', 'name', 'tenant__name')
    readonly_fields = ('prefix', 'key_hash', 'created_at')
    actions = ['revoke_keys', 'activate_keys']

    @admin.display(description="Status")
    def status_badge(self, obj):
        if obj.is_active:
            return format_html('<span style="color: #10b981; font-weight: 600;">● Active</span>')
        return format_html('<span style="color: #ef4444; font-weight: 600;">● Revoked</span>')

    @admin.action(description="Revoke selected API keys")
    def revoke_keys(self, request, queryset):
        count = queryset.update(is_active=False)
        self.message_user(request, f"Revoked {count} API key(s).", messages.WARNING)

    @admin.action(description="Activate selected API keys")
    def activate_keys(self, request, queryset):
        count = queryset.update(is_active=True)
        self.message_user(request, f"Activated {count} API key(s).", messages.SUCCESS)
