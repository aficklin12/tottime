# Generated by Django 5.0.3 on 2024-05-28 16:46

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("tottimeapp", "0023_location"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="WeeklyMenu",
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
                ("date", models.DateField()),
                ("facility", models.CharField(max_length=255)),
                ("sponsor", models.CharField(max_length=255)),
                ("am_fluid_milk", models.CharField(blank=True, max_length=255)),
                ("am_fruit_veg", models.CharField(blank=True, max_length=255)),
                ("am_bread", models.CharField(blank=True, max_length=255)),
                ("am_additional", models.CharField(blank=True, max_length=255)),
                ("ams_fluid_milk", models.CharField(blank=True, max_length=255)),
                ("ams_fruit_veg", models.CharField(blank=True, max_length=255)),
                ("ams_bread", models.CharField(blank=True, max_length=255)),
                ("ams_meat", models.CharField(blank=True, max_length=255)),
                ("lunch_main_dish", models.CharField(blank=True, max_length=255)),
                ("lunch_fluid_milk", models.CharField(blank=True, max_length=255)),
                ("lunch_vegetable", models.CharField(blank=True, max_length=255)),
                ("lunch_fruit", models.CharField(blank=True, max_length=255)),
                ("lunch_grain", models.CharField(blank=True, max_length=255)),
                ("lunch_meat", models.CharField(blank=True, max_length=255)),
                ("lunch_additional", models.CharField(blank=True, max_length=255)),
                ("pm_fluid_milk", models.CharField(blank=True, max_length=255)),
                ("pm_fruit_veg", models.CharField(blank=True, max_length=255)),
                ("pm_bread", models.CharField(blank=True, max_length=255)),
                ("pm_meat", models.CharField(blank=True, max_length=255)),
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
