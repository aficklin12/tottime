# Generated by Django 5.1.3 on 2025-02-04 19:35

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('tottimeapp', '0062_attendancerecord_classroom_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='classroom',
            name='ratios',
            field=models.IntegerField(default=1),
        ),
    ]
