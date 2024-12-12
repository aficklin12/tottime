# Generated by Django 5.0.3 on 2024-12-11 20:43

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("tottimeapp", "0060_mainuser_profile_picture"),
    ]

    operations = [
        migrations.AlterField(
            model_name="mainuser",
            name="profile_picture",
            field=models.ImageField(
                blank=True,
                default="profile_pictures/Default_pfp.jpg",
                null=True,
                upload_to="profile_pictures/",
            ),
        ),
    ]
