# Generated by Django 3.2.21 on 2025-05-21 16:03

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('tottimeapp', '0093_remove_inventory_barcode_image'),
    ]

    operations = [
        migrations.CreateModel(
            name='UserMessagingPermission',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('can_message', models.BooleanField(default=False)),
                ('main_user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='user_messaging_permissions', to=settings.AUTH_USER_MODEL)),
                ('receiver', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='can_receive_from', to=settings.AUTH_USER_MODEL)),
                ('sender', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='can_send_to', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'unique_together': {('main_user', 'sender', 'receiver')},
            },
        ),
    ]
