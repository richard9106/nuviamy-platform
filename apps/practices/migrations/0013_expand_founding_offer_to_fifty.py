from django.db import migrations, models


def add_places(apps, schema_editor):
    from django.utils import timezone
    Invitation = apps.get_model('practices', 'FoundingTherapistInvitation')
    for slot in range(21, 51):
        Invitation.objects.using(schema_editor.connection.alias).get_or_create(
            slot=slot, defaults={'token_hash': f'founding-unissued-{slot}', 'expires_at': timezone.now()})


class Migration(migrations.Migration):
    dependencies = [('practices', '0012_foundingtherapistinvitation')]
    operations = [
        migrations.RemoveConstraint(model_name='foundingtherapistinvitation', name='founding_offer_twenty_slots'),
        migrations.AddConstraint(model_name='foundingtherapistinvitation', constraint=models.CheckConstraint(
            condition=models.Q(slot__gte=1, slot__lte=50), name='founding_offer_fifty_slots')),
        # Preserve previously issued/redeemed invitations. Reversal must not discard them.
        migrations.RunPython(add_places),
    ]
