# Generated by Django 5.0.3 on 2024-12-09 21:36

import django.db.models.deletion
import django.utils.timezone
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("tottimeapp", "0058_mainuser_stripe_account_id"),
    ]

    operations = [
        migrations.AddField(
            model_name="mainuser",
            name="code",
            field=models.CharField(blank=True, max_length=4, null=True, unique=True),
        ),
        migrations.CreateModel(
            name="TeacherAttendanceRecord",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "sign_in_time",
                    models.DateTimeField(default=django.utils.timezone.now),
                ),
                ("sign_out_time", models.DateTimeField(blank=True, null=True)),
                (
                    "subuser",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        to="tottimeapp.subuser",
                    ),
                ),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
        ),
    ]