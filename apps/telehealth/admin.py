from django.contrib import admin

from .models import TelehealthRoom


@admin.register(TelehealthRoom)
class TelehealthRoomAdmin(admin.ModelAdmin):
    list_display = ("appointment", "practice", "provider", "status", "created_at")
    list_filter = ("practice", "provider", "status")
    search_fields = ("appointment__client__first_name", "appointment__client__last_name", "external_room_id")
    readonly_fields = tuple(field.name for field in TelehealthRoom._meta.fields)

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
