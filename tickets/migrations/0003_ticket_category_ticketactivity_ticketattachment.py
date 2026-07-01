import django.db.models.deletion
import tickets.models
from django.conf import settings
from django.db import migrations, models


def seed_created_activity(apps, schema_editor):
    Ticket = apps.get_model('tickets', 'Ticket')
    TicketActivity = apps.get_model('tickets', 'TicketActivity')
    for ticket in Ticket.objects.all().iterator():
        activity = TicketActivity.objects.create(
            ticket_id=ticket.pk,
            actor_id=ticket.created_by_id,
            event_type='CREATED',
            message='Ticket created',
        )
        TicketActivity.objects.filter(pk=activity.pk).update(created_at=ticket.created_at)


class Migration(migrations.Migration):
    dependencies = [
        ('tickets', '0002_ticket_assigned_to_ticket_created_by_comment'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name='ticket',
            name='category',
            field=models.CharField(choices=[('Hardware', 'Hardware'), ('Software', 'Software'), ('Network', 'Network'), ('Access', 'Access / Account'), ('Email', 'Email'), ('Other', 'Other')], default='Other', max_length=20),
        ),
        migrations.CreateModel(
            name='TicketActivity',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('event_type', models.CharField(choices=[('CREATED', 'Created'), ('COMMENT', 'Comment'), ('ATTACHMENT', 'Attachment'), ('STATUS', 'Status change'), ('ASSIGNMENT', 'Assignment'), ('UPDATE', 'Update')], max_length=20)),
                ('message', models.CharField(max_length=255)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('actor', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to=settings.AUTH_USER_MODEL)),
                ('ticket', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='activities', to='tickets.ticket')),
            ],
            options={'verbose_name_plural': 'ticket activities', 'ordering': ['-created_at']},
        ),
        migrations.CreateModel(
            name='TicketAttachment',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('file', models.FileField(upload_to=tickets.models.ticket_attachment_path)),
                ('uploaded_at', models.DateTimeField(auto_now_add=True)),
                ('ticket', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='attachments', to='tickets.ticket')),
                ('uploaded_by', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='ticket_attachments', to=settings.AUTH_USER_MODEL)),
            ],
        ),
        migrations.RunPython(seed_created_activity, migrations.RunPython.noop),
    ]
