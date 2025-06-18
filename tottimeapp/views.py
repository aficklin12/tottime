from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.models import Group
from django.contrib.auth import authenticate, login, logout, get_user_model
from django.db.models import Q, Subquery, IntegerField, Count, F, Sum, Max, Min, ExpressionWrapper, DurationField, Exists, OuterRef
from django.db.models.functions import Concat
from django.http import HttpResponseForbidden, HttpResponseBadRequest, JsonResponse, HttpResponseNotAllowed, HttpResponseRedirect
import urllib.parse, stripe, requests, random, logging, json, pytz, os, uuid
from square.client import Client
from django.conf import settings
stripe.api_key = settings.STRIPE_SECRET_KEY
from django.utils.timezone import now
from decimal import Decimal
from django.db import transaction, models
from django.contrib import messages
from .forms import SignupForm, ForgotUsernameForm, LoginForm, RuleForm, MessageForm, InvitationForm
from .models import Classroom, UserMessagingPermission, DiaperChangeRecord, IncidentReport, MainUser, SubUser, RolePermission, Student, Inventory, Recipe,MessagingPermission, BreakfastRecipe, Classroom, ClassroomAssignment, AMRecipe, PMRecipe, OrderList, Student, AttendanceRecord, Message, Conversation, Payment, WeeklyTuition, TeacherAttendanceRecord, TuitionPlan, PaymentRecord, MilkCount, WeeklyMenu, Rule, MainUser, FruitRecipe, VegRecipe, WgRecipe, RolePermission, SubUser, Invitation
from django.contrib.auth.decorators import login_required
from django.views.decorators.csrf import csrf_protect, csrf_exempt
from django.core.files.storage import default_storage
from django.core.files.base import ContentFile
import cv2
import pytesseract
from PIL import Image
from io import BytesIO
from pytz import utc
from datetime import datetime, timedelta, date, time
from collections import defaultdict
from django.utils import timezone
from django.apps import apps
from calendar import monthrange
from django.core.mail import send_mail
from django.urls import reverse
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
logger = logging.getLogger(__name__)

def get_user_for_view(request):
    try:
        subuser = SubUser.objects.get(user=request.user)
        return subuser.main_user  # Return the MainUser object
    except SubUser.DoesNotExist:
        return request.user  # This will return a MainUser object
    
def check_permissions(request, required_permission_id=None):
    """
    Check user permissions and return context variables for links.
    """
    allow_access = True if required_permission_id is None else False
    permissions_context = {
        'show_weekly_menu': False,
        'show_inventory': False,
        'show_milk_inventory': False,
        'show_meal_count': False,
        'show_classroom_options': False,
        'show_recipes': False,
        'show_sign_in': False,
        'show_daily_attendance': False,
        'show_rosters': False,
        'show_permissions': False,
        'show_menu_rules': False,
        'show_billing': False,
        'show_payment_setup': False,
        'show_clock_in': False,
        'show_pay_summary': False,
        'total_unread_count': 0,  # Add total_unread_count to the context
    }

    try:
        # Check if the user is a SubUser
        sub_user = SubUser.objects.get(user=request.user)
        group_id = sub_user.group_id.id

        # Check for required permission
        if required_permission_id:
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
            'pay_summary': 346,
        }

        for perm_key, perm_id in permissions_ids.items():
            permissions_context[f'show_{perm_key}'] = RolePermission.objects.filter(
                role_id=group_id,
                permission_id=perm_id,
                yes_no_permission=True
            ).exists()

        # Calculate total unread messages
        conversations = Conversation.objects.filter(
            Q(sender=request.user) | Q(recipient=request.user)
        ).annotate(
            unread_count=Count('messages', filter=Q(messages__recipient=request.user, messages__is_read=False))
        )
        total_unread_count = conversations.aggregate(total_unread=Sum('unread_count'))['total_unread'] or 0
        permissions_context['total_unread_count'] = total_unread_count

    except SubUser.DoesNotExist:
        # If user is not a SubUser, assume it's a main user and allow access
        allow_access = True
        for key in permissions_context:
            permissions_context[key] = True

    if not allow_access:
        return redirect('no_access')

    return permissions_context

def app_redirect(request):
    return render(request, 'app_redirect.html')

@login_required(login_url='/login/')
def index(request):
    # Check permissions for the specific page
    required_permission_id = None  # No specific permission required for this page
    permissions_context = check_permissions(request, required_permission_id)
    # If check_permissions returns a redirect, return it immediately
    if isinstance(permissions_context, HttpResponseRedirect):
        return permissions_context

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
        elif group_id == 7:
            return redirect('index_teacher_parent')
        elif group_id == 6:
            return redirect('index_free_user')
    except SubUser.DoesNotExist:
        # If the user is not a SubUser, assume they are the owner (ID 1)
        pass

    # Get order items for the Food Program section
    order_items = OrderList.objects.filter(user=user)

    # --- Build classroom ratio cards with dynamic ratios ---
    today = date.today()
    attendance_records = AttendanceRecord.objects.filter(
        sign_in_time__date=today,
        sign_out_time__isnull=True,  # Only records with NULL sign_out_time
        user=user
    )
    classrooms = Classroom.objects.filter(user=user)
    classroom_cards = {}

    for classroom in classrooms:
        # Count attendance records where classroom_override equals the classroom name
        count = attendance_records.filter(classroom_override=classroom.name).count()

        # Fetch assigned teachers for the classroom
        assignments = ClassroomAssignment.objects.filter(classroom=classroom)
        assigned_teachers = [
            assignment.mainuser or assignment.subuser for assignment in assignments
        ]

        # Calculate adjusted ratios based on the number of assigned teachers
        base_ratio = classroom.ratios
        teacher_count = len(assigned_teachers)
        adjusted_ratio = base_ratio * (2 ** (teacher_count - 1)) if teacher_count > 0 else base_ratio

        # Add classroom data to the cards, including classroom id
        classroom_cards[classroom.name] = {
            'id': classroom.id,         # <-- Added classroom id
            'count': count,
            'ratio': adjusted_ratio     # Use the adjusted ratio
        }

    context = {
        'order_items': order_items,
        'classroom_cards': classroom_cards,
        **permissions_context,  # Include permission flags dynamically
    }
    return render(request, 'index.html', context)

@login_required(login_url='/login/')
def index_director(request):
    user = get_user_for_view(request)
    required_permission_id = 157  # Example permission ID for "permissions"
    permissions_context = check_permissions(request, required_permission_id)
    if isinstance(permissions_context, HttpResponseRedirect):  # Redirect if no access
        return permissions_context

    order_items = OrderList.objects.filter(user=user)

    today = date.today()
    attendance_records = AttendanceRecord.objects.filter(
        sign_in_time__date=today,
        sign_out_time__isnull=True,
        user=user
    )
    classrooms = Classroom.objects.filter(user=user)
    classroom_cards = {}

    for classroom in classrooms:
        # Count attendance records where classroom_override equals the classroom name
        count = attendance_records.filter(classroom_override=classroom.name).count()

        # Fetch only active assigned teachers for the classroom
        assignments = ClassroomAssignment.objects.filter(
            classroom=classroom,
            unassigned_at__isnull=True
        )
        assigned_teachers = [
            assignment.mainuser or assignment.subuser
            for assignment in assignments
            if assignment.mainuser or assignment.subuser
        ]

        # Calculate adjusted ratios based on the number of assigned teachers
        base_ratio = classroom.ratios
        teacher_count = len(assigned_teachers)
        adjusted_ratio = base_ratio * (2 ** (teacher_count - 1)) if teacher_count > 0 else base_ratio

        classroom_cards[classroom.name] = {
            'id': classroom.id,
            'count': count,
            'ratio': adjusted_ratio
        }

    context = {
        'order_items': order_items,
        'classroom_cards': classroom_cards,
        **permissions_context,
    }

    return render(request, 'index_director.html', context)

@login_required(login_url='/login/')
def index_teacher(request):
    # Check permissions for the specific page
    required_permission_id = None  # No specific permission required for this page
    permissions_context = check_permissions(request, required_permission_id)
    # If check_permissions returns a redirect, return it immediately
    if isinstance(permissions_context, HttpResponseRedirect):
        return permissions_context

    user = get_user_for_view(request)

    # --- Build classroom ratio cards with dynamic ratios ---
    today = date.today()
    attendance_records = AttendanceRecord.objects.filter(
        sign_in_time__date=today,
        sign_out_time__isnull=True,
        user=user
    )
    classrooms = Classroom.objects.filter(user=user)
    classroom_cards = {}

    for classroom in classrooms:
        # Count attendance records where classroom_override equals the classroom name
        count = attendance_records.filter(classroom_override=classroom.name).count()

        # Fetch assigned teachers for the classroom
        assignments = ClassroomAssignment.objects.filter(classroom=classroom)
        assigned_teachers = [
            assignment.mainuser or assignment.subuser for assignment in assignments
        ]

        # Calculate adjusted ratios based on the number of assigned teachers
        base_ratio = classroom.ratios
        teacher_count = len(assigned_teachers)
        adjusted_ratio = base_ratio * (2 ** (teacher_count - 1)) if teacher_count > 0 else base_ratio

        # Add classroom data to the cards, including classroom id
        classroom_cards[classroom.name] = {
            'id': classroom.id,
            'count': count,
            'ratio': adjusted_ratio
        }

    context = {
        'classroom_cards': classroom_cards,
        **permissions_context,
    }
    return render(request, 'index_teacher.html', context)

@login_required(login_url='/login/')
def index_teacher_parent(request):
    # Check permissions for the specific page
    required_permission_id = None  # No specific permission required for this page
    permissions_context = check_permissions(request, required_permission_id)
    # If check_permissions returns a redirect, return it immediately
    if isinstance(permissions_context, HttpResponseRedirect):
        return permissions_context

    user = get_user_for_view(request)

    # --- Build classroom ratio cards with dynamic ratios ---
    today = date.today()
    attendance_records = AttendanceRecord.objects.filter(
        sign_in_time__date=today,
        sign_out_time__isnull=True,
        user=user
    )
    classrooms = Classroom.objects.filter(user=user)
    classroom_cards = {}

    for classroom in classrooms:
        # Count attendance records where classroom_override equals the classroom name
        count = attendance_records.filter(classroom_override=classroom.name).count()

        # Fetch assigned teachers for the classroom
        assignments = ClassroomAssignment.objects.filter(classroom=classroom)
        assigned_teachers = [
            assignment.mainuser or assignment.subuser for assignment in assignments
        ]

        # Calculate adjusted ratios based on the number of assigned teachers
        base_ratio = classroom.ratios
        teacher_count = len(assigned_teachers)
        adjusted_ratio = base_ratio * (2 ** (teacher_count - 1)) if teacher_count > 0 else base_ratio

        # Add classroom data to the cards, including classroom id
        classroom_cards[classroom.name] = {
            'id': classroom.id,
            'count': count,
            'ratio': adjusted_ratio
        }

    context = {
        'classroom_cards': classroom_cards,
        **permissions_context,
    }
    return render(request, 'index_teacher_parent.html', context)

@login_required(login_url='/login/')
def index_cook(request):
    # Check permissions for the specific page
    required_permission_id = None  # No specific permission required for this page
    permissions_context = check_permissions(request, required_permission_id)
    # If check_permissions returns a redirect, return it immediately
    if isinstance(permissions_context, HttpResponseRedirect):
        return permissions_context

    user = get_user_for_view(request)

    # Get order items for the Food Program section
    order_items = OrderList.objects.filter(user=user)

    # --- Build classroom ratio cards with dynamic ratios ---
    today = date.today()
    attendance_records = AttendanceRecord.objects.filter(
        sign_in_time__date=today,
        sign_out_time__isnull=True,
        user=user
    )
    classrooms = Classroom.objects.filter(user=user)
    classroom_cards = {}

    for classroom in classrooms:
        # Count attendance records where classroom_override equals the classroom name
        count = attendance_records.filter(classroom_override=classroom.name).count()

        # Fetch assigned teachers for the classroom
        assignments = ClassroomAssignment.objects.filter(classroom=classroom)
        assigned_teachers = [
            assignment.mainuser or assignment.subuser for assignment in assignments
        ]

        # Calculate adjusted ratios based on the number of assigned teachers
        base_ratio = classroom.ratios
        teacher_count = len(assigned_teachers)
        adjusted_ratio = base_ratio * (2 ** (teacher_count - 1)) if teacher_count > 0 else base_ratio

        # Add classroom data to the cards, including classroom id
        classroom_cards[classroom.name] = {
            'id': classroom.id,
            'count': count,
            'ratio': adjusted_ratio
        }

    context = {
        'order_items': order_items,
        'classroom_cards': classroom_cards,
        **permissions_context,
    }
    return render(request, 'index_cook.html', context)

@login_required(login_url='/login/')
def index_parent(request):
    # Check permissions for the specific page
    required_permission_id = None  # No specific permission required for this page
    permissions_context = check_permissions(request, required_permission_id)
    # If check_permissions returns a redirect, return it immediately
    if isinstance(permissions_context, HttpResponseRedirect):
        return permissions_context
    # Render the index_parent page with the permissions context
    return render(request, 'index_parent.html', permissions_context)

@login_required(login_url='/login/')
def index_free_user(request):
    # Check permissions for the specific page
    required_permission_id = None  # No specific permission required for this page
    permissions_context = check_permissions(request, required_permission_id)
    # If check_permissions returns a redirect, return it immediately
    if isinstance(permissions_context, HttpResponseRedirect):
        return permissions_context
    # Render the index_free_user page with the permissions context
    return render(request, 'index_free_user.html', permissions_context)

@login_required
def recipes(request):
    # Check permissions for the specific page
    required_permission_id = 267  # Permission ID for accessing recipes view
    permissions_context = check_permissions(request, required_permission_id)
    # If check_permissions returns a redirect, return it immediately
    if isinstance(permissions_context, HttpResponseRedirect):
        return permissions_context
    # If access is allowed, render the recipes page
    return render(request, 'recipes.html', permissions_context)

@login_required
def menu(request):
    # Detect if the request is from a mobile device
    is_mobile = any(device in request.META.get('HTTP_USER_AGENT', '').lower() for device in [
        'iphone', 'android', 'mobile', 'cordova', 'tablet', 'ipod', 'windows phone'
    ])
    # If it's a mobile request, redirect to the app_redirect page
    if is_mobile:
        return HttpResponseRedirect(reverse('app_redirect'))  # Ensure 'app_redirect' is defined in your URLs
    # Check permissions for the specific page
    required_permission_id = 271  # Permission ID for menu view
    permissions_context = check_permissions(request, required_permission_id)
    # If check_permissions returns a redirect, return it immediately
    if isinstance(permissions_context, HttpResponseRedirect):
        return permissions_context
    # If access is allowed, proceed with rendering the menu
    return render(request, 'weekly-menu.html', permissions_context)

@login_required
def account_settings(request):
    success_message = ""
    required_permission_id = None
    permissions_context = check_permissions(request, required_permission_id)
    if isinstance(permissions_context, HttpResponseRedirect):
        return permissions_context

    user = request.user

    if request.method == "POST":
        user.first_name = request.POST.get("first_name", user.first_name)
        user.last_name = request.POST.get("last_name", user.last_name)
        user.email = request.POST.get("email", user.email)
        user.phone_number = request.POST.get("phone_number", user.phone_number)
        user.address = request.POST.get("address", user.address)
        user.code = request.POST.get("code", user.code)
        if request.FILES.get("profile_picture"):
            user.profile_picture = request.FILES["profile_picture"]
        user.save()
        success_message = "Account information updated successfully."

    return render(request, 'account_settings.html', {
        **permissions_context,
        "success_message": success_message,
        "user": user, 
    })

@login_required
def menu_rules(request):
    # Check permissions for the specific page
    required_permission_id = 266  # Permission ID for accessing menu_rules view
    permissions_context = check_permissions(request, required_permission_id)
    # If check_permissions returns a redirect, return it immediately
    if isinstance(permissions_context, HttpResponseRedirect):
        return permissions_context
    # If access is allowed, proceed with the usual view logic
    form = RuleForm()
    rules = Rule.objects.all()  # Query all rules from the database
    return render(request, 'menu_rules.html', {
        'form': form,
        'rules': rules,
        **permissions_context,  # Include permission flags dynamically
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

def privacy_policy(request):
    return render(request, 'privacy_policy.html')

def delete_request(request):
    return render(request, 'delete_request.html')

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
            User = get_user_model()
            try:
                user_obj = User.objects.get(username__iexact=username)
                user = authenticate(request, username=user_obj.username, password=password)
            except User.DoesNotExist:
                user = None
            if user is not None:
                login(request, user)
                return redirect('index')  # Redirect to the index page on successful login
            else:
                messages.error(request, "Invalid username or password.")
        else:
            messages.error(request, "Please correct the errors below.")
    else:
        form = LoginForm()

    return render(request, 'login.html', {'form': form})
    
def forgot_username(request):
    if request.method == 'POST':
        form = ForgotUsernameForm(request.POST)
        if form.is_valid():
            email = form.cleaned_data['email']
            User = get_user_model()
            users = User.objects.filter(email__iexact=email)
            if users.exists():
                usernames = ', '.join([user.username for user in users])
                send_mail(
                    'Your Username(s)',
                    f'Your username(s): {usernames}',
                    'no-reply@yourdomain.com',
                    [email],
                )
                messages.success(request, 'Your username has been sent to your email.')
            else:
                messages.error(request, 'No user found with that email address.')
            return redirect('forgot_username')
    else:
        form = ForgotUsernameForm()
    return render(request, 'tottimeapp/forgot_username.html', {'form': form})

def logout_view(request):
    logout(request)
    # Redirect to the homepage or any other desired page
    return redirect('index')

@login_required
def inventory_list(request):
    # Check permissions for the specific page
    required_permission_id = 272  # Permission ID for inventory_list view
    permissions_context = check_permissions(request, required_permission_id)
    # If check_permissions returns a redirect, return it immediately
    if isinstance(permissions_context, HttpResponseRedirect):
        return permissions_context
    # Get the user (MainUser) for filtering
    user = get_user_for_view(request)
    # Retrieve inventory data for the user
    inventory_items = Inventory.objects.filter(user_id=user.id)
    # Get unique categories for filtering options
    categories = Inventory.objects.filter(user_id=user.id).values_list('category', flat=True).distinct()
    # Retrieve all rules
    rules = Rule.objects.all()

    # Handle AJAX request for category filtering
    if request.headers.get('x-requested-with') == 'XMLHttpRequest':
        category_filter = request.GET.get('category')
        if category_filter:
            inventory_items = inventory_items.filter(category=category_filter)
        inventory_data = list(inventory_items.values('id', 'item', 'quantity', 'units', 'category'))
        return JsonResponse({'inventory_items': inventory_data})

    # Render the inventory list page
    return render(request, 'inventory_list.html', {
        'inventory_items': inventory_items,
        'categories': categories,
        'rules': rules,  # Pass the rules to the template
        **permissions_context,  # Include permission flags dynamically
    })

@login_required
def add_item(request):
    if request.method == 'POST':
        item_name = request.POST.get('item')
        category = request.POST.get('category')
        new_category = request.POST.get('new_category')
        units = request.POST.get('units')
        quantity = request.POST.get('quantity')
        resupply = request.POST.get('resupply')
        barcode = request.POST.get('barcode')  # Retrieve the scanned barcode

        # Use the new category if provided
        if category == 'Other' and new_category:
            category = new_category

        # Check if the barcode already exists
        if barcode:
            existing_item = Inventory.objects.filter(user_id=get_user_for_view(request).id, barcode=barcode).first()
            if existing_item:
                return JsonResponse({'success': False, 'message': f'Item with barcode "{barcode}" already exists.'})

        # Create the new inventory item
        new_item = Inventory.objects.create(
            user_id=get_user_for_view(request).id,
            item=item_name,
            category=category,
            units=units,
            quantity=quantity,
            resupply=resupply,
            barcode=barcode.strip().upper() if barcode else None  # Normalize the barcode
        )
        return JsonResponse({'success': True, 'message': 'Item added successfully!'})

    return JsonResponse({'success': False, 'message': 'Invalid request method.'})

@csrf_exempt
@login_required
def update_item_quantity(request):
    if request.method == 'POST':
        barcode = request.POST.get('barcode')
        if not barcode:
            return JsonResponse({'success': False, 'message': 'No barcode provided.'})

        barcode = barcode.strip().upper()
        print(f"Scanned barcode: {barcode}")

        user = get_user_for_view(request)
        print(f"User ID: {user.id}")

        try:
            item = Inventory.objects.get(user=user, barcode=barcode)
            item.quantity += 1
            item.save()
            return JsonResponse({'success': True, 'message': f'Quantity for "{item.item}" updated successfully!'})
        except Inventory.DoesNotExist:
            return JsonResponse({'success': False, 'message': 'Item with this barcode not found.'})

    return JsonResponse({'success': False, 'message': 'Invalid request method.'})

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

        # Use get_user_for_view to get the correct user (main user or subuser)
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

        # Use get_user_for_view to get the main user (either logged-in user or main user if subuser)
        user = get_user_for_view(request)

        # Get the rule object if rule_id is provided
        rule = get_object_or_404(Rule, id=rule_id) if rule_id else None

        # Create fruit recipe instance
        fruit_recipe = FruitRecipe.objects.create(
            user=user,
            name=recipe_name,
            rule=rule  # This will be None if no rule is selected
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

        # Use get_user_for_view to determine the main user (current user or main user if subuser)
        user = get_user_for_view(request)

        # Get the rule object if rule_id is provided
        rule = get_object_or_404(Rule, id=rule_id) if rule_id else None

        # Create vegetable recipe instance
        veg_recipe = VegRecipe.objects.create(
            user=user,
            name=recipe_name,
            rule=rule  # This will be None if no rule is selected
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

        # Use get_user_for_view to determine the main user (either the current user or main user if subuser)
        user = get_user_for_view(request)

        # Get the rule object if rule_id is provided
        rule = get_object_or_404(Rule, id=rule_id) if rule_id else None

        # Create WG recipe instance
        wg_recipe = WgRecipe.objects.create(
            user=user,
            name=recipe_name,
            rule=rule  # This will be None if no rule is selected
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

        rule = get_object_or_404(Rule, id=rule_id) if rule_id else None

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
        for index, (ingredient_id, quantity) in enumerate(zip(main_ingredient_ids, quantities), start=1):
            if ingredient_id and quantity:
                ingredient = get_object_or_404(Inventory, id=ingredient_id)
                setattr(pm_recipe, f'ingredient{index}', ingredient)
                setattr(pm_recipe, f'qty{index}', quantity)

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

@login_required
def fetch_am_recipes(request):
    user = get_user_for_view(request)
    am_recipes = AMRecipe.objects.filter(user=user).values('id', 'name')
    return JsonResponse({'recipes': list(am_recipes)})

def fetch_pm_recipes(request):
    user = get_user_for_view(request)
    pm_recipes = PMRecipe.objects.filter(user=user).values('id', 'name')  
    return JsonResponse({'recipes': list(pm_recipes)})

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

@login_required
def delete_recipe(request, recipe_id, category):
    if request.method == 'DELETE':
        # Map category to the corresponding model
        model_mapping = {
            'breakfast': BreakfastRecipe,
            'am': AMRecipe,
            'pm': PMRecipe,
            'lunch': Recipe,
            'fruit': FruitRecipe,
            'veg': VegRecipe,
            'wg': WgRecipe,
        }

        # Get the model based on the category
        model = model_mapping.get(category)
        if not model:
            return JsonResponse({'status': 'error', 'message': 'Invalid category'}, status=400)

        # Retrieve and delete the recipe
        try:
            recipe = get_object_or_404(model, pk=recipe_id)
            recipe.delete()
            return JsonResponse({'status': 'success', 'message': f'{category.capitalize()} recipe deleted successfully'})
        except model.DoesNotExist:
            return JsonResponse({'status': 'error', 'message': f'{category.capitalize()} recipe not found'}, status=404)
    else:
        return JsonResponse({'status': 'error', 'message': 'Invalid request method'}, status=405)
    
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
    # Check permissions for the specific page
    required_permission_id = 273  # Permission ID for sign_in view
    permissions_context = check_permissions(request, required_permission_id)
    # If check_permissions returns a redirect, return it immediately
    if isinstance(permissions_context, HttpResponseRedirect):
        return permissions_context
    # Process sign-in if the request is POST and permission is granted
    if request.method == 'POST':
        code = request.POST.get('code')
        try:
            student = Student.objects.get(code=code)
        except Student.DoesNotExist:
            return render(request, 'sign_in.html', {
                'error': 'Student not found.',
                **permissions_context,  # Include permission flags dynamically
            })
        user = request.user  # Get the current user
        # Create or update attendance record
        record, created = AttendanceRecord.objects.get_or_create(student=student, sign_out_time=None)
        record.sign_in_time = timezone.now()
        record.user = user  # Assign the current user to the attendance record
        record.save()

        return redirect('home')

    # Render the sign-in page
    return render(request, 'sign_in.html', permissions_context)

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
def attendance_record(request):
    # Check permissions for the specific page
    required_permission_id = 274  # Permission ID for daily_attendance view
    permissions_context = check_permissions(request, required_permission_id)
    # If check_permissions returns a redirect, return it immediately
    if isinstance(permissions_context, HttpResponseRedirect):
        return permissions_context
    # Get the selected date from the request, default to the current day
    selected_date = request.GET.get('date')
    if selected_date:
        try:
            selected_date = datetime.strptime(selected_date, "%Y-%m-%d").date()
        except ValueError:
            selected_date = now().date()
    else:
        selected_date = now().date()
    # Get the selected classroom from the request
    selected_classroom = request.GET.get('classroom')
    # Filter attendance records by date and classroom
    attendance_records = AttendanceRecord.objects.filter(sign_in_time__date=selected_date)
    if selected_classroom:
        attendance_records = attendance_records.filter(classroom_id=selected_classroom)
    # Get all classrooms for the dropdown
    classrooms = Classroom.objects.all()
    # Determine which columns have data
    column_visibility = {
        'classroom_override_1': attendance_records.filter(classroom_override_1__isnull=False).exists(),
        'timestamp_override_1': attendance_records.filter(timestamp_override_1__isnull=False).exists(),
        'classroom_override_2': attendance_records.filter(classroom_override_2__isnull=False).exists(),
        'timestamp_override_2': attendance_records.filter(timestamp_override_2__isnull=False).exists(),
        'classroom_override_3': attendance_records.filter(classroom_override_3__isnull=False).exists(),
        'timestamp_override_3': attendance_records.filter(timestamp_override_3__isnull=False).exists(),
        'classroom_override_4': attendance_records.filter(classroom_override_4__isnull=False).exists(),
        'timestamp_override_4': attendance_records.filter(timestamp_override_4__isnull=False).exists(),
        'outside_time_out_1': attendance_records.filter(outside_time_out_1__isnull=False).exists(),
        'outside_time_out_2': attendance_records.filter(outside_time_out_2__isnull=False).exists(),
        'outside_time_in_1': attendance_records.filter(outside_time_in_1__isnull=False).exists(),
        'outside_time_in_2': attendance_records.filter(outside_time_in_2__isnull=False).exists(),
        'meal_1': attendance_records.filter(meal_1__isnull=False).exists(),
        'meal_2': attendance_records.filter(meal_2__isnull=False).exists(),
        'meal_3': attendance_records.filter(meal_3__isnull=False).exists(),
        'meal_4': attendance_records.filter(meal_4__isnull=False).exists(),
        'incident_report': attendance_records.filter(incident_report__isnull=False).exists(),
         'diaper_changes': DiaperChangeRecord.objects.filter(
        student__in=attendance_records.values_list('student', flat=True),
        timestamp__date=selected_date
    ).exists(),
    }
    diaper_change_students = set(
    DiaperChangeRecord.objects.filter(
        student__in=attendance_records.values_list('student', flat=True),
        timestamp__date=selected_date
    ).values_list('student_id', flat=True)
)
    # Render the attendance record page
    return render(request, 'attendance_record.html', {
        'attendance_records': attendance_records,
        'classrooms': classrooms,
        'selected_date': selected_date,
        'selected_classroom': selected_classroom,
        'column_visibility': column_visibility,
        'diaper_change_students': diaper_change_students,  # <-- add this
        **permissions_context,  # Include permission flags dynamically
    })

@login_required
def daily_attendance(request):
    required_permission_id = 274
    permissions_context = check_permissions(request, required_permission_id)
    if isinstance(permissions_context, HttpResponseRedirect):
        return permissions_context

    today = date.today()
    user = get_user_for_view(request)

    # Handle assignment POST
    if request.method == "POST":
        classroom_id = request.POST.get("classroom_id")
        teacher_type = request.POST.get("teacher_type")
        teacher_id = request.POST.get("teacher_id")
        classroom = Classroom.objects.get(id=classroom_id, user=user)

        # Unassign all current teachers
        ClassroomAssignment.objects.filter(classroom=classroom, unassigned_at__isnull=True).update(unassigned_at=timezone.now())

        # Assign new teacher
        if teacher_type == "main":
            mainuser = MainUser.objects.get(id=teacher_id)
            ClassroomAssignment.objects.create(classroom=classroom, mainuser=mainuser)
        elif teacher_type == "sub":
            subuser = SubUser.objects.get(id=teacher_id)
            ClassroomAssignment.objects.create(classroom=classroom, subuser=subuser)
        return redirect("daily_attendance")

    classrooms = Classroom.objects.filter(user=user)
    main_teachers = MainUser.objects.all()
    sub_teachers = SubUser.objects.all()
    classroom_data = []
    for classroom in classrooms:
        assignments = classroom.assignments.filter(unassigned_at__isnull=True)
        teachers = []
        for assignment in assignments:
            if assignment.subuser:
                teachers.append(assignment.subuser.user.get_full_name())
            elif assignment.mainuser:
                teachers.append(assignment.mainuser.get_full_name())
        teacher_count = len(teachers)
        base_ratio = classroom.ratios if classroom.ratios else 1
        adjusted_ratio = base_ratio * (2 ** (teacher_count - 1)) if teacher_count > 0 else base_ratio

        classroom_data.append({
            'id': classroom.id,
            'name': classroom.name,
            'ratio': adjusted_ratio,
            'teachers': teachers,
        })

    return render(request, 'daily_attendance.html', {
        **permissions_context,
        'classroom_data': classroom_data,
        'main_teachers': main_teachers,
        'sub_teachers': sub_teachers,
    })

@login_required
def classroom(request):
    required_permission_id = 274  # Permission ID for daily_attendance view
    permissions_context = check_permissions(request, required_permission_id)
    if isinstance(permissions_context, HttpResponseRedirect):
        return permissions_context

    try:
        main_user = MainUser.objects.get(id=request.user.id)
        classrooms = Classroom.objects.all()
        selected_classroom_id = request.GET.get('classroom_id')
        status_filter = request.GET.get('status', 'signed_in')  # Default to 'signed_in'

        # If no classroom is selected, default to the first assigned classroom
        if not selected_classroom_id:
            assigned_classroom = ClassroomAssignment.objects.filter(mainuser=main_user).first()
            if assigned_classroom:
                selected_classroom_id = assigned_classroom.classroom.id

        selected_classroom = None
        if selected_classroom_id:
            selected_classroom = Classroom.objects.filter(id=selected_classroom_id).first()

        # Build the base queryset for students
        if selected_classroom_id:
            students_in_classroom = Student.objects.filter(
                classroom_id=selected_classroom_id
            ).annotate(
                is_signed_in=Exists(
                    AttendanceRecord.objects.filter(
                        student=OuterRef('pk'),
                        sign_out_time__isnull=True
                    )
                )
            ).exclude(
                Exists(
                    AttendanceRecord.objects.filter(
                        student=OuterRef('pk'),
                        classroom_override__isnull=False,
                        sign_out_time__isnull=True
                    )
                )
            )
            students_with_override = Student.objects.filter(
                attendancerecord__classroom_override=Classroom.objects.get(id=selected_classroom_id).name,
                attendancerecord__sign_out_time__isnull=True
            ).annotate(
                is_signed_in=Exists(
                    AttendanceRecord.objects.filter(
                        student=OuterRef('pk'),
                        sign_out_time__isnull=True
                    )
                )
            )

            # Apply status filter BEFORE union
            if status_filter == 'signed_in':
                students_in_classroom = students_in_classroom.filter(is_signed_in=True)
                students_with_override = students_with_override.filter(is_signed_in=True)
            elif status_filter == 'signed_out':
                students_in_classroom = students_in_classroom.filter(is_signed_in=False)
                students_with_override = students_with_override.filter(is_signed_in=False)
            # else 'all': do not filter

            all_students = students_in_classroom.union(students_with_override)
        else:
            assigned_students = Student.objects.filter(
                classroom__assignments__mainuser=main_user
            ).annotate(
                is_signed_in=Exists(
                    AttendanceRecord.objects.filter(
                        student=OuterRef('pk'),
                        sign_out_time__isnull=True
                    )
                )
            ).exclude(
                Exists(
                    AttendanceRecord.objects.filter(
                        student=OuterRef('pk'),
                        classroom_override__isnull=False,
                        sign_out_time__isnull=True
                    )
                )
            )
            override_students = Student.objects.filter(
                attendancerecord__classroom_override__in=assigned_students.values_list('classroom__name', flat=True),
                attendancerecord__sign_out_time__isnull=True
            ).annotate(
                is_signed_in=Exists(
                    AttendanceRecord.objects.filter(
                        student=OuterRef('pk'),
                        sign_out_time__isnull=True
                    )
                )
            )

            # Apply status filter BEFORE union
            if status_filter == 'signed_in':
                assigned_students = assigned_students.filter(is_signed_in=True)
                override_students = override_students.filter(is_signed_in=True)
            elif status_filter == 'signed_out':
                assigned_students = assigned_students.filter(is_signed_in=False)
                override_students = override_students.filter(is_signed_in=False)
            # else 'all': do not filter

            all_students = assigned_students.union(override_students)

        all_students = all_students.order_by('-is_signed_in', 'last_name', 'first_name')

    except MainUser.DoesNotExist:
        all_students = Student.objects.none()
        classrooms = Classroom.objects.none()
        selected_classroom = None
        status_filter = 'signed_in'

    return render(request, 'classroom.html', {
        'assigned_students': all_students,
        'classrooms': classrooms,
        'classroom': selected_classroom,
        'status_filter': status_filter,
        **permissions_context,
    })

@login_required
@csrf_exempt
def add_incident_report(request):
    if request.method == 'POST':
        student_id = request.POST.get('student_id')
        date_of_incident = request.POST.get('date_of_incident')
        incident_description = request.POST.get('incident_description')
        injury_description = request.POST.get('injury_description')
        treatment_administered = request.POST.get('treatment_administered')
        try:
            student = Student.objects.get(id=student_id)
            # Create the incident report
            incident = IncidentReport.objects.create(
                student=student,
                date_of_incident=date_of_incident,
                incident_description=incident_description,
                injury_description=injury_description,
                treatment_administered=treatment_administered
            )
            # Link to the active attendance record (where sign_out_time is null)
            attendance = AttendanceRecord.objects.filter(
                student=student, sign_out_time__isnull=True
            ).order_by('-sign_in_time').first()
            if attendance:
                attendance.incident_report = incident
                attendance.save()
            return JsonResponse({'status': 'success'})
        except Exception as e:
            return JsonResponse({'status': 'error', 'message': str(e)})
    return JsonResponse({'status': 'error', 'message': 'Invalid request'})

@login_required
def incident_report_detail(request):
    incident_id = request.GET.get('id')
    try:
        incident = IncidentReport.objects.get(id=incident_id)
        return JsonResponse({
            'date_of_incident': incident.date_of_incident.strftime('%Y-%m-%d'),
            'incident_description': incident.incident_description,
            'injury_description': incident.injury_description,
            'treatment_administered': incident.treatment_administered,
        })
    except IncidentReport.DoesNotExist:
        return JsonResponse({'error': 'Not found'}, status=404)
    
@login_required
def add_diaper_change(request):
    if request.method == 'POST':
        student_id = request.POST.get('student_id')
        notes = request.POST.get('notes')
        time_str = request.POST.get('timestamp')  # format: 'HH:MM'
        try:
            student = Student.objects.get(id=student_id)
            # Combine today's date with submitted time
            today = date.today()
            timestamp = datetime.strptime(f"{today} {time_str}", "%Y-%m-%d %H:%M")
            diaper_change = DiaperChangeRecord.objects.create(
                student=student,
                changed_by=request.user,
                notes=notes,
                timestamp=timestamp
            )
            # Link to active attendance record
            attendance = AttendanceRecord.objects.filter(
                student=student, sign_out_time__isnull=True
            ).order_by('-sign_in_time').first()
            if attendance:
                attendance.diaper_change = diaper_change
                attendance.save()
            return JsonResponse({'status': 'success'})
        except Exception as e:
            return JsonResponse({'status': 'error', 'message': str(e)})
    return JsonResponse({'status': 'error', 'message': 'Invalid request'})

@login_required
def diaper_changes_for_student(request):
    student_id = request.GET.get('student_id')
    date = request.GET.get('date')
    try:
        changes = DiaperChangeRecord.objects.filter(
            student_id=student_id,
            timestamp__date=date
        ).order_by('timestamp')
        data = [{
            'time': change.timestamp.strftime('%I:%M %p'),
            'notes': change.notes
        } for change in changes]
        return JsonResponse({'changes': data})
    except Exception as e:
        return JsonResponse({'changes': [], 'error': str(e)}, status=400)

@login_required
def get_attendance_record(request, student_id):
    student = get_object_or_404(Student, id=student_id)
    attendance = AttendanceRecord.objects.filter(student=student, sign_out_time__isnull=True).last()
    
    if attendance:
        data = {
            'first_name': student.first_name,
            'last_name': student.last_name,
            'profile_picture': student.profile_picture.url if student.profile_picture else None,
            'sign_in_time': attendance.sign_in_time.strftime('%Y-%m-%d %H:%M:%S') if attendance.sign_in_time else None,
            'sign_out_time': attendance.sign_out_time.strftime('%Y-%m-%d %H:%M:%S') if attendance.sign_out_time else None,
            'classroom_override': attendance.classroom_override,
            'has_active_record': True,  # Indicate an active attendance record exists
        }
    else:
        # Default response when no attendance record exists
        data = {
            'first_name': student.first_name,
            'last_name': student.last_name,
            'profile_picture': student.profile_picture.url if student.profile_picture else None,
            'sign_in_time': None,
            'sign_out_time': None,
            'classroom_override': None,
            'has_active_record': False,  # Indicate no active attendance record exists
        }

    return JsonResponse(data)

@login_required
def edit_student_info(request, student_id):
    permissions_context = check_permissions(request)
    if isinstance(permissions_context, HttpResponseRedirect):
        return permissions_context

    student = get_object_or_404(Student, id=student_id)
    classrooms = Classroom.objects.all()
    previous_page = request.POST.get('previous_page', request.META.get('HTTP_REFERER', '/'))

    if request.method == 'POST':
        first_name = request.POST.get('firstName')
        last_name = request.POST.get('lastName')
        dob = request.POST.get('dob')
        code = request.POST.get('code')
        classroom_id = request.POST.get('classroom')
        profile_picture = request.FILES.get('profile_picture')
        status = request.POST.get('status')

        if not first_name or not last_name:
            return render(request, 'tottimeapp/edit_student.html', {
                'student': student,
                'classrooms': classrooms,
                'error': 'First and last name are required.',
                'previous_page': previous_page,
                **permissions_context,
            })

        classroom = get_object_or_404(Classroom, id=classroom_id)
        student.first_name = first_name
        student.last_name = last_name

        # Convert dob to date if needed
        if dob:
            try:
                student.date_of_birth = datetime.strptime(dob, "%Y-%m-%d").date()
            except ValueError:
                return render(request, 'tottimeapp/edit_student.html', {
                    'student': student,
                    'classrooms': classrooms,
                    'error': 'Invalid date format.',
                    'previous_page': previous_page,
                    **permissions_context,
                })

        student.code = code
        student.classroom = classroom
        student.status = status

        # Only update profile_picture if a new file is uploaded
        if profile_picture:
            student.profile_picture = profile_picture

        student.save()
        return redirect(previous_page)

    return render(request, 'tottimeapp/edit_student.html', {
        'student': student,
        'classrooms': classrooms,
        'previous_page': previous_page,
        **permissions_context,
    })

@csrf_exempt
@login_required
def update_classroom_attendance(request):
    if request.method == 'POST':
        student_id = request.POST.get('student_id')
        classroom_id = request.POST.get('classroom_id')
        action = request.POST.get('action')
        user = get_user_for_view(request)

        try:
            student = Student.objects.get(id=student_id)
            classroom = Classroom.objects.get(id=classroom_id) if classroom_id else student.classroom

            if action == 'move':
                # Existing logic for moving classrooms
                attendance = AttendanceRecord.objects.filter(
                    student=student,
                    sign_out_time__isnull=True
                ).last()

                if not attendance:
                    return JsonResponse({'status': 'error', 'message': 'No active attendance record found.'})

                now = timezone.now()
                if not attendance.classroom_override_1:
                    attendance.classroom_override_1 = classroom.name
                    attendance.timestamp_override_1 = now
                elif not attendance.classroom_override_2:
                    attendance.classroom_override_2 = classroom.name
                    attendance.timestamp_override_2 = now
                elif not attendance.classroom_override_3:
                    attendance.classroom_override_3 = classroom.name
                    attendance.timestamp_override_3 = now
                elif not attendance.classroom_override_4:
                    attendance.classroom_override_4 = classroom.name
                    attendance.timestamp_override_4 = now

                attendance.classroom_override = classroom.name
                attendance.save()

                return JsonResponse({'status': 'success', 'message': 'Classroom moved successfully.'})

            elif action == 'sign_in':
                # Existing logic for signing in
                existing_record = AttendanceRecord.objects.filter(
                    student=student,
                    classroom=classroom,
                    sign_out_time__isnull=True
                ).exists()

                if existing_record:
                    return JsonResponse({'status': 'error', 'message': 'Student is already signed in.'})

                AttendanceRecord.objects.create(
                    user=user,
                    student=student,
                    classroom=classroom,
                    classroom_override=classroom.name,
                    sign_in_time=timezone.now()
                )
                return JsonResponse({'status': 'success', 'message': 'Student signed in successfully.'})

            elif action == 'sign_out':
                # Existing logic for signing out
                attendance = AttendanceRecord.objects.filter(
                    student=student,
                    classroom=classroom,
                    sign_out_time__isnull=True
                ).last()
                if attendance:
                    attendance.sign_out_time = timezone.now()
                    attendance.save()
                    return JsonResponse({'status': 'success', 'message': 'Student signed out successfully.'})
                else:
                    return JsonResponse({'status': 'error', 'message': 'No active sign-in record found.'})

            elif action == 'mark_outside':
                # Record the "Mark Outside" timestamp
                attendance = AttendanceRecord.objects.filter(
                    student=student,
                    sign_out_time__isnull=True
                ).last()

                if not attendance:
                    return JsonResponse({'status': 'error', 'message': 'No active attendance record found.'})

                now = timezone.now()
                if not attendance.outside_time_out_1:
                    attendance.outside_time_out_1 = now
                elif not attendance.outside_time_out_2:
                    attendance.outside_time_out_2 = now
                attendance.save()

                return JsonResponse({'status': 'success', 'message': 'Marked as outside successfully.'})

            elif action == 'mark_inside':
                # Record the "Mark Inside" timestamp
                attendance = AttendanceRecord.objects.filter(
                    student=student,
                    sign_out_time__isnull=True
                ).last()

                if not attendance:
                    return JsonResponse({'status': 'error', 'message': 'No active attendance record found.'})

                now = timezone.now()
                if not attendance.outside_time_in_1:
                    attendance.outside_time_in_1 = now
                elif not attendance.outside_time_in_2:
                    attendance.outside_time_in_2 = now
                attendance.save()

                return JsonResponse({'status': 'success', 'message': 'Marked as inside successfully.'})

        except Student.DoesNotExist:
            return JsonResponse({'status': 'error', 'message': 'Student does not exist.'})
        except Classroom.DoesNotExist:
            return JsonResponse({'status': 'error', 'message': 'Classroom does not exist.'})

    return JsonResponse({'status': 'error', 'message': 'Invalid request method.'})

@login_required
def assign_teacher_to_classroom(request):
    if request.method == 'POST':
        classroom_id = request.POST.get('classroom_id')
        teacher_id = request.POST.get('teacher_id')

        try:
            # Fetch the classroom
            classroom = Classroom.objects.get(id=classroom_id)

            # Check if the teacher is a MainUser or SubUser
            try:
                teacher = MainUser.objects.get(id=teacher_id)
                # Assign the MainUser to the classroom
                assignment, created = ClassroomAssignment.objects.update_or_create(
                    classroom=classroom,
                    mainuser=teacher,
                    defaults={'subuser': None}  # Ensure subuser is cleared
                )
            except MainUser.DoesNotExist:
                # If not a MainUser, check if it's a SubUser
                teacher = SubUser.objects.get(id=teacher_id)
                # Assign the SubUser to the classroom
                assignment, created = ClassroomAssignment.objects.update_or_create(
                    classroom=classroom,
                    subuser=teacher,
                    defaults={'mainuser': None}  # Ensure mainuser is cleared
                )

            return JsonResponse({'success': True, 'message': 'Teacher assigned successfully.'})
        except Classroom.DoesNotExist:
            return JsonResponse({'success': False, 'error': 'Classroom not found.'})
        except SubUser.DoesNotExist:
            return JsonResponse({'success': False, 'error': 'Teacher not found.'})
        except Exception as e:
            return JsonResponse({'success': False, 'error': str(e)})

    return JsonResponse({'success': False, 'error': 'Invalid request method.'})

@login_required
def unassign_teacher_from_classroom(request):
    if request.method == 'POST':
        classroom_id = request.POST.get('classroom_id')
        teacher_id = request.POST.get('teacher_id')

        try:
            # Fetch the classroom assignment
            assignment = ClassroomAssignment.objects.get(
                models.Q(classroom_id=classroom_id) & 
                (models.Q(mainuser_id=teacher_id) | models.Q(subuser_id=teacher_id))
            )
            assignment.delete()  # Remove the assignment

            return JsonResponse({'success': True, 'message': 'Teacher unassigned successfully.'})
        except ClassroomAssignment.DoesNotExist:
            return JsonResponse({'success': False, 'error': 'Assignment not found.'})
        except Exception as e:
            return JsonResponse({'success': False, 'error': str(e)})

    return JsonResponse({'success': False, 'error': 'Invalid request method.'})

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

            elif field == 'classroom_override':
                # Update the classroom_override field
                record.classroom_override = new_value

                # Update the next available override slot and timestamp
                now_time = now()
                if not record.classroom_override_1:
                    record.classroom_override_1 = new_value
                    record.timestamp_override_1 = now_time
                elif not record.classroom_override_2:
                    record.classroom_override_2 = new_value
                    record.timestamp_override_2 = now_time
                elif not record.classroom_override_3:
                    record.classroom_override_3 = new_value
                    record.timestamp_override_3 = now_time
                elif not record.classroom_override_4:
                    record.classroom_override_4 = new_value
                    record.timestamp_override_4 = now_time
                # If all slots are filled, only update classroom_override without recording further

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
    # Check permissions for the specific page
    required_permission_id = 275  # Permission ID for rosters view
    permissions_context = check_permissions(request, required_permission_id)
    # If check_permissions returns a redirect, return it immediately
    if isinstance(permissions_context, HttpResponseRedirect):
        return permissions_context
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
    # Render the template with all required context
    context = {
        'student_attendance': student_attendance,
        'num_days': range(1, num_days_in_month + 1),  # Start from day 1
        'classrooms': classrooms,
        'selected_classroom': selected_classroom_id,  # Pass the selected classroom ID to retain selection in the form
        'selected_month': selected_month,
        'selected_year': selected_year,
        'months': months,
        'years': years,
        **permissions_context,  # Include permission flags dynamically
    }
    return render(request, 'rosters.html', context)

@login_required
def add_student(request):
    if request.method == 'POST':
        first_name = request.POST.get('first_name')
        last_name = request.POST.get('last_name')
        date_of_birth = request.POST.get('date_of_birth')
        classroom_id = request.POST.get('classroom_id')

        try:
            main_user = get_user_for_view(request)
            classroom = Classroom.objects.get(id=classroom_id)

            # Generate a unique 4-digit code for the student
            code = None
            while not code or Student.objects.filter(user=main_user, code=code).exists():
                code = str(random.randint(1000, 9999))

            # Create the student
            student = Student(
                first_name=first_name,
                last_name=last_name,
                date_of_birth=date_of_birth,
                code=code,
                classroom=classroom,
                user=main_user,
            )
            student.save()

            return JsonResponse({'success': True, 'message': 'Student added successfully!'})

        except Classroom.DoesNotExist:
            return JsonResponse({'success': False, 'message': 'Classroom not found.'})
        except Exception as e:
            return JsonResponse({'success': False, 'message': str(e)})

    return JsonResponse({'success': False, 'message': 'Invalid request method.'})

@login_required
def classroom_options(request):
    # Check permissions for the specific page
    required_permission_id = 268  # Permission ID for accessing classroom_options view
    permissions_context = check_permissions(request, required_permission_id)
    # If check_permissions returns a redirect, return it immediately
    if isinstance(permissions_context, HttpResponseRedirect):
        return permissions_context

    # Get filter parameters from the request
    classroom_id = request.GET.get('classroom')
    search_query = request.GET.get('search', '').strip()
    status_filter = request.GET.get('status', 'active')  # Default to 'active'

    # Fetch the list of students with optional filtering
    students = Student.objects.select_related('classroom').filter(status=status_filter).order_by('last_name', 'first_name')
    if classroom_id:
        students = students.filter(classroom_id=classroom_id)
    if search_query:
        students = students.filter(
            Q(first_name__icontains=search_query) | Q(last_name__icontains=search_query)
        )

    # Fetch all classrooms for the filter dropdown
    classrooms = Classroom.objects.all()

    return render(request, 'tottimeapp/classroom_options.html', {
        **permissions_context,  # Include permission flags dynamically
        'students': students,  # Pass the filtered list of students to the template
        'classrooms': classrooms,  # Pass the list of classrooms for the dropdown
        'selected_classroom': classroom_id,  # Keep track of the selected classroom
        'search_query': search_query,  # Keep track of the search query
        'selected_status': status_filter,  # Keep track of the selected status
    })

@login_required
def classroom_options_classrooms(request):
    # Check permissions for the specific page
    permissions_context = check_permissions(request)
    if isinstance(permissions_context, HttpResponseRedirect):
        return permissions_context

    # Get filter parameters from the request
    search_query = request.GET.get('search', '').strip()

    # Fetch the list of classrooms with optional filtering
    classrooms = Classroom.objects.prefetch_related('assignments__subuser__user', 'assignments__mainuser').all()
    if search_query:
        classrooms = classrooms.filter(name__icontains=search_query)

    # Prepare classroom data with assigned teachers
    classroom_data = []
    for classroom in classrooms:
        assigned_teachers = []
        for assignment in classroom.assignments.all():
            if assignment.subuser:
                assigned_teachers.append(f"{assignment.subuser.user.first_name} {assignment.subuser.user.last_name}")
            elif assignment.mainuser:
                assigned_teachers.append(f"{assignment.mainuser.first_name} {assignment.mainuser.last_name}")
        classroom_data.append({
            'id': classroom.id,  # Include the classroom ID
            'name': classroom.name,
            'ratios': classroom.ratios,
            'color': classroom.color,
            'teachers': ', '.join(assigned_teachers) if assigned_teachers else 'No teachers currrently assigned to this classroom.',
        })

    return render(request, 'tottimeapp/classroom_options_classrooms.html', {
        **permissions_context,
        'classroom_data': classroom_data,
        'search_query': search_query,
    })

@csrf_exempt
@login_required
def add_classroom(request):
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            name = data.get('name')
            ratios = data.get('ratios')
            color = data.get('color', '#57bdb4')

            if not name or not ratios:
                return JsonResponse({'success': False, 'error': 'Invalid data'})

            Classroom.objects.create(user=request.user, name=name, ratios=ratios, color=color)  # <-- add color here
            return JsonResponse({'success': True})
        except Exception as e:
            return JsonResponse({'success': False, 'error': str(e)})
    return JsonResponse({'success': False, 'error': 'Invalid request method'})

@csrf_exempt
@login_required
def delete_classroom(request):
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            classroom_id = data.get('id')

            if not classroom_id:
                return JsonResponse({'success': False, 'error': 'Invalid classroom ID'})

            classroom = Classroom.objects.get(id=classroom_id, user=request.user)
            classroom.delete()
            return JsonResponse({'success': True})
        except Classroom.DoesNotExist:
            return JsonResponse({'success': False, 'error': 'Classroom not found'})
        except Exception as e:
            return JsonResponse({'success': False, 'error': str(e)})
    return JsonResponse({'success': False, 'error': 'Invalid request method'})

@login_required
def classroom_options_teachers(request):
    # Check permissions for the specific page
    required_permission_id = 268  # Permission ID for accessing classroom_options_teachers view
    permissions_context = check_permissions(request, required_permission_id)
    if isinstance(permissions_context, HttpResponseRedirect):
        return permissions_context

    # Get filter parameters from the request
    classroom_id = request.GET.get('classroom')
    search_query = request.GET.get('search', '').strip()
    user_status = request.GET.get('status', 'active')  # Default to 'active'

    # Get the main user (account owner)
    main_user = get_user_for_view(request)

    # Prepare data for the main account holder
    main_user_classroom_assignment = ClassroomAssignment.objects.filter(mainuser=main_user).select_related('classroom').first()
    main_user_classroom_name = main_user_classroom_assignment.classroom.name if main_user_classroom_assignment else 'No Classroom'

    main_user_data = {
        'id': main_user.id,
        'first_name': main_user.first_name,
        'last_name': main_user.last_name,
        'code': main_user.code if main_user.code else 'N/A',
        'group_name': 'Owner',  # Default group name for the main account holder
        'classroom_name': main_user_classroom_name
    }

    # Fetch subusers under the main account
    subusers = SubUser.objects.filter(main_user=main_user).select_related('user', 'group_id')

    # Filter subusers based on the selected status and exclude group IDs 5 and 8
    if user_status == 'active':
        subusers = subusers.exclude(group_id__id__in=[5, 8])  # Exclude parents (group ID 5) and inactive users (group ID 8)
    elif user_status == 'inactive':
        subusers = subusers.filter(group_id__id=8)  # Include only inactive users (group ID 8)

    # Prepare data for subusers
    subuser_data = []
    for subuser in subusers:
        subuser_classroom_assignment = ClassroomAssignment.objects.filter(mainuser=subuser.user).select_related('classroom').first()
        subuser_classroom_name = subuser_classroom_assignment.classroom.name if subuser_classroom_assignment else 'No Classroom'

        subuser_data.append({
            'id': subuser.user.id,
            'first_name': subuser.user.first_name,
            'last_name': subuser.user.last_name,
            'code': subuser.user.code,
            'group_name': subuser.group_id.name if subuser.group_id else 'N/A',
            'classroom_name': subuser_classroom_name
        })

    # Combine main user data with subuser data
    if user_status == 'active':
        all_user_data = [main_user_data] + subuser_data
    else:
        all_user_data = subuser_data  # Exclude main user for inactive status

    # Apply classroom filter
    if classroom_id:
        all_user_data = [user for user in all_user_data if user['classroom_name'] == Classroom.objects.get(id=classroom_id).name]

    # Apply search filter
    if search_query:
        all_user_data = [
            user for user in all_user_data
            if search_query.lower() in f"{user['first_name']} {user['last_name']}".lower()
        ]

    # Fetch all classrooms for the filter dropdown
    classrooms = Classroom.objects.all()

    return render(request, 'tottimeapp/classroom_options_teachers.html', {
        **permissions_context,
        'subuser_data': all_user_data,
        'classrooms': classrooms,  # Pass the list of classrooms for the dropdown
        'selected_classroom': classroom_id,  # Keep track of the selected classroom
        'search_query': search_query,  # Keep track of the search query
        'user_status': user_status,  # Pass the selected user status
    })

@login_required
def classroom_options_parents(request):
    # Check permissions for the specific page
    required_permission_id = 269  # Permission ID for accessing classroom_options_parents view
    permissions_context = check_permissions(request, required_permission_id)
    if isinstance(permissions_context, HttpResponseRedirect):
        return permissions_context

    # Get filter parameters from the request
    search_query = request.GET.get('search', '').strip()
    user_status = request.GET.get('status', 'active')  # Default to 'active'

    # Get the main user (account owner)
    main_user = get_user_for_view(request)

    # Fetch subusers under the main account with group IDs 5, 7, or 8
    subusers = SubUser.objects.filter(main_user=main_user, group_id__id__in=[5, 7, 8]).select_related('user')

    # Filter subusers based on the selected status
    if user_status == 'active':
        subusers = subusers.exclude(group_id__id=8)  # Exclude inactive users (group ID 8)
    elif user_status == 'inactive':
        subusers = subusers.filter(group_id__id=8)  # Include only inactive users (group ID 8)

    # Prepare data for subusers
    subuser_data = []
    for subuser in subusers:
        # Fetch all students linked to the subuser
        students = subuser.students.all()
        student_info = [
            {
                'student_name': f"{student.first_name} {student.last_name}",
                'student_code': student.code,
                'classroom_name': student.classroom.name if student.classroom else 'N/A',
            }
            for student in students
        ]
        subuser_data.append({
            'id': subuser.user.id,
            'first_name': subuser.user.first_name,
            'last_name': subuser.user.last_name,
            'students': student_info,  # List of linked students
        })

    # Apply search filter
    if search_query:
        subuser_data = [
            user for user in subuser_data
            if search_query.lower() in f"{user['first_name']} {user['last_name']}".lower()
        ]

    return render(request, 'tottimeapp/classroom_options_parents.html', {
        **permissions_context,
        'subuser_data': subuser_data,  # Only subuser data is passed
        'search_query': search_query,  # Keep track of the search query
        'user_status': user_status,  # Pass the selected user status
    })

@login_required
def edit_teacher_info(request, teacher_id):
    # Check permissions for the specific page
    permissions_context = check_permissions(request)
    if isinstance(permissions_context, HttpResponseRedirect):
        return permissions_context

    # Fetch the teacher (MainUser or SubUser)
    try:
        teacher = MainUser.objects.get(id=teacher_id)
    except MainUser.DoesNotExist:
        return HttpResponseRedirect('/classroom-options-teachers/')  # Redirect if teacher not found

    # Fetch all classrooms for the dropdown
    classrooms = Classroom.objects.all()

    # Fetch all group IDs except for "Owner" (group_id=1) and exclude group_id=5 and group_id=6
    editable_groups = Group.objects.exclude(id__in=[1, 5, 6])

    # Determine if the teacher is the main account holder (Owner)
    main_user = get_user_for_view(request)
    is_owner = teacher == main_user

    # Fetch the SubUser instance if the teacher is not the main account holder
    subuser = None
    if not is_owner:
        try:
            subuser = SubUser.objects.get(user=teacher)
        except SubUser.DoesNotExist:
            return HttpResponseRedirect('/classroom-options-teachers/')  # Redirect if SubUser not found

    # Get the previous page URL from the Referer header or the form
    previous_page = request.POST.get('previous_page', request.META.get('HTTP_REFERER', '/classroom-options-teachers/'))

    if request.method == 'POST':
        # Handle form submission
        first_name = request.POST.get('firstName')
        last_name = request.POST.get('lastName')
        email = request.POST.get('email')
        phone_number = request.POST.get('phoneNumber')
        address = request.POST.get('address')
        code = request.POST.get('code')
        classroom_id = request.POST.get('classroom')
        group_id = request.POST.get('group')

        # Validate the code to ensure it is a 4-digit number
        if not code.isdigit() or not (1000 <= int(code) <= 9999):
            return render(request, 'tottimeapp/edit_teacher.html', {
                'teacher': teacher,
                'classrooms': classrooms,
                'editable_groups': editable_groups,
                'is_owner': is_owner,
                'error': 'Code must be a 4-digit number.',
                'previous_page': previous_page,
                **permissions_context,
            })

        if not first_name or not last_name or not email:
            return render(request, 'tottimeapp/edit_teacher.html', {
                'teacher': teacher,
                'classrooms': classrooms,
                'editable_groups': editable_groups,
                'is_owner': is_owner,
                'error': 'First name, last name, and email are required.',
                'previous_page': previous_page,
                **permissions_context,
            })

        # Update teacher information
        teacher.first_name = first_name
        teacher.last_name = last_name
        teacher.email = email
        teacher.phone_number = phone_number
        teacher.address = address
        teacher.code = code

        # Update classroom assignment
        if classroom_id:
            try:
                classroom = Classroom.objects.get(id=classroom_id)
                ClassroomAssignment.objects.update_or_create(
                    mainuser=teacher,
                    defaults={'classroom': classroom}
                )
            except Classroom.DoesNotExist:
                pass

        # Update group ID if not the Owner
        if not is_owner:
            try:
                group = Group.objects.get(id=group_id)
                subuser.group_id = group  # Update the SubUser's group_id
                subuser.save()
            except Group.DoesNotExist:
                pass

        teacher.save()

        # Redirect to the previous page or the teacher list
        return HttpResponseRedirect(previous_page)

    # Fetch the teacher's current classroom assignment
    classroom_assignment = ClassroomAssignment.objects.filter(mainuser=teacher).select_related('classroom').first()
    teacher_classroom = classroom_assignment.classroom if classroom_assignment else None

    # Fetch the teacher's current group
    teacher_group = None
    if is_owner:
        teacher_group_name = "Owner"
    else:
        teacher_group = subuser.group_id if subuser else None
        teacher_group_name = teacher_group.name if teacher_group else "N/A"

    return render(request, 'tottimeapp/edit_teacher.html', {
        'teacher': teacher,
        'classrooms': classrooms,
        'editable_groups': editable_groups,
        'is_owner': is_owner,
        'teacher_classroom': teacher_classroom,
        'teacher_group': teacher_group,
        'teacher_group_name': teacher_group_name,
        'previous_page': previous_page,
        **permissions_context,
    })

@login_required
def edit_parent_info(request, parent_id):
    # Check permissions for the specific page
    permissions_context = check_permissions(request)
    if isinstance(permissions_context, HttpResponseRedirect):
        return permissions_context

    # Fetch the parent (MainUser)
    try:
        parent = MainUser.objects.get(id=parent_id)
    except MainUser.DoesNotExist:
        return HttpResponseRedirect('/classroom-options-parents/')  # Redirect if parent not found

    # Fetch the SubUser instance linked to the parent
    try:
        subuser = SubUser.objects.get(user=parent)
    except SubUser.DoesNotExist:
        subuser = None

    # Fetch the students linked to the SubUser
    linked_students = subuser.students.all() if subuser else []

    # Fetch all students for the modal
    all_students = Student.objects.all()

    # Get the previous page URL from the Referer header or the form
    previous_page = request.POST.get('previous_page', request.META.get('HTTP_REFERER', '/classroom-options-parents/'))

    if request.method == 'POST':
        # Handle form submission
        if 'update_students' in request.POST:
            # Update linked students
            selected_students = request.POST.getlist('students')
            if subuser:
                subuser.students.set(selected_students)
            return HttpResponseRedirect(request.path_info)

        # Update parent information
        first_name = request.POST.get('firstName')
        last_name = request.POST.get('lastName')
        email = request.POST.get('email')
        phone_number = request.POST.get('phoneNumber')
        address = request.POST.get('address')

        # Validate required fields
        if not first_name or not last_name or not email:
            return render(request, 'tottimeapp/edit_parent.html', {
                'parent': parent,
                'linked_students': linked_students,
                'all_students': all_students,
                'error': 'First name, last name, and email are required.',
                'previous_page': previous_page,
                **permissions_context,
            })

        # Update parent information
        parent.first_name = first_name
        parent.last_name = last_name
        parent.email = email
        parent.phone_number = phone_number
        parent.address = address
        parent.save()

        # Redirect to the previous page or the parent list
        return HttpResponseRedirect(previous_page)

    return render(request, 'tottimeapp/edit_parent.html', {
        'parent': parent,
        'linked_students': linked_students,
        'all_students': all_students,
        'previous_page': previous_page,
        **permissions_context,
    })

@login_required
def edit_classroom(request, classroom_id):
    # Check permissions for the specific page
    permissions_context = check_permissions(request)
    if isinstance(permissions_context, HttpResponseRedirect):
        return permissions_context

    # Fetch the classroom
    try:
        classroom = Classroom.objects.get(id=classroom_id)
    except Classroom.DoesNotExist:
        return HttpResponseRedirect('/classroom-options-classrooms/')  # Redirect if classroom not found

    # Get the previous page URL from the Referer header or the form
    previous_page = request.POST.get('previous_page', request.META.get('HTTP_REFERER', '/classroom-options-classrooms/'))

    if request.method == 'POST':
        # Handle form submission
        name = request.POST.get('name')
        ratios = request.POST.get('ratios')
        color = request.POST.get('color', '#57bdb4')  # Default if not provided

        # Validate the form inputs
        if not name:
            return render(request, 'tottimeapp/edit_classroom.html', {
                'classroom': classroom,
                'error': 'Classroom name is required.',
                'previous_page': previous_page,
                **permissions_context,
            })

        if not ratios.isdigit() or int(ratios) <= 0:
            return render(request, 'tottimeapp/edit_classroom.html', {
                'classroom': classroom,
                'error': 'Ratios must be a positive integer.',
                'previous_page': previous_page,
                **permissions_context,
            })

        # Update classroom information
        classroom.name = name
        classroom.ratios = int(ratios)
        classroom.color = color  # Save the color
        classroom.save()

        # Redirect to the previous page or the classroom list
        return HttpResponseRedirect(previous_page)

    return render(request, 'tottimeapp/edit_classroom.html', {
        'classroom': classroom,
        'previous_page': previous_page,
        **permissions_context,
    })

@login_required
def milk_count(request):
    # Check permissions for the specific page
    required_permission_id = 270  # Permission ID for milk_count view
    permissions_context = check_permissions(request, required_permission_id)
    # If check_permissions returns a redirect, return it immediately
    if isinstance(permissions_context, HttpResponseRedirect):
        return permissions_context
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
        **permissions_context,  # Include permission flags dynamically
    }
    return render(request, 'milk_count.html', context)

@login_required
def milk_count_view(request):
    # Check permissions for the specific page
    required_permission_id = 270  # Permission ID for milk_count_view
    permissions_context = check_permissions(request, required_permission_id)
    # If check_permissions returns a redirect, return it immediately
    if isinstance(permissions_context, HttpResponseRedirect):
        return permissions_context
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
            **permissions_context,  # Include permission flags dynamically
        }
    else:
        context = {
            'months': months,
            'years': years,
            **permissions_context,  # Include permission flags dynamically
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
    # Check permissions for the specific page
    required_permission_id = 269  # Permission ID for meal_count view
    permissions_context = check_permissions(request, required_permission_id)
    # If check_permissions returns a redirect, return it immediately
    if isinstance(permissions_context, HttpResponseRedirect):
        return permissions_context
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
        **permissions_context,  # Include permission flags dynamically
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
    # Check permissions for the specific page
    required_permission_id = 271  # Permission ID for weekly_menu
    permissions_context = check_permissions(request, required_permission_id)
    # If check_permissions returns a redirect, return it immediately
    if isinstance(permissions_context, HttpResponseRedirect):
        return permissions_context
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
        **permissions_context,  # Include permission flags dynamically
    }
    return render(request, 'past-menus.html', context)

@login_required
def assign_user_to_role(user, role_name):
    role_group, created = Group.objects.get_or_create(name=role_name)
    user.groups.add(role_group)

@login_required
def send_invitation(request):
    required_permission_id = 157
    permissions_context = check_permissions(request, required_permission_id)
    if isinstance(permissions_context, HttpResponseRedirect):
        return permissions_context

    success_message = ""

    # Only account owner can see Director (id=2)
    if hasattr(request.user, 'is_account_owner') and request.user.is_account_owner:
        roles = Group.objects.filter(id__in=range(2, 8)).exclude(id=6)
    else:
        roles = Group.objects.filter(id__in=range(3, 8)).exclude(id=6)  # Exclude Director (id=2)

    students = Student.objects.all()

    if request.method == 'POST':
        form = InvitationForm(request.POST)
        if form.is_valid():
            email = form.cleaned_data['email']
            role = form.cleaned_data['role']
            # Prevent non-owners from inviting as Director (extra backend check)
            if role.id == 2 and not (hasattr(request.user, 'is_account_owner') and request.user.is_account_owner):
                return HttpResponseForbidden("You are not allowed to invite as Director.")
            token = str(uuid.uuid4())
            student_ids = request.POST.getlist('student_ids')

            invitation = Invitation.objects.create(
                email=email,
                role=role,
                invited_by=request.user,
                token=token,
                student_ids=','.join(student_ids) if student_ids else None
            )

            invitation_link = f"https://tot-time.com/accept-invitation/{token}/"

            send_mail(
                'Invitation to Join',
                f'You have been invited to join with role: {role.name}. Click the link to accept: {invitation_link}',
                'cutiepieschilddevelopment@gmail.com',
                [email],
                fail_silently=False,
            )
            success_message = "Invitation email sent successfully."
    else:
        form = InvitationForm()

    return render(request, 'send-invitations.html', {
        'form': form,
        'success_message': success_message,
        'roles': roles,
        'students': students,
        **permissions_context,
    })

def accept_invitation(request, token):
    User = get_user_model()
    try:
        invitation = Invitation.objects.get(token=token)
        if request.method == 'POST':
            existing_user = User.objects.filter(email=invitation.email).first()
            if existing_user:
                return render(request, 'already_accepted.html', {'user': existing_user})
            # Extract the form data
            first_name = request.POST.get('first_name')
            last_name = request.POST.get('last_name')
            username = request.POST.get('username')
            password = request.POST.get('password1')
            # Always use invitation.email
            user = User.objects.create_user(
                username=username,
                email=invitation.email,
                password=password,
                first_name=first_name,
                last_name=last_name,
                main_account_owner=invitation.invited_by
            )
            subuser = SubUser.objects.create(
                user=user,
                main_user=invitation.invited_by,
                group_id=invitation.role
            )
            # Link students if any
            if invitation.student_ids:
                student_ids = [int(sid) for sid in invitation.student_ids.split(',') if sid]
                subuser.students.set(student_ids)
            invitation.delete()
            return redirect('login')
    except Invitation.DoesNotExist:
        return render(request, 'invalid_invitation.html')
    return render(request, 'accept_invitation.html', {'invitation': invitation})

def invalid_invitation(request):
    return render(request, 'invalid_invitation.html')

@login_required
def inbox_perms(request):
    required_permission_id = 157  # Permission ID for permissions view
    permissions_context = check_permissions(request, required_permission_id)
    if isinstance(permissions_context, HttpResponseRedirect):
        return permissions_context

    main_user = get_user_for_view(request)
    groups = Group.objects.exclude(name="Free User").exclude(id=8)
    for sender in groups:
        for receiver in groups:
            MessagingPermission.objects.get_or_create(
                main_user=main_user,
                sender_role=sender,
                receiver_role=receiver,
                defaults={'can_message': False}
            )
    messaging_permissions = MessagingPermission.objects.filter(main_user=main_user)
    all_users = MainUser.objects.filter(
        Q(main_account_owner=main_user) | Q(id=main_user.id)
    )
    user_messaging_permissions = UserMessagingPermission.objects.filter(main_user=main_user)

    if request.method == "POST":
        # Handle user-specific override table
        if "user_override_submit" in request.POST:
            sender_id = request.POST.get("sender_user")
            if sender_id:
                sender = MainUser.objects.get(id=sender_id)
                # Remove all overrides for this sender first (to reset)
                UserMessagingPermission.objects.filter(main_user=main_user, sender=sender).delete()
                # Now add overrides for checked boxes
                for key in request.POST:
                    if key.startswith("override_restrict_"):
                        receiver_id = key.split("_")[-1]
                        restrict = request.POST[key] == "1"
                        receiver = MainUser.objects.get(id=receiver_id)
                        if restrict:
                            UserMessagingPermission.objects.update_or_create(
                                main_user=main_user,
                                sender=sender,
                                receiver=receiver,
                                defaults={'can_message': False}
                            )
                messages.success(request, "User-specific messaging restrictions updated!")
        else:
            # ...existing group/role-based permission logic...
            try:
                for sender in groups:
                    for receiver in groups:
                        checkbox_name = f"sender_{sender.id}_receiver_{receiver.id}"
                        can_message = checkbox_name in request.POST
                        MessagingPermission.objects.update_or_create(
                            main_user=main_user,
                            sender_role=sender,
                            receiver_role=receiver,
                            defaults={'can_message': can_message}
                        )
                messages.success(request, "Messaging permissions have been successfully updated!")
            except Exception as e:
                messages.error(request, f"An error occurred: {str(e)}")

    return render(request, 'inbox_perms.html', {
        'groups': groups,
        'messaging_permissions': messaging_permissions,
        'all_users': all_users,
        'user_messaging_permissions': user_messaging_permissions,
        **permissions_context,
    })

@login_required
def permissions(request):
    # Check permissions for the specific page
    required_permission_id = 157  # Permission ID for permissions view
    permissions_context = check_permissions(request, required_permission_id)
    # If check_permissions returns a redirect, return it immediately
    if isinstance(permissions_context, HttpResponseRedirect):
        return permissions_context

    if request.method == "POST":
        for key, value in request.POST.items():
            if key.startswith("permission_"):
                parts = key.split("_")
                if len(parts) == 3:
                    permission_id, group_id = int(parts[1]), int(parts[2])
                    try:
                        role_permission = RolePermission.objects.get(role_id=group_id, permission_id=permission_id)
                        role_permission.yes_no_permission = value == "on"
                        role_permission.save()
                    except RolePermission.DoesNotExist:
                        pass  # Silent fail
        return redirect('permissions')

    # Fetch groups and exclude group 8, then order them alphabetically by name
    groups = Group.objects.exclude(id=8).exclude(name__in=["Owner", "Parent", "Free User"]).order_by('name')

    role_permissions = defaultdict(list)
    # Fetch role permissions for each group
    for group in groups:
        group_role_id = group.id
        role_permissions_for_group = RolePermission.objects.filter(role_id=group_role_id).order_by('permission__name')
        for role_permission in role_permissions_for_group:
            permission = role_permission.permission
            role_permissions[group_role_id].append({
                'id': permission.id,
                'permission_name': permission.name,
                'has_permission': role_permission.yes_no_permission
            })

    return render(request, 'permissions.html', {
        'groups': groups,
        'role_permissions': json.dumps(role_permissions),
        **permissions_context,  # Include permission flags dynamically
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
                        pass
    return redirect('permissions')

@login_required
def no_access(request):
    # Check permissions for the specific page
    permissions_context = check_permissions(request)
    # If check_permissions returns a redirect, return it immediately
    if isinstance(permissions_context, HttpResponseRedirect):
        return permissions_context
    # Directly render the no_access.html template with the permissions context
    return render(request, 'no_access.html', permissions_context)

def can_user_message(main_user, sender, receiver):
    # Check user-specific override
    user_perm = UserMessagingPermission.objects.filter(
        main_user=main_user, sender=sender, receiver=receiver
    ).first()
    if user_perm is not None:
        return user_perm.can_message
    # Fallback to role-based
    sender_group = sender.subuser.group_id if hasattr(sender, 'subuser') else Group.objects.get(name="Owner")
    receiver_group = receiver.subuser.group_id if hasattr(receiver, 'subuser') else Group.objects.get(name="Owner")
    role_perm = MessagingPermission.objects.filter(
        main_user=main_user,
        sender_role=sender_group,
        receiver_role=receiver_group
    ).first()
    return role_perm.can_message if role_perm else False

@login_required
def get_allowed_receivers(request):
    main_user = get_user_for_view(request)
    sender_id = request.GET.get("sender_id")
    if not sender_id:
        return JsonResponse({"receivers": []})
    try:
        sender = MainUser.objects.get(id=sender_id)
    except MainUser.DoesNotExist:
        return JsonResponse({"receivers": []})

    # Get sender's group
    sender_group = sender.subuser.group_id if hasattr(sender, 'subuser') else Group.objects.get(name="Owner")

    # Find all MessagingPermission for this sender group where can_message=True
    allowed_receiver_roles = MessagingPermission.objects.filter(
        main_user=main_user,
        sender_role=sender_group,
        can_message=True
    ).values_list('receiver_role', flat=True)

    # Get all users with those roles, except the sender
    all_users = MainUser.objects.filter(
        Q(main_account_owner=main_user) | Q(id=main_user.id)
    ).exclude(id=sender.id)

    receivers = []
    for user in all_users:
        # Get user's group
        receiver_group = user.subuser.group_id if hasattr(user, 'subuser') else Group.objects.get(name="Owner")
        if receiver_group.id in allowed_receiver_roles:
            # Check for user-specific override
            user_perm = UserMessagingPermission.objects.filter(
                main_user=main_user, sender=sender, receiver=user
            ).first()
            receivers.append({
                "id": user.id,
                "name": user.get_full_name(),
                "restricted": user_perm is not None and user_perm.can_message is False
            })
    return JsonResponse({"receivers": receivers})

@login_required
def inbox(request):
    required_permission_id = None
    permissions_context = check_permissions(request, required_permission_id)
    if isinstance(permissions_context, HttpResponseRedirect):
        return permissions_context

    main_account_owner = request.user.main_account_owner if not request.user.is_account_owner else request.user
    all_users = MainUser.objects.filter(
        Q(main_account_owner=main_account_owner) | Q(id=main_account_owner.id)
    ).exclude(id=request.user.id)
    user_group = request.user.subuser.group_id if hasattr(request.user, 'subuser') else Group.objects.get(name="Owner")
    messaging_permissions = MessagingPermission.objects.filter(
        sender_role=user_group,
        can_message=True
    )
    allowed_receiver_roles = list(messaging_permissions.values_list('receiver_role', flat=True))
    recipients_with_subuser = all_users.filter(
        subuser__group_id__in=allowed_receiver_roles
    )
    has_permission_to_message_owner = messaging_permissions.filter(
        receiver_role__id=1
    ).exists()
    if has_permission_to_message_owner:
        account_owner = MainUser.objects.filter(id=main_account_owner.id)
    else:
        account_owner = MainUser.objects.none()
    recipients = (recipients_with_subuser | account_owner).distinct()

    # Annotate each conversation with the unread count for the current user
    unread_count_subquery = Message.objects.filter(
        conversation=OuterRef('pk'),
        recipient=request.user,
        is_read=False
    ).values('conversation').annotate(
        count=Count('pk')
    ).values('count')

    conversations = Conversation.objects.filter(
        Q(sender=request.user) | Q(recipient=request.user)
    ).annotate(
        latest_message_timestamp=Max('messages__timestamp'),
        unread_count=Subquery(unread_count_subquery, output_field=IntegerField())
    ).filter(
        messages__isnull=False
    ).order_by('-latest_message_timestamp')

    conversation_users = set()
    for conversation in conversations:
        conversation_users.add(conversation.sender)
        conversation_users.add(conversation.recipient)
    recipients = recipients.exclude(id__in=[user.id for user in conversation_users])

    # Filter recipients based on user-specific permission overrides
    recipients = [
        recipient for recipient in recipients
        if can_user_message(main_account_owner, request.user, recipient)
    ]

    for recipient in recipients:
        recipient.first_name = recipient.first_name.strip()

    return render(request, 'messaging/inbox.html', {
        'conversations': conversations,
        'recipients': recipients,
        'messaging_permissions': messaging_permissions,
        'allowed_receiver_roles': allowed_receiver_roles,
        **permissions_context,
    })

@login_required
def conversation(request, user_id):
    required_permission_id = None  # Permission ID for permissions view
    permissions_context = check_permissions(request, required_permission_id)
    if isinstance(permissions_context, HttpResponseRedirect):
        return permissions_context

    recipient = get_object_or_404(MainUser, id=user_id)
    main_account_owner = request.user.main_account_owner if not request.user.is_account_owner else request.user

    # Check permission to message this user (with override)
    if not can_user_message(main_account_owner, request.user, recipient):
        return HttpResponseForbidden("You do not have permission to message this user.")

    conversation_obj = Conversation.objects.filter(
        (Q(sender=request.user) & Q(recipient=recipient)) |
        (Q(sender=recipient) & Q(recipient=request.user))
    ).first()
    if not conversation_obj:
        conversation_obj = Conversation.objects.create(sender=request.user, recipient=recipient)

    # Mark all unread messages in this conversation as read
    Message.objects.filter(conversation=conversation_obj, recipient=request.user, is_read=False).update(is_read=True)

    messages = Message.objects.filter(conversation=conversation_obj).order_by('timestamp')

    # Annotate each conversation with the unread count for the current user
    unread_count_subquery = Message.objects.filter(
        conversation=OuterRef('pk'),
        recipient=request.user,
        is_read=False
    ).values('conversation').annotate(
        count=Count('pk')
    ).values('count')

    # Fetch all conversations for the logged-in user
    conversations = Conversation.objects.filter(
        Q(sender=request.user) | Q(recipient=request.user)
    ).annotate(
        latest_message_timestamp=Max('messages__timestamp'),
        unread_count=Subquery(unread_count_subquery, output_field=IntegerField())
    ).filter(
        messages__isnull=False
    ).order_by('-latest_message_timestamp')

    # Fetch recipients for starting new conversations
    all_users = MainUser.objects.filter(
        Q(main_account_owner=main_account_owner) | Q(id=main_account_owner.id)
    ).exclude(id=request.user.id)
    user_group = request.user.subuser.group_id if hasattr(request.user, 'subuser') else Group.objects.get(name="Owner")
    messaging_permissions = MessagingPermission.objects.filter(
        sender_role=user_group,
        can_message=True
    )
    allowed_receiver_roles = list(messaging_permissions.values_list('receiver_role', flat=True))
    recipients_with_subuser = all_users.filter(
        subuser__group_id__in=allowed_receiver_roles
    )
    has_permission_to_message_owner = messaging_permissions.filter(
        receiver_role__id=1
    ).exists()
    if has_permission_to_message_owner:
        account_owner = MainUser.objects.filter(id=main_account_owner.id)
    else:
        account_owner = MainUser.objects.none()
    recipients = (recipients_with_subuser | account_owner).distinct()

    # Exclude users the logged-in user already has conversations with
    conversation_users = set()
    for conv in conversations:
        conversation_users.add(conv.sender)
        conversation_users.add(conv.recipient)
    recipients = recipients.exclude(id__in=[user.id for user in conversation_users])

    # Filter recipients based on user-specific permission overrides
    recipients = [
        recipient for recipient in recipients
        if can_user_message(main_account_owner, request.user, recipient)
    ]

    if request.method == 'POST':
        form = MessageForm(request.POST)
        if form.is_valid():
            new_message = form.save(commit=False)
            new_message.sender = request.user
            new_message.recipient = recipient
            new_message.conversation = conversation_obj
            new_message.save()
            return redirect('conversation', user_id=recipient.id)
    else:
        form = MessageForm()

    return render(request, 'messaging/conversation.html', {
        'form': form,
        'recipient': recipient,
        'messages': messages,
        'conversations': conversations,
        'recipients': recipients,
        **permissions_context,
    })

@login_required
def start_conversation(request, user_id):
    recipient = get_object_or_404(MainUser, id=user_id)
    # Check if the logged-in user is the account owner
    if not request.user.is_account_owner:
        # Check messaging permissions
        sender_role = request.user.subuser.group_id if hasattr(request.user, 'subuser') else Group.objects.get(name="Owner")
        receiver_role = recipient.subuser.group_id if hasattr(recipient, 'subuser') else Group.objects.get(name="Owner")
        if not sender_role or not receiver_role:
            return HttpResponseForbidden("You do not have permission to start a conversation with this user.")
        permission = MessagingPermission.objects.filter(
            sender_role=sender_role,
            receiver_role=receiver_role,
            can_message=True
        ).exists()
        if not permission:
            return HttpResponseForbidden("You do not have permission to start a conversation with this user.")
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
    if is_mobile:
        return HttpResponseRedirect(reverse('app_redirect'))

    # Check permissions
    required_permission_id = 331  # Permission ID for "billing"
    permissions_context = check_permissions(request, required_permission_id)
    if isinstance(permissions_context, HttpResponseRedirect):  # Corrected check
        return permissions_context  # Redirect if no access

    # Fetch data for the view
    subusers = SubUser.objects.prefetch_related('students').all()
    tuition_plans = TuitionPlan.objects.all()
    classrooms = Classroom.objects.all()

    # Fetch all active students and deduplicate by ID
    active_students = Student.objects.filter(status='active').order_by('id').distinct('id')

    # Deduplicate subusers by their ID
    unique_subusers = {}
    for subuser in subusers:
        if subuser.id not in unique_subusers:
            unique_subusers[subuser.id] = subuser
    subusers = list(unique_subusers.values())

    # Combine permissions context with other context data
    context = {
        'subusers': subusers,  # Pass deduplicated SubUser queryset
        'classrooms': classrooms,
        'tuition_plans': tuition_plans,
        'active_students': active_students,  # Include deduplicated active students
        **permissions_context,  # Include permission flags
    }
    return render(request, 'tottimeapp/payment.html', context)

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

def record_payment(request, subuser_id):
    if request.method == 'POST':
        subuser = get_object_or_404(SubUser, id=subuser_id)
        payment_amount = Decimal(request.POST.get('payment_amount'))
        payment_method = request.POST.get('payment_method')
        payment_note = request.POST.get('payment_note')
        # Update SubUser balance
        subuser.balance += payment_amount
        subuser.save()
        # Create a PaymentRecord
        PaymentRecord.objects.create(
            main_user=subuser.main_user,
            subuser=subuser,
            amount=payment_amount,
            source=payment_method,
            note=payment_note,
        )
        # Add a success message
        messages.success(request, f"{payment_method.capitalize()} payment of ${payment_amount} recorded successfully.")
        return redirect('payment')
    
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

@login_required
def stripe_login(request):
    # Check permissions for the specific page
    required_permission_id = 332  # Permission ID for payment setup view
    permissions_context = check_permissions(request, required_permission_id)
    # If check_permissions returns a redirect, return it immediately
    if isinstance(permissions_context, HttpResponseRedirect):
        return permissions_context
    # Render the stripe.html template with the permissions context
    return render(request, 'stripe.html', permissions_context)

def get_stripe_keys(user):
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
    # Check permissions for the specific page
    required_permission_id = 337  # Permission ID for clock_in view
    permissions_context = check_permissions(request, required_permission_id)
    # If check_permissions returns a redirect, return it immediately
    if isinstance(permissions_context, HttpResponseRedirect):
        return permissions_context
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
    # Render the clock_in page with the permissions context
    return render(request, 'clock_in.html', permissions_context)

@login_required
def time_sheet(request):
    # Detect if the request is from a mobile device
    is_mobile = any(device in request.META.get('HTTP_USER_AGENT', '').lower() for device in [
        'iphone', 'android', 'mobile', 'cordova', 'tablet', 'ipod', 'windows phone'
    ])
    # If it's a mobile request, redirect to the app_redirect page
    if is_mobile:
        return HttpResponseRedirect(reverse('app_redirect'))  # Ensure 'app_redirect' is defined in your URLs
    # Check permissions for the specific page
    required_permission_id = 337  # Permission ID for time_sheet view
    permissions_context = check_permissions(request, required_permission_id)
    # If check_permissions returns a redirect, return it immediately
    if isinstance(permissions_context, HttpResponseRedirect):
        return permissions_context
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
    end_date = request.GET.get('end_date', previous_thursday.strftime('%Y-%m-%d'))
    try:
        start_date = datetime.strptime(str(start_date), '%Y-%m-%d').date()
        end_date = datetime.strptime(str(end_date), '%Y-%m-%d').date()
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
        **permissions_context,  # Include permission flags dynamically
    })

@login_required
def employee_detail(request):
    # Check permissions for the specific page
    required_permission_id = 337  # Permission ID for time_sheet view
    permissions_context = check_permissions(request, required_permission_id)
    # If check_permissions returns a redirect, return it immediately
    if isinstance(permissions_context, HttpResponseRedirect):
        return permissions_context
    employee_id = request.GET.get('employee')
    if not employee_id:
        return redirect('time_sheet')  # Redirect if no employee ID is provided
    user = get_user_for_view(request)
    today = now().date()
    # Calculate the previous Friday (the most recent Friday)
    days_since_friday = today.weekday() - 4  # 4 corresponds to Friday
    if days_since_friday < 0:
        days_since_friday += 7
    previous_friday = today - timedelta(days=days_since_friday)
    # Calculate the previous Thursday (the day before the previous Friday)
    previous_thursday = previous_friday + timedelta(days=6)
    # Get date range from request or use defaults
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
        **permissions_context,  # Include permission flags dynamically
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
    # Check permissions for the specific page
    required_permission_id = 332  # Permission ID for payment setup view
    permissions_context = check_permissions(request, required_permission_id)
    # If check_permissions returns a redirect, return it immediately
    if isinstance(permissions_context, HttpResponseRedirect):
        return permissions_context
    context = {
        "square_connected": square_connected,
        "square_login_url": "/square/login/",  # URL for Square login
        **permissions_context,  # Include permission flags dynamically
    }
    return render(request, 'square.html', context)

@login_required
def pay_summary(request):
    # Check permissions for the specific page
    required_permission_id = 346  # Permission ID for pay_summary view
    permissions_context = check_permissions(request, required_permission_id)
    # If check_permissions returns a redirect, return it immediately
    if isinstance(permissions_context, HttpResponseRedirect):
        return permissions_context
    # Retrieve the square credentials from the MainUser model
    main_user = request.user  # Assuming the MainUser is linked to request.user
    return render(request, 'pay_summary.html', {
        **permissions_context,  # Include permission flags dynamically
        'sub_user': SubUser.objects.filter(user=request.user).first(),  # Pass the sub_user if it exists
        'SQUARE_APPLICATION_ID': settings.SQUARE_APPLICATION_ID,
        'SQUARE_LOCATION_ID': getattr(main_user, 'square_location_id', None),
        'SQUARE_ACCESS_TOKEN': getattr(main_user, 'square_access_token', None),
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
                environment='sandbox'  # Change to 'production' for live
            )
            # Validate amount
            try:
                amount = int(float(data['amount']) * 100)  # Convert to cents
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
                    "customer_id": f"user_{request.user.id}",
                    "note": f"Wallet top-up for {request.user.email}"
                }
            )
            if result.is_success():
                # Only update balance and record payment if SubUser exists
                try:
                    subuser = SubUser.objects.get(user=request.user)
                    # Safely update balance
                    added_amount = Decimal(str(data['amount']))
                    SubUser.objects.filter(pk=subuser.pk).update(
                        balance=models.F('balance') + added_amount
                    )
                    # Create a PaymentRecord
                    PaymentRecord.objects.create(
                        main_user=subuser.main_user,
                        subuser=subuser,
                        amount=added_amount,
                        source='card',
                        note='Wallet top-up via Square'
                    )
                except SubUser.DoesNotExist:
                    return JsonResponse({'success': False, 'error': 'SubUser account not found'})
                return JsonResponse({
                    'success': True,
                    'message': f'Confirmation of payment: ${data["amount"]} successfully added to wallet.'
                })
            return JsonResponse({'success': False, 'error': result.errors})
        except Exception as e:
            logger.error(f"Payment error: {str(e)}")
            return JsonResponse({'success': False, 'error': str(e)})
    return JsonResponse({'success': False, 'error': 'Invalid method'})

@login_required
def add_tuition_plan(request):
    if request.method == 'POST':
        subuser_id = request.POST.get('subuser')
        weekly_amount = request.POST.get('weekly_amount')
        start_date = request.POST.get('start_date')
        # Create the tuition plan
        TuitionPlan.objects.create(
            subuser_id=subuser_id,
            weekly_amount=weekly_amount,
            start_date=start_date,
            is_active=True
        )
        messages.success(request, "Tuition plan added successfully.")
        return redirect('payment')
    return render(request, 'tottimeapp/payment.html')

def edit_tuition_plan(request, plan_id):
    if request.method == 'POST':
        plan = TuitionPlan.objects.get(id=plan_id)
        subuser_id = request.POST.get('subuser')
        weekly_amount = request.POST.get('weekly_amount')
        start_date = request.POST.get('start_date')
        is_active = request.POST.get('is_active') == 'true'
        # Check if another active tuition plan exists for the subuser
        if is_active and TuitionPlan.objects.filter(subuser_id=subuser_id, is_active=True).exclude(id=plan_id).exists():
            messages.error(request, "This user already has an active tuition set.")
            return redirect('payment')  # Redirect back to the payment page
        # Update the tuition plan
        plan.subuser_id = subuser_id
        plan.weekly_amount = weekly_amount
        plan.start_date = start_date
        plan.is_active = is_active
        plan.save()
        messages.success(request, "Tuition plan updated successfully.")
        return redirect('payment')
    return render(request, 'payment')

@login_required
def pay_history(request, subuser_id):
    # Check permissions for the specific page
    required_permission_id = 331  # Permission ID for "billing"
    permissions_context = check_permissions(request, required_permission_id)
    # If check_permissions returns a redirect, return it immediately
    if isinstance(permissions_context, HttpResponseRedirect):
        return permissions_context
    subuser = get_object_or_404(SubUser, id=subuser_id)
    # Get the current month and year
    current_month = datetime.now().month
    current_year = datetime.now().year
    # Get the filter values from the request or default to the current month
    start_date = request.GET.get('start_date', f'{current_year}-{current_month:02d}-01')
    end_date = request.GET.get('end_date', f'{current_year}-{current_month:02d}-{monthrange(current_year, current_month)[1]}')
    # Filter payment records by date range
    payment_records = PaymentRecord.objects.filter(
        subuser=subuser,
        timestamp__date__gte=start_date,
        timestamp__date__lte=end_date
    ).order_by('-timestamp')
    # Filter weekly tuitions by date range
    weekly_tuitions = WeeklyTuition.objects.filter(
        subuser=subuser,
        start_date__gte=start_date,
        end_date__lte=end_date
    ).order_by('start_date')
    context = {
        'subuser': subuser,
        'payment_records': payment_records,
        'weekly_tuitions': weekly_tuitions,
        'start_date': start_date,
        'end_date': end_date,
        **permissions_context,  # Include permission flags dynamically
    }
    return render(request, 'tottimeapp/pay_history.html', context)

@login_required
def all_pay_history(request):
    # Check permissions for the specific page
    required_permission_id = 331  # Permission ID for "billing"
    permissions_context = check_permissions(request, required_permission_id)
    if isinstance(permissions_context, HttpResponseRedirect):
        return permissions_context

    # Get the current month and year
    current_month = datetime.now().month
    current_year = datetime.now().year

    # Get the filter values from the request or default to the current month
    start_date = request.GET.get('start_date', f'{current_year}-{current_month:02d}-01')
    end_date = request.GET.get('end_date', f'{current_year}-{current_month:02d}-{monthrange(current_year, current_month)[1]}')
    search_query = request.GET.get('search', '').strip()

    # Fetch all payment records within the date range
    payment_records = PaymentRecord.objects.filter(
        timestamp__date__gte=start_date,
        timestamp__date__lte=end_date
    ).select_related('subuser', 'subuser__user').prefetch_related('subuser__students')

    # Apply search filter if a search query is provided
    if search_query:
        payment_records = payment_records.filter(
            Q(subuser__user__first_name__icontains=search_query) |
            Q(subuser__user__last_name__icontains=search_query) |
            Q(subuser__students__first_name__icontains=search_query) |
            Q(subuser__students__last_name__icontains=search_query)
        ).distinct()

    payment_records = payment_records.order_by('-timestamp')

    # Add student names and subuser names to the context
    payment_data = []
    for record in payment_records:
        linked_students = record.subuser.students.all()  # Fetch all students linked to the SubUser
        student_names = ", ".join([f"{student.first_name} {student.last_name}" for student in linked_students]) or "No Students Linked"
        subuser_name = f"{record.subuser.user.first_name} {record.subuser.user.last_name}"
        payment_data.append({
            'record': record,
            'subuser_name': subuser_name,
            'student_names': student_names,  # Pass as a single string
        })

    context = {
        'payment_data': payment_data,
        'start_date': start_date,
        'end_date': end_date,
        'search_query': search_query,
        **permissions_context,
    }
    return render(request, 'tottimeapp/all_pay_history.html', context)