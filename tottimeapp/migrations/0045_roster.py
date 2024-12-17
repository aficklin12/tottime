# Generated by Django 5.0.3 on 2024-11-10 03:58

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("tottimeapp", "0044_subuser_classroom"),
    ]

    operations = [
        migrations.CreateModel(
            name="Roster",
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
                    "classroom",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="rosters",
                        to="tottimeapp.classroom",
                    ),
                ),
                (
                    "main_user",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="rosters",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "student",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="rosters",
                        to="tottimeapp.student",
                    ),
                ),
                (
                    "subuser",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="rosters",
                        to="tottimeapp.subuser",
                    ),
                ),
            ],
            options={
                "unique_together": {("classroom", "student", "subuser", "main_user")},
            },
        ),
    ]