from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('dashboard', '0003_supportticket_supportmessage')]
    operations = [migrations.AlterField(model_name='supportticket', name='topic', field=models.CharField(
        max_length=20, choices=[('setup', 'Practice setup'), ('billing', 'Billing or payments'),
        ('integrations', 'Google Calendar or Stripe'), ('technical', 'Technical issue'),
        ('other', 'Other'), ('early_access', 'Founding therapist application')]))]
