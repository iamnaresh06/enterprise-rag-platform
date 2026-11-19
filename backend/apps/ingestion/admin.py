from django.contrib import admin
from django.utils.html import format_html
from .models import Document


@admin.register(Document)
class DocumentAdmin(admin.ModelAdmin):
    list_display = ('filename', 'tenant', 'status_badge', 'chunk_count', 'size_display', 'uploaded_at')
    list_filter = ('upload_status', 'uploaded_at', 'tenant')
    search_fields = ('filename', 'tenant__name', 'id')
    readonly_fields = ('id', 's3_url', 'chunk_count', 'uploaded_at', 'processed_at')

    @admin.display(description="Status")
    def status_badge(self, obj):
        colors = {
            'Processed': '#10b981',
            'Processing': '#3b82f6',
            'Pending': '#f59e0b',
            'Failed': '#ef4444',
        }
        color = colors.get(obj.upload_status, '#64748b')
        return format_html(f'<span style="color: {color}; font-weight: 600;">● {obj.upload_status}</span>')

    @admin.display(description="Size")
    def size_display(self, obj):
        if obj.file_size_bytes:
            return f"{(obj.file_size_bytes / 1024):.1f} KB"
        return "N/A"
