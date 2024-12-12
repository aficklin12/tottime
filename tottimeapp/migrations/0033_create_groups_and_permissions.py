# myapp/migrations/000X_create_groups_and_permissions.py

from django.db import migrations
from django.contrib.auth.models import Group, Permission
from django.contrib.contenttypes.models import ContentType

def create_groups(apps, schema_editor):
    roles = ['Owner', 'Director', 'Teacher', 'Cook', 'Parent']
    for role in roles:
        Group.objects.get_or_create(name=role)

    models_to_assign = {
        'Inventory': ['view_inventory', 'add_inventory'],
        'VegRecipe': ['view_vegrecipe', 'add_vegrecipe'],
        'AttendanceRecord': ['view_attendancerecord', 'add_attendancerecord'],
        'Student': ['view_student'],
        'Classroom': ['view_classroom'],
    }

    assign_permissions_to_groups(models_to_assign)

def assign_permissions_to_groups(models_to_assign):
    owner_permissions = []
    for model_name, perms in models_to_assign.items():
        model_content_type = ContentType.objects.get(model=model_name.lower())
        for perm in perms:
            permission = Permission.objects.get(codename=perm, content_type=model_content_type)
            owner_permissions.append(permission)

    owner_group = Group.objects.get(name='Owner')
    owner_group.permissions.set(owner_permissions)

    director_perms = [perm for perm in owner_permissions if 'view' in perm.codename]
    director_group = Group.objects.get(name='Director')
    director_group.permissions.set(director_perms)

class Migration(migrations.Migration):
    dependencies = dependencies = [
    ('tottimeapp', '0032_weeklymenu_day_of_week'),
]

    operations = [
        migrations.RunPython(create_groups),
    ]
