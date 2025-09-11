from django.db import models
from django.conf import settings
from django.contrib.auth.models import  AbstractUser, Group, Permission
from django.utils import timezone
from PIL import Image, ImageDraw
from io import BytesIO
from datetime import date
from django.core.exceptions import ValidationError
import random, uuid
from django.core.files.storage import default_storage
from django.conf import settings
from datetime import timedelta
from datetime import datetime
import os
from django.core.files.base import ContentFile
MAX_IMAGE_SIZE = 5 * 1024 * 1024  # 5 MB

class Location(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    facility = models.CharField(max_length=255)
    sponsor = models.CharField(max_length=255)

    def __str__(self):
        return f"Location: {self.user.username} - {self.facility} - {self.sponsor}"

class Rule(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    rule = models.TextField()
    WEEKLY_QTY_CHOICES = [(i, str(i)) for i in range(1, 8)]
    weekly_qty = models.IntegerField(choices=WEEKLY_QTY_CHOICES)
    YES_NO_CHOICES = [(True, 'Yes'), (False, 'No')]
    daily = models.BooleanField(choices=YES_NO_CHOICES)
    break_only = models.BooleanField(choices=YES_NO_CHOICES)
    am_only = models.BooleanField(choices=YES_NO_CHOICES)
    lunch_only = models.BooleanField(choices=YES_NO_CHOICES)
    pm_only = models.BooleanField(choices=YES_NO_CHOICES)

    def __str__(self):
        return self.rule

class Inventory(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    item = models.CharField(max_length=100, unique=True)
    category = models.CharField(max_length=100)
    units = models.CharField(max_length=50, null=True, blank=True)
    quantity = models.DecimalField(max_digits=10, decimal_places=2)  # Changed from IntegerField
    rule = models.ForeignKey(Rule, on_delete=models.CASCADE, null=True, blank=True)
    resupply = models.DecimalField(max_digits=10, decimal_places=2)  # Also changed resupply for consistency
    total_quantity = models.DecimalField(max_digits=10, decimal_places=2, default=0)  # Also changed total_quantity
    barcode = models.CharField(max_length=100, unique=True, null=True, blank=True)

    def __str__(self):
        return self.item

class VegRecipe(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    name = models.CharField(max_length=100, null=False)
    ingredient1 = models.ForeignKey('Inventory', related_name='veg_ingredient1', on_delete=models.SET_NULL, null=True)
    qty1 = models.PositiveIntegerField(null=True)
    rule = models.ForeignKey('Rule', on_delete=models.CASCADE, null=True, blank=True)

    def __str__(self):
        return self.name

class FruitRecipe(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    name = models.CharField(max_length=100, null=False)
    ingredient1 = models.ForeignKey('Inventory', related_name='fruit_ingredient1', on_delete=models.SET_NULL, null=True)
    qty1 = models.PositiveIntegerField(null=True)
    rule = models.ForeignKey('Rule', on_delete=models.CASCADE, null=True, blank=True)

    def __str__(self):
        return self.name

class WgRecipe(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    name = models.CharField(max_length=100, null=False)
    ingredient1 = models.ForeignKey('Inventory', related_name='wg_ingredient1', on_delete=models.SET_NULL, null=True)
    qty1 = models.PositiveIntegerField(null=True)
    rule = models.ForeignKey('Rule', on_delete=models.CASCADE, null=True, blank=True)

    def __str__(self):
        return self.name

class Recipe(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    name = models.CharField(max_length=100, null=False)
    instructions = models.TextField(null=True)
    ingredient1 = models.ForeignKey('Inventory', related_name='ingredient1', on_delete=models.SET_NULL, null=True)
    qty1 = models.PositiveIntegerField(null=True)
    ingredient2 = models.ForeignKey('Inventory', related_name='ingredient2', on_delete=models.SET_NULL, null=True)
    qty2 = models.PositiveIntegerField(null=True)
    ingredient3 = models.ForeignKey('Inventory', related_name='ingredient3', on_delete=models.SET_NULL, null=True)
    qty3 = models.PositiveIntegerField(null=True)
    ingredient4 = models.ForeignKey('Inventory', related_name='ingredient4', on_delete=models.SET_NULL, null=True)
    qty4 = models.PositiveIntegerField(null=True)
    ingredient5 = models.ForeignKey('Inventory', related_name='ingredient5', on_delete=models.SET_NULL, null=True)
    qty5 = models.PositiveIntegerField(null=True)
    last_used = models.DateTimeField(auto_now=True) 
    grain = models.CharField(max_length=100, blank=True, null=True)
    meat_alternate = models.CharField(max_length=100, blank=True, null=True)
    rule = models.ForeignKey(Rule, on_delete=models.CASCADE, null=True, blank=True)

    def __str__(self):
        return self.name
 
class BreakfastRecipe(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    name = models.CharField(max_length=100, null=False)
    instructions = models.TextField(null=True)
    ingredient1 = models.ForeignKey('Inventory', related_name='breakfast_ingredient1', on_delete=models.SET_NULL, null=True)
    qty1 = models.PositiveIntegerField(null=True)
    ingredient2 = models.ForeignKey('Inventory', related_name='breakfast_ingredient2', on_delete=models.SET_NULL, null=True)
    qty2 = models.PositiveIntegerField(null=True)
    ingredient3 = models.ForeignKey('Inventory', related_name='breakfast_ingredient3', on_delete=models.SET_NULL, null=True)
    qty3 = models.PositiveIntegerField(null=True)
    ingredient4 = models.ForeignKey('Inventory', related_name='breakfast_ingredient4', on_delete=models.SET_NULL, null=True)
    qty4 = models.PositiveIntegerField(null=True)
    ingredient5 = models.ForeignKey('Inventory', related_name='breakfast_ingredient5', on_delete=models.SET_NULL, null=True)
    qty5 = models.PositiveIntegerField(null=True)
    last_used = models.DateTimeField(auto_now=True) 
    addfood = models.CharField(max_length=100, blank=True, null=True)
    rule = models.ForeignKey(Rule, on_delete=models.CASCADE, null=True, blank=True)

    def __str__(self):
        return self.name

class AMRecipe(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    name = models.CharField(max_length=100, null=False)
    instructions = models.TextField(null=True)
    ingredient1 = models.ForeignKey('Inventory', related_name='am_ingredient1', on_delete=models.SET_NULL, null=True)
    qty1 = models.PositiveIntegerField(null=True)
    ingredient2 = models.ForeignKey('Inventory', related_name='am_ingredient2', on_delete=models.SET_NULL, null=True)
    qty2 = models.PositiveIntegerField(null=True)
    ingredient3 = models.ForeignKey('Inventory', related_name='am_ingredient3', on_delete=models.SET_NULL, null=True)
    qty3 = models.PositiveIntegerField(null=True)
    ingredient4 = models.ForeignKey('Inventory', related_name='am_ingredient4', on_delete=models.SET_NULL, null=True)
    qty4 = models.PositiveIntegerField(null=True)
    ingredient5 = models.ForeignKey('Inventory', related_name='am_ingredient5', on_delete=models.SET_NULL, null=True)
    qty5 = models.PositiveIntegerField(null=True)
    last_used = models.DateTimeField(auto_now=True) 
    fluid = models.CharField(max_length=100, blank=True, null=True)
    fruit_veg = models.CharField(max_length=100, blank=True, null=True)
    meat = models.CharField(max_length=100, blank=True, null=True)
    rule = models.ForeignKey(Rule, on_delete=models.CASCADE, null=True, blank=True)

    def __str__(self):
        return self.name
    
class PMRecipe(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    name = models.CharField(max_length=100, null=False)
    instructions = models.TextField(null=True)
    ingredient1 = models.ForeignKey('Inventory', related_name='pm_ingredient1', on_delete=models.SET_NULL, null=True)
    qty1 = models.PositiveIntegerField(null=True)
    ingredient2 = models.ForeignKey('Inventory', related_name='pm_ingredient2', on_delete=models.SET_NULL, null=True)
    qty2 = models.PositiveIntegerField(null=True)
    ingredient3 = models.ForeignKey('Inventory', related_name='pm_ingredient3', on_delete=models.SET_NULL, null=True)
    qty3 = models.PositiveIntegerField(null=True)
    ingredient4 = models.ForeignKey('Inventory', related_name='pm_ingredient4', on_delete=models.SET_NULL, null=True)
    qty4 = models.PositiveIntegerField(null=True)
    ingredient5 = models.ForeignKey('Inventory', related_name='pm_ingredient5', on_delete=models.SET_NULL, null=True)
    qty5 = models.PositiveIntegerField(null=True)
    last_used = models.DateTimeField(auto_now=True) 
    fluid = models.CharField(max_length=100, blank=True, null=True)
    fruit_veg = models.CharField(max_length=100, blank=True, null=True)
    meat = models.CharField(max_length=100, blank=True, null=True)
    rule = models.ForeignKey(Rule, on_delete=models.CASCADE, null=True, blank=True)
    
    def __str__(self):
        return self.name
    
class LastInventoryUpdate(models.Model):

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    last_updated = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Last inventory update for {self.user.username}"
    

class OrderList(models.Model):
    CATEGORY_CHOICES = [
        ('Meat', 'Meat'),
        ('Breakfast', 'Breakfast'),
        ('Snacks', 'Snacks'),
        ('Dairy', 'Dairy'),
        ('Fruits', 'Fruits'),
        ('Grains', 'Grains'),
        ('Vegetables', 'Vegetables'),
        ('Supplies', 'Supplies'),
        ('Other', 'Other'),
    ]
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    item = models.CharField(max_length=100, unique=True, default='default_item')
    quantity = models.IntegerField(default=1)  # Add default value here
    category = models.CharField(max_length=20, choices=CATEGORY_CHOICES, default='Other')
    ordered = models.BooleanField(default=False)

    def __str__(self):
        return self.item

   
class Classroom(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    name = models.CharField(max_length=100)
    ratios = models.IntegerField(default=1)
    color = models.CharField(max_length=7, default="#57bdb4")  # Default color

    def __str__(self):
        return self.name

    def get_assigned_teachers(self):
        """Returns all assigned teachers (SubUsers and MainUsers) for this classroom."""
        subusers = self.assignments.filter(subuser__isnull=False).select_related('subuser')
        mainusers = self.assignments.filter(subuser__isnull=True).select_related('classroom__user')
        return list(subusers) + list(mainusers)

class Student(models.Model):
    first_name = models.CharField(max_length=100)
    last_name = models.CharField(max_length=100)
    date_of_birth = models.DateField()
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    code = models.CharField(max_length=4, unique=True)
    classroom = models.ForeignKey('Classroom', on_delete=models.CASCADE, related_name='students')
    profile_picture = models.ImageField(
        upload_to='student_pictures/',
        blank=True,
        null=True,
        default='student_pictures/default.png'
    )
    STATUS_CHOICES = [
        ('active', 'Active'),
        ('inactive', 'Inactive'),
        ('transferred', 'Transferred'),
    ]
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='active')

    def __str__(self):
        return f"{self.first_name} {self.last_name}"

    def save(self, *args, **kwargs):
        # Only process if a new file is uploaded (InMemoryUploadedFile)
        from django.core.files.uploadedfile import InMemoryUploadedFile, TemporaryUploadedFile
        if isinstance(self.profile_picture, (InMemoryUploadedFile, TemporaryUploadedFile)):
            # Check file size
            if hasattr(self.profile_picture, 'size') and self.profile_picture.size > MAX_IMAGE_SIZE:
                raise ValidationError(f"Profile picture size exceeds {MAX_IMAGE_SIZE / (1024 * 1024)} MB.")

            try:
                img = Image.open(self.profile_picture)
                width, height = img.size
                min_dimension = min(width, height)
                # Center crop to a square
                left = (width - min_dimension) / 2
                top = (height - min_dimension) / 2
                right = (width + min_dimension) / 2
                bottom = (height + min_dimension) / 2
                img = img.crop((left, top, right, bottom))
                # Create circular mask
                mask = Image.new('L', img.size, 0)
                draw = ImageDraw.Draw(mask)
                draw.ellipse((0, 0, img.size[0], img.size[1]), fill=255)
                img.putalpha(mask)
                img = img.resize((60, 60), Image.Resampling.LANCZOS)
                # Save image with a unique filename
                img_io = BytesIO()
                img.save(img_io, format='PNG')
                img_io.seek(0)
                ext = 'png'
                filename = f"{self.first_name}_{self.last_name}_{uuid.uuid4().hex}.{ext}"
                self.profile_picture.save(filename, ContentFile(img_io.read()), save=False)
            except Exception as e:
                print(f"Error processing student image: {e}")

        # Set default if none
        default_pic = 'student_pictures/default.png'
        if not self.profile_picture or not self.profile_picture.name:
            self.profile_picture.name = default_pic

        super(Student, self).save(*args, **kwargs)

class IncidentReport(models.Model):
    student = models.ForeignKey(Student, on_delete=models.CASCADE)
    date_of_incident = models.DateField()
    incident_description = models.TextField()
    injury_description = models.TextField()
    treatment_administered = models.TextField()
    parent_signature = models.TextField(blank=True, null=True)  # For base64 image

    def __str__(self):
        return f"{self.student.first_name} {self.student.last_name} on {self.date_of_incident}"
    
class AttendanceRecord(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    student = models.ForeignKey(Student, on_delete=models.CASCADE)
    sign_in_time = models.DateTimeField(default=timezone.now)
    sign_out_time = models.DateTimeField(null=True, blank=True)
    classroom = models.ForeignKey(Classroom, on_delete=models.CASCADE, null=True, blank=True)
    classroom_override = models.CharField(max_length=100, null=True, blank=True) 
    classroom_override_1 = models.CharField(max_length=100, null=True, blank=True)
    timestamp_override_1 = models.DateTimeField(null=True, blank=True)
    classroom_override_2 = models.CharField(max_length=100, null=True, blank=True)
    timestamp_override_2 = models.DateTimeField(null=True, blank=True)
    classroom_override_3 = models.CharField(max_length=100, null=True, blank=True)
    timestamp_override_3 = models.DateTimeField(null=True, blank=True)
    classroom_override_4 = models.CharField(max_length=100, null=True, blank=True)
    timestamp_override_4 = models.DateTimeField(null=True, blank=True)
    ratios = models.IntegerField(null=True, blank=True)  # Field for storing ratios
    outside_time_out_1 = models.DateTimeField(null=True, blank=True)
    outside_time_out_2 = models.DateTimeField(null=True, blank=True)
    outside_time_in_1 = models.DateTimeField(null=True, blank=True)
    outside_time_in_2 = models.DateTimeField(null=True, blank=True)
    meal_1 = models.DateTimeField(null=True, blank=True)
    meal_2 = models.DateTimeField(null=True, blank=True)
    meal_3 = models.DateTimeField(null=True, blank=True)
    meal_4 = models.DateTimeField(null=True, blank=True)
    meal_desc_1 = models.CharField(max_length=255, null=True, blank=True)
    meal_desc_2 = models.CharField(max_length=255, null=True, blank=True)
    meal_desc_3 = models.CharField(max_length=255, null=True, blank=True)
    meal_desc_4 = models.CharField(max_length=255, null=True, blank=True)
    incident_report = models.ForeignKey(IncidentReport, on_delete=models.SET_NULL, null=True, blank=True)
    
    def save(self, *args, **kwargs):
        if not self.classroom:
            self.classroom = self.student.classroom  # Default to student's classroom
        if not self.classroom_override:
            self.classroom_override = self.classroom.name  # Copy classroom name by default
        if self.classroom:
            self.ratios = self.classroom.ratios 
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.student} - {self.sign_in_time}"

class TeacherAttendanceRecord(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)  # Referring to MainUser
    subuser = models.ForeignKey('SubUser', on_delete=models.SET_NULL, null=True, blank=True)  # Nullable for MainUser
    sign_in_time = models.DateTimeField(default=timezone.now)
    sign_out_time = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        if self.subuser:
            return f"{self.user} - {self.subuser} - {self.sign_in_time}"
        return f"{self.user} - {self.sign_in_time}"
    
    
class MilkCount(models.Model):
    inventory_item = models.ForeignKey(Inventory, on_delete=models.CASCADE)
    timestamp = models.DateTimeField(auto_now_add=True)
    current_qty = models.IntegerField(default=0)  # Current quantity
    received_qty = models.IntegerField(default=0)  # Received quantity for the month
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)

    def __str__(self):
        return f"{self.inventory_item.item} - {self.timestamp}"

    class Meta:
        unique_together = (('inventory_item', 'timestamp'),)

class WeeklyMenu(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    date = models.DateField()
     # Days of the week choices
    DAYS_OF_WEEK = [
        ('Mon', 'Monday'),
        ('Tue', 'Tuesday'),
        ('Wed', 'Wednesday'),
        ('Thu', 'Thursday'),
        ('Fri', 'Friday'),
        ('Sat', 'Saturday'),
        ('Sun', 'Sunday'),
    ]
    
    day_of_week = models.CharField(max_length=3, choices=DAYS_OF_WEEK)  # Make sure this is included

   
    facility = models.CharField(max_length=255)
    sponsor = models.CharField(max_length=255)
    am_fluid_milk = models.CharField(max_length=255, blank=True)
    am_fruit_veg = models.CharField(max_length=255, blank=True)
    am_bread = models.CharField(max_length=255, blank=True)
    am_additional = models.CharField(max_length=255, blank=True)
    ams_fluid_milk = models.CharField(max_length=255, blank=True)
    ams_fruit_veg = models.CharField(max_length=255, blank=True)
    ams_bread = models.CharField(max_length=255, blank=True)
    ams_meat = models.CharField(max_length=255, blank=True)
    lunch_main_dish = models.CharField(max_length=255, blank=True)
    lunch_fluid_milk = models.CharField(max_length=255, blank=True)
    lunch_vegetable = models.CharField(max_length=255, blank=True)
    lunch_fruit = models.CharField(max_length=255, blank=True)
    lunch_grain = models.CharField(max_length=255, blank=True)
    lunch_meat = models.CharField(max_length=255, blank=True)
    lunch_additional = models.CharField(max_length=255, blank=True)
    pm_fluid_milk = models.CharField(max_length=255, blank=True)
    pm_fruit_veg = models.CharField(max_length=255, blank=True)
    pm_bread = models.CharField(max_length=255, blank=True)
    pm_meat = models.CharField(max_length=255, blank=True)

    def __str__(self):
        return f"Menu for {self.user.username} on {self.date}"
    
class UserRole(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="roles")
    role = models.ForeignKey(Group, on_delete=models.CASCADE, related_name="user_roles")  # Django's Group model as the role

    def __str__(self):
        return f"{self.user.username} - {self.role.name}"

    class Meta:
        unique_together = ('user', 'role')

class RolePermission(models.Model):
    role = models.ForeignKey(Group, on_delete=models.CASCADE, related_name="role_permissions")  # Linking to Group
    permission = models.ForeignKey(Permission, on_delete=models.CASCADE, related_name="role_permissions")  # Linking to Permission
    yes_no_permission = models.BooleanField(default=False)  # Added yes/no field for permission control
    main_user = models.ForeignKey('MainUser', on_delete=models.CASCADE, related_name='role_permissions', null=True, blank=True)  # <-- Add this line

    class Meta:
        unique_together = ('role', 'permission')  # Ensure unique combination of role and permission

    def __str__(self):
        yes_no = "Yes" if self.yes_no_permission else "No"
        return f"{self.role.name} - {self.permission.codename} - Permission: {yes_no}"

class Invitation(models.Model):
    email = models.EmailField()
    role = models.ForeignKey(Group, on_delete=models.CASCADE)
    student_ids = models.CharField(max_length=255, blank=True, null=True)
    invited_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    token = models.CharField(max_length=100, unique=True)  # To create unique links
    created_at = models.DateTimeField(auto_now_add=True)

class Company(models.Model):
    name = models.CharField(max_length=255, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        return self.name
    
    class Meta:
        verbose_name_plural = "Companies"


class CompanyAccountOwner(models.Model):
    company = models.ForeignKey('Company', on_delete=models.CASCADE, related_name='account_owners')
    main_account_owner = models.ForeignKey('MainUser', on_delete=models.CASCADE, related_name='company_ownerships')
    location_name = models.CharField(max_length=255, blank=True, null=True)
    facility_address = models.CharField(max_length=500, blank=True, null=True)
    facility_city = models.CharField(max_length=100, blank=True, null=True)
    facility_state = models.CharField(max_length=50, blank=True, null=True)
    facility_zip = models.CharField(max_length=20, blank=True, null=True)
    facility_county = models.CharField(max_length=100, blank=True, null=True)
    is_primary = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        unique_together = ('company', 'main_account_owner')
        
    def __str__(self):
        primary_text = " (Primary)" if self.is_primary else ""
        location_text = f" - {self.location_name}" if self.location_name else ""
        return f"{self.company.name}{location_text} - {self.main_account_owner.username}{primary_text}"
    
    @property
    def full_facility_address(self):
        """Return formatted full address"""
        parts = [self.facility_city, self.facility_state, self.facility_zip]
        return ", ".join([part for part in parts if part])
    
MAX_IMAGE_SIZE = 5 * 1024 * 1024
class MainUser(AbstractUser):
    first_name = models.CharField(max_length=30, blank=False)
    last_name = models.CharField(max_length=30, blank=False)
    email = models.EmailField(unique=True, blank=False)
    company_name = models.CharField(max_length=255, blank=True, null=True)
    company = models.ForeignKey('Company', on_delete=models.SET_NULL, null=True, blank=True, related_name='centers')
    phone_number = models.CharField(max_length=15, blank=True, null=True)
    address = models.CharField(max_length=255, blank=True, null=True)
    groups = models.ManyToManyField(Group, related_name='mainuser_set', blank=True)
    user_permissions = models.ManyToManyField(Permission, related_name='mainuser_set', blank=True)
    stripe_account_id = models.CharField(max_length=255, null=True, blank=True)
    stripe_public_key = models.CharField(max_length=255, blank=True, null=True)
    stripe_secret_key = models.CharField(max_length=255, blank=True, null=True)
    square_access_token = models.CharField(max_length=255, blank=True, null=True)
    square_refresh_token = models.CharField(max_length=255, blank=True, null=True)
    square_merchant_id = models.CharField(max_length=255, blank=True, null=True)
    square_location_id = models.CharField(max_length=255, blank=True, null=True)
    code = models.CharField(max_length=4, unique=True, blank=True, null=True)
    profile_picture = models.ImageField(
        upload_to='profile_pictures/', 
        blank=True, 
        null=True, 
        default='profile_pictures/default.png'
    )
    can_switch = models.BooleanField(default=False)
    is_account_owner = models.BooleanField(default=False)
    main_account_owner = models.ForeignKey(
        'self',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='linked_users'
    )

    def __str__(self):
        if self.is_account_owner:
            return f"{self.first_name} {self.last_name} - Account Owner"
        elif self.main_account_owner:
            return f"{self.first_name} {self.last_name} - Linked to {self.main_account_owner.first_name} {self.main_account_owner.last_name}"
        return f"{self.first_name} {self.last_name} - Regular User"

    def save(self, *args, **kwargs):
        # Ensure that a user cannot be both an account owner and linked to another account owner
        if self.is_account_owner and self.main_account_owner:
            raise ValidationError("A user cannot be both an account owner and linked to another account owner.")

        # Only check size and process image if a new file is being uploaded (in memory)
        if self.profile_picture and getattr(self.profile_picture, '_file', None):
            # Check file size
            if hasattr(self.profile_picture._file, 'size') and self.profile_picture._file.size > MAX_IMAGE_SIZE:
                raise ValidationError(f"Profile picture size exceeds {MAX_IMAGE_SIZE / (1024 * 1024)} MB.")

            try:
                img = Image.open(self.profile_picture)
                width, height = img.size
                min_dimension = min(width, height)
                # Center crop to a square
                left = (width - min_dimension) / 2
                top = (height - min_dimension) / 2
                right = (width + min_dimension) / 2
                bottom = (height + min_dimension) / 2
                img = img.crop((left, top, right, bottom))
                # Create circular mask
                mask = Image.new('L', img.size, 0)
                draw = ImageDraw.Draw(mask)
                draw.ellipse((0, 0, img.size[0], img.size[1]), fill=255)
                img.putalpha(mask)
                img = img.resize((60, 60), Image.Resampling.LANCZOS)
                # Save image with a unique filename to avoid browser cache issues
                img_io = BytesIO()
                img.save(img_io, format='PNG')
                img_io.seek(0)
                ext = 'png'
                filename = f"{self.username}_{uuid.uuid4().hex}.{ext}"
                self.profile_picture.save(filename, img_io, save=False)
            except Exception as e:
                print(f"Error processing image: {e}")

        # Set default profile picture if none is uploaded
        default_pic = 'profile_pictures/default.png'
        if not self.profile_picture or not self.profile_picture.name:
            if default_storage.exists(default_pic):
                self.profile_picture.name = default_pic

        is_new = self.pk is None
        super(MainUser, self).save(*args, **kwargs)

        # Generate unique code for users not in 'Parent' or 'Free User' groups
        # (do this only after the first save, so self.groups is accessible)
        if is_new and not self.code and not self.groups.filter(id__in=[5, 6]).exists():
            self.code = self.generate_unique_code()
            super(MainUser, self).save(update_fields=['code'])

    def generate_unique_code(self):
        """Generates a unique 4-digit code."""
        code = str(random.randint(1000, 9999))
        while MainUser.objects.filter(code=code).exists():
            code = str(random.randint(1000, 9999))
        return code
    
class SubUser(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)  # Link to the custom User model
    main_user = models.ForeignKey('MainUser', on_delete=models.CASCADE, related_name='sub_users')
    group_id = models.ForeignKey(Group, on_delete=models.CASCADE, related_name="subusers", null=True, blank=True)
    balance = models.DecimalField(max_digits=10, decimal_places=2, default=0)  # Acts as wallet (can be positive or negative)
    students = models.ManyToManyField('Student', related_name='parents', blank=True)  # Changed to ManyToManyField
    can_switch = models.BooleanField(default=False)

    def __str__(self):
        return f"SubUser: {self.user.username} linked to MainUser: {self.main_user.username}"

class ClassroomAssignment(models.Model):
    classroom = models.ForeignKey(Classroom, on_delete=models.CASCADE, related_name='assignments')
    subuser = models.ForeignKey(SubUser, on_delete=models.CASCADE, null=True, blank=True, related_name='assignments')
    mainuser = models.ForeignKey('MainUser', on_delete=models.CASCADE, null=True, blank=True, related_name='assignments')
    ratio = models.IntegerField(default=1)  # Ratio specific to this teacher-classroom assignment
    assigned_at = models.DateTimeField(auto_now_add=True)  # Track when the assignment was made
    unassigned_at = models.DateTimeField(null=True, blank=True)  # Optional: Track when the assignment ended

    def __str__(self):
        if self.subuser:
            return f"{self.subuser.user.username} assigned to {self.classroom.name} with ratio {self.ratio}"
        elif self.mainuser:
            return f"{self.mainuser.username} assigned to {self.classroom.name} with ratio {self.ratio}"
        return f"Unassigned teacher in {self.classroom.name}"
    
    
class Roster(models.Model):
    classroom = models.ForeignKey('Classroom', on_delete=models.CASCADE, related_name='rosters')
    student = models.ForeignKey('Student', on_delete=models.CASCADE, related_name='rosters')
    subuser = models.ForeignKey('SubUser', on_delete=models.CASCADE, related_name='rosters')
    main_user = models.ForeignKey('MainUser', on_delete=models.CASCADE, related_name='rosters')

    class Meta:
        unique_together = ('classroom', 'student', 'subuser', 'main_user')  # Ensure each unique combination only appears once

    def __str__(self):
        return f"Roster for Student: {self.student} in Classroom: {self.classroom} under SubUser: {self.subuser} and MainUser: {self.main_user}"
    

class Conversation(models.Model):
    sender = models.ForeignKey(settings.AUTH_USER_MODEL, related_name='sent_conversations', on_delete=models.CASCADE)
    recipient = models.ForeignKey(settings.AUTH_USER_MODEL, related_name='received_conversations', on_delete=models.CASCADE)
    started_at = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        return f"Conversation between {self.sender} and {self.recipient}"
    
class Message(models.Model):
    sender = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='sent_messages')
    recipient = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='received_messages')
    conversation = models.ForeignKey(Conversation, on_delete=models.CASCADE, related_name='messages')
    content = models.TextField()
    timestamp = models.DateTimeField(default=timezone.now)
    is_read = models.BooleanField(default=False)

    def __str__(self):
        return f"Message from {self.sender} to {self.recipient} at {self.timestamp}"
    
class Payment(models.Model):
    subuser = models.ForeignKey('SubUser', on_delete=models.CASCADE, related_name='payments')
    student = models.ForeignKey('Student', on_delete=models.CASCADE, related_name='payments')  # New foreign key
    amount = models.DecimalField(max_digits=10, decimal_places=2)  # Amount for each cycle
    frequency = models.CharField(max_length=10, choices=[('weekly', 'Weekly'), ('monthly', 'Monthly'), ('yearly', 'Yearly')], default='weekly')
    start_date = models.DateField()
    end_date = models.DateField(null=True, blank=True)  # Optional end date for the recurring payment
    status = models.CharField(max_length=20, choices=[('pending', 'Pending'), ('paid', 'Paid'), ('overdue', 'Overdue'), ('partial_payment', 'Partial Payment')], default='pending')
    balance = models.DecimalField(max_digits=10, decimal_places=2, default=0)  # Amount remaining to be paid
    amount_paid = models.DecimalField(max_digits=10, decimal_places=2, default=0)  # Amount paid so far
    late_fees = models.DecimalField(max_digits=10, decimal_places=2, default=0)  # Any accumulated late fees
    due_date = models.DateField()
    notes = models.TextField(blank=True, null=True)
    payment_method = models.CharField(max_length=10, choices=[('card', 'Card'), ('cash', 'Cash'), ('check', 'Check')], default='card')
    next_invoice_date = models.DateField(null=True, blank=True)

    def __str__(self):
        return f"Payment for {self.subuser.user.first_name} {self.subuser.user.last_name} due on {self.due_date}"

    def update_status(self):
        # Ensure due_date is a date object
        if isinstance(self.due_date, str):
            self.due_date = datetime.strptime(self.due_date, '%Y-%m-%d').date()

        if self.amount_paid >= self.amount:
            self.status = 'paid'
        elif self.due_date < datetime.now().date() and self.balance > 0:
            self.status = 'overdue'
        elif self.amount_paid > 0:
            self.status = 'partial_payment'
        else:
            self.status = 'pending'

        self.save()

    def create_recurring_payments(self):
        # Check if the next invoice should be created based on next_invoice_date
        if not self.next_invoice_date:
            return  # No next invoice date set, cannot create

        today = datetime.now().date()
        if self.next_invoice_date > today:
            return  # Not yet time to create the next invoice

        # Check if an invoice for this period already exists
        existing_invoice = Payment.objects.filter(
            subuser=self.subuser,
            due_date=self.next_invoice_date,
            frequency=self.frequency
        ).exists()

        if existing_invoice:
            return  # Invoice already exists

        # Calculate the new due_date for the next payment
        new_due_date = self.calculate_next_date()
        if not new_due_date:
            return  # Unable to calculate next date

        # Create new payment with required fields
        new_payment = Payment(
            subuser=self.subuser,
            student=self.student,
            amount=self.amount,
            frequency=self.frequency,
            start_date=self.start_date,
            end_date=self.end_date,
            due_date=new_due_date,
            payment_method=self.payment_method,
            status='pending',
            balance=self.amount,
            amount_paid=0,
            late_fees=0,
            notes=f"Recurring payment from #{self.id}",
            next_invoice_date=new_due_date,
        )

        # INDENTATION FIX: This block was outside the method
        # Check if end_date allows the new payment
        if self.end_date is None or new_due_date <= self.end_date:
            new_payment.save()
            # Update the current payment's next_invoice_date
            self.next_invoice_date = new_payment.calculate_next_date()
            self.save()
        else:
            print("Skipping: Next due date exceeds end date.")

    def calculate_next_date(self):
        if self.frequency == 'weekly':
            return self.due_date + timedelta(weeks=1)
        elif self.frequency == 'monthly':
            return self.due_date + timedelta(days=30)  # Approximation
        elif self.frequency == 'yearly':
            return self.due_date + timedelta(days=365)
        return None

class PaymentRecord(models.Model):
    PAYMENT_SOURCES = [
        ('card', 'Card (Online)'),
        ('manual', 'Manual Entry'),
        ('balance', 'Balance Used'),
        ('refund', 'Refund Issued'),
        ('other', 'Other'),
    ]

    main_user = models.ForeignKey('MainUser', on_delete=models.CASCADE, related_name='payment_records')
    subuser = models.ForeignKey('SubUser', on_delete=models.CASCADE, related_name='payment_records')
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    source = models.CharField(max_length=10, choices=PAYMENT_SOURCES, default='card')
    note = models.TextField(blank=True, null=True)
    timestamp = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"${self.amount:.2f} from {self.subuser.user.username} ({self.get_source_display()}) on {self.timestamp.strftime('%Y-%m-%d')}"

    class Meta:
        ordering = ['-timestamp']

class WeeklyTuition(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('partially_paid', 'Partially Paid'),
        ('paid', 'Paid'),
        ('overdue', 'Overdue'),
    ]

    subuser = models.ForeignKey(SubUser, on_delete=models.CASCADE, related_name='weekly_tuitions')
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    amount_paid = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    start_date = models.DateField()
    end_date = models.DateField()
    has_been_charged = models.BooleanField(default=False)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')

    def __str__(self):
        return f"Tuition for {self.subuser.user.username}: ${self.amount} from {self.start_date} to {self.end_date}"

    class Meta:
        unique_together = ('subuser', 'start_date', 'end_date')
        
class TuitionPlan(models.Model):
    subuser = models.ForeignKey(SubUser, on_delete=models.CASCADE, related_name='tuition_plans')
    weekly_amount = models.DecimalField(max_digits=10, decimal_places=2)
    start_date = models.DateField()
    is_active = models.BooleanField(default=True)  # Optional: marks if the plan is still active

    def __str__(self):
        return f"{self.subuser.user.username} plan - ${self.weekly_amount}/week"

    @property
    def next_payment_dates(self):
        today = date.today()
        start_of_week = today - timedelta(days=today.weekday())  # Monday of this week
        end_of_week = start_of_week + timedelta(days=6)  # Sunday of this week
        return start_of_week, end_of_week

class MessagingPermission(models.Model):
    main_user = models.ForeignKey('MainUser', on_delete=models.CASCADE, related_name="messaging_permissions")
    sender_role = models.ForeignKey(Group, on_delete=models.CASCADE, related_name="sender_permissions")
    receiver_role = models.ForeignKey(Group, on_delete=models.CASCADE, related_name="receiver_permissions")
    can_message = models.BooleanField(default=False)

    class Meta:
        unique_together = ('main_user', 'sender_role', 'receiver_role')  # Updated constraint

    def __str__(self):
        return f"{self.main_user.username}: {self.sender_role.name} -> {self.receiver_role.name}: {'Allowed' if self.can_message else 'Not Allowed'}"
    
class DiaperChangeRecord(models.Model):
    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name='diaper_changes')
    changed_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    timestamp = models.DateTimeField(default=timezone.now)
    notes = models.TextField(null=True, blank=True)  # Optional field for additional details

    def __str__(self):
            return f"Diaper change for {self.student} at {self.timestamp}"

class UserMessagingPermission(models.Model):
    main_user = models.ForeignKey('MainUser', on_delete=models.CASCADE, related_name="user_messaging_permissions")
    sender = models.ForeignKey('MainUser', on_delete=models.CASCADE, related_name="can_send_to")
    receiver = models.ForeignKey('MainUser', on_delete=models.CASCADE, related_name="can_receive_from")
    can_message = models.BooleanField(default=False)

    class Meta:
        unique_together = ('main_user', 'sender', 'receiver')

    def __str__(self):
        return f"{self.sender} -> {self.receiver}: {'Allowed' if self.can_message else 'Not Allowed'}"

class Announcement(models.Model):
    RECIPIENT_CHOICES = [
        ('student', 'Student'),
        ('teacher', 'Teacher'),
    ]
    user = models.ForeignKey('MainUser', on_delete=models.CASCADE, related_name='announcements')
    title = models.CharField(max_length=200)
    message = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    recipient_type = models.CharField(max_length=10, choices=RECIPIENT_CHOICES, default='student')

    def __str__(self):
        return self.title
    
class EnrollmentTemplate(models.Model):
    """Template for enrollment forms - only facility info and policies are customizable"""
    company = models.ForeignKey('Company', on_delete=models.CASCADE, related_name='enrollment_templates')
    location = models.ForeignKey('CompanyAccountOwner', on_delete=models.CASCADE, related_name='enrollment_templates', null=True, blank=True)
    template_name = models.CharField(max_length=255, default="Default Enrollment Form")
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    main_user = models.ForeignKey('MainUser', on_delete=models.CASCADE, related_name='enrollment_templates', null=True, blank=True)
    
    # Header Information (static for all users)
    header_title = models.CharField(max_length=500, default="South Carolina Department of Social Services")
    header_subtitle = models.CharField(max_length=500, default="Child Care Regulatory Services")
    form_title = models.CharField(max_length=500, default="GENERAL RECORD AND STATEMENT OF CHILD'S HEALTH FOR ADMISSION TO CHILD CARE FACILITY")
    form_description = models.TextField(default="This form is to be completed for each child at the time of enrollment in the child care facility, updated as needed when changes occur, and maintained on file at the facility.")
    
    # Footer Information (static for all users)
    footer_text = models.CharField(max_length=255, default="DSS Form 2900 (MAR 10) Edition of OCT 07 is obsolete.", blank=True)
    
    class Meta:
        unique_together = ('company', 'location', 'template_name')
        ordering = ['-created_at']
    
    def __str__(self):
        location_text = f" - {self.location.location_name}" if self.location else ""
        return f"{self.company.name}{location_text} - {self.template_name}"

class EnrollmentPolicy(models.Model):
   
    main_user = models.ForeignKey('MainUser', on_delete=models.CASCADE, related_name='enrollment_policies', null=True, blank=True)
    template = models.ForeignKey('EnrollmentTemplate', on_delete=models.CASCADE, related_name='policies')
    title = models.CharField(max_length=255)
    content = models.TextField()
    order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)
    
    class Meta:
        ordering = ['order']
        unique_together = ('template', 'title')
    
    def __str__(self):
        return f"{self.template.template_name} - {self.title}"

class EnrollmentSubmission(models.Model):
    """Stores enrollment form submissions with standard structure"""
    # Reference to the template used (mainly for policies and facility info)
    template = models.ForeignKey('EnrollmentTemplate', on_delete=models.SET_NULL, null=True, blank=True, related_name='submissions')
    main_user = models.ForeignKey('MainUser', on_delete=models.CASCADE, related_name='enrollment_submissions', null=True, blank=True)
    
    # FACILITY INFORMATION (populated from CompanyAccountOwner via template)
    facility_name = models.CharField(max_length=255, blank=True)
    facility_address = models.CharField(max_length=500, blank=True)
    facility_city_state_zip = models.CharField(max_length=255, blank=True)
    facility_county = models.CharField(max_length=100, blank=True)
    
    # CHILD INFORMATION (standard fields for all users)
    child_first_name = models.CharField(max_length=100)
    child_last_name = models.CharField(max_length=100)
    child_middle_initial = models.CharField(max_length=1, blank=True)
    child_nick_name = models.CharField(max_length=100, blank=True)
    date_of_birth = models.DateField()
    enrollment_date = models.DateField()
    child_street_address = models.CharField(max_length=500, blank=True)
    child_city_state_zip = models.CharField(max_length=255, blank=True)
    
    # PARENT/GUARDIAN INFORMATION (standard fields for all users)
    parent1_full_name = models.CharField(max_length=200)
    parent1_home_phone = models.CharField(max_length=20, blank=True)
    parent1_work_phone = models.CharField(max_length=20, blank=True)
    parent1_other_phone = models.CharField(max_length=20, blank=True)
    
    parent2_full_name = models.CharField(max_length=200, blank=True)
    parent2_home_phone = models.CharField(max_length=20, blank=True)
    parent2_work_phone = models.CharField(max_length=20, blank=True)
    parent2_other_phone = models.CharField(max_length=20, blank=True)
    
    # EMERGENCY CONTACTS (standard fields for all users)
    emergency1_name = models.CharField(max_length=200, blank=True)
    emergency1_relationship = models.CharField(max_length=100, blank=True)
    emergency1_address = models.CharField(max_length=500, blank=True)
    emergency1_city_state_zip = models.CharField(max_length=255, blank=True)
    emergency1_phone = models.CharField(max_length=20, blank=True)
    emergency1_family_code = models.CharField(max_length=100, blank=True)
    
    emergency2_name = models.CharField(max_length=200, blank=True)
    emergency2_relationship = models.CharField(max_length=100, blank=True)
    emergency2_address = models.CharField(max_length=500, blank=True)
    emergency2_city_state_zip = models.CharField(max_length=255, blank=True)
    emergency2_phone = models.CharField(max_length=20, blank=True)
    emergency2_family_code = models.CharField(max_length=100, blank=True)
    
    # SCHEDULE INFORMATION (standard fields for all users)
    enrolled_in_school = models.CharField(max_length=10, blank=True)  # yes/no
    regular_hours_from = models.TimeField(null=True, blank=True)
    regular_hours_to = models.TimeField(null=True, blank=True)
    dropin_hours_from = models.TimeField(null=True, blank=True)
    dropin_hours_to = models.TimeField(null=True, blank=True)
    attendance_days = models.JSONField(default=list, blank=True)  # Store selected days as array
    meals = models.JSONField(default=list, blank=True)  # Store selected meals as array
    
    # HEALTH INFORMATION (standard fields for all users)
    family_physician_name = models.CharField(max_length=255, blank=True)
    physician_address = models.CharField(max_length=500, blank=True)
    physician_city_state_zip = models.CharField(max_length=255, blank=True)
    physician_telephone = models.CharField(max_length=20, blank=True)
    
    emergency_care_provider = models.CharField(max_length=255, blank=True)
    emergency_facility_address = models.CharField(max_length=500, blank=True)
    emergency_facility_city_state_zip = models.CharField(max_length=255, blank=True)
    emergency_facility_telephone = models.CharField(max_length=20, blank=True)
    
    dental_care_provider_name = models.CharField(max_length=255, blank=True)
    dental_provider_address = models.CharField(max_length=500, blank=True)
    dental_provider_city_state_zip = models.CharField(max_length=255, blank=True)
    dental_provider_telephone = models.CharField(max_length=20, blank=True)
    
    health_insurance_provider = models.CharField(max_length=255, blank=True)
    immunization_certificate = models.CharField(max_length=10, blank=True)  # yes/no/na
    immunization_explanation = models.TextField(blank=True)
    health_conditions = models.TextField(blank=True)
    additional_comments = models.TextField(blank=True)
    
    # PICKUP INFORMATION (standard fields for all users)
    pickup_child_name = models.CharField(max_length=255, blank=True)
    pickup_child_dob = models.DateField(null=True, blank=True)
    pickup_mother_name = models.CharField(max_length=255, blank=True)
    pickup_mother_cell = models.CharField(max_length=20, blank=True)
    pickup_mother_work = models.CharField(max_length=20, blank=True)
    pickup_mother_email = models.EmailField(blank=True)
    pickup_father_name = models.CharField(max_length=255, blank=True)
    pickup_father_cell = models.CharField(max_length=20, blank=True)
    pickup_father_work = models.CharField(max_length=20, blank=True)
    pickup_father_email = models.EmailField(blank=True)
    pickup_emergency1_name = models.CharField(max_length=255, blank=True)
    pickup_emergency1_phone = models.CharField(max_length=20, blank=True)
    pickup_emergency2_name = models.CharField(max_length=255, blank=True)
    pickup_emergency2_phone = models.CharField(max_length=20, blank=True)
    
    # CHILD INFO SECTION (standard fields for all users)
    mothers_ssn = models.CharField(max_length=4, blank=True)  # Last 4 digits only
    mothers_email = models.EmailField(blank=True)
    mothers_employment = models.CharField(max_length=255, blank=True)
    fathers_email = models.EmailField(blank=True)
    fathers_employment = models.CharField(max_length=255, blank=True)
    
    # Authorized pickup persons
    pickup_person1_name = models.CharField(max_length=255, blank=True)
    pickup_person1_phone = models.CharField(max_length=20, blank=True)
    pickup_person2_name = models.CharField(max_length=255, blank=True)
    pickup_person2_phone = models.CharField(max_length=20, blank=True)
    pickup_person3_name = models.CharField(max_length=255, blank=True)
    pickup_person3_phone = models.CharField(max_length=20, blank=True)
    pickup_person4_name = models.CharField(max_length=255, blank=True)
    pickup_person4_phone = models.CharField(max_length=20, blank=True)
    
    # SIGNATURES (standard fields for all users)
    parent_signature = models.TextField(blank=True)  # Base64 signature data
    parent_signature_date = models.DateField(null=True, blank=True)
    # Add second parent signature
    parent2_signature = models.TextField(blank=True)  # Base64 signature data
    parent2_signature_date = models.DateField(null=True, blank=True)
    photo_permission_parent = models.CharField(max_length=255, blank=True)
    
    staff_signature = models.TextField(blank=True)  # Base64 signature data
    staff_signature_date = models.DateField(null=True, blank=True)
    
    # Store any additional custom data as JSON (for future flexibility)
    additional_data = models.JSONField(default=dict, blank=True)
    
    # Submission metadata
    submitted_at = models.DateTimeField(auto_now_add=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    STATUS_CHOICES = [
        ('new', 'New'),
        ('enrolled', 'Enrolled'),
        ('archive', 'Archive'),
    ]
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='new')
    status_changed_by = models.CharField(max_length=150, null=True, blank=True)  # Username who changed status
    status_changed_date = models.DateTimeField(null=True, blank=True)  # When status was changed
    
    class Meta:
        db_table = 'enrollment_submissions'
        ordering = ['-submitted_at']
    
    def __str__(self):
        return f"Enrollment: {self.child_first_name} {self.child_last_name} - {self.submitted_at.strftime('%Y-%m-%d')}"