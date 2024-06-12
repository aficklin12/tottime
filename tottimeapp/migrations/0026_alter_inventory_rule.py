# Generated by Django 5.0.3 on 2024-05-31 17:30

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("tottimeapp", "0025_rule_alter_inventory_rule"),
    ]

    operations = [
        migrations.AlterField(
            model_name="inventory",
            name="rule",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                to="tottimeapp.rule",
            ),
        ),
    ]
