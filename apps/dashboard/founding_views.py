from django.shortcuts import redirect

from .forms import FoundingTherapistApplicationForm
from .views import SupportContactView


class FoundingTherapistApplicationView(SupportContactView):
    """Store enquiries using the existing encrypted, audited support workflow."""
    template_name = 'marketing/founding_therapists.html'
    form_class = FoundingTherapistApplicationForm
    success_url = '/founding-therapists/?sent=1'
    # Share the contact limiter so changing forms does not bypass the limit.
    rate_limit_scope = 'support-contact'

    def get_initial(self):
        initial = super().get_initial()
        if self.request.user.is_authenticated and not initial.get('name'):
            initial['name'] = self.request.user.get_username()
        return initial

    def get_context_data(self, **kwargs):
        from apps.practices.models import FoundingTherapistInvitation
        context = super().get_context_data(**kwargs)
        context['offer_full'] = not FoundingTherapistInvitation.objects.filter(
            email='', redeemed_at__isnull=True).exists()
        return context

    def form_valid(self, form):
        response = super().form_valid(form)
        return redirect(self.success_url) if response.status_code == 302 else response
