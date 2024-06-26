# Generated by Django 5.0.3 on 2024-03-22 02:36

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("tottimeapp", "0001_initial"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="Recipes",
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
                ("name", models.CharField(max_length=100)),
                ("instructions", models.TextField()),
                ("qty1", models.PositiveIntegerField(null=True)),
                ("qty2", models.PositiveIntegerField(null=True)),
                ("qty3", models.PositiveIntegerField(null=True)),
                ("qty4", models.PositiveIntegerField(null=True)),
                ("qty5", models.PositiveIntegerField(null=True)),
                (
                    "ingredient1",
                    models.ForeignKey(
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="ingredient1",
                        to="tottimeapp.inventory",
                    ),
                ),
                (
                    "ingredient2",
                    models.ForeignKey(
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="ingredient2",
                        to="tottimeapp.inventory",
                    ),
                ),
                (
                    "ingredient3",
                    models.ForeignKey(
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="ingredient3",
                        to="tottimeapp.inventory",
                    ),
                ),
                (
                    "ingredient4",
                    models.ForeignKey(
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="ingredient4",
                        to="tottimeapp.inventory",
                    ),
                ),
                (
                    "ingredient5",
                    models.ForeignKey(
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="ingredient5",
                        to="tottimeapp.inventory",
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
        migrations.DeleteModel(
            name="Recipe",
        ),
    ]
