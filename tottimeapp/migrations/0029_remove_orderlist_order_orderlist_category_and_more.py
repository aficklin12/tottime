# Generated by Django 5.0.3 on 2024-08-30 22:47

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("tottimeapp", "0028_fruitrecipe_vegrecipe_wgrecipe"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="orderlist",
            name="order",
        ),
       
    ]