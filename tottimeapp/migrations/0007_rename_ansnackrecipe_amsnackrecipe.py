# Generated by Django 5.0.3 on 2024-03-26 18:17

from django.conf import settings
from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("tottimeapp", "0006_ansnackrecipe_breakfastrecipe_pmsnackrecipe"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.RenameModel(
            old_name="anSnackRecipe",
            new_name="amSnackRecipe",
        ),
    ]
