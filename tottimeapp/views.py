from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.models import Group
from django.contrib.auth import authenticate, login, logout
from django.db.models import Q
import stripe, requests
import urllib.parse
from square.client import Client
from django.conf import settings
stripe.api_key = settings.STRIPE_SECRET_KEY
from django.utils.timezone import now
from django.db.models import Sum, F, ExpressionWrapper, DurationField
from decimal import Decimal, InvalidOperation
from django.db import transaction
from django.contrib import messages
from .forms import SignupForm, LoginForm, RuleForm, MessageForm
from .models import Inventory, Recipe, BreakfastRecipe, Classroom, AMRecipe, PMRecipe, OrderList, Student, AttendanceRecord
from .models import MilkCount, WeeklyMenu, Rule, MainUser, FruitRecipe, VegRecipe, WgRecipe, RolePermission, SubUser, Invitation
from .models import Message, Conversation, Payment, TeacherAttendanceRecord
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.http import HttpResponseBadRequest, JsonResponse, HttpResponseNotAllowed, HttpResponse
import random, logging, json
from django.utils.dateparse import parse_datetime
from django.views.decorators.csrf import csrf_protect
import pytz, os
from PIL import Image
from io import BytesIO
from .forms import InvitationForm
from django.utils.timezone import make_aware
from django.db import models
from django.utils.timezone import is_aware, make_aware
from pytz import utc
from datetime import datetime, timedelta, date, time
from collections import defaultdict
from django.utils import timezone
from django.apps import apps
from django.db.models import F, Sum, Max, Min
from django.views.decorators.csrf import csrf_exempt
from calendar import monthrange
from django.core.mail import send_mail
from django.urls import reverse
from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import Group
from django.shortcuts import render, redirect
import uuid
from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from .models import Classroom, MainUser, SubUser, RolePermission, Student
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
logger = logging.getLogger(__name__)
from django.http import HttpResponseRedirect
from django.urls import reverse

def get_user_for_view(request):
    try:
        subuser = SubUser.objects.get(user=request.user)
        return subuser.main_user  # Return the MainUser object
    except SubUser.DoesNotExist:
        return request.user  # This will return a MainUser object

def login_view(request):
    return render(request, 'login.html')


def app_redirect(request):
    return render(request, 'app_redirect.html')

@login_required(login_url='/login/')
def index(request):
    # Get the main user or subuser
    user = get_user_for_view(request)

    # Check if the user is a SubUser and redirect accordingly
    try:
        sub_user = SubUser.objects.get(user=request.user)
        group_id = sub_user.group_id_id  # Get group_id_id from SubUser table

        if group_id == 2:
            return redirect('index_director')
        elif group_id == 3:
            return redirect('index_teacher')
        elif group_id == 4:
            return redirect('index_cook')
        elif group_id == 5:
            return redirect('index_parent')
        elif group_id == 6:
            return redirect('index_free_user')
    except SubUser.DoesNotExist:
        # If the user is not a SubUser, assume they are the owner (ID 1)
        pass

    # Get order items for the Food Program section
    order_items = OrderList.objects.filter(user=user)

    # --- New: Build classroom ratio cards ---
    today = date.today()
    attendance_records = AttendanceRecord.objects.filter(
    sign_in_time__date=today, 
    sign_out_time__isnull=True,  # Add this condition to filter only records with NULL sign_out_time
    user=user
)
    # Get the user's classrooms (assuming you have a Classroom model)
    classrooms = Classroom.objects.filter(user=user)
    classroom_cards = {}
    for classroom in classrooms:
        # Count attendance records where classroom_override equals the classroom name
        count = attendance_records.filter(classroom_override=classroom.name).count()
        classroom_cards[classroom.name] = {
            'count': count,
            'ratio': classroom.ratios  # target ratio from the Classroom model
        }

    context = {
        'order_items': order_items,
        'classroom_cards': classroom_cards,
    }
    return render(request, 'index.html', context)

@login_required(login_url='/login/')
def index_director(request):
    user = get_user_for_view(request)
    
    show_weekly_menu = False
    show_inventory = False
    show_milk_inventory = False
    show_meal_count = False
    show_classroom_options = False
    show_recipes = False
    show_sign_in = False
    show_daily_attendance = False
    show_rosters = False
    show_permissions = False
    show_menu_rules = False
    show_billing = False
    show_payment_setup = False
    show_clock_in = False

    try:
        # Check if the user is a SubUser
        sub_user = SubUser.objects.get(user=request.user)
        group_id = sub_user.group_id.id

        # Dynamically check permissions
        permissions_ids = {
            'weekly_menu': 271,
            'inventory': 272,
            'milk_inventory': 270,
            'meal_count': 269,
            'classroom_options': 268,
            'recipes': 267,
            'sign_in': 273,
            'daily_attendance': 274,
            'rosters': 275,
            'permissions': 157,
            'menu_rules': 266,
            'billing': 331,
            'payment_setup': 332,
            'clock_in': 337,
        }

        for perm_key, perm_id in permissions_ids.items():
            try:
                role_permission = RolePermission.objects.get(role_id=group_id, permission_id=perm_id)
                if perm_key == 'weekly_menu':
                    show_weekly_menu = role_permission.yes_no_permission
                elif perm_key == 'inventory':
                    show_inventory = role_permission.yes_no_permission
                elif perm_key == 'milk_inventory':
                    show_milk_inventory = role_permission.yes_no_permission
                elif perm_key == 'meal_count':
                    show_meal_count = role_permission.yes_no_permission
                elif perm_key == 'permissions':
                    show_permissions = role_permission.yes_no_permission
                elif perm_key == 'menu_rules':
                    show_menu_rules = role_permission.yes_no_permission
                elif perm_key == 'classroom_options':
                    show_classroom_options = role_permission.yes_no_permission
                elif perm_key == 'recipes':
                    show_recipes = role_permission.yes_no_permission
                elif perm_key == 'sign_in':
                    show_sign_in = role_permission.yes_no_permission
                elif perm_key == 'daily_attendance':
                    show_daily_attendance = role_permission.yes_no_permission
                elif perm_key == 'rosters':
                    show_rosters = role_permission.yes_no_permission
                elif perm_key == 'billing':
                    show_billing = role_permission.yes_no_permission
                elif perm_key == 'payment_setup':
                    show_payment_setup = role_permission.yes_no_permission
                elif perm_key == 'clock_in':
                    show_clock_in = role_permission.yes_no_permission  
            except RolePermission.DoesNotExist:
                continue  

    except SubUser.DoesNotExist:
        # If the user is not a SubUser, default to no permissions (or set defaults as needed)
        pass

    # Ensure order items are always retrieved
    order_items = OrderList.objects.filter(user=user)

    # --- New: Build classroom ratio cards ---
    today = date.today()
    attendance_records = AttendanceRecord.objects.filter(
    sign_in_time__date=today, 
    sign_out_time__isnull=True,  # Add this condition to filter only records with NULL sign_out_time
    user=user
)
    # Get the user's classrooms (assuming you have a Classroom model)
    classrooms = Classroom.objects.filter(user=user)
    classroom_cards = {}
    for classroom in classrooms:
        # Count attendance records where classroom_override equals the classroom name
        count = attendance_records.filter(classroom_override=classroom.name).count()
        classroom_cards[classroom.name] = {
            'count': count,
            'ratio': classroom.ratios 
            }

    context = {
        'order_items': order_items,
        'classroom_cards': classroom_cards,
        'show_weekly_menu': show_weekly_menu,
        'show_inventory': show_inventory,
        'show_milk_inventory': show_milk_inventory,
        'show_meal_count': show_meal_count,
        'show_classroom_options': show_classroom_options,
        'show_recipes': show_recipes,
        'show_sign_in': show_sign_in,
        'show_daily_attendance': show_daily_attendance,
        'show_rosters': show_rosters,
        'show_permissions': show_permissions,
        'show_menu_rules': show_menu_rules,
        'show_billing': show_billing,
        'show_payment_setup': show_payment_setup,
        'show_clock_in': show_clock_in, 
    }

    # Render the index_director page with context
    return render(request, 'index_director.html', context)


@login_required(login_url='/login/')
def index_teacher(request):
    show_weekly_menu = False
    show_inventory = False
    show_milk_inventory = False
    show_meal_count = False
    show_classroom_options = False
    show_recipes = False
    show_sign_in = False
    show_daily_attendance = False
    show_rosters = False
    show_permissions = False
    show_menu_rules = False
    show_billing = False
    show_payment_setup = False
    show_clock_in = False

    try:
        # Check if the user is a SubUser
        sub_user = SubUser.objects.get(user=request.user)
        group_id = sub_user.group_id.id

        # Dynamically check permissions
        permissions_ids = {
            'weekly_menu': 271,
            'inventory': 272,
            'milk_inventory': 270,
            'meal_count': 269,
            'classroom_options': 268,
            'recipes': 267,
            'sign_in': 273,
            'daily_attendance': 274,
            'rosters': 275,
            'permissions': 157,
            'menu_rules': 266,
            'billing': 331,
            'payment_setup': 332,
            'clock_in': 337,
        }

        for perm_key, perm_id in permissions_ids.items():
            try:
                role_permission = RolePermission.objects.get(role_id=group_id, permission_id=perm_id)
                if perm_key == 'weekly_menu':
                    show_weekly_menu = role_permission.yes_no_permission
                elif perm_key == 'inventory':
                    show_inventory = role_permission.yes_no_permission
                elif perm_key == 'milk_inventory':
                    show_milk_inventory = role_permission.yes_no_permission
                elif perm_key == 'meal_count':
                    show_meal_count = role_permission.yes_no_permission
                elif perm_key == 'permissions':
                    show_permissions = role_permission.yes_no_permission
                elif perm_key == 'menu_rules':
                    show_menu_rules = role_permission.yes_no_permission
                elif perm_key == 'classroom_options':
                    show_classroom_options = role_permission.yes_no_permission
                elif perm_key == 'recipes':
                    show_recipes = role_permission.yes_no_permission
                elif perm_key == 'sign_in':
                    show_sign_in = role_permission.yes_no_permission
                elif perm_key == 'daily_attendance':
                    show_daily_attendance = role_permission.yes_no_permission
                elif perm_key == 'rosters':
                    show_rosters = role_permission.yes_no_permission
                elif perm_key == 'billing':
                    show_billing = role_permission.yes_no_permission
                elif perm_key == 'payment_setup':
                    show_payment_setup = role_permission.yes_no_permission
                elif perm_key == 'clock_in':
                    show_clock_in = role_permission.yes_no_permission 
            except RolePermission.DoesNotExist:
                continue

    except SubUser.DoesNotExist:
        # If the user is not a SubUser, default to no permissions (or set defaults as needed)
        pass

    # Render the index_director page without restricting access
    return render(request, 'index_teacher.html', {
        'show_weekly_menu': show_weekly_menu,
        'show_inventory': show_inventory,
        'show_milk_inventory': show_milk_inventory,
        'show_meal_count': show_meal_count,
        'show_classroom_options': show_classroom_options,
        'show_recipes': show_recipes,
        'show_sign_in': show_sign_in,
        'show_daily_attendance': show_daily_attendance,
        'show_rosters': show_rosters,
        'show_permissions': show_permissions,
        'show_menu_rules': show_menu_rules,
        'show_billing': show_billing,
        'show_payment_setup': show_payment_setup,
        'show_clock_in': show_clock_in, 
    })

@login_required(login_url='/login/')
def index_cook(request):
    show_weekly_menu = False
    show_inventory = False
    show_milk_inventory = False
    show_meal_count = False
    show_classroom_options = False
    show_recipes = False
    show_sign_in = False
    show_daily_attendance = False
    show_rosters = False
    show_permissions = False
    show_menu_rules = False
    show_billing = False
    show_payment_setup = False
    show_clock_in = False

    try:
        # Check if the user is a SubUser
        sub_user = SubUser.objects.get(user=request.user)
        group_id = sub_user.group_id.id

        # Dynamically check permissions
        permissions_ids = {
            'weekly_menu': 271,
            'inventory': 272,
            'milk_inventory': 270,
            'meal_count': 269,
            'classroom_options': 268,
            'recipes': 267,
            'sign_in': 273,
            'daily_attendance': 274,
            'rosters': 275,
            'permissions': 157,
            'menu_rules': 266,
            'billing': 331,
            'payment_setup': 332,
            'clock_in': 337,
        }

        for perm_key, perm_id in permissions_ids.items():
            try:
                role_permission = RolePermission.objects.get(role_id=group_id, permission_id=perm_id)
                if perm_key == 'weekly_menu':
                    show_weekly_menu = role_permission.yes_no_permission
                elif perm_key == 'inventory':
                    show_inventory = role_permission.yes_no_permission
                elif perm_key == 'milk_inventory':
                    show_milk_inventory = role_permission.yes_no_permission
                elif perm_key == 'meal_count':
                    show_meal_count = role_permission.yes_no_permission
                elif perm_key == 'permissions':
                    show_permissions = role_permission.yes_no_permission
                elif perm_key == 'menu_rules':
                    show_menu_rules = role_permission.yes_no_permission
                elif perm_key == 'classroom_options':
                    show_classroom_options = role_permission.yes_no_permission
                elif perm_key == 'recipes':
                    show_recipes = role_permission.yes_no_permission
                elif perm_key == 'sign_in':
                    show_sign_in = role_permission.yes_no_permission
                elif perm_key == 'daily_attendance':
                    show_daily_attendance = role_permission.yes_no_permission
                elif perm_key == 'rosters':
                    show_rosters = role_permission.yes_no_permission
                elif perm_key == 'billing':
                    show_billing = role_permission.yes_no_permission
                elif perm_key == 'payment_setup':
                    show_payment_setup = role_permission.yes_no_permission
                elif perm_key == 'clock_in':
                    show_clock_in = role_permission.yes_no_permission
            except RolePermission.DoesNotExist:
                continue

    except SubUser.DoesNotExist:
        # If the user is not a SubUser, default to no permissions (or set defaults as needed)
        pass

    # Render the index_director page without restricting access
    return render(request, 'index_cook.html', {
        'show_weekly_menu': show_weekly_menu,
        'show_inventory': show_inventory,
        'show_milk_inventory': show_milk_inventory,
        'show_meal_count': show_meal_count,
        'show_classroom_options': show_classroom_options,
        'show_recipes': show_recipes,
        'show_sign_in': show_sign_in,
        'show_daily_attendance': show_daily_attendance,
        'show_rosters': show_rosters,
        'show_permissions': show_permissions,
        'show_menu_rules': show_menu_rules,
        'show_billing': show_billing,
        'show_payment_setup': show_payment_setup,
        'show_clock_in': show_clock_in,
    })

@login_required(login_url='/login/')
def index_parent(request):
    show_weekly_menu = False
    show_inventory = False
    show_milk_inventory = False
    show_meal_count = False
    show_classroom_options = False
    show_recipes = False
    show_sign_in = False
    show_daily_attendance = False
    show_rosters = False
    show_permissions = False
    show_menu_rules = False
    show_billing = False
    show_payment_setup = False
    show_clock_in = False

    try:
        # Check if the user is a SubUser
        sub_user = SubUser.objects.get(user=request.user)
        group_id = sub_user.group_id.id

        # Dynamically check permissions
        permissions_ids = {
            'weekly_menu': 271,
            'inventory': 272,
            'milk_inventory': 270,
            'meal_count': 269,
            'classroom_options': 268,
            'recipes': 267,
            'sign_in': 273,
            'daily_attendance': 274,
            'rosters': 275,
            'permissions': 157,
            'menu_rules': 266,
            'billing': 331,
            'payment_setup': 332,
            'clock_in': 337,
        }

        for perm_key, perm_id in permissions_ids.items():
            try:
                role_permission = RolePermission.objects.get(role_id=group_id, permission_id=perm_id)
                if perm_key == 'weekly_menu':
                    show_weekly_menu = role_permission.yes_no_permission
                elif perm_key == 'inventory':
                    show_inventory = role_permission.yes_no_permission
                elif perm_key == 'milk_inventory':
                    show_milk_inventory = role_permission.yes_no_permission
                elif perm_key == 'meal_count':
                    show_meal_count = role_permission.yes_no_permission
                elif perm_key == 'permissions':
                    show_permissions = role_permission.yes_no_permission
                elif perm_key == 'menu_rules':
                    show_menu_rules = role_permission.yes_no_permission
                elif perm_key == 'classroom_options':
                    show_classroom_options = role_permission.yes_no_permission
                elif perm_key == 'recipes':
                    show_recipes = role_permission.yes_no_permission
                elif perm_key == 'sign_in':
                    show_sign_in = role_permission.yes_no_permission
                elif perm_key == 'daily_attendance':
                    show_daily_attendance = role_permission.yes_no_permission
                elif perm_key == 'rosters':
                    show_rosters = role_permission.yes_no_permission
                elif perm_key == 'billing':
                    show_billing = role_permission.yes_no_permission
                elif perm_key == 'payment_setup':
                    show_payment_setup = role_permission.yes_no_permission
                elif perm_key == 'clock_in':
                    show_clock_in = role_permission.yes_no_permission 
            except RolePermission.DoesNotExist:
                continue

    except SubUser.DoesNotExist:
        # If the user is not a SubUser, default to no permissions (or set defaults as needed)
        pass

    # Render the index_director page without restricting access
    return render(request, 'index_parent.html', {
        'show_weekly_menu': show_weekly_menu,
        'show_inventory': show_inventory,
        'show_milk_inventory': show_milk_inventory,
        'show_meal_count': show_meal_count,
        'show_classroom_options': show_classroom_options,
        'show_recipes': show_recipes,
        'show_sign_in': show_sign_in,
        'show_daily_attendance': show_daily_attendance,
        'show_rosters': show_rosters,
        'show_permissions': show_permissions,
        'show_menu_rules': show_menu_rules,
        'show_billing': show_billing,
        'show_payment_setup': show_payment_setup,
        'show_clock_in': show_clock_in, 
        
    })

@login_required(login_url='/login/')
def index_free_user(request):
    show_weekly_menu = False
    show_inventory = False
    show_milk_inventory = False
    show_meal_count = False
    show_classroom_options = False
    show_recipes = False
    show_sign_in = False
    show_daily_attendance = False
    show_rosters = False
    show_permissions = False
    show_menu_rules = False
    show_billing = False
    show_payment_setup = False
    show_clock_in = False

    try:
        # Check if the user is a SubUser
        sub_user = SubUser.objects.get(user=request.user)
        group_id = sub_user.group_id.id

        # Dynamically check permissions
        permissions_ids = {
            'weekly_menu': 271,
            'inventory': 272,
            'milk_inventory': 270,
            'meal_count': 269,
            'classroom_options': 268,
            'recipes': 267,
            'sign_in': 273,
            'daily_attendance': 274,
            'rosters': 275,
            'permissions': 157,
            'menu_rules': 266,
            'billing': 331,
            'payment_setup': 332,
            'clock_in': 337,
        }

        for perm_key, perm_id in permissions_ids.items():
            try:
                role_permission = RolePermission.objects.get(role_id=group_id, permission_id=perm_id)
                if perm_key == 'weekly_menu':
                    show_weekly_menu = role_permission.yes_no_permission
                elif perm_key == 'inventory':
                    show_inventory = role_permission.yes_no_permission
                elif perm_key == 'milk_inventory':
                    show_milk_inventory = role_permission.yes_no_permission
                elif perm_key == 'meal_count':
                    show_meal_count = role_permission.yes_no_permission
                elif perm_key == 'permissions':
                    show_permissions = role_permission.yes_no_permission
                elif perm_key == 'menu_rules':
                    show_menu_rules = role_permission.yes_no_permission
                elif perm_key == 'classroom_options':
                    show_classroom_options = role_permission.yes_no_permission
                elif perm_key == 'recipes':
                    show_recipes = role_permission.yes_no_permission
                elif perm_key == 'sign_in':
                    show_sign_in = role_permission.yes_no_permission
                elif perm_key == 'daily_attendance':
                    show_daily_attendance = role_permission.yes_no_permission
                elif perm_key == 'rosters':
                    show_rosters = role_permission.yes_no_permission
                elif perm_key == 'billing':
                    show_billing = role_permission.yes_no_permission
                elif perm_key == 'payment_setup':
                    show_payment_setup = role_permission.yes_no_permission
                elif perm_key == 'clock_in':
                    show_clock_in = role_permission.yes_no_permission 
            except RolePermission.DoesNotExist:
                continue

    except SubUser.DoesNotExist:
        # If the user is not a SubUser, default to no permissions (or set defaults as needed)
        pass

    # Render the index_director page without restricting access
    return render(request, 'index_free_user.html', {
        'show_weekly_menu': show_weekly_menu,
        'show_inventory': show_inventory,
        'show_milk_inventory': show_milk_inventory,
        'show_meal_count': show_meal_count,
        'show_classroom_options': show_classroom_options,
        'show_recipes': show_recipes,
        'show_sign_in': show_sign_in,
        'show_daily_attendance': show_daily_attendance,
        'show_rosters': show_rosters,
        'show_permissions': show_permissions,
        'show_menu_rules': show_menu_rules,
        'show_billing': show_billing,
        'show_payment_setup': show_payment_setup,
        'show_clock_in': show_clock_in, 
    })

@login_required
def recipes(request):
    allow_access = False
    show_weekly_menu = False
    show_inventory = False
    show_milk_inventory = False
    show_meal_count = False
    show_classroom_options = False
    show_recipes = False
    show_sign_in = False
    show_daily_attendance = False
    show_rosters = False
    show_permissions = False  
    show_menu_rules = False  
    show_billing = False          
    show_payment_setup = False
    show_clock_in = False

    try:
        # Check if the user is a SubUser
        sub_user = SubUser.objects.get(user=request.user)
        group_id = sub_user.group_id.id
        required_permission_id = 267  # Permission ID for accessing recipes view

        # Check if there is a RolePermission entry with 'yes_no_permission' set to True for this permission
        try:
            role_permission = RolePermission.objects.get(role_id=group_id, permission_id=required_permission_id)
            allow_access = role_permission.yes_no_permission
        except RolePermission.DoesNotExist:
            allow_access = False

        # Check additional permissions based on the same group_id
        permissions_ids = {
            'weekly_menu': 271,
            'inventory': 272,
            'milk_inventory': 270,
            'meal_count': 269,
            'classroom_options': 268,
            'recipes': 267,
            'sign_in': 273,
            'daily_attendance': 274,
            'rosters': 275,
            'permissions': 157, 
            'menu_rules': 266,
            'billing': 331,          
            'payment_setup': 332,   
            'clock_in': 337,
        }

        # Dynamically check each permission
        for perm_key, perm_id in permissions_ids.items():
            try:
                role_permission = RolePermission.objects.get(role_id=group_id, permission_id=perm_id)
                if perm_key == 'weekly_menu':
                    show_weekly_menu = role_permission.yes_no_permission
                elif perm_key == 'inventory':
                    show_inventory = role_permission.yes_no_permission
                elif perm_key == 'milk_inventory':
                    show_milk_inventory = role_permission.yes_no_permission
                elif perm_key == 'meal_count':
                    show_meal_count = role_permission.yes_no_permission
                elif perm_key == 'permissions':
                    show_permissions = role_permission.yes_no_permission
                elif perm_key == 'menu_rules':
                    show_menu_rules = role_permission.yes_no_permission
                elif perm_key == 'classroom_options':
                    show_classroom_options = role_permission.yes_no_permission
                elif perm_key == 'recipes':
                    show_recipes = role_permission.yes_no_permission
                elif perm_key == 'sign_in':
                    show_sign_in = role_permission.yes_no_permission
                elif perm_key == 'daily_attendance':
                    show_daily_attendance = role_permission.yes_no_permission
                elif perm_key == 'rosters':
                    show_rosters = role_permission.yes_no_permission
                elif perm_key == 'billing':
                    show_billing = role_permission.yes_no_permission
                elif perm_key == 'payment_setup':
                    show_payment_setup = role_permission.yes_no_permission
                elif perm_key == 'clock_in':
                    show_clock_in = role_permission.yes_no_permission 
            except RolePermission.DoesNotExist:
                continue  

    except SubUser.DoesNotExist:
        # If user is not a SubUser, grant access by default (assuming main user)
        allow_access = True
        show_weekly_menu = True
        show_inventory = True
        show_milk_inventory = True
        show_meal_count = True
        show_classroom_options = True
        show_recipes = True
        show_sign_in = True
        show_daily_attendance = True
        show_rosters = True
        show_permissions = True
        show_menu_rules = True
        show_billing = True
        show_payment_setup = True
        show_clock_in = True

    # Redirect to 'no_access' page if access is not allowed
    if not allow_access:
        return redirect('no_access')

    # If access is allowed, render the recipes page
    return render(request, 'recipes.html', {
        'show_weekly_menu': show_weekly_menu,
        'show_inventory': show_inventory,
        'show_milk_inventory': show_milk_inventory,
        'show_meal_count': show_meal_count,
        'show_classroom_options': show_classroom_options,
        'show_recipes': show_recipes,
        'show_sign_in': show_sign_in,
        'show_daily_attendance': show_daily_attendance,
        'show_rosters': show_rosters,
        'show_permissions': show_permissions,
        'show_menu_rules': show_menu_rules,
        'show_billing': show_billing,            
        'show_payment_setup': show_payment_setup,
        'show_clock_in': show_clock_in,
    })

@login_required
def menu(request):
    
    # Detect if the request is from a mobile device
    is_mobile = any(device in request.META.get('HTTP_USER_AGENT', '').lower() for device in [
        'iphone', 'android', 'mobile', 'cordova', 'tablet', 'ipod', 'windows phone'
    ])
    
    # If it's a mobile request, redirect to the app_redirect page
    if is_mobile:
        return HttpResponseRedirect(reverse('app_redirect'))  # Ensure 'app_redirect' is defined in your URLs

    allow_access = False
    show_weekly_menu = False
    show_inventory = False
    show_milk_inventory = False
    show_meal_count = False
    show_classroom_options = False
    show_recipes = False
    show_sign_in = False
    show_daily_attendance = False
    show_rosters = False
    show_permissions = False  
    show_menu_rules = False   
    show_billing = False          
    show_payment_setup = False
    show_clock_in = False

    try:
        # Check if the user is a SubUser
        sub_user = SubUser.objects.get(user=request.user)
        group_id = sub_user.group_id.id
        required_permission_id = 271  # Permission ID for menu view

        # Check if there is a RolePermission entry with 'yes_no_permission' set to True for this permission
        try:
            role_permission = RolePermission.objects.get(role_id=group_id, permission_id=required_permission_id)
            allow_access = role_permission.yes_no_permission
        except RolePermission.DoesNotExist:
            allow_access = False  # No specific permission set for this role

        permissions_ids = {
            'weekly_menu': 271,
            'inventory': 272,
            'milk_inventory': 270,
            'meal_count': 269,
            'classroom_options': 268,
            'recipes': 267,
            'sign_in': 273,
            'daily_attendance': 274,
            'rosters': 275,
            'permissions': 157, 
            'menu_rules': 266,
            'billing': 331,          
            'payment_setup': 332, 
            'clock_in': 337,  
        }

        # Dynamically check each permission
        for perm_key, perm_id in permissions_ids.items():
            try:
                role_permission = RolePermission.objects.get(role_id=group_id, permission_id=perm_id)
                if perm_key == 'weekly_menu':
                    show_weekly_menu = role_permission.yes_no_permission
                elif perm_key == 'inventory':
                    show_inventory = role_permission.yes_no_permission
                elif perm_key == 'milk_inventory':
                    show_milk_inventory = role_permission.yes_no_permission
                elif perm_key == 'meal_count':
                    show_meal_count = role_permission.yes_no_permission
                elif perm_key == 'permissions':
                    show_permissions = role_permission.yes_no_permission
                elif perm_key == 'menu_rules':
                    show_menu_rules = role_permission.yes_no_permission
                elif perm_key == 'classroom_options':
                    show_classroom_options = role_permission.yes_no_permission
                elif perm_key == 'recipes':
                    show_recipes = role_permission.yes_no_permission
                elif perm_key == 'sign_in':
                    show_sign_in = role_permission.yes_no_permission
                elif perm_key == 'daily_attendance':
                    show_daily_attendance = role_permission.yes_no_permission
                elif perm_key == 'rosters':
                    show_rosters = role_permission.yes_no_permission
                elif perm_key == 'billing':
                    show_billing = role_permission.yes_no_permission
                elif perm_key == 'payment_setup':
                    show_payment_setup = role_permission.yes_no_permission
                elif perm_key == 'clock_in':
                    show_clock_in = role_permission.yes_no_permission  
            except RolePermission.DoesNotExist:
                continue  

    except SubUser.DoesNotExist:
        # If user is not a SubUser, grant access by default (assuming main user)
        allow_access = True
        show_weekly_menu = True
        show_inventory = True
        show_milk_inventory = True
        show_meal_count = True
        show_classroom_options = True
        show_recipes = True
        show_sign_in = True
        show_daily_attendance = True
        show_rosters = True
        show_permissions = True
        show_menu_rules = True
        show_billing = True
        show_payment_setup = True
        show_clock_in = True


    # Redirect to 'no_access' page if access is not allowed
    if not allow_access:
        return redirect('no_access')

    # If access is allowed, proceed with rendering the menu
    context = {
        'show_weekly_menu': show_weekly_menu,
        'show_inventory': show_inventory,
        'show_milk_inventory': show_milk_inventory,
        'show_meal_count': show_meal_count,
        'show_classroom_options': show_classroom_options,
        'show_recipes': show_recipes,
        'show_sign_in': show_sign_in,
        'show_daily_attendance': show_daily_attendance,
        'show_rosters': show_rosters,
        'show_permissions': show_permissions,
        'show_menu_rules': show_menu_rules,
        'show_billing': show_billing,            
        'show_payment_setup': show_payment_setup,
        'show_clock_in': show_clock_in, 
    }

    return render(request, 'weekly-menu.html', context)

@login_required
def account_settings(request):
    success_message = ""
    allow_access = True

    # Initialize permission flags
    show_weekly_menu = False
    show_inventory = False
    show_milk_inventory = False
    show_meal_count = False
    show_classroom_options = False
    show_recipes = False
    show_sign_in = False
    show_daily_attendance = False
    show_rosters = False
    show_permissions = False  
    show_menu_rules = False  
    show_billing = False          
    show_payment_setup = False
    show_clock_in = False

    sub_user = None

    try:
        sub_user = SubUser.objects.get(user=request.user)
        group_id = sub_user.group_id.id

        permissions_ids = {
            'weekly_menu': 271,
            'inventory': 272,
            'milk_inventory': 270,
            'meal_count': 269,
            'classroom_options': 268,
            'recipes': 267,
            'sign_in': 273,
            'daily_attendance': 274,
            'rosters': 275,
            'permissions': 157, 
            'menu_rules': 266,
            'billing': 331,          
            'payment_setup': 332,   
            'clock_in': 337,
        }

        for perm_key, perm_id in permissions_ids.items():
            try:
                role_permission = RolePermission.objects.get(role_id=group_id, permission_id=perm_id)
                if perm_key == 'weekly_menu':
                    show_weekly_menu = role_permission.yes_no_permission
                elif perm_key == 'inventory':
                    show_inventory = role_permission.yes_no_permission
                elif perm_key == 'milk_inventory':
                    show_milk_inventory = role_permission.yes_no_permission
                elif perm_key == 'meal_count':
                    show_meal_count = role_permission.yes_no_permission
                elif perm_key == 'permissions':
                    show_permissions = role_permission.yes_no_permission
                elif perm_key == 'menu_rules':
                    show_menu_rules = role_permission.yes_no_permission
                elif perm_key == 'classroom_options':
                    show_classroom_options = role_permission.yes_no_permission
                elif perm_key == 'recipes':
                    show_recipes = role_permission.yes_no_permission
                elif perm_key == 'sign_in':
                    show_sign_in = role_permission.yes_no_permission
                elif perm_key == 'daily_attendance':
                    show_daily_attendance = role_permission.yes_no_permission
                elif perm_key == 'rosters':
                    show_rosters = role_permission.yes_no_permission
                elif perm_key == 'billing':
                    show_billing = role_permission.yes_no_permission
                elif perm_key == 'payment_setup':
                    show_payment_setup = role_permission.yes_no_permission
                elif perm_key == 'clock_in':
                    show_clock_in = role_permission.yes_no_permission
            except RolePermission.DoesNotExist:
                continue
    except SubUser.DoesNotExist:
        # Grant full access if not a SubUser
        allow_access = True
        show_weekly_menu = True
        show_inventory = True
        show_milk_inventory = True
        show_meal_count = True
        show_classroom_options = True
        show_recipes = True
        show_sign_in = True
        show_daily_attendance = True
        show_rosters = True
        show_permissions = True
        show_menu_rules = True
        show_billing = True
        show_payment_setup = True
        show_clock_in = True

    if not allow_access:
        return redirect('no_access')

    if sub_user and sub_user.main_user.stripe_secret_key:
        stripe.api_key = sub_user.main_user.stripe_secret_key
    else:
        stripe.api_key = settings.STRIPE_SECRET_KEY

    print("Stripe API Key:", stripe.api_key)  # Debug log

    # Process wallet deposit if POST
    if request.method == "POST":
        try:
            amount = float(request.POST.get("amount", 0))
        except (TypeError, ValueError):
            return JsonResponse({'error': 'Invalid deposit amount.'}, status=400)

        payment_method = request.POST.get("payment_method")
        if amount <= 0:
            return JsonResponse({'error': 'Deposit amount must be positive.'}, status=400)
        
        # For cash or check, update the wallet balance directly
        if payment_method in ["cash", "check"]:
            sub_user.balance += Decimal(amount)
            sub_user.save()
            return JsonResponse({
                'success': f"${amount} deposited successfully.",
                'new_balance': str(sub_user.balance)
            })
        else:
            # For card payments, create a Stripe PaymentIntent
            try:
                payment_intent = stripe.PaymentIntent.create(
                    amount = int(amount * 100),  # Convert dollars to cents
                    currency = "usd",
                    description = f"Wallet deposit for {request.user.username}",
                    receipt_email = request.user.email,
                )
                return JsonResponse({'client_secret': payment_intent['client_secret']})
            except Exception as e:
                return JsonResponse({'error': str(e)}, status=400)
        print("Stripe API Key:", stripe.api_key)

    return render(request, 'account_settings.html', {
        'show_weekly_menu': show_weekly_menu,
        'show_inventory': show_inventory,
        'show_milk_inventory': show_milk_inventory,
        'show_meal_count': show_meal_count,
        'show_classroom_options': show_classroom_options,
        'show_recipes': show_recipes,
        'show_sign_in': show_sign_in,
        'show_daily_attendance': show_daily_attendance,
        'show_rosters': show_rosters,
        'show_permissions': show_permissions,
        'show_menu_rules': show_menu_rules,
        'sub_user': sub_user,
        'show_billing': show_billing,
        'show_payment_setup': show_payment_setup,
        'show_clock_in': show_clock_in,
        'stripe_public_key': getattr(sub_user.main_user, 'stripe_public_key', settings.STRIPE_PUBLIC_KEY) if sub_user else settings.STRIPE_PUBLIC_KEY,
    })

@login_required
def menu_rules(request):
    allow_access = False
    show_weekly_menu = False
    show_inventory = False
    show_milk_inventory = False
    show_meal_count = False
    show_classroom_options = False
    show_recipes = False
    show_sign_in = False
    show_daily_attendance = False
    show_rosters = False
    show_permissions = False  
    show_menu_rules = False  
    show_billing = False          
    show_payment_setup = False
    show_clock_in = False

    try:
        # Check if the user is a SubUser
        sub_user = SubUser.objects.get(user=request.user)
        group_id = sub_user.group_id.id
        required_permission_id = 266  # Permission ID for accessing menu_rules view

        # Check if there is a RolePermission entry with 'yes_no_permission' set to True for this permission
        try:
            role_permission = RolePermission.objects.get(role_id=group_id, permission_id=required_permission_id)
            allow_access = role_permission.yes_no_permission
        except RolePermission.DoesNotExist:
            allow_access = False

        permissions_ids = {
            'weekly_menu': 271,
            'inventory': 272,
            'milk_inventory': 270,
            'meal_count': 269,
            'classroom_options': 268,
            'recipes': 267,
            'sign_in': 273,
            'daily_attendance': 274,
            'rosters': 275,
            'permissions': 157, 
            'menu_rules': 266,
            'billing': 331,          
            'payment_setup': 332,   
            'clock_in': 337,
        }

        # Dynamically check each permission
        for perm_key, perm_id in permissions_ids.items():
            try:
                role_permission = RolePermission.objects.get(role_id=group_id, permission_id=perm_id)
                if perm_key == 'weekly_menu':
                    show_weekly_menu = role_permission.yes_no_permission
                elif perm_key == 'inventory':
                    show_inventory = role_permission.yes_no_permission
                elif perm_key == 'milk_inventory':
                    show_milk_inventory = role_permission.yes_no_permission
                elif perm_key == 'meal_count':
                    show_meal_count = role_permission.yes_no_permission
                elif perm_key == 'permissions':
                    show_permissions = role_permission.yes_no_permission
                elif perm_key == 'menu_rules':
                    show_menu_rules = role_permission.yes_no_permission
                elif perm_key == 'classroom_options':
                    show_classroom_options = role_permission.yes_no_permission
                elif perm_key == 'recipes':
                    show_recipes = role_permission.yes_no_permission
                elif perm_key == 'sign_in':
                    show_sign_in = role_permission.yes_no_permission
                elif perm_key == 'daily_attendance':
                    show_daily_attendance = role_permission.yes_no_permission
                elif perm_key == 'rosters':
                    show_rosters = role_permission.yes_no_permission
                elif perm_key == 'billing':
                    show_billing = role_permission.yes_no_permission
                elif perm_key == 'payment_setup':
                    show_payment_setup = role_permission.yes_no_permission
                elif perm_key == 'clock_in':
                    show_clock_in = role_permission.yes_no_permission  
            except RolePermission.DoesNotExist:
                continue  

    except SubUser.DoesNotExist:
        # If user is not a SubUser, grant access by default (assuming main user)
        allow_access = True
        show_weekly_menu = True
        show_inventory = True
        show_milk_inventory = True
        show_meal_count = True
        show_classroom_options = True
        show_recipes = True
        show_sign_in = True
        show_daily_attendance = True
        show_rosters = True
        show_permissions = True
        show_menu_rules = True
        show_billing = True
        show_payment_setup = True
        show_clock_in = True

    # Redirect to 'no_access' page if access is not allowed
    if not allow_access:
        return redirect('no_access')

    # If access is allowed, proceed with the usual view logic
    form = RuleForm()
    rules = Rule.objects.all()  # Query all rules from the database
    return render(request, 'menu_rules.html', {
        'form': form,
        'rules': rules,
        'show_weekly_menu': show_weekly_menu,
        'show_inventory': show_inventory,
        'show_milk_inventory': show_milk_inventory,
        'show_meal_count': show_meal_count,
        'show_classroom_options': show_classroom_options,
        'show_recipes': show_recipes,
        'show_sign_in': show_sign_in,
        'show_daily_attendance': show_daily_attendance,
        'show_rosters': show_rosters,
        'show_permissions': show_permissions,  # Corrected variable name
        'show_menu_rules': show_menu_rules,
        'show_billing': show_billing,            
        'show_payment_setup': show_payment_setup,
        'show_clock_in': show_clock_in,
    })

@login_required
def add_rule(request):
    if request.method == 'POST':
        form = RuleForm(request.POST)
        if form.is_valid():
            # Get the main user (either the logged-in user or the linked main user if they are a subuser)
            user = get_user_for_view(request)
            
            # Assign the main user to the rule before saving
            rule = form.save(commit=False)
            rule.user = user
            rule.save()
            
            return redirect('menu_rules')
    
    return redirect('menu_rules')

def error401(request):
    return render(request, '401.html')

def error404(request):
    return render(request, '404.html')

def error500(request):
    return render(request, '500.html')

def user_signup(request):
    if request.method == 'POST':
        form = SignupForm(request.POST)
        if form.is_valid():
            # Save the auth_user instance
            user = form.save()
            
           
            # Log in the user and redirect
            login(request, user)
            return redirect('login')  # Replace with the name of the view to redirect after signup
    else:
        form = SignupForm()
    return render(request, 'signup.html', {'form': form})

def user_login(request):
    if request.method == 'POST':
        form = LoginForm(request.POST)
        if form.is_valid():
            username = form.cleaned_data['username']
            password = form.cleaned_data['password']
            user = authenticate(request, username=username, password=password)
            if user is not None:
                login(request, user)
                return redirect('index')  # Redirect to the index page on successful login
            else:
                # If authentication fails, add an error message to the request
                messages.error(request, "Invalid username or password.")
        else:
            messages.error(request, "Please correct the errors below.")
    else:
        form = LoginForm()

    # Render the login template with the form
    return render(request, 'login.html', {'form': form})
    
def logout_view(request):
    logout(request)
    # Redirect to the homepage or any other desired page
    return redirect('index')

@login_required
def inventory_list(request):
    allow_access = False

    show_weekly_menu = False
    show_inventory = False
    show_milk_inventory = False
    show_meal_count = False
    show_classroom_options = False
    show_recipes = False
    show_sign_in = False
    show_daily_attendance = False
    show_rosters = False
    show_permissions = False  
    show_menu_rules = False   
    show_billing = False          
    show_payment_setup = False
    show_clock_in = False

    try:
        # Check if the user is a SubUser
        sub_user = SubUser.objects.get(user=request.user)
        group_id = sub_user.group_id.id
        required_permission_id = 272  # Permission ID for inventory_list view

        # Check if there is a RolePermission entry with 'yes_no_permission' set to True for this permission
        try:
            role_permission = RolePermission.objects.get(role_id=group_id, permission_id=required_permission_id)
            allow_access = role_permission.yes_no_permission
        except RolePermission.DoesNotExist:
            allow_access = False  # No specific permission set for this role

        permissions_ids = {
            'weekly_menu': 271,
            'inventory': 272,
            'milk_inventory': 270,
            'meal_count': 269,
            'classroom_options': 268,
            'recipes': 267,
            'sign_in': 273,
            'daily_attendance': 274,
            'rosters': 275,
            'permissions': 157, 
            'menu_rules': 266,
            'billing': 331,          
            'payment_setup': 332,
            'clock_in': 337,   
        }

        # Dynamically check each permission
        for perm_key, perm_id in permissions_ids.items():
            try:
                role_permission = RolePermission.objects.get(role_id=group_id, permission_id=perm_id)
                if perm_key == 'weekly_menu':
                    show_weekly_menu = role_permission.yes_no_permission
                elif perm_key == 'inventory':
                    show_inventory = role_permission.yes_no_permission
                elif perm_key == 'milk_inventory':
                    show_milk_inventory = role_permission.yes_no_permission
                elif perm_key == 'meal_count':
                    show_meal_count = role_permission.yes_no_permission
                elif perm_key == 'permissions':
                    show_permissions = role_permission.yes_no_permission
                elif perm_key == 'menu_rules':
                    show_menu_rules = role_permission.yes_no_permission
                elif perm_key == 'classroom_options':
                    show_classroom_options = role_permission.yes_no_permission
                elif perm_key == 'recipes':
                    show_recipes = role_permission.yes_no_permission
                elif perm_key == 'sign_in':
                    show_sign_in = role_permission.yes_no_permission
                elif perm_key == 'daily_attendance':
                    show_daily_attendance = role_permission.yes_no_permission
                elif perm_key == 'rosters':
                    show_rosters = role_permission.yes_no_permission
                elif perm_key == 'billing':
                    show_billing = role_permission.yes_no_permission
                elif perm_key == 'payment_setup':
                    show_payment_setup = role_permission.yes_no_permission
                elif perm_key == 'clock_in':
                    show_clock_in = role_permission.yes_no_permission
            except RolePermission.DoesNotExist:
                continue  

    except SubUser.DoesNotExist:
        # If user is not a SubUser, grant access by default (assuming main user)
        allow_access = True
        show_weekly_menu = True
        show_inventory = True
        show_milk_inventory = True
        show_meal_count = True
        show_classroom_options = True
        show_recipes = True
        show_sign_in = True
        show_daily_attendance = True
        show_rosters = True
        show_permissions = True
        show_menu_rules = True
        show_billing = True
        show_payment_setup = True
        show_clock_in = True

    # Redirect to 'no_access' page if access is not allowed
    if not allow_access:
        return redirect('no_access')

    # Get the user (MainUser) for filtering
    user = get_user_for_view(request)

    # Retrieve inventory data for the user
    inventory_items = Inventory.objects.filter(user_id=user.id)

    # Get unique categories for filtering options
    categories = Inventory.objects.filter(user_id=user.id).values_list('category', flat=True).distinct()

    # Filter by category if selected
    category_filter = request.GET.get('category')
    if category_filter:
        inventory_items = inventory_items.filter(category=category_filter)

    # Retrieve rules from the Rule model
    rules = Rule.objects.all()

    return render(request, 'inventory_list.html', {
        'inventory_items': inventory_items,
        'categories': categories,
        'rules': rules,
        'show_weekly_menu': show_weekly_menu,
        'show_inventory': show_inventory,
        'show_milk_inventory': show_milk_inventory,
        'show_meal_count': show_meal_count,
        'show_classroom_options': show_classroom_options,
        'show_recipes': show_recipes,
        'show_sign_in': show_sign_in,
        'show_daily_attendance': show_daily_attendance,
        'show_rosters': show_rosters,
        'show_permissions': show_permissions,
        'show_menu_rules': show_menu_rules,
        'show_billing': show_billing,            
        'show_payment_setup': show_payment_setup,
        'show_clock_in': show_clock_in,
    })


@login_required
def add_item(request):
    if request.method == 'POST':
        item = request.POST.get('item')
        category = request.POST.get('category')
        quantity = request.POST.get('quantity')
        resupply = request.POST.get('resupply')
        units = request.POST.get('units')  # Capture the user's input

        rule_id = request.POST.get('rule')  # Get the rule value from the form
        rule = get_object_or_404(Rule, id=rule_id) if rule_id else None

        # Get the main user (either the logged-in user or the main user if they are a subuser)
        user = get_user_for_view(request)

        # Create the inventory item for the main user
        Inventory.objects.create(
            user_id=user.id,
            item=item,
            category=category,
            quantity=quantity,
            resupply=resupply,
            rule=rule,
            units=units
        )
        
        # Redirect to the inventory list after adding the item
        return redirect('inventory_list')
    else:
        return render(request, 'inventory_list.html')

@login_required
def edit_quantity(request, item_id):
    if request.method == 'POST':
        new_quantity = request.POST.get('new_quantity')
        try:
            item = Inventory.objects.get(pk=item_id)
            item.quantity = new_quantity
            item.save()
            return redirect('inventory_list')  # Redirect to the inventory list after successful edit
        except Inventory.DoesNotExist:
            return HttpResponseBadRequest("Item does not exist")
    else:
        return HttpResponseBadRequest("Invalid request method")
    
def remove_item(request, item_id):
    # Retrieve the inventory item to be removed
    inventory_item = get_object_or_404(Inventory, pk=item_id)
    # Perform the deletion
    inventory_item.delete()
    # Redirect back to the inventory list page
    return redirect('inventory_list')

def get_out_of_stock_items(request):
    user = get_user_for_view(request)
    out_of_stock_items = Inventory.objects.filter(user=user,quantity=0)
    data = [{'name': item.item} for item in out_of_stock_items]
    return JsonResponse(data, safe=False)

def order_soon_items_view(request):
    user = get_user_for_view(request)
    order_soon_items = Inventory.objects.filter(user=user, quantity__lt=F('resupply'), quantity__gt=0)

    # Convert queryset to a list of dictionaries containing item names
    order_soon_items_data = [{'name': item.item} for item in order_soon_items]

    # Return the items as a JSON response
    return JsonResponse(order_soon_items_data, safe=False)

def fetch_ingredients(request):
    user = get_user_for_view(request)
    ingredients = Inventory.objects.filter(user_id=user.id).values('id', 'item')
    return JsonResponse({'ingredients': list(ingredients)})

@login_required
def create_recipe(request):
    if request.method == 'POST':
        # Extract form data
        recipe_name = request.POST.get('mealName')
        main_ingredient_ids = [
            request.POST.get('mainIngredient1'),
            request.POST.get('mainIngredient2'),
            request.POST.get('mainIngredient3'),
            request.POST.get('mainIngredient4'),
            request.POST.get('mainIngredient5')
        ]
        quantities = [
            request.POST.get('qtyMainIngredient1'),
            request.POST.get('qtyMainIngredient2'),
            request.POST.get('qtyMainIngredient3'),
            request.POST.get('qtyMainIngredient4'),
            request.POST.get('qtyMainIngredient5')
        ]
        instructions = request.POST.get('instructions')
        grain = request.POST.get('grain')
        meat_alternate = request.POST.get('meatAlternate')
        rule_id = request.POST.get('rule')  # Extract rule from form data

        # Use get_user_for_view to get the main user (either logged-in user or main user if subuser)
        user = get_user_for_view(request)

        # Get the rule object if rule_id is provided
        rule = get_object_or_404(Rule, id=rule_id) if rule_id else None

        # Create recipe instance
        recipe = Recipe.objects.create(
            user=user,
            name=recipe_name,
            instructions=instructions,
            grain=grain,
            meat_alternate=meat_alternate,
            rule=rule  # Set rule
        )

        # Save main ingredients and their quantities to the recipe
        for index, (ingredient_id, quantity) in enumerate(zip(main_ingredient_ids, quantities), start=1):
            if ingredient_id and quantity:
                ingredient = get_object_or_404(Inventory, id=ingredient_id)
                setattr(recipe, f'ingredient{index}', ingredient)
                setattr(recipe, f'qty{index}', quantity)
        recipe.save()

        return JsonResponse({'success': True})
    else:
        return JsonResponse({'error': 'Method not allowed'}, status=405)


@login_required
def create_fruit_recipe(request):
    if request.method == 'POST':
        # Extract form data
        recipe_name = request.POST.get('fruitName')
        ingredient_id = request.POST.get('fruitMainIngredient1')
        quantity = request.POST.get('fruitQtyMainIngredient1')
        rule_id = request.POST.get('fruitRule')

        # Validate form data
        if not recipe_name:
            return JsonResponse({'error': 'Recipe name is required'}, status=400)
        if not ingredient_id:
            return JsonResponse({'error': 'Main ingredient is required'}, status=400)
        if not quantity:
            return JsonResponse({'error': 'Quantity is required'}, status=400)
        if not rule_id:
            return JsonResponse({'error': 'Rule is required'}, status=400)

        # Use get_user_for_view to get the main user (either logged-in user or main user if subuser)
        user = get_user_for_view(request)

        # Get the rule object if rule_id is provided
        rule = get_object_or_404(Rule, id=rule_id) if rule_id else None

        # Create fruit recipe instance
        fruit_recipe = FruitRecipe.objects.create(
            user=user,
            name=recipe_name,
            rule=rule
        )

        # Save the ingredient and its quantity to the fruit recipe
        if ingredient_id and quantity:
            ingredient = get_object_or_404(Inventory, id=ingredient_id)
            fruit_recipe.ingredient1 = ingredient
            fruit_recipe.qty1 = quantity
        fruit_recipe.save()

        return JsonResponse({'success': True})
    else:
        return JsonResponse({'error': 'Method not allowed'}, status=405)

@login_required
def create_veg_recipe(request):
    if request.method == 'POST':
        # Extract form data
        recipe_name = request.POST.get('vegName')
        ingredient_id = request.POST.get('vegMainIngredient1')
        quantity = request.POST.get('vegQtyMainIngredient1')
        rule_id = request.POST.get('vegRule')

        # Validate form data
        if not recipe_name:
            return JsonResponse({'error': 'Recipe name is required'}, status=400)
        if not ingredient_id:
            return JsonResponse({'error': 'Main ingredient is required'}, status=400)
        if not quantity:
            return JsonResponse({'error': 'Quantity is required'}, status=400)
        if not rule_id:
            return JsonResponse({'error': 'Rule is required'}, status=400)

        # Use get_user_for_view to determine the main user (current user or main user if subuser)
        user = get_user_for_view(request)

        # Get the rule object if rule_id is provided
        rule = get_object_or_404(Rule, id=rule_id) if rule_id else None

        # Create vegetable recipe instance
        veg_recipe = VegRecipe.objects.create(
            user=user,
            name=recipe_name,
            rule=rule
        )

        # Save the ingredient and its quantity to the vegetable recipe
        if ingredient_id and quantity:
            ingredient = get_object_or_404(Inventory, id=ingredient_id)
            veg_recipe.ingredient1 = ingredient
            veg_recipe.qty1 = quantity
        veg_recipe.save()

        return JsonResponse({'success': True})
    else:
        return JsonResponse({'error': 'Method not allowed'}, status=405)

@login_required
def create_wg_recipe(request):
    if request.method == 'POST':
        # Extract form data
        recipe_name = request.POST.get('wgName')
        ingredient_id = request.POST.get('wgMainIngredient1')
        quantity = request.POST.get('wgQtyMainIngredient1')
        rule_id = request.POST.get('wgRule')

        # Validate form data
        if not recipe_name:
            return JsonResponse({'error': 'Recipe name is required'}, status=400)
        if not ingredient_id:
            return JsonResponse({'error': 'Main ingredient is required'}, status=400)
        if not quantity:
            return JsonResponse({'error': 'Quantity is required'}, status=400)
        if not rule_id:
            return JsonResponse({'error': 'Rule is required'}, status=400)

        # Use get_user_for_view to determine the main user (either the current user or main user if subuser)
        user = get_user_for_view(request)

        # Get the rule object if rule_id is provided
        rule = get_object_or_404(Rule, id=rule_id) if rule_id else None

        # Create WG recipe instance
        wg_recipe = WgRecipe.objects.create(
            user=user,
            name=recipe_name,
            rule=rule
        )

        # Save the ingredient and its quantity to the WG recipe
        if ingredient_id and quantity:
            ingredient = get_object_or_404(Inventory, id=ingredient_id)
            wg_recipe.ingredient1 = ingredient
            wg_recipe.qty1 = quantity
        wg_recipe.save()

        return JsonResponse({'success': True})
    else:
        return JsonResponse({'error': 'Method not allowed'}, status=405)

@login_required
def create_breakfast_recipe(request):
    if request.method == 'POST':
        # Extract form data
        recipe_name = request.POST.get('breakfastMealName')
        main_ingredient_ids = [
            request.POST.get('breakfastMainIngredient1'),
            request.POST.get('breakfastMainIngredient2'),
            request.POST.get('breakfastMainIngredient3'),
            request.POST.get('breakfastMainIngredient4'),
            request.POST.get('breakfastMainIngredient5')
        ]
        quantities = [
            request.POST.get('breakfastQtyMainIngredient1'),
            request.POST.get('breakfastQtyMainIngredient2'),
            request.POST.get('breakfastQtyMainIngredient3'),
            request.POST.get('breakfastQtyMainIngredient4'),
            request.POST.get('breakfastQtyMainIngredient5')
        ]
        instructions = request.POST.get('breakfastInstructions')
        additional_food = request.POST.get('additionalFood')
        rule_id = request.POST.get('breakfastRule')  # Extract rule from form data

        # Use get_user_for_view to get the correct user (main user or subuser)
        user = get_user_for_view(request)

        rule = Rule.objects.get(id=rule_id) if rule_id else None
        # Create breakfast recipe instance
        breakfast_recipe = BreakfastRecipe.objects.create(
            user=user,
            name=recipe_name,
            instructions=instructions,
            addfood=additional_food,
            rule=rule
        )

        # Save main ingredients and their quantities to the breakfast recipe
        for ingredient_id, quantity in zip(main_ingredient_ids, quantities):
            if ingredient_id and quantity:
                ingredient = Inventory.objects.get(id=ingredient_id)
                # Assign main ingredients and their quantities directly to the breakfast recipe instance
                setattr(breakfast_recipe, f'ingredient{main_ingredient_ids.index(ingredient_id) + 1}', ingredient)
                setattr(breakfast_recipe, f'qty{main_ingredient_ids.index(ingredient_id) + 1}', quantity)

        breakfast_recipe.save()  # Save the changes to the database

        return JsonResponse({'success': True})  # Or return any relevant data
    else:
        # If the request method is not POST, return error response
        return JsonResponse({'error': 'Method not allowed'}, status=405)

@login_required
def create_am_recipe(request):
    if request.method == 'POST':
        # Extract form data
        recipe_name = request.POST.get('amRecipeName')
        main_ingredient_ids = [
            request.POST.get('amIngredient1'),
            request.POST.get('amIngredient2'),
            request.POST.get('amIngredient3'),
            request.POST.get('amIngredient4'),
            request.POST.get('amIngredient5')
        ]
        quantities = [
            request.POST.get('amQty1'),
            request.POST.get('amQty2'),
            request.POST.get('amQty3'),
            request.POST.get('amQty4'),
            request.POST.get('amQty5')
        ]
        instructions = request.POST.get('amInstructions')
        fluid = request.POST.get('amFluid')
        fruit_veg = request.POST.get('amFruitVeg')
        meat = request.POST.get('amMeat')
        rule_id = request.POST.get('amRule')  # Extract rule from form data

        # Use get_user_for_view to get the correct user (main user or subuser)
        user = get_user_for_view(request)

        rule = Rule.objects.get(id=rule_id) if rule_id else None

        # Create AM recipe instance
        am_recipe = AMRecipe.objects.create(
            user=user,
            name=recipe_name,
            instructions=instructions,
            fluid=fluid,
            fruit_veg=fruit_veg,
            meat=meat,
            rule=rule  # Set rule
        )

        # Save main ingredients and their quantities to the AM recipe
        for ingredient_id, quantity in zip(main_ingredient_ids, quantities):
            if ingredient_id and quantity:
                ingredient = Inventory.objects.get(id=ingredient_id)
                # Assign main ingredients and their quantities directly to the AM recipe instance
                setattr(am_recipe, f'ingredient{main_ingredient_ids.index(ingredient_id) + 1}', ingredient)
                setattr(am_recipe, f'qty{main_ingredient_ids.index(ingredient_id) + 1}', quantity)

        am_recipe.save()  # Save the changes to the database

        return JsonResponse({'success': True})  # Or return any relevant data
    else:
        # If the request method is not POST, return error response
        return JsonResponse({'error': 'Method not allowed'}, status=405)

@login_required
def create_pm_recipe(request):
    if request.method == 'POST':
        # Extract form data
        recipe_name = request.POST.get('pmRecipeName')
        main_ingredient_ids = [
            request.POST.get('pmIngredient1'),
            request.POST.get('pmIngredient2'),
            request.POST.get('pmIngredient3'),
            request.POST.get('pmIngredient4'),
            request.POST.get('pmIngredient5')
        ]
        quantities = [
            request.POST.get('pmQty1'),
            request.POST.get('pmQty2'),
            request.POST.get('pmQty3'),
            request.POST.get('pmQty4'),
            request.POST.get('pmQty5')
        ]
        instructions = request.POST.get('pmInstructions')
        fluid = request.POST.get('pmFluid')
        fruit_veg = request.POST.get('pmFruitVeg')
        meat = request.POST.get('pmMeat')
        rule_id = request.POST.get('pmRule')

        # Use get_user_for_view to get the correct user (main user or subuser)
        user = get_user_for_view(request)

        rule = Rule.objects.get(id=rule_id) if rule_id else None

        # Create PM recipe instance
        pm_recipe = PMRecipe.objects.create(
            user=user,
            name=recipe_name,
            instructions=instructions,
            fluid=fluid,
            fruit_veg=fruit_veg,
            meat=meat,
            rule=rule  # Set rule
        )

        # Save main ingredients and their quantities to the PM recipe
        for ingredient_id, quantity in zip(main_ingredient_ids, quantities):
            if ingredient_id and quantity:
                ingredient = Inventory.objects.get(id=ingredient_id)
                # Assign main ingredients and their quantities directly to the PM recipe instance
                setattr(pm_recipe, f'ingredient{main_ingredient_ids.index(ingredient_id) + 1}', ingredient)
                setattr(pm_recipe, f'qty{main_ingredient_ids.index(ingredient_id) + 1}', quantity)

        pm_recipe.save()  # Save the changes to the database

        return JsonResponse({'success': True})  # Or return any relevant data
    else:
        # If the request method is not POST, return error response
        return JsonResponse({'error': 'Method not allowed'}, status=405)

def fetch_recipes(request):
    # Use get_user_for_view to get the correct user (main user or subuser)
    user = get_user_for_view(request)

    # Retrieve all recipes from the database for the identified user
    recipes = Recipe.objects.filter(user=user).values('id', 'name')  
    return JsonResponse({'recipes': list(recipes)})

@login_required
def fetch_rules(request):
    rules = Rule.objects.all()
    rule_list = [{'id': rule.id, 'rule': rule.rule} for rule in rules]
    return JsonResponse({'rules': rule_list})
    
def get_inventory_items(request):
    # Fetch inventory items
    inventory_items = Inventory.objects.all().values_list('item', flat=True)
    
    # Serialize inventory items into JSON format
    inventory_items_list = list(inventory_items)
    
    # Return JSON response
    return JsonResponse(inventory_items_list, safe=False)
 
def get_recipe(request, recipe_id):
    # Retrieve the recipe from the database
    recipe = get_object_or_404(Recipe, pk=recipe_id)
    
    # Serialize the recipe data (convert it to JSON format)
    recipe_data = {
        'id': recipe.id,
        'name': recipe.name,
        'instructions': recipe.instructions,
        'grain': recipe.grain,  # Include 'grain' field
        'meat_alternate': recipe.meat_alternate, 
    }
    
    # Return the recipe data as a JSON response
    return JsonResponse({'recipe': recipe_data})

@login_required
def fetch_veg_recipes(request):
    user = get_user_for_view(request)
    veg_recipes = VegRecipe.objects.filter(user=user).values('id', 'name')
    return JsonResponse({'recipes': list(veg_recipes)})

@login_required
def fetch_wg_recipes(request):
    user = get_user_for_view(request)
    wg_recipes = WgRecipe.objects.filter(user=user).values('id', 'name')
    return JsonResponse({'recipes': list(wg_recipes)})

def fetch_fruit_recipes(request):
    user = get_user_for_view(request)
    fruit_recipes = FruitRecipe.objects.filter(user=user).values('id', 'name')
    return JsonResponse({'recipes': list(fruit_recipes)})

def fetch_breakfast_recipes(request):
    user = get_user_for_view(request)
    breakfast_recipes = BreakfastRecipe.objects.filter(user=user).values('id', 'name')
    return JsonResponse({'recipes': list(breakfast_recipes)})

def fetch_am_recipes(request):
    user = get_user_for_view(request)
    am_recipes = AMRecipe.objects.filter(user=user).values('id', 'name')  
    return JsonResponse({'am_recipes': list(am_recipes)})

def fetch_pm_recipes(request):
    user = get_user_for_view(request)
    am_recipes = PMRecipe.objects.filter(user=user).values('id', 'name')  
    return JsonResponse({'pm_recipes': list(am_recipes)})

def check_ingredients_availability(request, recipe):
    """Check if all ingredients in a recipe are available in sufficient quantities."""
    user = get_user_for_view(request)  # Get the user (main user or subuser)
    
    for i in range(1, 6):
        ingredient_id = getattr(recipe, f"ingredient{i}_id")
        qty = getattr(recipe, f"qty{i}")
        
        if ingredient_id and qty:
            # Check if the ingredient is available in the user's inventory
            if not Inventory.objects.filter(user=user, id=ingredient_id, quantity__gte=qty).exists():
                return False
    return True
    
@login_required
@csrf_exempt
def check_menu(request):
    if request.method == 'POST':
        try:
            raw_body = request.body.decode('utf-8')
            data = json.loads(raw_body)
            dates_to_check = data.get('dates', [])

            # Get the user using get_user_for_view
            user = get_user_for_view(request)

            # Check if any of the dates have existing menu entries for the user
            exists = WeeklyMenu.objects.filter(date__in=dates_to_check, user=user).exists()

            return JsonResponse({'exists': exists}, status=200)

        except Exception as e:
            return JsonResponse({'status': 'fail', 'error': 'Unexpected error occurred'}, status=500)

    return JsonResponse({'status': 'fail', 'error': 'Invalid request method'}, status=400)

@login_required
@csrf_protect
@csrf_exempt
def save_menu(request):
    if request.method == 'POST':
        try:
            # Log the raw body of the request (consider removing this as well if not needed)
            raw_body = request.body.decode('utf-8')
            
            # Parse JSON data from the request body
            data = json.loads(raw_body)

            # Get today's date
            today = datetime.now()

            # Calculate the next Monday
            next_monday = today + timedelta(days=(7 - today.weekday()))
            # Create a list of the next week dates (Monday to Friday)
            week_dates = [(next_monday + timedelta(days=i)).date() for i in range(5)]

            # Define the days of the week
            days_of_week = {
                'monday': 'Mon',
                'tuesday': 'Tue',
                'wednesday': 'Wed',
                'thursday': 'Thu',
                'friday': 'Fri'
            }

            # Get the user using get_user_for_view
            user = get_user_for_view(request)

            # Loop through each day to save menu data
            for day_key, day_abbr in days_of_week.items():
                day_data = data.get(day_key, {})

                # Create or update the WeeklyMenu for each day
                WeeklyMenu.objects.update_or_create(
                    user=user,  # Use the retrieved user
                    date=week_dates[list(days_of_week.keys()).index(day_key)],  # Use calculated date
                    day_of_week=day_abbr,
                    defaults={
                        'am_fluid_milk': day_data.get('am_fluid_milk', ''),
                        'am_fruit_veg': day_data.get('am_fruit_veg', ''),
                        'am_bread': day_data.get('am_bread', ''),
                        'am_additional': day_data.get('am_additional', ''),
                        'ams_fluid_milk': day_data.get('ams_fluid_milk', ''),
                        'ams_fruit_veg': day_data.get('ams_fruit_veg', ''),
                        'ams_bread': day_data.get('ams_bread', ''),
                        'ams_meat': day_data.get('ams_meat', ''),
                        'lunch_main_dish': day_data.get('lunch_main_dish', ''),
                        'lunch_fluid_milk': day_data.get('lunch_fluid_milk', ''),
                        'lunch_vegetable': day_data.get('lunch_vegetable', ''),
                        'lunch_fruit': day_data.get('lunch_fruit', ''),
                        'lunch_grain': day_data.get('lunch_grain', ''),
                        'lunch_meat': day_data.get('lunch_meat', ''),
                        'lunch_additional': day_data.get('lunch_additional', ''),
                        'pm_fluid_milk': day_data.get('pm_fluid_milk', ''),
                        'pm_fruit_veg': day_data.get('pm_fruit_veg', ''),
                        'pm_bread': day_data.get('pm_bread', ''),
                        'pm_meat': day_data.get('pm_meat', '')
                    }
                )

            # Log success and return a success response
            return JsonResponse({'status': 'success'}, status=200)

        except json.JSONDecodeError as e:
            # Log decoding errors
            return JsonResponse({'status': 'fail', 'error': 'Invalid JSON'}, status=400)

        except Exception as e:
            # Log any other errors
            return JsonResponse({'status': 'fail', 'error': 'Unexpected error occurred'}, status=500)

    return JsonResponse({'status': 'fail', 'error': 'Invalid request method'}, status=400)

def delete_recipe(request, recipe_id):
    if request.method == 'DELETE':
        # Handle recipe deletion
        # Example logic:
        recipe = Recipe.objects.get(pk=recipe_id)
        recipe.delete()
        return JsonResponse({'status': 'success', 'message': 'Recipe deleted successfully'})
    else:
        return JsonResponse({'status': 'error', 'message': 'Invalid request method'})
    
def delete_breakfast_recipe(request, recipe_id):
    if request.method == 'DELETE':
        # Handle breakfast recipe deletion
        try:
            # Retrieve the breakfast recipe object
            recipe = BreakfastRecipe.objects.get(pk=recipe_id)
            # Delete the breakfast recipe
            recipe.delete()
            return JsonResponse({'status': 'success', 'message': 'Breakfast recipe deleted successfully'})
        except BreakfastRecipe.DoesNotExist:
            return JsonResponse({'status': 'error', 'message': 'Breakfast recipe not found'}, status=404)
    else:
        return JsonResponse({'status': 'error', 'message': 'Invalid request method'}, status=405)
  
def delete_am_recipe(request, recipe_id):
    if request.method == 'DELETE':
        try:
            am_recipe = AMRecipe.objects.get(pk=recipe_id)
            am_recipe.delete()
            return JsonResponse({'status': 'success', 'message': 'AM Recipe deleted successfully'})
        except AMRecipe.DoesNotExist:
            return JsonResponse({'status': 'error', 'message': 'AM Recipe not found'})
    else:
        return JsonResponse({'status': 'error', 'message': 'Invalid request method'})
    
def delete_pm_recipe(request, recipe_id):
    if request.method == 'DELETE':
        try:
            am_recipe = PMRecipe.objects.get(pk=recipe_id)
            am_recipe.delete()
            return JsonResponse({'status': 'success', 'message': 'PM Recipe deleted successfully'})
        except AMRecipe.DoesNotExist:
            return JsonResponse({'status': 'error', 'message': 'PM Recipe not found'})
    else:
        return JsonResponse({'status': 'error', 'message': 'Invalid request method'})

@login_required
def order_list(request):
    if request.method == 'POST':
        item = request.POST.get('item', '')
        quantity = request.POST.get('quantity', 1)  # Default to 1 if not provided
        category = request.POST.get('category', 'Other')  # Default to 'Other' if not provided

        if item:
            # Get the user using get_user_for_view
            user = get_user_for_view(request)
            OrderList.objects.create(user=user, item=item, quantity=quantity, category=category)
            return redirect('order_list')
        else:
            return HttpResponseBadRequest('Invalid form submission')
    else:
        # Get the user using get_user_for_view
        user = get_user_for_view(request)
        order_items = OrderList.objects.filter(user=user)
        return render(request, 'index.html', {'order_items': order_items})

@login_required
def shopping_list_api(request):
    if request.method == 'GET':
        # Get the user using get_user_for_view
        user = get_user_for_view(request)
        shopping_list_items = OrderList.objects.filter(user=user)
        serialized_items = [{'name': item.item} for item in shopping_list_items]
        return JsonResponse(serialized_items, safe=False)
    else:
        return HttpResponseNotAllowed(['GET'])

def update_orders(request):
    if request.method == 'POST':
        item_ids = request.POST.getlist('items')
        try:
            # Get the user using get_user_for_view
            user = get_user_for_view(request)
            for item_id in item_ids:
                order_item = get_object_or_404(OrderList, id=item_id, user=user)
                order_item.ordered = True
                order_item.save()
            return JsonResponse({'success': True, 'message': 'Orders updated successfully'})
        except Exception as e:
            return JsonResponse({'success': False, 'error': str(e)}, status=500)
    else:
        return HttpResponseNotAllowed(['POST'])

def delete_shopping_items(request):
    if request.method == 'POST':
        item_ids = request.POST.getlist('items[]')
        # Assuming your model is called OrderList and has a primary key 'id'
        OrderList.objects.filter(id__in=item_ids).delete()
        return redirect('order_list')  # Redirect to the order list page after deletion
    else:
        # Handle other HTTP methods if needed
        pass

@login_required
def sign_in(request):
    allow_access = False

    show_weekly_menu = False
    show_inventory = False
    show_milk_inventory = False
    show_meal_count = False
    show_classroom_options = False
    show_recipes = False
    show_sign_in = False
    show_daily_attendance = False
    show_rosters = False
    show_permissions = False  
    show_menu_rules = False  
    show_billing = False          
    show_payment_setup = False
    show_clock_in = False

    try:
        # Check if the user is a SubUser
        sub_user = SubUser.objects.get(user=request.user)
        group_id = sub_user.group_id.id
        required_permission_id = 273  # Permission ID for sign_in view

        # Check if the SubUser has permission to access this view
        try:
            role_permission = RolePermission.objects.get(role_id=group_id, permission_id=required_permission_id)
            allow_access = role_permission.yes_no_permission
        except RolePermission.DoesNotExist:
            allow_access = False  # No specific permission set for this role

        permissions_ids = {
            'weekly_menu': 271,
            'inventory': 272,
            'milk_inventory': 270,
            'meal_count': 269,
            'classroom_options': 268,
            'recipes': 267,
            'sign_in': 273,
            'daily_attendance': 274,
            'rosters': 275,
            'permissions': 157, 
            'menu_rules': 266,
            'billing': 331,          
            'payment_setup': 332, 
            'clock_in': 337,  
        }

        # Dynamically check each permission
        for perm_key, perm_id in permissions_ids.items():
            try:
                role_permission = RolePermission.objects.get(role_id=group_id, permission_id=perm_id)
                if perm_key == 'weekly_menu':
                    show_weekly_menu = role_permission.yes_no_permission
                elif perm_key == 'inventory':
                    show_inventory = role_permission.yes_no_permission
                elif perm_key == 'milk_inventory':
                    show_milk_inventory = role_permission.yes_no_permission
                elif perm_key == 'meal_count':
                    show_meal_count = role_permission.yes_no_permission
                elif perm_key == 'permissions':
                    show_permissions = role_permission.yes_no_permission
                elif perm_key == 'menu_rules':
                    show_menu_rules = role_permission.yes_no_permission
                elif perm_key == 'classroom_options':
                    show_classroom_options = role_permission.yes_no_permission
                elif perm_key == 'recipes':
                    show_recipes = role_permission.yes_no_permission
                elif perm_key == 'sign_in':
                    show_sign_in = role_permission.yes_no_permission
                elif perm_key == 'daily_attendance':
                    show_daily_attendance = role_permission.yes_no_permission
                elif perm_key == 'rosters':
                    show_rosters = role_permission.yes_no_permission
                elif perm_key == 'billing':
                    show_billing = role_permission.yes_no_permission
                elif perm_key == 'payment_setup':
                    show_payment_setup = role_permission.yes_no_permission
                elif perm_key == 'clock_in':
                    show_clock_in = role_permission.yes_no_permission
            except RolePermission.DoesNotExist:
                continue  

    except SubUser.DoesNotExist:
        # If user is not a SubUser, grant access by default (assuming main user)
        allow_access = True
        show_weekly_menu = True
        show_inventory = True
        show_milk_inventory = True
        show_meal_count = True
        show_classroom_options = True
        show_recipes = True
        show_sign_in = True
        show_daily_attendance = True
        show_rosters = True
        show_permissions = True
        show_menu_rules = True
        show_billing = True
        show_payment_setup = True
        show_clock_in = True

    # Redirect to 'no_access' page if access is not allowed
    if not allow_access:
        return redirect('no_access')

    # Process sign-in if the request is POST and permission is granted
    if request.method == 'POST':
        code = request.POST['code']
        try:
            student = Student.objects.get(code=code)
        except Student.DoesNotExist:
            return render(request, 'sign_in.html', {'error': 'Student not found.'})

        user = request.user  # Get the current user

        # Create or update attendance record
        record, created = AttendanceRecord.objects.get_or_create(student=student, sign_out_time=None)
        record.sign_in_time = timezone.now()
        record.user = user  # Assign the current user to the attendance record
        record.save()

        return redirect('home')
    
    return render(request, 'sign_in.html', {
        'show_weekly_menu': show_weekly_menu,
        'show_inventory': show_inventory,
        'show_milk_inventory': show_milk_inventory,
        'show_meal_count': show_meal_count,
        'show_classroom_options': show_classroom_options,
        'show_recipes': show_recipes,
        'show_sign_in': show_sign_in,
        'show_daily_attendance': show_daily_attendance,
        'show_rosters': show_rosters,
        'show_permissions': show_permissions,
        'show_menu_rules': show_menu_rules,
        'show_billing': show_billing,            
        'show_payment_setup': show_payment_setup,
        'show_clock_in': show_clock_in,
    })

@login_required
def process_code(request):
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            code = data.get('code')
            user = get_user_for_view(request)  # Retrieve the user using get_user_for_view

            if code and user:
                timestamp = timezone.now()

                # Retrieve student from the database using the code
                student = Student.objects.get(code=code)

                # Check if the student has an open attendance record (signed in but not signed out)
                open_record = AttendanceRecord.objects.filter(student=student, sign_out_time__isnull=True).first()

                if open_record:  # If student already signed in
                    open_record.sign_out_time = timestamp
                    open_record.save()
                    message = f"{student.first_name} {student.last_name} has been signed out at {timezone.localtime(timestamp).strftime('%I:%M %p')}."
                else:  # If student not signed in
                    new_record = AttendanceRecord.objects.create(student=student, sign_in_time=timestamp, user=user)
                    message = f"{student.first_name} {student.last_name} has been signed in at {timezone.localtime(timestamp).strftime('%I:%M %p')}."

                return JsonResponse({'success': True, 'message': message})
            else:
                return JsonResponse({'success': False, 'message': 'Code and user are required.'})
        except Student.DoesNotExist:
            return JsonResponse({'success': False, 'message': 'Invalid code. Please try again.'})
        except Exception as e:
            return JsonResponse({'success': False, 'message': str(e)})

    return JsonResponse({'success': False, 'message': 'Invalid request method'})



@login_required
def daily_attendance(request):
    allow_access = False
    show_weekly_menu = False
    show_inventory = False
    show_milk_inventory = False
    show_meal_count = False
    show_classroom_options = False
    show_recipes = False
    show_sign_in = False
    show_daily_attendance = False
    show_rosters = False
    show_permissions = False  
    show_menu_rules = False
    show_billing = False          
    show_payment_setup = False
    show_clock_in = False

    try:
        # Check if the user is a SubUser
        sub_user = SubUser.objects.get(user=request.user)
        group_id = sub_user.group_id.id
        required_permission_id = 274  # Permission ID for daily_attendance view

        # Check if the SubUser has permission to access this view
        try:
            role_permission = RolePermission.objects.get(role_id=group_id, permission_id=required_permission_id)
            allow_access = role_permission.yes_no_permission
        except RolePermission.DoesNotExist:
            allow_access = False  # No specific permission set for this role

        permissions_ids = {
            'weekly_menu': 271,
            'inventory': 272,
            'milk_inventory': 270,
            'meal_count': 269,
            'classroom_options': 268,
            'recipes': 267,
            'sign_in': 273,
            'daily_attendance': 274,
            'rosters': 275,
            'permissions': 157, 
            'menu_rules': 266,
            'billing': 331,          
            'payment_setup': 332,   
            'clock_in': 337,
        }

        # Dynamically check each permission
        for perm_key, perm_id in permissions_ids.items():
            try:
                role_permission = RolePermission.objects.get(role_id=group_id, permission_id=perm_id)
                if perm_key == 'weekly_menu':
                    show_weekly_menu = role_permission.yes_no_permission
                elif perm_key == 'inventory':
                    show_inventory = role_permission.yes_no_permission
                elif perm_key == 'milk_inventory':
                    show_milk_inventory = role_permission.yes_no_permission
                elif perm_key == 'meal_count':
                    show_meal_count = role_permission.yes_no_permission
                elif perm_key == 'permissions':
                    show_permissions = role_permission.yes_no_permission
                elif perm_key == 'menu_rules':
                    show_menu_rules = role_permission.yes_no_permission
                elif perm_key == 'classroom_options':
                    show_classroom_options = role_permission.yes_no_permission
                elif perm_key == 'recipes':
                    show_recipes = role_permission.yes_no_permission
                elif perm_key == 'sign_in':
                    show_sign_in = role_permission.yes_no_permission
                elif perm_key == 'daily_attendance':
                    show_daily_attendance = role_permission.yes_no_permission
                elif perm_key == 'rosters':
                    show_rosters = role_permission.yes_no_permission
                elif perm_key == 'billing':
                    show_billing = role_permission.yes_no_permission
                elif perm_key == 'payment_setup':
                    show_payment_setup = role_permission.yes_no_permission
                elif perm_key == 'clock_in':
                    show_clock_in = role_permission.yes_no_permission
            except RolePermission.DoesNotExist:
                continue  

    except SubUser.DoesNotExist:
        # If user is not a SubUser, grant access by default (assuming main user)
        allow_access = True
        show_weekly_menu = True
        show_inventory = True
        show_milk_inventory = True
        show_meal_count = True
        show_classroom_options = True
        show_recipes = True
        show_sign_in = True
        show_daily_attendance = True
        show_rosters = True
        show_permissions = True
        show_menu_rules = True
        show_billing = True
        show_payment_setup = True
        show_clock_in = True

    # Redirect to 'no_access' page if access is not allowed
    if not allow_access:
        return redirect('no_access')

    today = date.today()
    user = get_user_for_view(request)
    students = Student.objects.all() 
    # Fetch attendance records
    attendance_records = AttendanceRecord.objects.filter(sign_in_time__date=today, user=user)

    # Get classroom names from Classroom model
    classroom_options = Classroom.objects.filter(user=user).values_list('name', flat=True)
   
    attendance_data = {}
    relative_counts = {}

    # Fetch attendance data and calculate relative counts for each classroom
    for classroom in Classroom.objects.filter(user=user):
        populated_records = AttendanceRecord.objects.filter(
            classroom_override=classroom, 
            sign_in_time__date=today, 
            user=user
        )
        if populated_records.exists():
            attendance_data[classroom] = populated_records
            relative_counts[classroom] = populated_records.filter(sign_out_time__isnull=True).count()

    # Add empty classrooms if there are no records
    for classroom in Classroom.objects.filter(user=user):
        if classroom not in attendance_data:
            attendance_data[classroom] = []
            relative_counts[classroom] = 0  # No students signed in

    return render(request, 'daily_attendance.html', {
        'attendance_records': attendance_records,
        'relative_counts': relative_counts,
        'students': students,
        'classroom_options': classroom_options,
        'attendance_data': attendance_data,  
        'show_weekly_menu': show_weekly_menu,
        'show_inventory': show_inventory,
        'show_milk_inventory': show_milk_inventory,
        'show_meal_count': show_meal_count,
        'show_classroom_options': show_classroom_options,
        'show_recipes': show_recipes,
        'show_sign_in': show_sign_in,
        'show_daily_attendance': show_daily_attendance,
        'show_rosters': show_rosters,
        'show_permissions': show_permissions,
        'show_menu_rules': show_menu_rules,
        'show_billing': show_billing,            
        'show_payment_setup': show_payment_setup,
        'show_clock_in': show_clock_in, 
    })
 
@csrf_exempt
def update_attendance(request):
    if request.method == 'POST':
        record_id = request.POST.get('id')
        field = request.POST.get('field')
        new_value = request.POST.get('new_value')

        try:
            record = AttendanceRecord.objects.get(id=record_id)

            if field in ['sign_in_time', 'sign_out_time']:
                # Get current date and combine it with new time
                current_date = record.sign_in_time.date() if record.sign_in_time else datetime.today().date()
                new_value = datetime.strptime(new_value, "%H:%M").time()
                new_value = datetime.combine(current_date, new_value)  # Convert to datetime

            setattr(record, field, new_value)
            record.save()
            return JsonResponse({'status': 'success'})
        except AttendanceRecord.DoesNotExist:
            return JsonResponse({'status': 'error', 'message': 'Record not found'})
        except ValueError:
            return JsonResponse({'status': 'error', 'message': 'Invalid time format'})
    
    return JsonResponse({'status': 'error', 'message': 'Invalid request'})

@login_required
def manual_sign_in_ajax(request):
    if request.method == 'POST':
        student_id = request.POST.get('student')
        sign_in_time_str = request.POST.get('sign_in_time')  # Expecting "HH:MM"

        if student_id:
            student = get_object_or_404(Student, pk=student_id)
            today_date = timezone.now().date()

            if sign_in_time_str:
                try:
                    # Parse time from string (HH:MM)
                    time_obj = datetime.strptime(sign_in_time_str, '%H:%M').time()
                    # Combine with today's date
                    sign_in_datetime = timezone.make_aware(datetime.combine(today_date, time_obj))
                except ValueError:
                    return JsonResponse({'success': False, 'error': 'Invalid time format. Use HH:MM.'}, status=400)
            else:
                # If no time is provided, use the current time
                sign_in_datetime = timezone.now()

            # Use get_user_for_view to determine the correct user
            assigned_user = get_user_for_view(request)

            # Save record
            AttendanceRecord.objects.create(
                user=assigned_user,  # Assigning the user from get_user_for_view
                student=student,
                sign_in_time=sign_in_datetime
            )
            return JsonResponse({'success': True})

    return JsonResponse({'success': False}, status=400)


@login_required
def delete_attendance(request):
    if request.method == 'POST':
        record_id = request.POST.get('id')
        if record_id:
            try:
                record = AttendanceRecord.objects.get(pk=record_id)
                record.delete()
                return JsonResponse({'success': True})
            except AttendanceRecord.DoesNotExist:
                return JsonResponse({'success': False, 'error': 'Record not found.'}, status=404)
    return JsonResponse({'success': False}, status=400)

@login_required
def rosters(request):
    
    allow_access = False

    show_weekly_menu = False
    show_inventory = False
    show_milk_inventory = False
    show_meal_count = False
    show_classroom_options = False
    show_recipes = False
    show_sign_in = False
    show_daily_attendance = False
    show_rosters = False
    show_permissions = False  
    show_menu_rules = False 
    show_billing = False          
    show_payment_setup = False
    show_clock_in = False

    try:
        # Check if the user is a SubUser
        sub_user = SubUser.objects.get(user=request.user)
        group_id = sub_user.group_id.id
        required_permission_id = 275  # Permission ID for rosters view

        # Check if the SubUser has permission to access this view
        try:
            role_permission = RolePermission.objects.get(role_id=group_id, permission_id=required_permission_id)
            allow_access = role_permission.yes_no_permission
        except RolePermission.DoesNotExist:
            allow_access = False  # No specific permission set for this role

        permissions_ids = {
            'weekly_menu': 271,
            'inventory': 272,
            'milk_inventory': 270,
            'meal_count': 269,
            'classroom_options': 268,
            'recipes': 267,
            'sign_in': 273,
            'daily_attendance': 274,
            'rosters': 275,
            'permissions': 157, 
            'menu_rules': 266,
            'billing': 331,          
            'payment_setup': 332,   
            'clock_in': 337,
        }

        # Dynamically check each permission
        for perm_key, perm_id in permissions_ids.items():
            try:
                role_permission = RolePermission.objects.get(role_id=group_id, permission_id=perm_id)
                if perm_key == 'weekly_menu':
                    show_weekly_menu = role_permission.yes_no_permission
                elif perm_key == 'inventory':
                    show_inventory = role_permission.yes_no_permission
                elif perm_key == 'milk_inventory':
                    show_milk_inventory = role_permission.yes_no_permission
                elif perm_key == 'meal_count':
                    show_meal_count = role_permission.yes_no_permission
                elif perm_key == 'permissions':
                    show_permissions = role_permission.yes_no_permission
                elif perm_key == 'menu_rules':
                    show_menu_rules = role_permission.yes_no_permission
                elif perm_key == 'classroom_options':
                    show_classroom_options = role_permission.yes_no_permission
                elif perm_key == 'recipes':
                    show_recipes = role_permission.yes_no_permission
                elif perm_key == 'sign_in':
                    show_sign_in = role_permission.yes_no_permission
                elif perm_key == 'daily_attendance':
                    show_daily_attendance = role_permission.yes_no_permission
                elif perm_key == 'rosters':
                    show_rosters = role_permission.yes_no_permission
                elif perm_key == 'billing':
                    show_billing = role_permission.yes_no_permission
                elif perm_key == 'payment_setup':
                    show_payment_setup = role_permission.yes_no_permission
                elif perm_key == 'clock_in':
                    show_clock_in = role_permission.yes_no_permission  
            except RolePermission.DoesNotExist:
                continue  

    except SubUser.DoesNotExist:
        # If user is not a SubUser, grant access by default (assuming main user)
        allow_access = True
        show_weekly_menu = True
        show_inventory = True
        show_milk_inventory = True
        show_meal_count = True
        show_classroom_options = True
        show_recipes = True
        show_sign_in = True
        show_daily_attendance = True
        show_rosters = True
        show_permissions = True
        show_menu_rules = True
        show_billing = True
        show_payment_setup = True
        show_clock_in = True

    # Redirect to 'no_access' page if access is not allowed
    if not allow_access:
        return redirect('no_access')

    # Get current date information
    current_date = datetime.now()
    current_year = current_date.year
    current_month = current_date.month
    current_day = current_date.day
    
    # Get the selected month and year from the request.GET dictionary
    selected_month = int(request.GET.get('month', current_month))
    selected_year = int(request.GET.get('year', current_year))
    
    # Get the number of days in the selected month
    _, num_days_in_month = monthrange(selected_year, selected_month)
    
    # Prepare data for rendering in template
    student_attendance = {}
    
    # Query attendance records for the selected month and year
    attendance_records = AttendanceRecord.objects.filter(
        sign_in_time__year=selected_year,
        sign_in_time__month=selected_month
    )
    
    # Populate attendance for each student
    for record in attendance_records:
        student = record.student
        if student not in student_attendance:
            student_attendance[student] = [''] * num_days_in_month
        day_index = record.sign_in_time.day - 1
        student_attendance[student][day_index] = '✓'
    
    # Populate dashes for days before the current date for the current month
    if selected_year == current_year and selected_month == current_month:
        for student, attendance_list in student_attendance.items():
            for day in range(1, current_day):
                if attendance_list[day - 1] == '':
                    attendance_list[day - 1] = '-'

    # Populate dashes for days before the current date for past months
    if (selected_year < current_year) or (selected_year == current_year and selected_month < current_month):
        for student, attendance_list in student_attendance.items():
            for day in range(num_days_in_month):
                if attendance_list[day] == '':
                    attendance_list[day] = '-'

    # Retrieve all classrooms
    classrooms = Classroom.objects.all()
    
    # Get the selected classroom ID from the request.GET dictionary
    selected_classroom_id = request.GET.get('classroom', None)

    # Query students based on the selected classroom, if any
    if selected_classroom_id:
        students = Student.objects.filter(classroom_id=selected_classroom_id)
        # Filter attendance data for selected students
        student_attendance = {student: student_attendance.get(student, ['']) for student in students}
    
    # Prepare a list of months and years for the template
    months = [
        {'month': i, 'name': datetime.strptime(str(i), "%m").strftime("%B")}
        for i in range(1, 13)
    ]
    years = list(range(2020, 2031))
    
    context = {
        'student_attendance': student_attendance,
        'num_days': range(1, num_days_in_month + 1),  # Start from day 1
        'classrooms': classrooms,
        'selected_classroom': selected_classroom_id,  # Pass the selected classroom ID to retain selection in the form
        'selected_month': selected_month,
        'selected_year': selected_year,
        'months': months,
        'years': years,
        'show_weekly_menu': show_weekly_menu,
        'show_inventory': show_inventory,
        'show_milk_inventory': show_milk_inventory,
        'show_meal_count': show_meal_count,
        'show_classroom_options': show_classroom_options,
        'show_recipes': show_recipes,
        'show_sign_in': show_sign_in,
        'show_daily_attendance': show_daily_attendance,
        'show_rosters': show_rosters,
        'show_permissions': show_permissions,
        'show_menu_rules': show_menu_rules,
        'show_billing': show_billing,            
        'show_payment_setup': show_payment_setup,
        'show_clock_in': show_clock_in,
    }
    
    return render(request, 'rosters.html', context)

    
@csrf_exempt
def add_student(request):
    if request.method == 'POST':
        # Extract data from POST request
        first_name = request.POST.get('firstName')
        last_name = request.POST.get('lastName')
        dob = request.POST.get('dob')
        code = request.POST.get('code')
        classroom_name = request.POST.get('classroom')

        # Fetch the corresponding Classroom instance
        classroom = Classroom.objects.get(name=classroom_name, user=request.user)

        # Get the current user using get_user_for_view
        user = get_user_for_view(request)

        # Save the student to the database
        student = Student.objects.create(
            first_name=first_name,
            last_name=last_name,
            date_of_birth=dob,
            code=code,
            classroom=classroom,
            user=user  # Assign the current user instance
        )

        # Retrieve the list of classrooms again
        classrooms = Classroom.objects.filter(user=request.user)

        return render(request, 'rosters.html', {'success': True, 'classrooms': classrooms})
    else:
        # Retrieve the list of classrooms
        classrooms = Classroom.objects.filter(user=request.user)
        return render(request, 'rosters.html', {'classrooms': classrooms})

@login_required
def classroom_options(request):
    allow_access = False
    show_weekly_menu = False
    show_inventory = False
    show_milk_inventory = False
    show_meal_count = False
    show_classroom_options = False
    show_recipes = False
    show_sign_in = False
    show_daily_attendance = False
    show_rosters = False
    show_permissions = False
    show_menu_rules = False
    show_billing = False          
    show_payment_setup = False
    show_clock_in = False

    try:
        # Check if the user is a SubUser
        sub_user = SubUser.objects.get(user=request.user)
        group_id = sub_user.group_id.id
        required_permission_id = 268  # Permission ID for accessing classroom_options view

        # Check if there is a RolePermission entry with 'yes_no_permission' set to True for this permission
        try:
            role_permission = RolePermission.objects.get(role_id=group_id, permission_id=required_permission_id)
            allow_access = role_permission.yes_no_permission
        except RolePermission.DoesNotExist:
            allow_access = False

        # Check additional permissions based on the same group_id
        permissions_ids = {
            'weekly_menu': 271,
            'inventory': 272,
            'milk_inventory': 270,
            'meal_count': 269,
            'classroom_options': 268,
            'recipes': 267,
            'sign_in': 273,
            'daily_attendance': 274,
            'rosters': 275,
            'permissions': 157, 
            'menu_rules': 266,
            'billing': 331,          
            'payment_setup': 332, 
            'clock_in': 337,  
        }

        # Dynamically check each permission
        for perm_key, perm_id in permissions_ids.items():
            try:
                role_permission = RolePermission.objects.get(role_id=group_id, permission_id=perm_id)
                if perm_key == 'weekly_menu':
                    show_weekly_menu = role_permission.yes_no_permission
                elif perm_key == 'inventory':
                    show_inventory = role_permission.yes_no_permission
                elif perm_key == 'milk_inventory':
                    show_milk_inventory = role_permission.yes_no_permission
                elif perm_key == 'meal_count':
                    show_meal_count = role_permission.yes_no_permission
                elif perm_key == 'permissions':
                    show_permissions = role_permission.yes_no_permission
                elif perm_key == 'menu_rules':
                    show_menu_rules = role_permission.yes_no_permission
                elif perm_key == 'classroom_options':
                    show_classroom_options = role_permission.yes_no_permission
                elif perm_key == 'recipes':
                    show_recipes = role_permission.yes_no_permission
                elif perm_key == 'sign_in':
                    show_sign_in = role_permission.yes_no_permission
                elif perm_key == 'daily_attendance':
                    show_daily_attendance = role_permission.yes_no_permission
                elif perm_key == 'rosters':
                    show_rosters = role_permission.yes_no_permission
                elif perm_key == 'billing':
                    show_billing = role_permission.yes_no_permission
                elif perm_key == 'payment_setup':
                    show_payment_setup = role_permission.yes_no_permission
                elif perm_key == 'clock_in':
                    show_clock_in = role_permission.yes_no_permission
            except RolePermission.DoesNotExist:
                continue  

    except SubUser.DoesNotExist:
        # If user is not a SubUser, grant access by default (assuming main user)
        allow_access = True
        show_weekly_menu = True
        show_inventory = True
        show_milk_inventory = True
        show_meal_count = True
        show_classroom_options = True
        show_recipes = True
        show_sign_in = True
        show_daily_attendance = True
        show_rosters = True
        show_permissions = True
        show_menu_rules = True
        show_billing = True
        show_payment_setup = True
        show_clock_in = True

    # Redirect to 'no_access' page if access is not allowed
    if not allow_access:
        return redirect('no_access')

    # Use the get_user_for_view logic for filtering
    user = get_user_for_view(request)

    # Retrieve classrooms associated with the user
    classrooms = Classroom.objects.filter(user=user)

    # Attach students to each classroom
    for classroom in classrooms:
        classroom.students = Student.objects.filter(classroom=classroom)

    # Retrieve the teachers linked to the current user
    teachers = MainUser.objects.filter(id=user.id)  # Teachers related to the MainUser of the current user

    # For subusers, include teachers under the same MainUser
    if hasattr(user, 'subuser'):
        teachers |= MainUser.objects.filter(subuser__main_user=user)

    # For subusers under the same main user, include them as well
    subusers = SubUser.objects.filter(main_user=user)
    teachers |= MainUser.objects.filter(id__in=subusers.values('user_id'))  # Include all subusers' main users

    # Filter out users with auth_group 5 (Parent) or 6 (Free User)
    teachers = teachers.exclude(groups__id__in=[5, 6])

    return render(request, 'classroom_options.html', {
        'classrooms': classrooms,
        'teachers': teachers,  # Add the filtered teachers list to the context
        'show_weekly_menu': show_weekly_menu,
        'show_inventory': show_inventory,
        'show_milk_inventory': show_milk_inventory,
        'show_meal_count': show_meal_count,
        'show_classroom_options': show_classroom_options,
        'show_recipes': show_recipes,
        'show_sign_in': show_sign_in,
        'show_daily_attendance': show_daily_attendance,
        'show_rosters': show_rosters,
        'show_permissions': show_permissions,
        'show_menu_rules': show_menu_rules,
        'show_billing': show_billing,            
        'show_payment_setup': show_payment_setup,
        'show_clock_in': show_clock_in, 
    })

@login_required
def edit_student(request, student_id):
    student = get_object_or_404(Student, id=student_id)

    if request.method == 'POST':
        print("Received POST data:", request.POST)  # Debugging output
        first_name = request.POST.get('firstName')
        last_name = request.POST.get('lastName')
        dob = request.POST.get('dob')
        code = request.POST.get('code')
        classroom_id = request.POST.get('classroom')

        if not first_name or not last_name:
            return JsonResponse({'success': False, 'error': 'First and last name are required.'})

        classroom = get_object_or_404(Classroom, id=classroom_id)

        student.first_name = first_name
        student.last_name = last_name
        student.date_of_birth = dob
        student.code = code
        student.classroom = classroom
        student.save()

        return JsonResponse({'success': True})

    return JsonResponse({'success': False, 'error': 'Invalid request method.'})


def edit_classroom(request, classroom_id):
    if request.method == 'POST':
        classroom = get_object_or_404(Classroom, id=classroom_id)
        classroom.name = request.POST.get('classroomName')
        classroom.ratios = request.POST.get('classroomRatio')  # Ensure it's assigned to 'ratios'
      
        classroom.save()
        return JsonResponse({'success': True})

    return JsonResponse({'success': False})

@login_required
def add_classroom(request):
    if request.method == 'POST':
        classroom_name = request.POST.get('className')
        class_ratios = request.POST.get('classRatio')  # Use correct field name

        # Get the current user using get_user_for_view
        user = get_user_for_view(request)

        # Validate input
        if not classroom_name or not class_ratios or not class_ratios.isdigit():
            return JsonResponse({'success': False, 'error': 'Invalid input'})

        # Convert class_ratios to an integer
        class_ratios = int(class_ratios)

        # Save classroom with the correct field name
        new_classroom = Classroom(name=classroom_name, ratios=class_ratios, user=user)  # Use 'ratios' instead of 'ratio'
        new_classroom.save()

        return JsonResponse({'success': True})

    return JsonResponse({'success': False, 'error': 'Invalid request'})



def delete_classrooms(request):
    if request.method == 'POST':
        classroom_ids = request.POST.getlist('classroomIds[]')  # assuming the IDs are sent as an array
        try:
            # Delete the selected classrooms
            Classroom.objects.filter(id__in=classroom_ids).delete()
            return JsonResponse({'success': True})
        except Exception as e:
            return JsonResponse({'success': False, 'error': str(e)})
    else:
        return JsonResponse({'success': False, 'error': 'Invalid request method'})
    
@login_required
def milk_count(request):
    allow_access = False
    show_weekly_menu = False
    show_inventory = False
    show_milk_inventory = False
    show_meal_count = False
    show_classroom_options = False
    show_recipes = False
    show_sign_in = False
    show_daily_attendance = False
    show_rosters = False
    show_permissions = False  
    show_menu_rules = False
    show_billing = False          
    show_payment_setup = False
    show_clock_in = False

    try:
        # Check if the user is a SubUser
        sub_user = SubUser.objects.get(user=request.user)
        group_id = sub_user.group_id.id
        required_permission_id = 270  # Permission ID for milk_count view

        # Check if there is a RolePermission entry with 'yes_no_permission' set to True for this permission
        try:
            role_permission = RolePermission.objects.get(role_id=group_id, permission_id=required_permission_id)
            allow_access = role_permission.yes_no_permission
        except RolePermission.DoesNotExist:
            allow_access = False

        permissions_ids = {
            'weekly_menu': 271,
            'inventory': 272,
            'milk_inventory': 270,
            'meal_count': 269,
            'classroom_options': 268,
            'recipes': 267,
            'sign_in': 273,
            'daily_attendance': 274,
            'rosters': 275,
            'permissions': 157, 
            'menu_rules': 266,
            'billing': 331,          
            'payment_setup': 332,   
            'clock_in': 337,
        }

        # Dynamically check each permission
        for perm_key, perm_id in permissions_ids.items():
            try:
                role_permission = RolePermission.objects.get(role_id=group_id, permission_id=perm_id)
                if perm_key == 'weekly_menu':
                    show_weekly_menu = role_permission.yes_no_permission
                elif perm_key == 'inventory':
                    show_inventory = role_permission.yes_no_permission
                elif perm_key == 'milk_inventory':
                    show_milk_inventory = role_permission.yes_no_permission
                elif perm_key == 'meal_count':
                    show_meal_count = role_permission.yes_no_permission
                elif perm_key == 'permissions':
                    show_permissions = role_permission.yes_no_permission
                elif perm_key == 'menu_rules':
                    show_menu_rules = role_permission.yes_no_permission
                elif perm_key == 'classroom_options':
                    show_classroom_options = role_permission.yes_no_permission
                elif perm_key == 'recipes':
                    show_recipes = role_permission.yes_no_permission
                elif perm_key == 'sign_in':
                    show_sign_in = role_permission.yes_no_permission
                elif perm_key == 'daily_attendance':
                    show_daily_attendance = role_permission.yes_no_permission
                elif perm_key == 'rosters':
                    show_rosters = role_permission.yes_no_permission
                elif perm_key == 'billing':
                    show_billing = role_permission.yes_no_permission
                elif perm_key == 'payment_setup':
                    show_payment_setup = role_permission.yes_no_permission
                elif perm_key == 'clock_in':
                    show_clock_in = role_permission.yes_no_permission 
            except RolePermission.DoesNotExist:
                continue  

    except SubUser.DoesNotExist:
        # If user is not a SubUser, grant access by default (assuming main user)
        allow_access = True
        show_weekly_menu = True
        show_inventory = True
        show_milk_inventory = True
        show_meal_count = True
        show_classroom_options = True
        show_recipes = True
        show_sign_in = True
        show_daily_attendance = True
        show_rosters = True
        show_permissions = True
        show_menu_rules = True
        show_billing = True
        show_payment_setup = True
        show_clock_in = True

    # Redirect to 'no_access' page if access is not allowed
    if not allow_access:
        return redirect('no_access')

    # If access is allowed, proceed with the usual view logic
    current_date = datetime.now()
    current_year = current_date.year
    current_month = current_date.month
    
    selected_month = int(request.GET.get('month', current_month))
    selected_year = int(request.GET.get('year', current_year))
    
    months = [{'month': i, 'name': datetime.strptime(str(i), "%m").strftime("%B")} for i in range(1, 13)]
    years = list(range(2020, 2031))
    
    context = {
        'months': months,
        'years': years,
        'selected_month': selected_month,
        'selected_year': selected_year,
        'show_weekly_menu': show_weekly_menu,
        'show_inventory': show_inventory,
        'show_milk_inventory': show_milk_inventory,
        'show_meal_count': show_meal_count,
        'show_classroom_options': show_classroom_options,
        'show_recipes': show_recipes,
        'show_sign_in': show_sign_in,
        'show_daily_attendance': show_daily_attendance,
        'show_rosters': show_rosters,
        'show_permissions': show_permissions,
        'show_menu_rules': show_menu_rules,
        'show_billing': show_billing,            
        'show_payment_setup': show_payment_setup,
        'show_clock_in': show_clock_in,
    }
    
    return render(request, 'milk_count.html', context)

@login_required
def milk_count_view(request):
    allow_access = False
    show_weekly_menu = False
    show_inventory = False
    show_milk_inventory = False
    show_meal_count = False
    show_classroom_options = False
    show_recipes = False
    show_sign_in = False
    show_daily_attendance = False
    show_rosters = False
    show_permissions = False  # Initialize to False
    show_menu_rules = False   # Initialize to False
    show_billing = False          
    show_payment_setup = False
    show_clock_in = False

    try:
        # Check if the user is a SubUser
        sub_user = SubUser.objects.get(user=request.user)
        group_id = sub_user.group_id.id
        required_permission_id = 270  # Permission ID for milk_count_view

        # Check if there is a RolePermission entry with 'yes_no_permission' set to True for this permission
        try:
            role_permission = RolePermission.objects.get(role_id=group_id, permission_id=required_permission_id)
            allow_access = role_permission.yes_no_permission
        except RolePermission.DoesNotExist:
            allow_access = False  # No specific permission set for this role

        permissions_ids = {
            'weekly_menu': 271,
            'inventory': 272,
            'milk_inventory': 270,
            'meal_count': 269,
            'classroom_options': 268,
            'recipes': 267,
            'sign_in': 273,
            'daily_attendance': 274,
            'rosters': 275,
            'permissions': 157, 
            'menu_rules': 266,
            'billing': 331,          
            'payment_setup': 332,   
            'clock_in': 337,
        }

        # Dynamically check each permission
        for perm_key, perm_id in permissions_ids.items():
            try:
                role_permission = RolePermission.objects.get(role_id=group_id, permission_id=perm_id)
                if perm_key == 'weekly_menu':
                    show_weekly_menu = role_permission.yes_no_permission
                elif perm_key == 'inventory':
                    show_inventory = role_permission.yes_no_permission
                elif perm_key == 'milk_inventory':
                    show_milk_inventory = role_permission.yes_no_permission
                elif perm_key == 'meal_count':
                    show_meal_count = role_permission.yes_no_permission
                elif perm_key == 'permissions':
                    show_permissions = role_permission.yes_no_permission
                elif perm_key == 'menu_rules':
                    show_menu_rules = role_permission.yes_no_permission
                elif perm_key == 'classroom_options':
                    show_classroom_options = role_permission.yes_no_permission
                elif perm_key == 'recipes':
                    show_recipes = role_permission.yes_no_permission
                elif perm_key == 'sign_in':
                    show_sign_in = role_permission.yes_no_permission
                elif perm_key == 'daily_attendance':
                    show_daily_attendance = role_permission.yes_no_permission
                elif perm_key == 'rosters':
                    show_rosters = role_permission.yes_no_permission
                elif perm_key == 'billing':
                    show_billing = role_permission.yes_no_permission
                elif perm_key == 'payment_setup':
                    show_payment_setup = role_permission.yes_no_permission
                elif perm_key == 'clock_in':
                    show_clock_in = role_permission.yes_no_permission 
            except RolePermission.DoesNotExist:
                continue  

    except SubUser.DoesNotExist:
        # If user is not a SubUser, grant access by default (assuming main user)
        allow_access = True
        show_weekly_menu = True
        show_inventory = True
        show_milk_inventory = True
        show_meal_count = True
        show_classroom_options = True
        show_recipes = True
        show_sign_in = True
        show_daily_attendance = True
        show_rosters = True
        show_permissions = True
        show_menu_rules = True
        show_billing = True
        show_payment_setup = True
        show_clock_in = True

    # Redirect to 'no_access' page if access is not allowed
    if not allow_access:
        return redirect('no_access')

    # If access is allowed, proceed with the usual view logic
    months = MilkCount.objects.dates('timestamp', 'month')
    years = MilkCount.objects.dates('timestamp', 'year')

    selected_month = request.GET.get('month')
    selected_year = request.GET.get('year')

    if selected_month and selected_year:
        tz = timezone.get_current_timezone()
        start_date = datetime(int(selected_year), int(selected_month), 1, tzinfo=tz)
        end_date = start_date.replace(day=1, month=start_date.month % 12 + 1)

        milk_counts = MilkCount.objects.filter(timestamp__gte=start_date, timestamp__lt=end_date)

        first_entries = milk_counts.values('inventory_item').annotate(
            min_timestamp=Min('timestamp')
        ).values_list('min_timestamp', flat=True)

        beginning_inventory_count = MilkCount.objects.filter(timestamp__in=first_entries).aggregate(
            beginning_inventory_qty=Sum('current_qty')
        )['beginning_inventory_qty'] or 0

        last_entries = milk_counts.values('inventory_item').annotate(
            max_timestamp=Max('timestamp')
        ).values_list('max_timestamp', flat=True)

        end_of_month_inventory = MilkCount.objects.filter(timestamp__in=last_entries).aggregate(
            end_of_month_qty=Sum('current_qty')
        )['end_of_month_qty'] or 0

        total_received_qty = milk_counts.aggregate(total_qty=Sum('received_qty'))['total_qty'] or 0
        total_available_qty = beginning_inventory_count + total_received_qty
        total_used_qty = total_available_qty - end_of_month_inventory

        context = {
            'total_received_qty': total_received_qty,
            'beginning_inventory_count': beginning_inventory_count,
            'total_available_qty': total_available_qty,
            'end_of_month_inventory': end_of_month_inventory,
            'total_used_qty': total_used_qty,
            'months': months,
            'years': years,
            'selected_month': selected_month,
            'selected_year': selected_year,
            'show_weekly_menu': show_weekly_menu,
            'show_inventory': show_inventory,
            'show_milk_inventory': show_milk_inventory,
            'show_meal_count': show_meal_count,
            'show_classroom_options': show_classroom_options,
            'show_recipes': show_recipes,
            'show_sign_in': show_sign_in,
            'show_daily_attendance': show_daily_attendance,
            'show_rosters': show_rosters,
            'show_permissions': show_permissions,
            'show_menu_rules': show_menu_rules,
            'show_billing': show_billing,            
            'show_payment_setup': show_payment_setup,
            'show_clock_in': show_clock_in,
         }
    else:
        context = {
            'months': months,
            'years': years,
            'show_weekly_menu': show_weekly_menu,
            'show_inventory': show_inventory,
            'show_milk_inventory': show_milk_inventory,
            'show_meal_count': show_meal_count,
            'show_classroom_options': show_classroom_options,
            'show_recipes': show_recipes,
            'show_sign_in': show_sign_in,
            'show_daily_attendance': show_daily_attendance,
            'show_rosters': show_rosters,
            'show_permissions': show_permissions,
            'show_menu_rules': show_menu_rules,
            'show_billing': show_billing,            
            'show_payment_setup': show_payment_setup,
            'show_clock_in': show_clock_in,
        }

    return render(request, 'milk_count.html', context)


def update_milk_count(request):
    if request.method == 'POST' and request.headers.get('x-requested-with') == 'XMLHttpRequest':
        inventory_item_id = request.POST.get('inventory_item_id')
        extra_milk_quantity = request.POST.get('extra_milk_quantity')

        # Get the Inventory item
        inventory_item = Inventory.objects.get(pk=inventory_item_id)

        # Get the current date and time
        now = datetime.now()

        # Get the current user using get_user_for_view
        user = get_user_for_view(request)

        # Create a new MilkCount entry for the current update
        milk_count = MilkCount.objects.create(
            inventory_item=inventory_item,
            timestamp=now,
            current_qty=inventory_item.quantity,  # Set the current quantity
            received_qty=int(extra_milk_quantity) if extra_milk_quantity else 0,  # Set received quantity
            user=user  # Use the retrieved user
        )

        return JsonResponse({'success': True})
    else:
        return JsonResponse({'success': False, 'error': 'Invalid request'})



@login_required
def meal_count(request):
    allow_access = False
    show_weekly_menu = False
    show_inventory = False
    show_milk_inventory = False
    show_meal_count = False
    show_classroom_options = False
    show_recipes = False
    show_sign_in = False
    show_daily_attendance = False
    show_rosters = False
    show_permissions = False  
    show_menu_rules = False   
    show_billing = False          
    show_payment_setup = False
    show_clock_in = False

    try:
        # Check if the user is a SubUser
        sub_user = SubUser.objects.get(user=request.user)
        group_id = sub_user.group_id.id
        required_permission_id = 269  # Permission ID for meal_count view

        # Check if there is a RolePermission entry with 'yes_no_permission' set to True for this permission
        try:
            role_permission = RolePermission.objects.get(role_id=group_id, permission_id=required_permission_id)
            allow_access = role_permission.yes_no_permission
        except RolePermission.DoesNotExist:
            allow_access = False

        permissions_ids = {
            'weekly_menu': 271,
            'inventory': 272,
            'milk_inventory': 270,
            'meal_count': 269,
            'classroom_options': 268,
            'recipes': 267,
            'sign_in': 273,
            'daily_attendance': 274,
            'rosters': 275,
            'permissions': 157, 
            'menu_rules': 266,
            'billing': 331,          
            'payment_setup': 332,  
            'clock_in': 337, 
        }

        # Dynamically check each permission
        for perm_key, perm_id in permissions_ids.items():
            try:
                role_permission = RolePermission.objects.get(role_id=group_id, permission_id=perm_id)
                if perm_key == 'weekly_menu':
                    show_weekly_menu = role_permission.yes_no_permission
                elif perm_key == 'inventory':
                    show_inventory = role_permission.yes_no_permission
                elif perm_key == 'milk_inventory':
                    show_milk_inventory = role_permission.yes_no_permission
                elif perm_key == 'meal_count':
                    show_meal_count = role_permission.yes_no_permission
                elif perm_key == 'permissions':
                    show_permissions = role_permission.yes_no_permission
                elif perm_key == 'menu_rules':
                    show_menu_rules = role_permission.yes_no_permission
                elif perm_key == 'classroom_options':
                    show_classroom_options = role_permission.yes_no_permission
                elif perm_key == 'recipes':
                    show_recipes = role_permission.yes_no_permission
                elif perm_key == 'sign_in':
                    show_sign_in = role_permission.yes_no_permission
                elif perm_key == 'daily_attendance':
                    show_daily_attendance = role_permission.yes_no_permission
                elif perm_key == 'rosters':
                    show_rosters = role_permission.yes_no_permission
                elif perm_key == 'billing':
                    show_billing = role_permission.yes_no_permission
                elif perm_key == 'payment_setup':
                    show_payment_setup = role_permission.yes_no_permission
                elif perm_key == 'clock_in':
                    show_clock_in = role_permission.yes_no_permission
            except RolePermission.DoesNotExist:
                continue  

    except SubUser.DoesNotExist:
        # If user is not a SubUser, grant access by default (assuming main user)
        allow_access = True
        show_weekly_menu = True
        show_inventory = True
        show_milk_inventory = True
        show_meal_count = True
        show_classroom_options = True
        show_recipes = True
        show_sign_in = True
        show_daily_attendance = True
        show_rosters = True
        show_permissions = True
        show_menu_rules = True
        show_billing = True
        show_payment_setup = True
        show_clock_in = True

    # Redirect to 'no_access' page if access is not allowed
    if not allow_access:
        return redirect('no_access')

    # If access is allowed, proceed with the usual view logic
    months = MilkCount.objects.dates('timestamp', 'month', order='DESC')
    years = MilkCount.objects.dates('timestamp', 'year', order='DESC')

    selected_month = request.GET.get('month')
    selected_year = request.GET.get('year')

    if selected_month and selected_year:
        tz = timezone.get_current_timezone()
        start_date = datetime(int(selected_year), int(selected_month), 1, tzinfo=tz)
        end_date = start_date.replace(day=1, month=start_date.month % 12 + 1)
        attendance_records = AttendanceRecord.objects.filter(sign_in_time__gte=start_date, sign_in_time__lt=end_date)
    else:
        attendance_records = AttendanceRecord.objects.all()

    am_count = 0
    lunch_count = 0
    pm_count = 0

    am_range = (4, 0, 9, 0)
    lunch_range = (10, 30, 12, 30)
    pm_range = (13, 0, 17, 0)

    eastern = pytz.timezone('US/Eastern')

    def overlaps(time_range, sign_in_time, sign_out_time):
        start_hour, start_minute, end_hour, end_minute = time_range
        start_time = timezone.make_aware(timezone.datetime(2000, 1, 1, start_hour, start_minute), eastern).time()
        end_time = timezone.make_aware(timezone.datetime(2000, 1, 1, end_hour, end_minute), eastern).time()
        return (sign_in_time.time() < end_time and sign_out_time.time() > start_time)

    for record in attendance_records:
        sign_in_time_est = record.sign_in_time.astimezone(eastern)
        sign_out_time_est = record.sign_out_time.astimezone(eastern) if record.sign_out_time else sign_in_time_est

        if overlaps(am_range, sign_in_time_est, sign_out_time_est):
            am_count += 1
        if overlaps(lunch_range, sign_in_time_est, sign_out_time_est):
            lunch_count += 1
        if overlaps(pm_range, sign_in_time_est, sign_out_time_est):
            pm_count += 1

    return render(request, 'meal_count.html', {
        'am_count': am_count,
        'lunch_count': lunch_count,
        'pm_count': pm_count,
        'months': months,
        'years': years,
        'selected_month': selected_month,
        'selected_year': selected_year,
        'show_weekly_menu': show_weekly_menu,
        'show_inventory': show_inventory,
        'show_milk_inventory': show_milk_inventory,
        'show_meal_count': show_meal_count,
        'show_classroom_options': show_classroom_options,
        'show_recipes': show_recipes,
        'show_sign_in': show_sign_in,
        'show_daily_attendance': show_daily_attendance,
        'show_rosters': show_rosters,
        'show_permissions': show_permissions,
        'show_menu_rules': show_menu_rules,
        'show_billing': show_billing,            
        'show_payment_setup': show_payment_setup,
        'show_clock_in': show_clock_in, 
    })


def select_meals_for_days(recipes, user):
    """Select available meals for each day from the given recipes, accounting for inventory usage."""
    days_of_week = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]
    menu_data = {}

    # Get a copy of the user's inventory to simulate inventory changes
    inventory = {item.id: item for item in Inventory.objects.filter(user=user)}

    for day in days_of_week:
        # For Monday and Tuesday, exclude meals if any ingredient has quantity = 0
        if day in ["Monday", "Tuesday"]:
            available_meals = [r for r in recipes if check_ingredients_availability(r, user, inventory, exclude_zero_quantity=True)]
        else:
            available_meals = [r for r in recipes if check_ingredients_availability(r, user, inventory)]
        
        if available_meals:
            selected_meal = random.choice(available_meals)
            recipes = [r for r in recipes if r != selected_meal]
            
            # Subtract used ingredients from inventory
            subtract_ingredients_from_inventory(selected_meal, inventory)
        else:
            selected_meal = None

        if selected_meal:
            menu_data[day] = {
                'meal_name': selected_meal.name,
                'grain': selected_meal.grain,
                'meat_alternate': selected_meal.meat_alternate
            }
        else:
            menu_data[day] = {
                'meal_name': "No available meal",
                'grain': "",
                'meat_alternate': ""
            }

    return menu_data

def check_ingredients_availability(recipe, user, inventory, exclude_zero_quantity=False):
    """Check if the ingredients for a recipe are available in the inventory.
    
    Args:
        exclude_zero_quantity (bool): If True, exclude ingredients with quantity = 0.
    """
    required_ingredients = [
        (recipe.ingredient1, recipe.qty1),
        (recipe.ingredient2, recipe.qty2),
        (recipe.ingredient3, recipe.qty3),
        (recipe.ingredient4, recipe.qty4),
        (recipe.ingredient5, recipe.qty5)
    ]

    for ingredient, qty in required_ingredients:
        if ingredient:
            item = inventory.get(ingredient.id, None)
            if item:
                if exclude_zero_quantity and item.quantity == 0:
                    return False
                if item.total_quantity < qty:
                    return False

    return True

def subtract_ingredients_from_inventory(recipe, inventory):
    """Subtract the ingredients used in a recipe from the inventory."""
    required_ingredients = [
        (recipe.ingredient1, recipe.qty1),
        (recipe.ingredient2, recipe.qty2),
        (recipe.ingredient3, recipe.qty3),
        (recipe.ingredient4, recipe.qty4),
        (recipe.ingredient5, recipe.qty5)
    ]

    for ingredient, qty in required_ingredients:
        if ingredient:
            item = inventory.get(ingredient.id, None)
            if item:
                item.total_quantity -= qty
                item.save()

def get_filtered_recipes(user, model, recent_days=14):
    """Filter recipes not used in the last `recent_days` days."""
    all_recipes = list(model.objects.filter(user=user))
    cutoff_date = timezone.now() - timedelta(days=recent_days)
    recent_recipes = model.objects.filter(user=user, last_used__gte=cutoff_date)
    return [recipe for recipe in all_recipes if recipe not in recent_recipes]

def generate_menu(request):
    user = get_user_for_view(request)  # Get the correct user context
    recipes = get_filtered_recipes(user, Recipe)
    menu_data = select_meals_for_days(recipes, user)
    return JsonResponse(menu_data)


@login_required
def generate_snack_menu(request, model, fluid_key, fruit_key, bread_key, meat_key):
    user = get_user_for_view(request)  # Get the appropriate user (main user or subuser's main user)
    snack_data = {}
    days_of_week = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]
    recipes = list(model.objects.filter(user=user))  # Fetch recipes for the determined user

    for day in days_of_week:
        if recipes:
            selected_recipe = random.choice(recipes)
            recipes.remove(selected_recipe)
            snack_data[day] = {
                fluid_key: selected_recipe.fluid,
                fruit_key: selected_recipe.fruit_veg,
                bread_key: selected_recipe.name,
                meat_key: selected_recipe.meat
            }
        else:
            snack_data[day] = {
                fluid_key: "",
                fruit_key: "",
                bread_key: "",
                meat_key: ""
            }

    return JsonResponse(snack_data)  # Return the snack data as a JSON response

def generate_am_menu(request):
    return generate_snack_menu(request, AMRecipe, 'choose1', 'fruit2', 'bread2', 'meat1')

def generate_pm_menu(request):
    return generate_snack_menu(request, PMRecipe, 'choose2', 'fruit4', 'bread3', 'meat3')

@login_required
def generate_breakfast_menu(request):
    user = get_user_for_view(request)  # Get the appropriate user (main user or subuser's main user)
    breakfast_data = {}
    days_of_week = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]
    recipes = list(BreakfastRecipe.objects.filter(user=user))  # Fetch recipes for the determined user

    for day in days_of_week:
        if recipes:
            selected_recipe = random.choice(recipes)
            recipes.remove(selected_recipe)
            breakfast_data[day] = {
                'bread': selected_recipe.name,
                'add1': selected_recipe.addfood
            }
        else:
            breakfast_data[day] = {
                'bread': "No available breakfast option",
                'add1': ""
            }

    return JsonResponse(breakfast_data)  # Return the breakfast data as a JSON response

@login_required
def generate_fruit_menu(request):
    user = get_user_for_view(request)  # Get the appropriate user (main user or subuser's main user)
    fruit_menu_data = {}
    days_of_week = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]
    
    # Retrieve available fruits for the entire week
    all_fruits = list(
        Inventory.objects.filter(
            user=user,  # Use the retrieved user
            category="Fruits",
            total_quantity__gt=0
        ).values_list('item', flat=True)
    )
    
    # Retrieve available fruits with quantity > 0
    fruits_with_quantity = list(
        Inventory.objects.filter(
            user=user,  # Use the retrieved user
            category="Fruits",
            quantity__gt=0
        ).values_list('item', flat=True)
    )
    
    # Separate fruits for Monday and Tuesday
    fruits_for_monday_tuesday = [
        fruit for fruit in fruits_with_quantity
        if fruit in all_fruits
    ]
    
    # Track used fruits to avoid repetition
    used_fruits = set()
    
    # Helper function to select a fruit and update the used_fruits set
    def select_fruit(fruit_list):
        available_fruits = [fruit for fruit in fruit_list if fruit not in used_fruits]
        if available_fruits:
            selected_fruit = random.choice(available_fruits)
            used_fruits.add(selected_fruit)
            return selected_fruit
        return "NO FRUIT AVAILABLE"

    # Generate fruit menu for Monday and Tuesday
    for day in ["Monday", "Tuesday"]:
        fruit_snack_data = {}
        
        selected_fruit = select_fruit(fruits_for_monday_tuesday)
        fruit_snack_data['fruit'] = selected_fruit
        
        # Filter out "Juice" and "Raisins" for the 'fruit3' selection
        available_for_fruit3 = [
            fruit for fruit in fruits_for_monday_tuesday
            if "Juice" not in fruit and "Raisins" not in fruit
        ]
        
        selected_fruit_for_fruit3 = select_fruit(available_for_fruit3)
        fruit_snack_data['fruit3'] = selected_fruit_for_fruit3
        
        fruit_menu_data[day] = fruit_snack_data
    
    # Generate fruit menu for the remaining days
    for day in ["Wednesday", "Thursday", "Friday"]:
        fruit_snack_data = {}
        
        selected_fruit = select_fruit(all_fruits)
        fruit_snack_data['fruit'] = selected_fruit
        
        # Filter out "Juice" and "Raisins" for the 'fruit3' selection
        available_for_fruit3 = [
            fruit for fruit in all_fruits
            if "Juice" not in fruit and "Raisins" not in fruit
        ]
        
        selected_fruit_for_fruit3 = select_fruit(available_for_fruit3)
        fruit_snack_data['fruit3'] = selected_fruit_for_fruit3
        
        fruit_menu_data[day] = fruit_snack_data

    return JsonResponse(fruit_menu_data)

def get_fruits(request):
    fruits = Inventory.objects.filter(category='Fruits').values_list('item', flat=True)
    return JsonResponse(list(fruits), safe=False)

@login_required
def generate_vegetable_menu(request):
    user = get_user_for_view(request)  # Get the appropriate user (main user or subuser's main user)
    vegetable_menu_data = {}
    days_of_week = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]

    # Retrieve available vegetables based on total_quantity
    all_vegetables = list(Inventory.objects.filter(
        user=user,  # Use the retrieved user
        category="Vegetables",
        total_quantity__gt=0
    ).values_list('item', flat=True))

    # Retrieve vegetables with quantity > 0
    vegetables_with_quantity = list(Inventory.objects.filter(
        user=user,  # Use the retrieved user
        category="Vegetables",
        quantity__gt=0
    ).values_list('item', flat=True))

    # Separate vegetables for Monday and Tuesday
    vegetables_for_monday_tuesday = [
        veg for veg in vegetables_with_quantity
        if veg in all_vegetables
    ]

    # Track used vegetables to avoid repetition
    used_vegetables = set()

    # Helper function to select a vegetable and update the used_vegetables set
    def select_vegetable(vegetable_list):
        available_vegetables = [veg for veg in vegetable_list if veg not in used_vegetables]
        if available_vegetables:
            selected_vegetable = random.choice(available_vegetables)
            used_vegetables.add(selected_vegetable)
            return selected_vegetable
        return "NO VEGETABLE AVAILABLE"

    # Generate vegetable menu for Monday and Tuesday
    for day in ["Monday", "Tuesday"]:
        vegetable_data = {}
        
        selected_vegetable = select_vegetable(vegetables_for_monday_tuesday)
        vegetable_data['vegetable'] = selected_vegetable
        
        vegetable_menu_data[day] = vegetable_data

    # Generate vegetable menu for the remaining days
    for day in ["Wednesday", "Thursday", "Friday"]:
        vegetable_data = {}
        
        selected_vegetable = select_vegetable(all_vegetables)
        vegetable_data['vegetable'] = selected_vegetable
        
        vegetable_menu_data[day] = vegetable_data

    return JsonResponse(vegetable_menu_data)

@login_required
def past_menus(request):
    user = get_user_for_view(request)  # Get the appropriate user (main user or subuser's main user)

    # Fetch all unique Monday dates from the WeeklyMenu model for the logged-in user, ordered by date in descending order
    monday_dates = WeeklyMenu.objects.filter(day_of_week='Mon', user=user).values_list('date', flat=True).distinct().order_by('-date')

    # Generate date ranges only for valid Mondays
    date_ranges = []
    for monday in monday_dates:
        # Calculate the corresponding Friday for each Monday
        friday = monday + timedelta(days=4)

        # Ensure that the Monday-Friday range is valid (avoid reversing dates)
        if friday > monday:
            date_range_str = f"{monday.strftime('%b %d')} - {friday.strftime('%b %d')}"
            date_ranges.append(date_range_str)

    # Initialize selected range and menu data
    selected_menu_data = None
    selected_range = None

    # Permission check variables
    show_weekly_menu = False
    show_inventory = False
    show_milk_inventory = False
    show_meal_count = False
    show_classroom_options = False
    show_recipes = False
    show_sign_in = False
    show_daily_attendance = False
    show_rosters = False
    show_permissions = False
    show_menu_rules = False
    show_billing = False          
    show_payment_setup = False
    show_clock_in = False

    # Check permissions for different links
    try:
        # Check if the user is a SubUser
        sub_user = SubUser.objects.get(user=request.user)
        group_id = sub_user.group_id.id

        permissions_ids = {
            'weekly_menu': 271,  # Added permission for weekly_menu (for this page)
            'inventory': 272,
            'milk_inventory': 270,
            'meal_count': 269,
            'classroom_options': 268,
            'recipes': 267,
            'sign_in': 273,
            'daily_attendance': 274,
            'rosters': 275,
            'permissions': 157, 
            'menu_rules': 266,
            'billing': 331,          
            'payment_setup': 332,   
            'clock_in': 337,
        }

        # Dynamically check each permission
        for perm_key, perm_id in permissions_ids.items():
            try:
                role_permission = RolePermission.objects.get(role_id=group_id, permission_id=perm_id)
                if perm_key == 'weekly_menu':
                    show_weekly_menu = role_permission.yes_no_permission
                elif perm_key == 'inventory':
                    show_inventory = role_permission.yes_no_permission
                elif perm_key == 'milk_inventory':
                    show_milk_inventory = role_permission.yes_no_permission
                elif perm_key == 'meal_count':
                    show_meal_count = role_permission.yes_no_permission
                elif perm_key == 'permissions':
                    show_permissions = role_permission.yes_no_permission
                elif perm_key == 'menu_rules':
                    show_menu_rules = role_permission.yes_no_permission
                elif perm_key == 'classroom_options':
                    show_classroom_options = role_permission.yes_no_permission
                elif perm_key == 'recipes':
                    show_recipes = role_permission.yes_no_permission
                elif perm_key == 'sign_in':
                    show_sign_in = role_permission.yes_no_permission
                elif perm_key == 'daily_attendance':
                    show_daily_attendance = role_permission.yes_no_permission
                elif perm_key == 'rosters':
                    show_rosters = role_permission.yes_no_permission
                elif perm_key == 'billing':
                    show_billing = role_permission.yes_no_permission
                elif perm_key == 'payment_setup':
                    show_payment_setup = role_permission.yes_no_permission
                elif perm_key == 'clock_in':
                    show_clock_in = role_permission.yes_no_permission 
            except RolePermission.DoesNotExist:
                continue  

    except SubUser.DoesNotExist:
        # If the user is not a SubUser, assume they are a MainUser with access to everything
        show_weekly_menu = True
        show_inventory = True
        show_milk_inventory = True
        show_meal_count = True
        show_classroom_options = True
        show_recipes = True
        show_sign_in = True
        show_daily_attendance = True
        show_rosters = True
        show_permissions = True
        show_menu_rules = True
        show_billing = True
        show_payment_setup = True
        show_clock_in = True

    # Ensure user has access to this page
    if not show_weekly_menu:
        return redirect('no_access')  # Redirect to a no-permission page or another view

    # Check if a date range was selected
    if request.method == 'POST':
        selected_range = request.POST.get('dateRangeSelect')
        if selected_range:
            # Parse the date range
            start_date_str, end_date_str = selected_range.split(' - ')
            start_date = datetime.strptime(start_date_str, '%b %d')
            end_date = datetime.strptime(end_date_str, '%b %d')

            # Adjust the year based on the current year's Mondays
            current_year = datetime.now().year
            start_date = start_date.replace(year=current_year)
            end_date = end_date.replace(year=current_year)

            # Fetch WeeklyMenu entries within the selected range for the logged-in user, sorted by date
            selected_menu_data = WeeklyMenu.objects.filter(date__range=[start_date, end_date], user=user).order_by('date')

        # Handle form submission to save menu changes
        if 'save_changes' in request.POST and selected_menu_data:
            for i, menu in enumerate(selected_menu_data):
                menu.am_fluid_milk = request.POST.get(f'am_fluid_milk_{i}')
                menu.am_fruit_veg = request.POST.get(f'am_fruit_veg_{i}')
                menu.am_bread = request.POST.get(f'am_bread_{i}')
                menu.am_additional = request.POST.get(f'am_additional_{i}')
                menu.ams_fluid_milk = request.POST.get(f'ams_fluid_milk_{i}')
                menu.ams_fruit_veg = request.POST.get(f'ams_fruit_veg_{i}')
                menu.ams_bread = request.POST.get(f'ams_bread_{i}')
                menu.ams_meat = request.POST.get(f'ams_meat_{i}')
                menu.lunch_main_dish = request.POST.get(f'lunch_main_dish_{i}')
                menu.lunch_fluid_milk = request.POST.get(f'lunch_fluid_milk_{i}')
                menu.lunch_vegetable = request.POST.get(f'lunch_vegetable_{i}')
                menu.lunch_fruit = request.POST.get(f'lunch_fruit_{i}')
                menu.lunch_grain = request.POST.get(f'lunch_grain_{i}')
                menu.lunch_meat = request.POST.get(f'lunch_meat_{i}')
                menu.lunch_additional = request.POST.get(f'lunch_additional_{i}')
                menu.pm_fluid_milk = request.POST.get(f'pm_fluid_milk_{i}')
                menu.pm_fruit_veg = request.POST.get(f'pm_fruit_veg_{i}')
                menu.pm_bread = request.POST.get(f'pm_bread_{i}')
                menu.pm_meat = request.POST.get(f'pm_meat_{i}')
                
                menu.save()

            return redirect('past_menus')  # Redirect to refresh data

    # Pass the date ranges, selected menu data, and selected range to the template
    context = {
        'date_ranges': date_ranges,
        'selected_menu_data': selected_menu_data,
        'selected_range': selected_range,
        'show_weekly_menu': show_weekly_menu,
        'show_inventory': show_inventory,
        'show_milk_inventory': show_milk_inventory,
        'show_meal_count': show_meal_count,
        'show_classroom_options': show_classroom_options,
        'show_recipes': show_recipes,
        'show_sign_in': show_sign_in,
        'show_daily_attendance': show_daily_attendance,
        'show_rosters': show_rosters,
        'show_permissions': show_permissions,
        'show_menu_rules': show_menu_rules,
        'show_billing': show_billing,            
        'show_payment_setup': show_payment_setup,
        'show_clock_in': show_clock_in, 
    }

    return render(request, 'past-menus.html', context)

@login_required
def assign_user_to_role(user, role_name):
    role_group, created = Group.objects.get_or_create(name=role_name)
    user.groups.add(role_group)

@login_required
def send_invitation(request):
    success_message = ""  # Initialize success message
    allow_access = False

    # Check permissions for different links
    show_weekly_menu = False
    show_inventory = False
    show_milk_inventory = False
    show_meal_count = False
    show_classroom_options = False
    show_recipes = False
    show_sign_in = False
    show_daily_attendance = False
    show_rosters = False
    show_permissions = False  
    show_menu_rules = False 
    show_billing = False          
    show_payment_setup = False
    show_clock_in = False


    try:
        # Check if the user is a SubUser
        sub_user = SubUser.objects.get(user=request.user)
        group_id = sub_user.group_id.id

        permissions_ids = {
            'weekly_menu': 271,
            'inventory': 272,
            'milk_inventory': 270,
            'meal_count': 269,
            'classroom_options': 268,
            'recipes': 267,
            'sign_in': 273,
            'daily_attendance': 274,
            'rosters': 275,
            'permissions': 157, 
            'menu_rules': 266,
            'billing': 331,          
            'payment_setup': 332,   
            'clock_in': 337,
        }

        # Dynamically check each permission
        for perm_key, perm_id in permissions_ids.items():
            try:
                role_permission = RolePermission.objects.get(role_id=group_id, permission_id=perm_id)
                if perm_key == 'weekly_menu':
                    show_weekly_menu = role_permission.yes_no_permission
                elif perm_key == 'inventory':
                    show_inventory = role_permission.yes_no_permission
                elif perm_key == 'milk_inventory':
                    show_milk_inventory = role_permission.yes_no_permission
                elif perm_key == 'meal_count':
                    show_meal_count = role_permission.yes_no_permission
                elif perm_key == 'permissions':
                    show_permissions = role_permission.yes_no_permission
                elif perm_key == 'menu_rules':
                    show_menu_rules = role_permission.yes_no_permission
                elif perm_key == 'classroom_options':
                    show_classroom_options = role_permission.yes_no_permission
                elif perm_key == 'recipes':
                    show_recipes = role_permission.yes_no_permission
                elif perm_key == 'sign_in':
                    show_sign_in = role_permission.yes_no_permission
                elif perm_key == 'daily_attendance':
                    show_daily_attendance = role_permission.yes_no_permission
                elif perm_key == 'rosters':
                    show_rosters = role_permission.yes_no_permission
                elif perm_key == 'billing':
                    show_billing = role_permission.yes_no_permission
                elif perm_key == 'payment_setup':
                    show_payment_setup = role_permission.yes_no_permission
                elif perm_key == 'clock_in':
                    show_clock_in = role_permission.yes_no_permission
            except RolePermission.DoesNotExist:
                continue  

    except SubUser.DoesNotExist:
        allow_access = True
        show_weekly_menu = True
        show_inventory = True
        show_milk_inventory = True
        show_meal_count = True
        show_classroom_options = True
        show_recipes = True
        show_sign_in = True
        show_daily_attendance = True
        show_rosters = True
        show_permissions = True
        show_menu_rules = True
        show_billing = True
        show_payment_setup = True
        show_clock_in = True

    if not allow_access:
        return redirect('no_access')
    
    # Process the invitation form
    if request.method == 'POST':
        form = InvitationForm(request.POST)
        if form.is_valid():
            email = form.cleaned_data['email']
            role = form.cleaned_data['role']
            token = str(uuid.uuid4())  # Generate a unique token

            # Create the invitation instance
            invitation = Invitation.objects.create(
                email=email,
                role=role,
                invited_by=request.user,
                token=token
            )

            # Create the invitation link
            invitation_link = f"http://127.0.0.1:8000/accept-invitation/{token}/"

            # Send the email
            send_mail(
                'Invitation to Join',
                f'You have been invited to join with role: {role.name}. Click the link to accept: {invitation_link}',
                'from@example.com',  # Replace with your sender email
                [email],
                fail_silently=False,
            )

            success_message = "Invitation email sent successfully."  # Set success message

    else:
        form = InvitationForm()  # Initialize the form if not a POST request

    # Render the template with the form, success message, and permission flags
    return render(request, 'send-invitations.html', {
        'form': form,
        'success_message': success_message,
        'show_weekly_menu': show_weekly_menu,
        'show_inventory': show_inventory,
        'show_milk_inventory': show_milk_inventory,
        'show_meal_count': show_meal_count,
        'show_classroom_options': show_classroom_options,
        'show_recipes': show_recipes,
        'show_sign_in': show_sign_in,
        'show_daily_attendance': show_daily_attendance,
        'show_rosters': show_rosters,
        'show_permissions': show_permissions,
        'show_menu_rules': show_menu_rules,
        'show_billing': show_billing,            
        'show_payment_setup': show_payment_setup,
        'show_clock_in': show_clock_in, 
    })

def accept_invitation(request, token):
    User = get_user_model()

    try:
        invitation = Invitation.objects.get(token=token)
        
        if request.method == 'POST':
            # Check if a user with the given email already exists
            existing_user = User.objects.filter(email=invitation.email).first()
            if existing_user:
                return render(request, 'already_accepted.html', {'user': existing_user})

            # Extract the form data
            first_name = request.POST.get('first_name')
            last_name = request.POST.get('last_name')
            email = request.POST.get('email')
            username = request.POST.get('username')
            password = request.POST.get('password1')  # Use password1 as the password

            # Create the user account for the invited user
            user = User.objects.create_user(
                username=username, 
                email=email,  
                password=password,
                first_name=first_name,
                last_name=last_name
            )

            # Assign the selected role to the new user
            user.groups.add(invitation.role)

            # Create a SubUser instance linking to the MainUser who sent the invitation and add the role
            SubUser.objects.create(user=user, main_user=invitation.invited_by, role=invitation.role)

            # Optionally, delete the invitation after it has been accepted
            invitation.delete()
            return redirect('login')  # Redirect to the login page

    except Invitation.DoesNotExist:
        return render(request, 'invalid_invitation.html')  # Handle invalid invitation

    return render(request, 'accept_invitation.html', {'invitation': invitation})

def invalid_invitation(request):
    return render(request, 'invalid_invitation.html')

@login_required
def permissions(request):
    allow_access = False

    show_weekly_menu = False
    show_inventory = False
    show_milk_inventory = False
    show_meal_count = False
    show_classroom_options = False
    show_recipes = False
    show_sign_in = False
    show_daily_attendance = False
    show_rosters = False
    show_permissions = False  
    show_menu_rules = False  
    show_billing = False          
    show_payment_setup = False
    show_clock_in = False

    try:
        # Check if the user is a SubUser
        try:
            sub_user = SubUser.objects.get(user=request.user)
            user_role_id = sub_user.group_id.id
            group_id = sub_user.group_id.id
        except SubUser.DoesNotExist:
            user_role_id = 1  # Assuming main users have role id 1
            group_id = 1

        required_permission_id = 157  # Permission ID for permissions view

        # Check if the SubUser (or main user) has permission to access this view
        try:
            role_permission = RolePermission.objects.get(role_id=group_id, permission_id=required_permission_id)
            allow_access = role_permission.yes_no_permission
        except RolePermission.DoesNotExist:
            allow_access = False  # No specific permission set for this role

        permissions_ids = {
            'weekly_menu': 271,
            'inventory': 272,
            'milk_inventory': 270,
            'meal_count': 269,
            'classroom_options': 268,
            'recipes': 267,
            'sign_in': 273,
            'daily_attendance': 274,
            'rosters': 275,
            'permissions': 157, 
            'menu_rules': 266,
            'billing': 331,          
            'payment_setup': 332,  
            'clock_in': 337, 
        }

        # Dynamically check each permission
        for perm_key, perm_id in permissions_ids.items():
            try:
                role_permission = RolePermission.objects.get(role_id=group_id, permission_id=perm_id)
                if perm_key == 'weekly_menu':
                    show_weekly_menu = role_permission.yes_no_permission
                elif perm_key == 'inventory':
                    show_inventory = role_permission.yes_no_permission
                elif perm_key == 'milk_inventory':
                    show_milk_inventory = role_permission.yes_no_permission
                elif perm_key == 'meal_count':
                    show_meal_count = role_permission.yes_no_permission
                elif perm_key == 'permissions':
                    show_permissions = role_permission.yes_no_permission
                elif perm_key == 'menu_rules':
                    show_menu_rules = role_permission.yes_no_permission
                elif perm_key == 'classroom_options':
                    show_classroom_options = role_permission.yes_no_permission
                elif perm_key == 'recipes':
                    show_recipes = role_permission.yes_no_permission
                elif perm_key == 'sign_in':
                    show_sign_in = role_permission.yes_no_permission
                elif perm_key == 'daily_attendance':
                    show_daily_attendance = role_permission.yes_no_permission
                elif perm_key == 'rosters':
                    show_rosters = role_permission.yes_no_permission
                elif perm_key == 'billing':
                    show_billing = role_permission.yes_no_permission
                elif perm_key == 'payment_setup':
                    show_payment_setup = role_permission.yes_no_permission
                elif perm_key == 'clock_in':
                    show_clock_in = role_permission.yes_no_permission  
            except RolePermission.DoesNotExist:
                continue  

    except SubUser.DoesNotExist:
        # If user is not a SubUser, grant access by default (assuming main user)
        allow_access = True
        show_weekly_menu = True
        show_inventory = True
        show_milk_inventory = True
        show_meal_count = True
        show_classroom_options = True
        show_recipes = True
        show_sign_in = True
        show_daily_attendance = True
        show_rosters = True
        show_permissions = True
        show_menu_rules = True
        show_billing = True
        show_payment_setup = True
        show_clock_in = True

    # Redirect to 'no_access' page if access is not allowed
    if not allow_access:
        return redirect('no_access')

    if request.method == "POST":
        for group_id, permissions in request.POST.items():
            if group_id.startswith("permission_"):
                parts = group_id.split("_")
                if len(parts) >= 3:
                    grp_id, permission_id = parts[1], parts[2]
                    grp_id, permission_id = int(grp_id), int(permission_id)
                    try:
                        role_permission = RolePermission.objects.get(role_id=grp_id, permission_id=permission_id)
                        role_permission.yes_no_permission = True if permissions == "on" else False
                        role_permission.save()
                    except RolePermission.DoesNotExist:
                        pass  # Silent fail, or consider adding a user-friendly message if needed

        return redirect('permissions')

    # Fetch groups and order them alphabetically by name
    groups = Group.objects.exclude(name__in=["Owner", "Parent", "Free User"]).order_by('name')  # Order by name

    role_permissions = defaultdict(list)

    for group in groups:
        group_role_id = group.id
        role_permissions_for_group = RolePermission.objects.filter(role_id=group_role_id).order_by('permission__name')

        for role_permission in role_permissions_for_group:
            permission = role_permission.permission

            # Apply role-based filtering:
            # If the current user's role (user_role_id) is lower than the group's role, show all (true & false).
            # If the roles are equal, show only permissions that are True.
            if user_role_id < group_role_id:
                role_permissions[group_role_id].append({
                    'id': permission.id,
                    'permission_name': permission.name,
                    'has_permission': role_permission.yes_no_permission
                })
            elif user_role_id == group_role_id:
                if role_permission.yes_no_permission:
                    role_permissions[group_role_id].append({
                        'id': permission.id,
                        'permission_name': permission.name,
                        'has_permission': role_permission.yes_no_permission
                    })

    return render(request, 'permissions.html', {
        'groups': groups,
        'role_permissions': json.dumps(role_permissions),
        'show_weekly_menu': show_weekly_menu,
        'show_inventory': show_inventory,
        'show_milk_inventory': show_milk_inventory,
        'show_meal_count': show_meal_count,
        'show_classroom_options': show_classroom_options,
        'show_recipes': show_recipes,
        'show_sign_in': show_sign_in,
        'show_daily_attendance': show_daily_attendance,
        'show_rosters': show_rosters,
        'show_permissions': show_permissions,
        'show_menu_rules': show_menu_rules,
        'show_billing': show_billing,            
        'show_payment_setup': show_payment_setup,
        'show_clock_in': show_clock_in, 
    })

def save_permissions(request):
    if request.method == "POST":
        for key, value in request.POST.items():
            if key.startswith("permission_"):
                parts = key.split("_")
                if len(parts) == 3:
                    permission_id, group_id = int(parts[1]), int(parts[2])
                    try:
                        role_permission = RolePermission.objects.get(role_id=group_id, permission_id=permission_id)
                        role_permission.yes_no_permission = True if value == "True" else False
                        role_permission.save()
                    except RolePermission.DoesNotExist:
                        pass  # Silent fail

    return redirect('permissions')

@login_required
def no_access(request):
    success_message = "" 
    allow_access = False

    # Default all permissions to False
    show_weekly_menu = False
    show_inventory = False
    show_milk_inventory = False
    show_meal_count = False
    show_classroom_options = False
    show_recipes = False
    show_sign_in = False
    show_daily_attendance = False
    show_rosters = False
    show_permissions = False  
    show_menu_rules = False  
    show_billing = False          
    show_payment_setup = False
    show_clock_in = False

    try:
        # Check if the user is a SubUser
        sub_user = SubUser.objects.get(user=request.user)
        group_id = sub_user.group_id.id

        permissions_ids = {
            'weekly_menu': 271,
            'inventory': 272,
            'milk_inventory': 270,
            'meal_count': 269,
            'classroom_options': 268,
            'recipes': 267,
            'sign_in': 273,
            'daily_attendance': 274,
            'rosters': 275,
            'permissions': 157, 
            'menu_rules': 266,
            'billing': 331,          
            'payment_setup': 332,   
            'clock_in': 337,
        }

        # Dynamically check each permission
        for perm_key, perm_id in permissions_ids.items():
            try:
                role_permission = RolePermission.objects.get(role_id=group_id, permission_id=perm_id)
                if perm_key == 'weekly_menu':
                    show_weekly_menu = role_permission.yes_no_permission
                elif perm_key == 'inventory':
                    show_inventory = role_permission.yes_no_permission
                elif perm_key == 'milk_inventory':
                    show_milk_inventory = role_permission.yes_no_permission
                elif perm_key == 'meal_count':
                    show_meal_count = role_permission.yes_no_permission
                elif perm_key == 'permissions':
                    show_permissions = role_permission.yes_no_permission
                elif perm_key == 'menu_rules':
                    show_menu_rules = role_permission.yes_no_permission
                elif perm_key == 'classroom_options':
                    show_classroom_options = role_permission.yes_no_permission
                elif perm_key == 'recipes':
                    show_recipes = role_permission.yes_no_permission
                elif perm_key == 'sign_in':
                    show_sign_in = role_permission.yes_no_permission
                elif perm_key == 'daily_attendance':
                    show_daily_attendance = role_permission.yes_no_permission
                elif perm_key == 'rosters':
                    show_rosters = role_permission.yes_no_permission
                elif perm_key == 'billing':
                    show_billing = role_permission.yes_no_permission
                elif perm_key == 'payment_setup':
                    show_payment_setup = role_permission.yes_no_permission
                elif perm_key == 'clock_in':
                    show_clock_in = role_permission.yes_no_permission
            except RolePermission.DoesNotExist:
                continue  

    except SubUser.DoesNotExist:
        allow_access = True
        # If no SubUser is found, enable all permissions
        show_weekly_menu = True
        show_inventory = True
        show_milk_inventory = True
        show_meal_count = True
        show_classroom_options = True
        show_recipes = True
        show_sign_in = True
        show_daily_attendance = True
        show_rosters = True
        show_permissions = True
        show_menu_rules = True
        show_billing = True
        show_payment_setup = True
        show_clock_in = True

    # Remove this redirect as it causes the loop
    # if not allow_access:
    #     return redirect('no_access')

    # Directly render the no_access.html template
    return render(request, 'no_access.html', {
        'show_weekly_menu': show_weekly_menu,
        'show_inventory': show_inventory,
        'show_milk_inventory': show_milk_inventory,
        'show_meal_count': show_meal_count,
        'show_classroom_options': show_classroom_options,
        'show_recipes': show_recipes,
        'show_sign_in': show_sign_in,
        'show_daily_attendance': show_daily_attendance,
        'show_rosters': show_rosters,
        'show_permissions': show_permissions,
        'show_menu_rules': show_menu_rules,
        'show_billing': show_billing,            
        'show_payment_setup': show_payment_setup,
        'show_clock_in': show_clock_in, 
    })

@login_required
def inbox(request):
    # Get all users excluding the logged-in user
    all_users = MainUser.objects.exclude(id=request.user.id)

    # Get all conversations where the logged-in user is either the sender or recipient
    conversations = Conversation.objects.filter(
        Q(sender=request.user) | Q(recipient=request.user)
    )

    # Annotate each conversation with the latest message timestamp (fixing the ordering)
    conversations = conversations.annotate(
        latest_message_timestamp=Max('messages__timestamp')
    ).order_by('-latest_message_timestamp')

    # Populate recipients: users the logged-in user hasn't had a conversation with
    conversation_users = set()
    for conversation in conversations:
        conversation_users.add(conversation.sender)
        conversation_users.add(conversation.recipient)

    recipients = all_users.exclude(id__in=[user.id for user in conversation_users])

    # Initialize permissions variables
    show_weekly_menu = False
    show_inventory = False
    show_milk_inventory = False
    show_meal_count = False
    show_classroom_options = False
    show_recipes = False
    show_sign_in = False
    show_daily_attendance = False
    show_rosters = False
    show_permissions = False
    show_menu_rules = False
    show_billing = False
    show_payment_setup = False
    show_clock_in = False

    try:
        # Check if the user is a SubUser
        sub_user = SubUser.objects.get(user=request.user)
        group_id = sub_user.group_id.id

        # Dynamically check permissions
        permissions_ids = {
            'weekly_menu': 271,
            'inventory': 272,
            'milk_inventory': 270,
            'meal_count': 269,
            'classroom_options': 268,
            'recipes': 267,
            'sign_in': 273,
            'daily_attendance': 274,
            'rosters': 275,
            'permissions': 157,
            'menu_rules': 266,
            'billing': 331,
            'payment_setup': 332,
            'clock_in': 337,
        }

        for perm_key, perm_id in permissions_ids.items():
            try:
                role_permission = RolePermission.objects.get(role_id=group_id, permission_id=perm_id)
                if perm_key == 'weekly_menu':
                    show_weekly_menu = role_permission.yes_no_permission
                elif perm_key == 'inventory':
                    show_inventory = role_permission.yes_no_permission
                elif perm_key == 'milk_inventory':
                    show_milk_inventory = role_permission.yes_no_permission
                elif perm_key == 'meal_count':
                    show_meal_count = role_permission.yes_no_permission
                elif perm_key == 'permissions':
                    show_permissions = role_permission.yes_no_permission
                elif perm_key == 'menu_rules':
                    show_menu_rules = role_permission.yes_no_permission
                elif perm_key == 'classroom_options':
                    show_classroom_options = role_permission.yes_no_permission
                elif perm_key == 'recipes':
                    show_recipes = role_permission.yes_no_permission
                elif perm_key == 'sign_in':
                    show_sign_in = role_permission.yes_no_permission
                elif perm_key == 'daily_attendance':
                    show_daily_attendance = role_permission.yes_no_permission
                elif perm_key == 'rosters':
                    show_rosters = role_permission.yes_no_permission
                elif perm_key == 'billing':
                    show_billing = role_permission.yes_no_permission
                elif perm_key == 'payment_setup':
                    show_payment_setup = role_permission.yes_no_permission
                elif perm_key == 'clock_in':
                    show_clock_in = role_permission.yes_no_permission  
            except RolePermission.DoesNotExist:
                continue  

    except SubUser.DoesNotExist:
        # If the user is not a SubUser, assign default permissions or full access for MainUser
        # For example, assuming MainUser should have full access, we assign all permissions:
        show_weekly_menu = True
        show_inventory = True
        show_milk_inventory = True
        show_meal_count = True
        show_classroom_options = True
        show_recipes = True
        show_sign_in = True
        show_daily_attendance = True
        show_rosters = True
        show_permissions = True
        show_menu_rules = True
        show_billing = True
        show_payment_setup = True
        show_clock_in = True

    # Render the inbox page, adding the permission variables
    return render(request, 'messaging/inbox.html', {
        'conversations': conversations,
        'recipients': recipients,
        'show_weekly_menu': show_weekly_menu,
        'show_inventory': show_inventory,
        'show_milk_inventory': show_milk_inventory,
        'show_meal_count': show_meal_count,
        'show_classroom_options': show_classroom_options,
        'show_recipes': show_recipes,
        'show_sign_in': show_sign_in,
        'show_daily_attendance': show_daily_attendance,
        'show_rosters': show_rosters,
        'show_permissions': show_permissions,
        'show_menu_rules': show_menu_rules,
        'show_billing': show_billing,
        'show_payment_setup': show_payment_setup,
        'show_clock_in': show_clock_in,
    })

@login_required
def conversation(request, user_id):
    # Retrieve the recipient's MainUser instance
    recipient = get_object_or_404(MainUser, id=user_id)
    
    # Check if a conversation already exists between the logged-in user and the recipient
    conversation = Conversation.objects.filter(
        (Q(sender=request.user) & Q(recipient=recipient)) |
        (Q(sender=recipient) & Q(recipient=request.user))
    ).first()
    
    # If no conversation exists, create a new one
    if not conversation:
        conversation = Conversation.objects.create(sender=request.user, recipient=recipient)
    
    # Fetch all messages between the logged-in user and the recipient, ordered by timestamp
    messages = Message.objects.filter(conversation=conversation).order_by('timestamp')
    
    # Fetch all conversations involving the logged-in user and sort by the other user's first name
    conversations = Conversation.objects.filter(
        Q(sender=request.user) | Q(recipient=request.user)
    ).distinct()

    # Sort conversations by the other user's first name
    conversations = sorted(
        conversations,
        key=lambda conv: conv.recipient.first_name if conv.sender == request.user else conv.sender.first_name
    )
    
    # Initialize permission variables
    show_weekly_menu = False
    show_inventory = False
    show_milk_inventory = False
    show_meal_count = False
    show_classroom_options = False
    show_recipes = False
    show_sign_in = False
    show_daily_attendance = False
    show_rosters = False
    show_permissions = False
    show_menu_rules = False
    show_billing = False
    show_payment_setup = False
    show_clock_in = False

    try:
        # Check if the user is a SubUser
        sub_user = SubUser.objects.get(user=request.user)
        group_id = sub_user.group_id.id

        # Dynamically check permissions
        permissions_ids = {
            'weekly_menu': 271,
            'inventory': 272,
            'milk_inventory': 270,
            'meal_count': 269,
            'classroom_options': 268,
            'recipes': 267,
            'sign_in': 273,
            'daily_attendance': 274,
            'rosters': 275,
            'permissions': 157,
            'menu_rules': 266,
            'billing': 331,
            'payment_setup': 332,
            'clock_in': 337,
        }

        for perm_key, perm_id in permissions_ids.items():
            try:
                role_permission = RolePermission.objects.get(role_id=group_id, permission_id=perm_id)
                if perm_key == 'weekly_menu':
                    show_weekly_menu = role_permission.yes_no_permission
                elif perm_key == 'inventory':
                    show_inventory = role_permission.yes_no_permission
                elif perm_key == 'milk_inventory':
                    show_milk_inventory = role_permission.yes_no_permission
                elif perm_key == 'meal_count':
                    show_meal_count = role_permission.yes_no_permission
                elif perm_key == 'permissions':
                    show_permissions = role_permission.yes_no_permission
                elif perm_key == 'menu_rules':
                    show_menu_rules = role_permission.yes_no_permission
                elif perm_key == 'classroom_options':
                    show_classroom_options = role_permission.yes_no_permission
                elif perm_key == 'recipes':
                    show_recipes = role_permission.yes_no_permission
                elif perm_key == 'sign_in':
                    show_sign_in = role_permission.yes_no_permission
                elif perm_key == 'daily_attendance':
                    show_daily_attendance = role_permission.yes_no_permission
                elif perm_key == 'rosters':
                    show_rosters = role_permission.yes_no_permission
                elif perm_key == 'billing':
                    show_billing = role_permission.yes_no_permission
                elif perm_key == 'payment_setup':
                    show_payment_setup = role_permission.yes_no_permission
                elif perm_key == 'clock_in':
                    show_clock_in = role_permission.yes_no_permission  
            except RolePermission.DoesNotExist:
                continue  

    except SubUser.DoesNotExist:
        # If the user is not a SubUser, assign default permissions or full access for MainUser
        # For example, assuming MainUser should have full access, we assign all permissions:
        show_weekly_menu = True
        show_inventory = True
        show_milk_inventory = True
        show_meal_count = True
        show_classroom_options = True
        show_recipes = True
        show_sign_in = True
        show_daily_attendance = True
        show_rosters = True
        show_permissions = True
        show_menu_rules = True
        show_billing = True
        show_payment_setup = True
        show_clock_in = True

    if request.method == 'POST':
        form = MessageForm(request.POST)
        if form.is_valid():
            new_message = form.save(commit=False)
            new_message.sender = request.user
            new_message.recipient = recipient
            new_message.conversation = conversation
            new_message.save()
            if request.headers.get('x-requested-with') == 'XMLHttpRequest':
                return JsonResponse({
                    'sender': new_message.sender.first_name,
                    'content': new_message.content,
                    'timestamp': new_message.timestamp.strftime('%Y-%m-%d %H:%M:%S')
                })
            return redirect('conversation', user_id=recipient.id)
    else:
        form = MessageForm()

    if request.headers.get('x-requested-with') == 'XMLHttpRequest':
        return render(request, 'messaging/conversation.html', {
            'form': form,
            'recipient': recipient,
            'messages': messages,
        })

    return render(request, 'messaging/conversation.html', {
        'form': form,
        'recipient': recipient,
        'messages': messages,  # Pass the messages to the template
        'conversations': conversations,  # Pass the sorted conversations to the template
        'show_weekly_menu': show_weekly_menu,
        'show_inventory': show_inventory,
        'show_milk_inventory': show_milk_inventory,
        'show_meal_count': show_meal_count,
        'show_classroom_options': show_classroom_options,
        'show_recipes': show_recipes,
        'show_sign_in': show_sign_in,
        'show_daily_attendance': show_daily_attendance,
        'show_rosters': show_rosters,
        'show_permissions': show_permissions,
        'show_menu_rules': show_menu_rules,
        'show_billing': show_billing,
        'show_payment_setup': show_payment_setup,
        'show_clock_in': show_clock_in,
    })

def start_conversation(request, user_id):
    User = get_user_model()
    recipient = get_object_or_404(User, id=user_id)
    conversation, created = Conversation.objects.get_or_create(
        sender=request.user, recipient=recipient
    )
    return redirect('conversation', user_id=recipient.id)


@login_required 
def payment_view(request, subuser_id=None):
    # Detect if the request is from a mobile device
    is_mobile = any(device in request.META.get('HTTP_USER_AGENT', '').lower() for device in [
        'iphone', 'android', 'mobile', 'cordova', 'tablet', 'ipod', 'windows phone'
    ])
    
    # If it's a mobile request, redirect to the app_redirect page
    if is_mobile:
        return HttpResponseRedirect(reverse('app_redirect'))

    # Initialize permissions (omitted for brevity; same as before)
    allow_access = False
    show_weekly_menu = False
    show_inventory = False
    show_milk_inventory = False
    show_meal_count = False
    show_classroom_options = False
    show_recipes = False
    show_sign_in = False
    show_daily_attendance = False
    show_rosters = False
    show_permissions = False
    show_menu_rules = False
    show_billing = False
    show_payment_setup = False
    show_clock_in = False

    try:
        # Check if the user is a SubUser
        sub_user = SubUser.objects.get(user=request.user)
        group_id = sub_user.group_id.id
        required_permission_id = 331  # Permission ID for "billing"

        # Check for required permission
        allow_access = RolePermission.objects.filter(
            role_id=group_id,
            permission_id=required_permission_id,
            yes_no_permission=True
        ).exists()

        # Check additional permissions
        permissions_ids = {
            'weekly_menu': 271,
            'inventory': 272,
            'milk_inventory': 270,
            'meal_count': 269,
            'classroom_options': 268,
            'recipes': 267,
            'sign_in': 273,
            'daily_attendance': 274,
            'rosters': 275,
            'permissions': 157,
            'menu_rules': 266,
            'billing': 331,
            'payment_setup': 332,
            'clock_in': 337,
        }

        for perm_key, perm_id in permissions_ids.items():
            has_permission = RolePermission.objects.filter(
                role_id=group_id,
                permission_id=perm_id,
                yes_no_permission=True
            ).exists()
            if perm_key == 'weekly_menu':
                show_weekly_menu = has_permission
            elif perm_key == 'inventory':
                show_inventory = has_permission
            elif perm_key == 'milk_inventory':
                show_milk_inventory = has_permission
            elif perm_key == 'meal_count':
                show_meal_count = has_permission
            elif perm_key == 'classroom_options':
                show_classroom_options = has_permission
            elif perm_key == 'recipes':
                show_recipes = has_permission
            elif perm_key == 'sign_in':
                show_sign_in = has_permission
            elif perm_key == 'daily_attendance':
                show_daily_attendance = has_permission
            elif perm_key == 'rosters':
                show_rosters = has_permission
            elif perm_key == 'permissions':
                show_permissions = has_permission
            elif perm_key == 'menu_rules':
                show_menu_rules = has_permission
            elif perm_key == 'billing':
                show_billing = has_permission
            elif perm_key == 'payment_setup':
                show_payment_setup = has_permission
            elif perm_key == 'clock_in':
                show_clock_in = has_permission

    except SubUser.DoesNotExist:
        # If user is not a SubUser, assume it's a main user and allow access
        allow_access = True
        show_weekly_menu = True
        show_inventory = True
        show_milk_inventory = True
        show_meal_count = True
        show_classroom_options = True
        show_recipes = True
        show_sign_in = True
        show_daily_attendance = True
        show_rosters = True
        show_permissions = True
        show_menu_rules = True
        show_billing = True
        show_payment_setup = True
        show_clock_in = True

    # Redirect if user does not have the required permission
    if not allow_access:
        return redirect('no_access')

    main_user = get_user_for_view(request)
    if not main_user.stripe_secret_key:
        main_user.stripe_secret_key = settings.STRIPE_SECRET_KEY  # Fallback to default test key

    stripe.api_key = main_user.stripe_secret_key

    # Handle POST request for creating a payment (unchanged)
    if request.method == "POST" and subuser_id:
        subuser = get_object_or_404(SubUser, id=subuser_id, main_user=main_user)
        amount = float(request.POST.get('amount'))
        payment_method = request.POST.get('payment_method')

        existing_payment = Payment.objects.filter(
            subuser=subuser,
            amount=amount,
            status='pending'
        ).first()
        if existing_payment:
            return JsonResponse({
                'error': 'Payment intent already exists for this subuser and amount.'
            }, status=400)

        if payment_method in ['cash', 'check']:
            payment = Payment.objects.create(
                subuser=subuser,
                amount=amount,
                status='paid',  # Mark as paid
                payment_method=payment_method,
            )
            payment.save()
            return JsonResponse({'success': 'Payment recorded successfully'})

        try:
            payment_intent = stripe.PaymentIntent.create(
                amount=int(amount * 100),  # Convert to cents
                currency="usd",
                description=f"Payment for {subuser.user.first_name} {subuser.user.last_name}",
                receipt_email=subuser.main_user.email,
            )
            return JsonResponse({'client_secret': payment_intent['client_secret']})
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=500)

    # Get all subusers belonging to the main user
    subusers = SubUser.objects.filter(main_user=main_user, user__groups__id=5)
    
    # Build a queryset of payments for these subusers
    payments = Payment.objects.filter(subuser__in=subusers).select_related(
        'subuser', 'subuser__user', 'subuser__student'
    ).order_by('due_date')
    
    # Apply filtering based on GET parameters
    status_filter = request.GET.get('status')
    if status_filter:
        payments = payments.filter(status=status_filter)
    
    start_date_filter = request.GET.get('start_date')
    if start_date_filter:
        payments = payments.filter(start_date__gte=start_date_filter)
    
    end_date_filter = request.GET.get('end_date')
    if end_date_filter:
        payments = payments.filter(due_date__lte=end_date_filter)

    context = {
        'stripe_public_key': main_user.stripe_public_key,
        'payments': payments,
        'status_filter': status_filter or '',
        'start_date_filter': start_date_filter or '',
        'end_date_filter': end_date_filter or '',
        'subusers': subusers,
        'show_weekly_menu': show_weekly_menu,
        'show_inventory': show_inventory,
        'show_milk_inventory': show_milk_inventory,
        'show_meal_count': show_meal_count,
        'show_classroom_options': show_classroom_options,
        'show_recipes': show_recipes,
        'show_sign_in': show_sign_in,
        'show_daily_attendance': show_daily_attendance,
        'show_rosters': show_rosters,
        'show_permissions': show_permissions,
        'show_menu_rules': show_menu_rules,
        'show_billing': show_billing,
        'show_payment_setup': show_payment_setup,
        'show_clock_in': show_clock_in, 
    }
    return render(request, 'payment.html', context)

@login_required
def create_payment(request):
    if request.method == 'POST':
        try:
            # Extract form data
            subuser_id = request.POST.get('subuser')
            frequency = request.POST.get('frequency')
            rate = request.POST.get('rate')
            start_date = request.POST.get('start_date')
            due_date = request.POST.get('due_date')
            end_date = request.POST.get('end_date')
            notes = request.POST.get('notes')

            # Get SubUser and Student
            subuser = get_object_or_404(SubUser, id=subuser_id)
            student = subuser.student  # Get the student from SubUser (adjust based on your model relationships)

            # Create Payment
            payment = Payment.objects.create(
                subuser=subuser,
                student=student,  # REQUIRED FIELD
                amount=Decimal(rate),
                frequency=frequency,
                start_date=start_date,
                due_date=due_date,
                end_date=None if end_date == '' else end_date,
                notes=notes,
                balance=Decimal(rate),
                next_invoice_date=due_date  # Set initial next_invoice_date to trigger recurring logic
            )
            messages.success(request, 'Recurring invoice created successfully.')
            return redirect('payment')
        except Exception as e:
            messages.error(request, f"Error creating payment: {e}")
            return redirect('payment')

@csrf_exempt
@login_required
def create_payment_intent(request):
    if request.method == 'POST':
        try:
            print(f"Received request body: {request.body}")  # Debugging step

            data = json.loads(request.body)
            amount = data.get('amount')  # Get amount from JSON

            if not amount:
                return JsonResponse({'error': 'Amount is required'}, status=400)

            amount = float(amount)  # Convert to float for safety

            # Ensure the user is either a SubUser or a MainUser
            try:
                subuser = request.user.subuser
                main_user = subuser.main_user
                description = f"{subuser.user.username}'s wallet deposit for {main_user.company_name}"
            except SubUser.DoesNotExist:
                if isinstance(request.user, MainUser):
                    main_user = request.user
                    description = f"Wallet deposit for {main_user.company_name}"
                else:
                    return JsonResponse({'error': 'User is neither a SubUser nor a MainUser'}, status=400)

            stripe_secret_key = main_user.stripe_secret_key

            if not stripe_secret_key:
                return JsonResponse({'error': 'Stripe secret key is missing for the user.'}, status=400)

            print(f"Using Stripe Secret Key: {stripe_secret_key}")  # Debugging step
            print(f"Stripe Secret Key: {stripe_secret_key}")  # Debugging line

            stripe.api_key = stripe_secret_key  # Set Stripe API key dynamically

            # Create a PaymentIntent
            payment_intent = stripe.PaymentIntent.create(
                amount=int(amount * 100),  # Convert to cents
                currency="usd",
                description=description,
                payment_method_types=["card"],
            )

            return JsonResponse({'client_secret': payment_intent.client_secret})

        except json.JSONDecodeError:
            return JsonResponse({'error': 'Invalid JSON format in request body'}, status=400)
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=500)

    return JsonResponse({'error': 'Invalid request'}, status=400)

@csrf_exempt
def update_payment_status(request):
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            payment_id = data.get('payment_id')
            new_payment_amount = Decimal(data.get('amount_paid', '0'))

            # Retrieve the payment object and validate
            payment = Payment.objects.get(id=payment_id)
            if new_payment_amount <= 0:
                return JsonResponse({'error': 'Payment amount must be positive.'}, status=400)

            # Begin transaction for consistency
            with transaction.atomic():
                # Add the new payment amount to the existing amount_paid
                payment.amount_paid += new_payment_amount

                # Calculate new balance based on the updated amount_paid
                payment.balance = payment.amount - payment.amount_paid

                # Prioritize "Paid in Full" status if payment is fully made
                if payment.amount_paid >= payment.amount:
                    payment.status = 'Paid in Full'
                    payment.balance = Decimal(0)  # Fully paid, so no remaining balance
                # Only set to "Overdue" if payment is not fully made and due date is past
                elif payment.due_date < datetime.now().date() and payment.balance > 0:
                    payment.status = 'Overdue'
                # Preserve "Partial Payment" status if some amount is paid but not full
                elif payment.amount_paid > 0:
                    payment.status = 'Partial Payment'
                else:
                    payment.status = 'Pending'  # Ensure Pending for new invoices without payment

                # Save the updated payment
                payment.save()

            return JsonResponse({'success': 'Payment status updated successfully'})

        except Payment.DoesNotExist:
            return JsonResponse({'error': 'Payment not found'}, status=404)

        except Exception as e:
            return JsonResponse({'error': str(e)}, status=500)

    return JsonResponse({'error': 'Invalid request'}, status=400)

@csrf_exempt
def record_payment(request):
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            payment_id = data.get('payment_id')
            amount = Decimal(data.get('amount', '0'))
            payment_method = data.get('payment_method')
            notes = data.get('notes')

            # Retrieve the payment object
            payment = Payment.objects.get(id=payment_id)

            # Validate payment amount
            if amount <= 0:
                return JsonResponse({'error': 'Payment amount must be positive.'}, status=400)

            # Begin transaction for consistency
            with transaction.atomic():
                # Add the new payment amount to the existing amount_paid
                payment.amount_paid += amount

                # Calculate the new balance based on the updated amount_paid
                payment.balance = payment.amount - payment.amount_paid

                # Update the payment method and notes
                payment.payment_method = payment_method
                payment.notes = notes

                # Prioritize "Paid in Full" status if payment is fully made
                if payment.amount_paid >= payment.amount:
                    payment.status = 'Paid in Full'
                    payment.balance = Decimal(0)  # Fully paid, no remaining balance
                # Set "Overdue" if the payment is not fully made and the due date has passed
                elif payment.due_date < datetime.now().date() and payment.balance > 0:
                    payment.status = 'Overdue'
                # Preserve "Partial Payment" status if some amount is paid but not full
                elif payment.amount_paid > 0:
                    payment.status = 'Partial Payment'
                else:
                    payment.status = 'Pending'  # Ensure Pending for new invoices without payment

                # Save the updated payment
                payment.save()

            return JsonResponse({'success': 'Payment recorded and status updated successfully'})

        except Payment.DoesNotExist:
            return JsonResponse({'error': 'Payment not found'}, status=404)

        except Exception as e:
            return JsonResponse({'error': str(e)}, status=500)

    return JsonResponse({'error': 'Invalid request'}, status=400)

def apply_late_fee(request, payment_id):
    if request.method == 'POST':
        try:
            # Fetch the Payment object by ID
            payment = get_object_or_404(Payment, id=payment_id)

            # Retrieve the late fee value from the request (default to 10.00)
            late_fee = Decimal(request.POST.get('late_fee', '10.00'))

            # Add the late fee to the balance and late fees
            payment.late_fees += late_fee
            payment.balance += late_fee

            # Save the updated payment instance
            payment.save()

            return JsonResponse({'success': True, 'message': 'Late fee applied successfully!'})
        except Exception as e:
            return JsonResponse({'success': False, 'message': str(e)})
    return JsonResponse({'success': False, 'message': 'Invalid request method'})

def stripe_login(request):
    allow_access = False
    show_weekly_menu = False
    show_inventory = False
    show_milk_inventory = False
    show_meal_count = False
    show_classroom_options = False
    show_recipes = False
    show_sign_in = False
    show_daily_attendance = False
    show_rosters = False
    show_permissions = False
    show_menu_rules = False
    show_billing = False
    show_payment_setup = False
    show_clock_in = False

    try:
        # Check if the user is a SubUser
        sub_user = SubUser.objects.get(user=request.user)
        group_id = sub_user.group_id.id
        required_permission_id = 332

        try:
            role_permission = RolePermission.objects.get(role_id=group_id, permission_id=required_permission_id)
            allow_access = role_permission.yes_no_permission
        except RolePermission.DoesNotExist:
            allow_access = False

        # Check additional permissions based on the same group_id
        permissions_ids = {
            'weekly_menu': 271,
            'inventory': 272,
            'milk_inventory': 270,
            'meal_count': 269,
            'classroom_options': 268,
            'recipes': 267,
            'sign_in': 273,
            'daily_attendance': 274,
            'rosters': 275,
            'permissions': 157, 
            'menu_rules': 266,
            'billing': 331,          
            'payment_setup': 332, 
            'clock_in': 337,  
        }

        # Dynamically check each permission
        for perm_key, perm_id in permissions_ids.items():
            try:
                role_permission = RolePermission.objects.get(role_id=group_id, permission_id=perm_id)
                if perm_key == 'weekly_menu':
                    show_weekly_menu = role_permission.yes_no_permission
                elif perm_key == 'inventory':
                    show_inventory = role_permission.yes_no_permission
                elif perm_key == 'milk_inventory':
                    show_milk_inventory = role_permission.yes_no_permission
                elif perm_key == 'meal_count':
                    show_meal_count = role_permission.yes_no_permission
                elif perm_key == 'permissions':
                    show_permissions = role_permission.yes_no_permission
                elif perm_key == 'menu_rules':
                    show_menu_rules = role_permission.yes_no_permission
                elif perm_key == 'classroom_options':
                    show_classroom_options = role_permission.yes_no_permission
                elif perm_key == 'recipes':
                    show_recipes = role_permission.yes_no_permission
                elif perm_key == 'sign_in':
                    show_sign_in = role_permission.yes_no_permission
                elif perm_key == 'daily_attendance':
                    show_daily_attendance = role_permission.yes_no_permission
                elif perm_key == 'rosters':
                    show_rosters = role_permission.yes_no_permission
                elif perm_key == 'billing':
                    show_billing = role_permission.yes_no_permission
                elif perm_key == 'payment_setup':
                    show_payment_setup = role_permission.yes_no_permission
                elif perm_key == 'clock_in':
                    show_clock_in = role_permission.yes_no_permission
            except RolePermission.DoesNotExist:
                continue  

    except SubUser.DoesNotExist:
        # If user is not a SubUser, grant access by default (assuming main user)
        allow_access = True
        show_weekly_menu = True
        show_inventory = True
        show_milk_inventory = True
        show_meal_count = True
        show_classroom_options = True
        show_recipes = True
        show_sign_in = True
        show_daily_attendance = True
        show_rosters = True
        show_permissions = True
        show_menu_rules = True
        show_billing = True
        show_payment_setup = True
        show_clock_in = True

    # Redirect to 'no_access' page if access is not allowed
    if not allow_access:
        return redirect('no_access')

    return render(request, 'stripe.html', {
        'show_weekly_menu': show_weekly_menu,
        'show_inventory': show_inventory,
        'show_milk_inventory': show_milk_inventory,
        'show_meal_count': show_meal_count,
        'show_classroom_options': show_classroom_options,
        'show_recipes': show_recipes,
        'show_sign_in': show_sign_in,
        'show_daily_attendance': show_daily_attendance,
        'show_rosters': show_rosters,
        'show_permissions': show_permissions,
        'show_menu_rules': show_menu_rules,
        'show_billing': show_billing,            
        'show_payment_setup': show_payment_setup,
        'show_clock_in': show_clock_in, 
    })

def get_stripe_keys(user):
    """
    Return the appropriate Stripe keys based on user connection status.
    """
    if user and hasattr(user, 'stripe_secret_key') and user.stripe_secret_key:
        return {
            "public_key": user.stripe_public_key,
            "secret_key": user.stripe_secret_key,
            "account_id": user.stripe_account_id,
        }
    # Fallback to platform defaults
    return {
        "public_key": settings.STRIPE_PUBLIC_KEY,
        "secret_key": settings.STRIPE_SECRET_KEY,
        "account_id": None,  # No account_id for the platform keys
    }

def stripe_connect(request):
    """Redirects the user to Stripe for account connection or creation."""
    stripe_keys = get_stripe_keys(request.user)  # Fetch appropriate keys

    stripe.api_key = stripe_keys["secret_key"]  # Set API key dynamically based on user keys or platform

    main_user = request.user  # Assuming request.user is an instance of MainUser
    
    # If you need to ensure the request.user is a MainUser:
    if isinstance(request.user, MainUser):
        user_email = main_user.email
    else:
        # Handle case if it's not a MainUser instance
        messages.error(request, "Invalid user. Please log in again.")
        return redirect('stripe')  # Redirect to an error or appropriate page

    if not main_user.stripe_account_id or "test_" in main_user.stripe_account_id:
        # Create a new Stripe account in the correct mode if none exists or if it's a test account
        try:
            account = stripe.Account.create(
                type="express",
                email=user_email,  # Use the MainUser's email
            )
            main_user.stripe_account_id = account.id
            main_user.save()
        except stripe.error.StripeError as e:
            error_message = e.error.message if hasattr(e, "error") else str(e)
            messages.error(request, f"Error creating Stripe account: {error_message}")
            return redirect('stripe')  # Redirect back to stripe.html

    # Ensure success and failure URLs use HTTPS
    base_url = 'https://23e4-174-93-62-247.ngrok-free.app'  # Replace this with your actual ngrok HTTPS URL
    success_url = f'{base_url}/stripe/?status=success'
    failure_url = f'{base_url}/stripe/?status=error'

    # Generate account link for onboarding
    try:
        account_link = stripe.AccountLink.create(
            account=main_user.stripe_account_id,
            failure_url=failure_url,
            success_url=success_url,
            type="account_onboarding",
        )
        return redirect(account_link.url)
    except stripe.error.StripeError as e:
        error_message = e.error.message if hasattr(e, "error") else str(e)
        messages.error(request, f"Error creating Stripe account link: {error_message}")
        return redirect('stripe')
    
def stripe_callback(request):
    """Handles the Stripe OAuth callback and stores the user's keys."""
    status = request.GET.get("status")
    if status == "success":
        try:
            # Retrieve the account details from Stripe
            account = stripe.Account.retrieve(request.user.stripe_account_id)

            # Optionally, fetch additional details if required
            # E.g., You might need to retrieve API keys via a connected account flow
            request.user.stripe_public_key = account.get('settings', {}).get('payouts', {}).get('debit_negative_balances')
            # Stripe does not expose secret keys through the API; those are specific to the account creation flow.
            request.user.save()

            messages.success(request, "Your Stripe account has been successfully connected.")
        except stripe.error.StripeError as e:
            messages.error(request, f"Error retrieving Stripe account details: {str(e)}")
    else:
        messages.error(request, "There was an error connecting your Stripe account.")

    return redirect('stripe')

@login_required
def clock_in(request):
    allow_access = False
    show_weekly_menu = False
    show_inventory = False
    show_milk_inventory = False
    show_meal_count = False
    show_classroom_options = False
    show_recipes = False
    show_sign_in = False
    show_daily_attendance = False
    show_rosters = False
    show_permissions = False
    show_menu_rules = False
    show_billing = False
    show_payment_setup = False
    show_clock_in = False

    try:
        # Check if the user is a SubUser
        sub_user = SubUser.objects.get(user=request.user)
        group_id = sub_user.group_id.id
        required_permission_id = 337  # Permission ID for clock_in view

        # Check if there is a RolePermission entry with 'yes_no_permission' set to True for this permission
        try:
            role_permission = RolePermission.objects.get(role_id=group_id, permission_id=required_permission_id)
            allow_access = role_permission.yes_no_permission
        except RolePermission.DoesNotExist:
            allow_access = False

        permissions_ids = {
            'weekly_menu': 271,
            'inventory': 272,
            'milk_inventory': 270,
            'meal_count': 269,
            'classroom_options': 268,
            'recipes': 267,
            'sign_in': 273,
            'daily_attendance': 274,
            'rosters': 275,
            'permissions': 157, 
            'menu_rules': 266,
            'billing': 331,          
            'payment_setup': 332,   
            'clock_in': 337, 
        }

        # Dynamically check each permission
        for perm_key, perm_id in permissions_ids.items():
            try:
                role_permission = RolePermission.objects.get(role_id=group_id, permission_id=perm_id)
                if perm_key == 'weekly_menu':
                    show_weekly_menu = role_permission.yes_no_permission
                elif perm_key == 'inventory':
                    show_inventory = role_permission.yes_no_permission
                elif perm_key == 'milk_inventory':
                    show_milk_inventory = role_permission.yes_no_permission
                elif perm_key == 'meal_count':
                    show_meal_count = role_permission.yes_no_permission
                elif perm_key == 'permissions':
                    show_permissions = role_permission.yes_no_permission
                elif perm_key == 'menu_rules':
                    show_menu_rules = role_permission.yes_no_permission
                elif perm_key == 'classroom_options':
                    show_classroom_options = role_permission.yes_no_permission
                elif perm_key == 'recipes':
                    show_recipes = role_permission.yes_no_permission
                elif perm_key == 'sign_in':
                    show_sign_in = role_permission.yes_no_permission
                elif perm_key == 'daily_attendance':
                    show_daily_attendance = role_permission.yes_no_permission
                elif perm_key == 'rosters':
                    show_rosters = role_permission.yes_no_permission
                elif perm_key == 'billing':
                    show_billing = role_permission.yes_no_permission
                elif perm_key == 'payment_setup':
                    show_payment_setup = role_permission.yes_no_permission
                elif perm_key == 'clock_in':
                    show_clock_in = role_permission.yes_no_permission  
            except RolePermission.DoesNotExist:
                continue  

    except SubUser.DoesNotExist:
        # If user is not a SubUser, grant access by default (assuming main user)
        allow_access = True
        show_weekly_menu = True
        show_inventory = True
        show_milk_inventory = True
        show_meal_count = True
        show_classroom_options = True
        show_recipes = True
        show_sign_in = True
        show_daily_attendance = True
        show_rosters = True
        show_permissions = True
        show_menu_rules = True
        show_billing = True
        show_payment_setup = True
        show_clock_in = True

    # Redirect to 'no_access' page if access is not allowed
    if not allow_access:
        return redirect('no_access')

    # Process the clock-in/out if POST request
    if request.method == 'POST':
        data = json.loads(request.body)
        code = data.get('code')

        # Find MainUser by the code
        try:
            main_user = MainUser.objects.get(code=code)
        except MainUser.DoesNotExist:
            return JsonResponse({'success': False, 'message': 'Invalid code for MainUser'})

        # Check if the code corresponds to a SubUser
        sub_user = None
        try:
            sub_user = SubUser.objects.get(user__id=main_user.id)
        except SubUser.DoesNotExist:
            pass  # No need to log or handle this separately

        # Look for the existing attendance record for the user
        try:
            record = TeacherAttendanceRecord.objects.get(user=main_user, subuser=sub_user, sign_out_time=None)
            # If there's an existing record, it's a clock-out, so we set the sign-out time
            record.sign_out_time = timezone.now()
            record.save()
            return JsonResponse({'success': True, 'message': f'{main_user.first_name} {main_user.last_name} clocked out successfully'})

        except TeacherAttendanceRecord.DoesNotExist:
            # If there's no open record, this is a clock-in
            record = TeacherAttendanceRecord(user=main_user, subuser=sub_user)
            record.save()
            return JsonResponse({'success': True, 'message': f'{main_user.first_name} {main_user.last_name} clocked in successfully'})

    return render(request, 'clock_in.html', {
        'show_weekly_menu': show_weekly_menu,
        'show_inventory': show_inventory,
        'show_milk_inventory': show_milk_inventory,
        'show_meal_count': show_meal_count,
        'show_classroom_options': show_classroom_options,
        'show_recipes': show_recipes,
        'show_sign_in': show_sign_in,
        'show_daily_attendance': show_daily_attendance,
        'show_rosters': show_rosters,
        'show_permissions': show_permissions,
        'show_menu_rules': show_menu_rules,
        'show_billing': show_billing,
        'show_payment_setup': show_payment_setup,
        'show_clock_in': show_clock_in, 
    })


@login_required
def time_sheet(request):

    # Detect if the request is from a mobile device
    is_mobile = any(device in request.META.get('HTTP_USER_AGENT', '').lower() for device in [
        'iphone', 'android', 'mobile', 'cordova', 'tablet', 'ipod', 'windows phone'
    ])
    
    # If it's a mobile request, redirect to the app_redirect page
    if is_mobile:
        return HttpResponseRedirect(reverse('app_redirect'))  # Ensure 'app_redirect' is defined in your URLs

    allow_access = False
    show_weekly_menu = False
    show_inventory = False
    show_milk_inventory = False
    show_meal_count = False
    show_classroom_options = False
    show_recipes = False
    show_sign_in = False
    show_daily_attendance = False
    show_rosters = False
    show_permissions = False
    show_menu_rules = False
    show_billing = False
    show_payment_setup = False
    show_clock_in = False

    try:
        # Check if the user is a SubUser
        sub_user = SubUser.objects.get(user=request.user)
        group_id = sub_user.group_id.id
        required_permission_id = 337  # Permission ID for time_sheet view

        # Check if there is a RolePermission entry with 'yes_no_permission' set to True for this permission
        try:
            role_permission = RolePermission.objects.get(role_id=group_id, permission_id=required_permission_id)
            allow_access = role_permission.yes_no_permission
        except RolePermission.DoesNotExist:
            allow_access = False

        permissions_ids = {
            'weekly_menu': 271,
            'inventory': 272,
            'milk_inventory': 270,
            'meal_count': 269,
            'classroom_options': 268,
            'recipes': 267,
            'sign_in': 273,
            'daily_attendance': 274,
            'rosters': 275,
            'permissions': 157, 
            'menu_rules': 266,
            'billing': 331,          
            'payment_setup': 332,   
            'clock_in': 337, 
        }

        # Dynamically check each permission
        for perm_key, perm_id in permissions_ids.items():
            try:
                role_permission = RolePermission.objects.get(role_id=group_id, permission_id=perm_id)
                if perm_key == 'weekly_menu':
                    show_weekly_menu = role_permission.yes_no_permission
                elif perm_key == 'inventory':
                    show_inventory = role_permission.yes_no_permission
                elif perm_key == 'milk_inventory':
                    show_milk_inventory = role_permission.yes_no_permission
                elif perm_key == 'meal_count':
                    show_meal_count = role_permission.yes_no_permission
                elif perm_key == 'permissions':
                    show_permissions = role_permission.yes_no_permission
                elif perm_key == 'menu_rules':
                    show_menu_rules = role_permission.yes_no_permission
                elif perm_key == 'classroom_options':
                    show_classroom_options = role_permission.yes_no_permission
                elif perm_key == 'recipes':
                    show_recipes = role_permission.yes_no_permission
                elif perm_key == 'sign_in':
                    show_sign_in = role_permission.yes_no_permission
                elif perm_key == 'daily_attendance':
                    show_daily_attendance = role_permission.yes_no_permission
                elif perm_key == 'rosters':
                    show_rosters = role_permission.yes_no_permission
                elif perm_key == 'billing':
                    show_billing = role_permission.yes_no_permission
                elif perm_key == 'payment_setup':
                    show_payment_setup = role_permission.yes_no_permission
                elif perm_key == 'clock_in':
                    show_clock_in = role_permission.yes_no_permission  
            except RolePermission.DoesNotExist:
                continue  

    except SubUser.DoesNotExist:
        # If user is not a SubUser, grant access by default (assuming main user)
        allow_access = True
        show_weekly_menu = True
        show_inventory = True
        show_milk_inventory = True
        show_meal_count = True
        show_classroom_options = True
        show_recipes = True
        show_sign_in = True
        show_daily_attendance = True
        show_rosters = True
        show_permissions = True
        show_menu_rules = True
        show_billing = True
        show_payment_setup = True
        show_clock_in = True

    # Redirect to 'no_access' page if access is not allowed
    if not allow_access:
        return redirect('no_access')

    user = get_user_for_view(request)
    today = now().date()  # Define 'today' using Django's timezone-aware 'now'

    # Calculate the previous Friday (the most recent Friday)
    days_since_friday = today.weekday() - 4  # 4 corresponds to Friday
    if days_since_friday < 0:
        days_since_friday += 7
    previous_friday = today - timedelta(days=days_since_friday)

    # Calculate the previous Thursday (the day before the previous Friday)
    previous_thursday = previous_friday + timedelta(days=6)

        # Get date range from request or use defaults
    start_date = request.GET.get('start_date', previous_friday.strftime('%Y-%m-%d'))
    end_date = request.GET.get('end_date', previous_thursday.strftime('%Y-%m-%d'))  # Correct the variable name here

    try:
        start_date = datetime.strptime(str(start_date), '%Y-%m-%d').date()
        end_date = datetime.strptime(str(end_date), '%Y-%m-%d').date()  # Ensure end_date is correctly set
    except ValueError:
        # Fallback in case of an invalid date format
        start_date = previous_friday
        end_date = previous_thursday

        
    # Get the employee filter from the GET request
    employee_id = request.GET.get('employee', '')

    # Fetch the records and filter by employee if selected
    records = (
        TeacherAttendanceRecord.objects.filter(
            user__in=[user] + list(SubUser.objects.filter(main_user=user).values_list('user', flat=True)),
            sign_in_time__date__gte=start_date,
            sign_in_time__date__lte=end_date,
            sign_out_time__isnull=False,
        )
        .annotate(
            total_time=ExpressionWrapper(
                F('sign_out_time') - F('sign_in_time'),
                output_field=DurationField()
            )
        )
        .values('user__id', 'user__first_name', 'user__last_name')
        .annotate(
            total_hours=Sum(F('total_time'))
        )
    )

    # If an employee is selected, filter the records based on the selected employee
    if employee_id:
        records = records.filter(user_id=employee_id)

    # Get a list of employees associated with the current MainUser, excluding users in auth_group IDs 5 and 6
    employees = MainUser.objects.filter(
        Q(id=user.id) | Q(id__in=SubUser.objects.filter(main_user=user).values_list('user', flat=True))
    ).exclude(
        id__in=MainUser.objects.filter(groups__id__in=[5, 6]).values_list('id', flat=True)
    ).values('id', 'first_name', 'last_name')

    # Format total hours for display
    for record in records:
        if record['total_hours']:
            total_seconds = record['total_hours'].total_seconds()
            hours = int(total_seconds // 3600)
            minutes = int((total_seconds % 3600) // 60)
            record['total_hours'] = f"{hours}h {minutes}m"
        else:
            record['total_hours'] = "N/A"

    return render(request, 'time_sheet.html', {
        'records': records,
        'start_date': start_date,
        'end_date': end_date,
        'employees': employees,  # Pass employees to the template
        'show_weekly_menu': show_weekly_menu,
        'show_inventory': show_inventory,
        'show_milk_inventory': show_milk_inventory,
        'show_meal_count': show_meal_count,
        'show_classroom_options': show_classroom_options,
        'show_recipes': show_recipes,
        'show_sign_in': show_sign_in,
        'show_daily_attendance': show_daily_attendance,
        'show_rosters': show_rosters,
        'show_permissions': show_permissions,
        'show_menu_rules': show_menu_rules,
        'show_billing': show_billing,
        'show_payment_setup': show_payment_setup,
        'show_clock_in': show_clock_in,
    })


@login_required
def employee_detail(request):
    allow_access = False
    show_weekly_menu = False
    show_inventory = False
    show_milk_inventory = False
    show_meal_count = False
    show_classroom_options = False
    show_recipes = False
    show_sign_in = False
    show_daily_attendance = False
    show_rosters = False
    show_permissions = False
    show_menu_rules = False
    show_billing = False
    show_payment_setup = False
    show_clock_in = False

    try:
        # Check if the user is a SubUser
        sub_user = SubUser.objects.get(user=request.user)
        group_id = sub_user.group_id.id
        required_permission_id = 337  # Permission ID for time_sheet view

        # Check if there is a RolePermission entry with 'yes_no_permission' set to True for this permission
        try:
            role_permission = RolePermission.objects.get(role_id=group_id, permission_id=required_permission_id)
            allow_access = role_permission.yes_no_permission
        except RolePermission.DoesNotExist:
            allow_access = False

        permissions_ids = {
            'weekly_menu': 271,
            'inventory': 272,
            'milk_inventory': 270,
            'meal_count': 269,
            'classroom_options': 268,
            'recipes': 267,
            'sign_in': 273,
            'daily_attendance': 274,
            'rosters': 275,
            'permissions': 157, 
            'menu_rules': 266,
            'billing': 331,          
            'payment_setup': 332,   
            'clock_in': 337, 
        }

        # Dynamically check each permission
        for perm_key, perm_id in permissions_ids.items():
            try:
                role_permission = RolePermission.objects.get(role_id=group_id, permission_id=perm_id)
                if perm_key == 'weekly_menu':
                    show_weekly_menu = role_permission.yes_no_permission
                elif perm_key == 'inventory':
                    show_inventory = role_permission.yes_no_permission
                elif perm_key == 'milk_inventory':
                    show_milk_inventory = role_permission.yes_no_permission
                elif perm_key == 'meal_count':
                    show_meal_count = role_permission.yes_no_permission
                elif perm_key == 'permissions':
                    show_permissions = role_permission.yes_no_permission
                elif perm_key == 'menu_rules':
                    show_menu_rules = role_permission.yes_no_permission
                elif perm_key == 'classroom_options':
                    show_classroom_options = role_permission.yes_no_permission
                elif perm_key == 'recipes':
                    show_recipes = role_permission.yes_no_permission
                elif perm_key == 'sign_in':
                    show_sign_in = role_permission.yes_no_permission
                elif perm_key == 'daily_attendance':
                    show_daily_attendance = role_permission.yes_no_permission
                elif perm_key == 'rosters':
                    show_rosters = role_permission.yes_no_permission
                elif perm_key == 'billing':
                    show_billing = role_permission.yes_no_permission
                elif perm_key == 'payment_setup':
                    show_payment_setup = role_permission.yes_no_permission
                elif perm_key == 'clock_in':
                    show_clock_in = role_permission.yes_no_permission  
            except RolePermission.DoesNotExist:
                continue  

    except SubUser.DoesNotExist:
        # If user is not a SubUser, grant access by default (assuming main user)
        allow_access = True
        show_weekly_menu = True
        show_inventory = True
        show_milk_inventory = True
        show_meal_count = True
        show_classroom_options = True
        show_recipes = True
        show_sign_in = True
        show_daily_attendance = True
        show_rosters = True
        show_permissions = True
        show_menu_rules = True
        show_billing = True
        show_payment_setup = True
        show_clock_in = True

    # Redirect to 'no_access' page if access is not allowed
    if not allow_access:
        return redirect('no_access')

    employee_id = request.GET.get('employee')
    
    if not employee_id:
        return redirect('time_sheet')  # Redirect if no employee ID is provided

    user = get_user_for_view(request)
    today = now().date()
    days_since_friday = today.weekday() - 4
    if days_since_friday < 0:
        days_since_friday += 7
    previous_friday = today - timedelta(days=days_since_friday)
    previous_thursday = previous_friday + timedelta(days=6)

    start_date = request.GET.get('start_date', previous_friday.strftime('%Y-%m-%d'))
    end_date = request.GET.get('end_date', previous_thursday.strftime('%Y-%m-%d'))

    try:
        start_date = datetime.strptime(start_date, '%Y-%m-%d').date()
        end_date = datetime.strptime(end_date, '%Y-%m-%d').date()
    except ValueError:
        start_date = previous_friday
        end_date = previous_thursday

    # Filter records by employee ID and date range
    records = TeacherAttendanceRecord.objects.filter(
        user_id=employee_id,
        sign_in_time__date__gte=start_date,
        sign_in_time__date__lte=end_date,
        
    ).annotate(
        total_time=ExpressionWrapper(
            F('sign_out_time') - F('sign_in_time'),
            output_field=DurationField()
        )
    ).order_by('sign_in_time')

    for record in records:
        if record.total_time:
            total_seconds = record.total_time.total_seconds()
            hours = int(total_seconds // 3600)
            minutes = int((total_seconds % 3600) // 60)
            record.formatted_total_time = f"{hours}h {minutes}m"
        else:
            record.formatted_total_time = "Please Clock-Out"


    return render(request, 'employee_detail.html', {
        'records': records,
        'start_date': start_date,
        'end_date': end_date,
        'records': records,
        'start_date': start_date,
        'end_date': end_date,
        'show_weekly_menu': show_weekly_menu,
        'show_inventory': show_inventory,
        'show_milk_inventory': show_milk_inventory,
        'show_meal_count': show_meal_count,
        'show_classroom_options': show_classroom_options,
        'show_recipes': show_recipes,
        'show_sign_in': show_sign_in,
        'show_daily_attendance': show_daily_attendance,
        'show_rosters': show_rosters,
        'show_permissions': show_permissions,
        'show_menu_rules': show_menu_rules,
        'show_billing': show_billing,
        'show_payment_setup': show_payment_setup,
        'show_clock_in': show_clock_in,
    })

@csrf_exempt
def edit_time(request):
    if request.method == 'POST':
        record_id = request.POST.get('record_id')
        date = request.POST.get('date')
        sign_in_time = request.POST.get('sign_in_time')
        sign_out_time = request.POST.get('sign_out_time')

        try:
            record = TeacherAttendanceRecord.objects.get(id=record_id)
            record.sign_in_time = datetime.strptime(f"{date} {sign_in_time}", '%Y-%m-%d %H:%M')
            record.sign_out_time = datetime.strptime(f"{date} {sign_out_time}", '%Y-%m-%d %H:%M')
            record.save()

            return JsonResponse({'status': 'success'})
        except TeacherAttendanceRecord.DoesNotExist:
            return JsonResponse({'status': 'error', 'message': 'Record not found'}, status=404)

    return JsonResponse({'status': 'error', 'message': 'Invalid request'}, status=400)

@csrf_exempt
def delete_time(request):
    if request.method == 'POST':
        record_id = request.POST.get('record_id')

        try:
            record = TeacherAttendanceRecord.objects.get(id=record_id)
            record.delete()
            return JsonResponse({'status': 'success'})
        except TeacherAttendanceRecord.DoesNotExist:
            return JsonResponse({'status': 'error', 'message': 'Record not found'}, status=404)

    return JsonResponse({'status': 'error', 'message': 'Invalid request'}, status=400)


MAX_IMAGE_SIZE = 5 * 1024 * 1024  # 5 MB


@login_required
def upload_profile_picture(request):
    if request.method == 'POST' and request.FILES.get('profile_picture'):
        # Get the user and uploaded file
        user = request.user
        profile_picture = request.FILES['profile_picture']
        
        # Check file size
        if profile_picture.size > MAX_IMAGE_SIZE:
            logger.error(f"File size exceeded: {profile_picture.size} bytes")
            return JsonResponse({
                'success': False,
                'error': f"File size exceeds the limit of {MAX_IMAGE_SIZE / (1024 * 1024)} MB."
            }, status=400)

        # Check file extension
        valid_extensions = ['.jpg', '.jpeg', '.png']
        _, ext = os.path.splitext(profile_picture.name.lower())

        # Validate file type
        if ext not in valid_extensions:
            logger.error(f"Invalid file extension: {ext}")
            return JsonResponse({
                'success': False,
                'error': "Invalid file type. Only JPEG, JPG, and PNG are allowed."
            }, status=400)

        # Open the image to ensure proper format is assigned
        try:
            img = Image.open(profile_picture)

            # Log the original size of the image
            logger.debug(f"Original image size: {img.size}")

            # Ensure the image is in a supported mode
            if img.mode in ['P', 'PA']:  # Palette-based image or image with alpha
                img = img.convert('RGBA')  # Convert to 'RGBA' mode to handle transparency
            elif img.mode == 'LA':  # Luminance + Alpha (Grayscale with transparency)
                img = img.convert('RGBA')

            # Get original image size
            width, height = img.size

            # Resize image to one-third of its original size
            img = img.resize((width // 3, height // 3), Image.Resampling.LANCZOS)

            # Save the image to a BytesIO object
            img_io = BytesIO()
            img.save(img_io, format=img.format if img.format else 'PNG')  # Ensure format is set
            img_io.seek(0)  # Reset the pointer to the start of the BytesIO buffer

            # Save the image back to the user's profile picture
            user.profile_picture.save(profile_picture.name, img_io, save=True)
            
            # Log the successful upload
            logger.info(f"Profile picture uploaded successfully for user {user.id}")
        except ValidationError as e:
            logger.error(f"Image validation error: {str(e)}")
            return JsonResponse({
                'success': False,
                'error': f"Image validation error: {str(e)}"
            }, status=400)
        except Exception as e:
            logger.error(f"Error processing the image: {str(e)}")
            return JsonResponse({
                'success': False,
                'error': f"Error processing the image: {str(e)}"
            }, status=500)

        # Save the user object after updating the profile picture
        user.save()

        return JsonResponse({
            'success': True,
            'new_picture_url': user.profile_picture.url
        })

    # If the request is not a POST or no file is provided
    logger.warning("No file provided or request method is not POST")
    return JsonResponse({'success': False}, status=400)

def square_login(request):
    auth_url = f"https://connect.squareup.com/oauth2/authorize?client_id={settings.SQUARE_APPLICATION_ID}&scope=PAYMENTS_READ+ORDERS_WRITE&session=False&redirect_uri={urllib.parse.quote(settings.SQUARE_REDIRECT_URI)}"
    return redirect(auth_url)

@login_required
def square_oauth_callback(request):
    code = request.GET.get("code")
    
    if not code:
        messages.error(request, "Authorization code not found.")
        return redirect("dashboard")  # Change to your dashboard URL

    # Exchange the authorization code for an access token
    token_url = "https://connect.squareup.com/oauth2/token"
    payload = {
        "client_id": settings.SQUARE_APPLICATION_ID,  # Use the correct client_id from settings
        "client_secret": settings.SQUARE_CLIENT_SECRET,  # Use the correct client_secret from settings
        "code": code,
        "grant_type": "authorization_code",
        "redirect_uri": settings.SQUARE_REDIRECT_URI  # Make sure this matches the redirect URI in Square Developer portal
    }

    response = requests.post(token_url, json=payload)
    data = response.json()
    print(data)  # Log the entire response to see the error message from Square

    if "access_token" in data:
        # Store tokens in the MainUser model
        user = request.user
        user.square_access_token = data["access_token"]
        user.square_refresh_token = data.get("refresh_token")
        user.square_merchant_id = data.get("merchant_id")
        user.save()

        messages.success(request, "Square account linked successfully!")
        return redirect("index")  # Redirect to a dashboard or success page
    
    messages.error(request, f"Failed to link Square account: {data}")
    return redirect("index")  # Redirect with error message

@login_required
def square_account_view(request):
    user = get_user_for_view(request)
    square_connected = bool(user.square_access_token)  # Check if Square is linked

    # Initialize all permissions to False
    allow_access = False
    show_weekly_menu = False
    show_inventory = False
    show_milk_inventory = False
    show_meal_count = False
    show_classroom_options = False
    show_recipes = False
    show_sign_in = False
    show_daily_attendance = False
    show_rosters = False
    show_permissions = False
    show_menu_rules = False
    show_billing = False
    show_payment_setup = False
    show_clock_in = False

    try:
        # Check if the user is a SubUser
        sub_user = SubUser.objects.get(user=request.user)
        group_id = sub_user.group_id.id
        required_permission_id = 332

        try:
            role_permission = RolePermission.objects.get(role_id=group_id, permission_id=required_permission_id)
            allow_access = role_permission.yes_no_permission
        except RolePermission.DoesNotExist:
            allow_access = False

        # Check additional permissions based on the same group_id
        permissions_ids = {
            'weekly_menu': 271,
            'inventory': 272,
            'milk_inventory': 270,
            'meal_count': 269,
            'classroom_options': 268,
            'recipes': 267,
            'sign_in': 273,
            'daily_attendance': 274,
            'rosters': 275,
            'permissions': 157, 
            'menu_rules': 266,
            'billing': 331,          
            'payment_setup': 332, 
            'clock_in': 337,  
        }

        # Dynamically check each permission
        for perm_key, perm_id in permissions_ids.items():
            try:
                role_permission = RolePermission.objects.get(role_id=group_id, permission_id=perm_id)
                if perm_key == 'weekly_menu':
                    show_weekly_menu = role_permission.yes_no_permission
                elif perm_key == 'inventory':
                    show_inventory = role_permission.yes_no_permission
                elif perm_key == 'milk_inventory':
                    show_milk_inventory = role_permission.yes_no_permission
                elif perm_key == 'meal_count':
                    show_meal_count = role_permission.yes_no_permission
                elif perm_key == 'permissions':
                    show_permissions = role_permission.yes_no_permission
                elif perm_key == 'menu_rules':
                    show_menu_rules = role_permission.yes_no_permission
                elif perm_key == 'classroom_options':
                    show_classroom_options = role_permission.yes_no_permission
                elif perm_key == 'recipes':
                    show_recipes = role_permission.yes_no_permission
                elif perm_key == 'sign_in':
                    show_sign_in = role_permission.yes_no_permission
                elif perm_key == 'daily_attendance':
                    show_daily_attendance = role_permission.yes_no_permission
                elif perm_key == 'rosters':
                    show_rosters = role_permission.yes_no_permission
                elif perm_key == 'billing':
                    show_billing = role_permission.yes_no_permission
                elif perm_key == 'payment_setup':
                    show_payment_setup = role_permission.yes_no_permission
                elif perm_key == 'clock_in':
                    show_clock_in = role_permission.yes_no_permission
            except RolePermission.DoesNotExist:
                continue  

    except SubUser.DoesNotExist:
        # If user is not a SubUser, grant access by default (assuming main user)
        allow_access = True
        show_weekly_menu = True
        show_inventory = True
        show_milk_inventory = True
        show_meal_count = True
        show_classroom_options = True
        show_recipes = True
        show_sign_in = True
        show_daily_attendance = True
        show_rosters = True
        show_permissions = True
        show_menu_rules = True
        show_billing = True
        show_payment_setup = True
        show_clock_in = True

    # Redirect to 'no_access' page if access is not allowed
    if not allow_access:
        return redirect('no_access')

    context = {
        "square_connected": square_connected,
        "square_login_url": "/square/login/",  # URL for Square login
        "show_weekly_menu": show_weekly_menu,
        "show_inventory": show_inventory,
        "show_milk_inventory": show_milk_inventory,
        "show_meal_count": show_meal_count,
        "show_classroom_options": show_classroom_options,
        "show_recipes": show_recipes,
        "show_sign_in": show_sign_in,
        "show_daily_attendance": show_daily_attendance,
        "show_rosters": show_rosters,
        "show_permissions": show_permissions,
        "show_menu_rules": show_menu_rules,
        "show_billing": show_billing,            
        "show_payment_setup": show_payment_setup,
        "show_clock_in": show_clock_in, 
    }

    return render(request, 'square.html', context)

@login_required
def pay_summary(request):
    success_message = ""
    allow_access = True

    # Initialize permission flags
    show_weekly_menu = False
    show_inventory = False
    show_milk_inventory = False
    show_meal_count = False
    show_classroom_options = False
    show_recipes = False
    show_sign_in = False
    show_daily_attendance = False
    show_rosters = False
    show_permissions = False  
    show_menu_rules = False  
    show_billing = False          
    show_payment_setup = False
    show_clock_in = False

    sub_user = None
    user = get_user_for_view(request)

    try:
        sub_user = SubUser.objects.get(user=user)
        group_id = sub_user.group_id.id

        permissions_ids = {
            'weekly_menu': 271,
            'inventory': 272,
            'milk_inventory': 270,
            'meal_count': 269,
            'classroom_options': 268,
            'recipes': 267,
            'sign_in': 273,
            'daily_attendance': 274,
            'rosters': 275,
            'permissions': 157, 
            'menu_rules': 266,
            'billing': 331,          
            'payment_setup': 332,   
            'clock_in': 337,
        }

        for perm_key, perm_id in permissions_ids.items():
            try:
                role_permission = RolePermission.objects.get(role_id=group_id, permission_id=perm_id)
                if perm_key == 'weekly_menu':
                    show_weekly_menu = role_permission.yes_no_permission
                elif perm_key == 'inventory':
                    show_inventory = role_permission.yes_no_permission
                elif perm_key == 'milk_inventory':
                    show_milk_inventory = role_permission.yes_no_permission
                elif perm_key == 'meal_count':
                    show_meal_count = role_permission.yes_no_permission
                elif perm_key == 'permissions':
                    show_permissions = role_permission.yes_no_permission
                elif perm_key == 'menu_rules':
                    show_menu_rules = role_permission.yes_no_permission
                elif perm_key == 'classroom_options':
                    show_classroom_options = role_permission.yes_no_permission
                elif perm_key == 'recipes':
                    show_recipes = role_permission.yes_no_permission
                elif perm_key == 'sign_in':
                    show_sign_in = role_permission.yes_no_permission
                elif perm_key == 'daily_attendance':
                    show_daily_attendance = role_permission.yes_no_permission
                elif perm_key == 'rosters':
                    show_rosters = role_permission.yes_no_permission
                elif perm_key == 'billing':
                    show_billing = role_permission.yes_no_permission
                elif perm_key == 'payment_setup':
                    show_payment_setup = role_permission.yes_no_permission
                elif perm_key == 'clock_in':
                    show_clock_in = role_permission.yes_no_permission
            except RolePermission.DoesNotExist:
                continue
    except SubUser.DoesNotExist:
        # Grant full access if not a SubUser
        allow_access = True
        show_weekly_menu = True
        show_inventory = True
        show_milk_inventory = True
        show_meal_count = True
        show_classroom_options = True
        show_recipes = True
        show_sign_in = True
        show_daily_attendance = True
        show_rosters = True
        show_permissions = True
        show_menu_rules = True
        show_billing = True
        show_payment_setup = True
        show_clock_in = True

    if not allow_access:
        return redirect('no_access')

    # Retrieve the square credentials from the MainUser model
    main_user = get_user_for_view(request)
    

    return render(request, 'pay_summary.html', {
        'show_weekly_menu': show_weekly_menu,
        'show_inventory': show_inventory,
        'show_milk_inventory': show_milk_inventory,
        'show_meal_count': show_meal_count,
        'show_classroom_options': show_classroom_options,
        'show_recipes': show_recipes,
        'show_sign_in': show_sign_in,
        'show_daily_attendance': show_daily_attendance,
        'show_rosters': show_rosters,
        'show_permissions': show_permissions,
        'show_menu_rules': show_menu_rules,
        'sub_user': sub_user,
        'show_billing': show_billing,
        'show_payment_setup': show_payment_setup,
        'show_clock_in': show_clock_in,
        'SQUARE_APPLICATION_ID': main_user.square_merchant_id,
        'SQUARE_LOCATION_ID': main_user.square_location_id,
        'SQUARE_ACCESS_TOKEN': main_user.square_access_token,
        
        
    })

@csrf_exempt
def process_payment(request):
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            main_user = get_user_for_view(request)
            
            # Validate Square credentials
            if not all([
                main_user.square_access_token,
                main_user.square_location_id,
                main_user.square_merchant_id
            ]):
                return JsonResponse({
                    'success': False, 
                    'error': 'Square payment system not configured'
                })
            
           # Initialize Square client
            square_client = Client(
                access_token=main_user.square_access_token,
                environment='sandbox' if settings.DEBUG else 'production'
            )

            # Validate amount
            try:
                amount = int(float(data['amount']) * 100)
                if amount <= 0:
                    raise ValueError
            except (ValueError, TypeError):
                return JsonResponse({'success': False, 'error': 'Invalid amount'})

             # Create payment
            result = square_client.payments.create_payment(
                body={
                    "source_id": data['token'],
                    "amount_money": {
                        "amount": amount,
                        "currency": "USD"
                    },
                    "idempotency_key": str(uuid.uuid4()),
                    "autocomplete": True,
                    "customer_id": f"user_{request.user.id}",  # Optional customer tracking
                    "note": f"Wallet top-up for {request.user.email}"
                }
            )
            if result.is_success():
                # Update balance using atomic update
                SubUser.objects.filter(user=request.user).update(
                    balance=models.F('balance') + float(data['amount'])
                )
                return JsonResponse({'success': True})
            
            return JsonResponse({'success': False, 'error': result.errors})
            
        except Exception as e:
            logger.error(f"Payment error: {str(e)}")
            return JsonResponse({'success': False, 'error': str(e)})
    
    return JsonResponse({'success': False, 'error': 'Invalid method'})