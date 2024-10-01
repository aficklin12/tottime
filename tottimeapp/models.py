from django.db import models
from django.contrib.auth.models import User, AbstractUser, Group, Permission
from django.utils import timezone
import uuid

class Location(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    facility = models.CharField(max_length=255)
    sponsor = models.CharField(max_length=255)

    def __str__(self):
        return f"Location: {self.user.username} - {self.facility} - {self.sponsor}"

class Rule(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
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
    user = models.ForeignKey(User, on_delete=models.CASCADE)
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
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    name = models.CharField(max_length=100, null=False)
    ingredient1 = models.ForeignKey('Inventory', related_name='veg_ingredient1', on_delete=models.SET_NULL, null=True)
    qty1 = models.PositiveIntegerField(null=True)
    rule = models.ForeignKey('Rule', on_delete=models.CASCADE, null=True, blank=True)

    def __str__(self):
        return self.name

class FruitRecipe(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    name = models.CharField(max_length=100, null=False)
    ingredient1 = models.ForeignKey('Inventory', related_name='fruit_ingredient1', on_delete=models.SET_NULL, null=True)
    qty1 = models.PositiveIntegerField(null=True)
    rule = models.ForeignKey('Rule', on_delete=models.CASCADE, null=True, blank=True)

    def __str__(self):
        return self.name

class WgRecipe(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    name = models.CharField(max_length=100, null=False)
    ingredient1 = models.ForeignKey('Inventory', related_name='wg_ingredient1', on_delete=models.SET_NULL, null=True)
    qty1 = models.PositiveIntegerField(null=True)
    rule = models.ForeignKey('Rule', on_delete=models.CASCADE, null=True, blank=True)

    def __str__(self):
        return self.name

class Recipe(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
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
    user = models.ForeignKey(User, on_delete=models.CASCADE)
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
    user = models.ForeignKey(User, on_delete=models.CASCADE)
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
    user = models.ForeignKey(User, on_delete=models.CASCADE)
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

    user = models.ForeignKey(User, on_delete=models.CASCADE)
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
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    item = models.CharField(max_length=100, unique=True, default='default_item')
    quantity = models.IntegerField(default=1)  # Add default value here
    category = models.CharField(max_length=20, choices=CATEGORY_CHOICES, default='Other')
    ordered = models.BooleanField(default=False)

    def __str__(self):
        return self.item


    
class Classroom(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    name = models.CharField(max_length=100)

    def __str__(self):
        return self.name

class Student(models.Model):
    first_name = models.CharField(max_length=100)
    last_name = models.CharField(max_length=100)
    date_of_birth = models.DateField()
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    code = models.CharField(max_length=4, unique=True)
    classroom = models.ForeignKey(Classroom, on_delete=models.CASCADE)

    def __str__(self):
        return f"{self.first_name} {self.last_name}"

class AttendanceRecord(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    student = models.ForeignKey(Student, on_delete=models.CASCADE)
    sign_in_time = models.DateTimeField(default=timezone.now)
    sign_out_time = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"{self.student} - {self.sign_in_time}"
    
class MilkCount(models.Model):
    inventory_item = models.ForeignKey(Inventory, on_delete=models.CASCADE)
    timestamp = models.DateTimeField(auto_now_add=True)
    current_qty = models.IntegerField(default=0)  # Current quantity
    received_qty = models.IntegerField(default=0)  # Received quantity for the month
    user = models.ForeignKey(User, on_delete=models.CASCADE)

    def __str__(self):
        return f"{self.inventory_item.item} - {self.timestamp}"

    class Meta:
        unique_together = (('inventory_item', 'timestamp'),)

class WeeklyMenu(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    date = models.DateField()
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