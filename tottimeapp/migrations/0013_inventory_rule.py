# Generated by Django 5.0.3 on 2024-03-28 14:56

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("tottimeapp", "0012_pmrecipe"),
    ]

    operations = [
        migrations.AddField(
            model_name="inventory",
            name="rule",
            field=models.TextField(default=""),
            preserve_default=False,
        ),
    ]
