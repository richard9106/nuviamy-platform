import json

from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404
from django.utils.decorators import method_decorator
from django.views.decorators.cache import never_cache
from django.views.generic import TemplateView, View
from apps.appointments.models import Appointment
from apps.audit.models import AuditLog
from apps.audit.utils import log_audit_event
from apps.rate_limit import PostRateLimitMixin
from .access import agreements_ready, enabled_for, role_for
from .service import Unavailable, action, request_nonce


class VideoHeaders:
    def dispatch(self, request, *args, **kwargs):
        response = super().dispatch(request, *args, **kwargs)
        response['Cache-Control'] = 'no-store, private'
        response['Permissions-Policy'] = 'camera=(self), microphone=(self), display-capture=()'
        response['Content-Security-Policy'] = (
            "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; "
            "media-src 'self' blob:; connect-src 'self' https://*.chime.aws wss://*.chime.aws "
            "https://*.amazonaws.com wss://*.amazonaws.com; worker-src 'self' blob:; "
            "frame-ancestors 'none'; form-action 'self'; base-uri 'self'; object-src 'none'")
        return response


@method_decorator(never_cache, name='dispatch')
class VideoRoomView(VideoHeaders, LoginRequiredMixin, TemplateView):
    template_name = 'telehealth/room.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        appointment = get_object_or_404(Appointment.objects.select_related('practice', 'therapist__user'), pk=self.kwargs['pk'])
        role = role_for(self.request.user, appointment)
        if (appointment.appointment_type != 'video' or appointment.meeting_url
                or not enabled_for(appointment.practice_id) or not agreements_ready(appointment.practice_id)):
            raise Http404
        context.update(appointment=appointment, video_role=role,
            video_back='portal:dashboard' if role == 'patient' else 'appointments:list')
        return context


@method_decorator(never_cache, name='dispatch')
class VideoActionView(VideoHeaders, PostRateLimitMixin, View):
    http_method_names = ['post']
    rate_limit_count = 120
    rate_limit_seconds = 60

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return JsonResponse({'error': 'sign_in_required'}, status=401)
        self.rate_limit_scope = f'telehealth:{request.user.pk}'
        return super().dispatch(request, *args, **kwargs)

    def post(self, request, pk):
        if len(request.body) > 1024:
            return JsonResponse({'error': 'invalid_request'}, status=400)
        try:
            data = json.loads(request.body)
            if not isinstance(data, dict):
                raise ValueError
            operation = data.get('action')
            result = action(request, pk, operation, request_nonce(data.get('nonce')))
        except (ValueError, TypeError, json.JSONDecodeError):
            return JsonResponse({'error': 'invalid_request'}, status=400)
        except (Http404, Appointment.DoesNotExist):
            return JsonResponse({'error': 'session_unavailable'}, status=404)
        except Unavailable:
            return JsonResponse({'error': 'video_temporarily_unavailable'}, status=503)
        except Exception:
            # AWS responses, meeting tokens and participant details never enter errors/logs.
            return JsonResponse({'error': 'video_temporarily_unavailable'}, status=503)
        if operation != 'heartbeat':
            log_audit_event(request, AuditLog.Action.UPDATE, 'telehealth.TelehealthRoom', pk,
                metadata={'event': 'video_'+operation+'_requested'})
        return JsonResponse(result, status=503 if 'error' in result else 200)
