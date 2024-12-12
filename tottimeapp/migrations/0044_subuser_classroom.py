# Generated by Django 5.0.3 on 2024-11-10 02:33

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("tottimeapp", "0043_rolepermission_yes_no_permission"),
    ]

    operations = [
        migrations.AddField(
            model_name="subuser",
            name="classroom",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="subusers",
                to="tottimeapp.classroom",
            ),
        ),
    ]
