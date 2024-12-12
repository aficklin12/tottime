from django.db import models
from django.conf import settings
from django.contrib.auth.models import  AbstractUser, Group, Permission
from django.utils import timezone
from PIL import Image, ImageDraw
from io import BytesIO
from django.core.exceptions import ValidationError
import random
from django.core.files.storage import default_storage
from django.conf import settings
from datetime import timedelta
from datetime import datetime
import os
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
    quantity = models.IntegerField()
    rule = models.ForeignKey(Rule, on_delete=models.CASCADE, null=True, blank=True)  # Allow null and blank values permanently
    resupply = models.IntegerField()
    total_quantity = models.IntegerField(default=0)
    

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

    def __str__(self):
        return self.name

class Student(models.Model):
    first_name = models.CharField(max_length=100)
    last_name = models.CharField(max_length=100)
    date_of_birth = models.DateField()
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    code = models.CharField(max_length=4, unique=True)
    classroom = models.ForeignKey(Classroom, on_delete=models.CASCADE)

    def __str__(self):
        return f"{self.first_name} {self.last_name}"

class AttendanceRecord(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    student = models.ForeignKey(Student, on_delete=models.CASCADE)
    sign_in_time = models.DateTimeField(default=timezone.now)
    sign_out_time = models.DateTimeField(null=True, blank=True)

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

    class Meta:
        unique_together = ('role', 'permission')  # Ensure unique combination of role and permission

    def __str__(self):
        yes_no = "Yes" if self.yes_no_permission else "No"
        return f"{self.role.name} - {self.permission.codename} - Permission: {yes_no}"

class Invitation(models.Model):
    email = models.EmailField()
    role = models.ForeignKey(Group, on_delete=models.CASCADE)
    invited_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    token = models.CharField(max_length=100, unique=True)  # To create unique links
    created_at = models.DateTimeField(auto_now_add=True)

class MainUser(AbstractUser):
    first_name = models.CharField(max_length=30, blank=False)
    last_name = models.CharField(max_length=30, blank=False)
    email = models.EmailField(unique=True, blank=False)
    company_name = models.CharField(max_length=255, blank=True, null=True)
    phone_number = models.CharField(max_length=15, blank=True, null=True)
    address = models.CharField(max_length=255, blank=True, null=True)
    groups = models.ManyToManyField(Group, related_name='mainuser_set', blank=True)
    user_permissions = models.ManyToManyField(Permission, related_name='mainuser_set', blank=True)
    stripe_account_id = models.CharField(max_length=255, null=True, blank=True)
    stripe_public_key = models.CharField(max_length=255, blank=True, null=True)
    stripe_secret_key = models.CharField(max_length=255, blank=True, null=True)
    code = models.CharField(max_length=4, unique=True, blank=True, null=True)
    profile_picture = models.ImageField(upload_to='profile_pictures/', blank=True, null=True, default='profile_pictures/Default_pfp.jpg')

    def __str__(self):
        return f"{self.first_name} {self.last_name} - {self.company_name}"

    def save(self, *args, **kwargs):
        # Check if the profile picture is too large
        if self.profile_picture and self.profile_picture.size > MAX_IMAGE_SIZE:
            raise ValidationError(f"Profile picture size exceeds the maximum allowed size of {MAX_IMAGE_SIZE / (1024 * 1024)} MB.")

        # Check if the user has uploaded a profile picture
        if not self.profile_picture:
            # If not, set the profile picture to the default image
            default_pic_path = os.path.join('media', 'profile_pictures', 'blank pro pic.avif')
            if os.path.exists(default_pic_path):
                with open(default_pic_path, 'rb') as default_pic_file:
                    self.profile_picture.save('Default_pfp.jpg', default_pic_file, save=False)
        
        # Resize the profile picture if it is provided
        if self.profile_picture:
            # Open the uploaded image
            img = Image.open(self.profile_picture)
            
            # Ensure the image is in a square shape, resize if necessary
            width, height = img.size
            min_dimension = min(width, height)

            # Crop the image to a square (center crop)
            left = (width - min_dimension) / 2
            top = (height - min_dimension) / 2
            right = (width + min_dimension) / 2
            bottom = (height + min_dimension) / 2
            img = img.crop((left, top, right, bottom))

            # Create a circular mask
            mask = Image.new('L', img.size, 0)
            draw = ImageDraw.Draw(mask)
            draw.ellipse((0, 0, img.size[0], img.size[1]), fill=255)

            # Apply the mask to the image
            img.putalpha(mask)

            # Resize the image to the final 60x60 size (nickel-sized)
            img = img.resize((60, 60), Image.Resampling.LANCZOS)

            # Save the resized image to a BytesIO object
            img_io = BytesIO()
            img.save(img_io, img.format if img.format else 'PNG')  # Ensure format is set
            img_io.seek(0)

            # Save the resized image back to the model's field
            self.profile_picture = default_storage.save(self.profile_picture.name, img_io)
        
        # Check if the user is in "Parent" or "Free User" groups (IDs 5 or 6)
        if not self.code and not self.groups.filter(id__in=[5, 6]).exists():
            self.code = self.generate_unique_code()

        # Save the model instance
        super(MainUser, self).save(*args, **kwargs)

    def generate_unique_code(self):
        """Generates a unique 4-digit code."""
        code = str(random.randint(1000, 9999))  # Generates a random 4-digit number
        while MainUser.objects.filter(code=code).exists():  # Ensure the code is unique
            code = str(random.randint(1000, 9999))
        return code
    
class SubUser(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)  # Link to the custom User model
    main_user = models.ForeignKey('MainUser', on_delete=models.CASCADE, related_name='sub_users')
    group_id = models.ForeignKey(Group, on_delete=models.CASCADE, related_name="subusers", null=True, blank=True)
    classroom = models.ForeignKey('Classroom', on_delete=models.SET_NULL, null=True, blank=True, related_name='subusers')
    student = models.ForeignKey('Student', on_delete=models.CASCADE, null=True, blank=True)  # Linking to a Student
    balance = models.DecimalField(max_digits=10, decimal_places=2, default=0)  # New balance field

    def __str__(self):
        return f"SubUser: {self.user.username} linked to MainUser: {self.main_user.username}"
    
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
    status = models.CharField(max_length=20, choices=[('pending', 'Pending'), ('paid', 'Paid'), ('overdue', 'Overdue'), ('partial_payment', 'Partial Payment')], default='Pending')
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
        if isinstance(self.due_date, str):
            self.due_date = datetime.strptime(self.due_date, '%Y-%m-%d').date()

        if self.amount_paid >= self.amount:
            self.status = 'Paid in Full'
        elif self.due_date < datetime.now().date() and self.balance > 0 and self.status != 'Paid in Full':
            self.status = 'Overdue'
        elif self.amount_paid > 0:
            self.status = 'Partial Payment'
        else:
            self.status = 'Pending'

        self.save()

    def create_recurring_payments(self):
        # Check if the current date is before the stop date (end_date)
        if self.__class__.objects.filter(subuser=self.subuser, next_invoice_date=self.next_invoice_date).exists():
            print("Invoice already exists for this week.")
            return
        # Logic for creating the new payment (invoice)
        new_payment = self.__class__(amount=self.amount,
                                    frequency=self.frequency,
                                    start_date=self.start_date,
                                    end_date=self.end_date,
                                    subuser=self.subuser,
                                    payment_method=self.payment_method)
        
        # Update the next invoice date to be 1 week later, ensuring we don't exceed the stop date
        new_payment.next_invoice_date = self.next_invoice_date + timedelta(weeks=1)
        
        if new_payment.next_invoice_date <= self.end_date:
            new_payment.save()  # Save the new payment only if within the valid period
        else:
            print("Skipping invoice creation: next invoice date exceeds stop date.")

    def calculate_next_date(self):
        if self.frequency == 'weekly':
            return self.due_date + timedelta(weeks=1)
        elif self.frequency == 'monthly':
            return self.due_date + timedelta(days=30)  # Approximation
        elif self.frequency == 'yearly':
            return self.due_date + timedelta(days=365)
        return None
