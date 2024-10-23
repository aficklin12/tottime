# Generated by Django 5.0.3 on 2024-10-17 18:50

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("tottimeapp", "0031_inventory_units"),
    ]

    operations = [
        migrations.AddField(
            model_name="weeklymenu",
            name="day_of_week",
            field=models.CharField(
                choices=[
                    ("Mon", "Monday"),
                    ("Tue", "Tuesday"),
                    ("Wed", "Wednesday"),
                    ("Thu", "Thursday"),
                    ("Fri", "Friday"),
                    ("Sat", "Saturday"),
                    ("Sun", "Sunday"),
                ],
                default="Mon",
                max_length=3,
            ),
            preserve_default=False,
        ),
    ]
