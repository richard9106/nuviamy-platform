from django.contrib import admin

from .models import Customer, OperationalEvent, Product, Sale, SupportTicket, SupportMessage
from .support_requests import notify_support
from apps.audit.models import AuditLog
from apps.audit.utils import log_audit_event
from django.db import transaction

admin.site.register([Customer, Product, Sale, OperationalEvent])


class SupportMessageInline(admin.StackedInline):
    model = SupportMessage
    fields = ('body', 'author', 'is_operator', 'created_at')
    readonly_fields = ('author', 'is_operator', 'created_at')
    extra = 1
    can_delete = False

    def has_view_permission(self, request, obj=None):
        return request.user.is_active and request.user.is_superuser

    def has_add_permission(self, request, obj=None):
        return bool(request.user.is_active and request.user.is_superuser and obj
                    and obj.requester_id and obj.status == SupportTicket.Status.OPEN)

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(SupportTicket)
class SupportTicketAdmin(admin.ModelAdmin):
    list_display = ('id', 'topic', 'status', 'created_at')
    list_filter = ('status', 'topic')
    readonly_fields = ('id', 'requester', 'practice', 'contact_name', 'contact_email', 'topic', 'created_at')
    fields = readonly_fields + ('status',)
    inlines = (SupportMessageInline,)
    actions = None

    def has_module_permission(self, request):
        return request.user.is_active and request.user.is_superuser

    def has_view_permission(self, request, obj=None):
        return self.has_module_permission(request)

    def has_change_permission(self, request, obj=None):
        return self.has_module_permission(request)

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def save_formset(self, request, form, formset, change):
        for item in formset.save(commit=False):
            if item.pk:  # Existing messages are immutable through support admin.
                continue
            item.author = request.user
            item.is_operator = True
            item.save()
            log_audit_event(request, AuditLog.Action.CREATE, 'dashboard.SupportMessage',
                item.pk, practice=item.ticket.practice, metadata={'event': 'operator_support_reply'})
            transaction.on_commit(lambda ticket=item.ticket: notify_support(ticket, customer=True))
        formset.save_m2m()
