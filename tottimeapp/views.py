from django.shortcuts import render, redirect, get_object_or_404
from .models import Recipe, BreakfastRecipe, AMRecipe, PMRecipe, FruitRecipe, VegRecipe, WgRecipe, RecipeSimilarityGroup
from django.contrib.auth.models import Group
from django.contrib.auth import authenticate, login, logout, get_user_model
from django.db.models import Q, Subquery, IntegerField, Count, F, Sum, Max, Min, ExpressionWrapper, DurationField, Exists, OuterRef
from django.db.models.functions import Concat, Lower
from django.http import HttpResponseForbidden, HttpResponseBadRequest, JsonResponse, HttpResponseNotAllowed, HttpResponseRedirect
from django.utils import timezone as django_timezone
import urllib.parse, stripe, requests, random, logging, json, pytz, os, uuid
from square.client import Client
from django.conf import settings
import re
from django.http import Http404
from functools import wraps
from django.core.exceptions import FieldError
from bs4 import BeautifulSoup, Comment
from django.core.paginator import Paginator
from django.db import IntegrityError
stripe.api_key = settings.STRIPE_SECRET_KEY
from django.db.models.functions import TruncDate
from django.utils.timezone import now
from decimal import Decimal
from django.db import transaction, models
from django.contrib import messages
from django.db.models import Count, Avg
from django.contrib.sites.shortcuts import get_current_site
from .forms import SignupForm, ImprovementGoalFormSet, ImprovementPlan,ImprovementPlanForm, ImprovementGoal, SurveyForm, QuestionForm, ForgotUsernameForm, LoginForm, RuleForm, MessageForm, InvitationForm
from .models import Classroom, WeeklyMenuAssignedRule, TemporaryAccess, FeedRecord, CurriculumTheme, CurriculumActivity, IndicatorPageLink, PublicLink, Response, Survey, Answer, Question, Choice, ABCQualityElement, ABCQualityIndicator, ResourceSignature, Resource, StandardCategory, ClassroomScoreSheet, StandardCriteria, ScoreItem, OrientationItem, StaffOrientation, OrientationProgress, EnrollmentTemplate, EnrollmentPolicy, EnrollmentSubmission, CompanyAccountOwner, Announcement, UserMessagingPermission, DiaperChangeRecord, IncidentReport, MainUser, SubUser, RolePermission, Student, Inventory, Recipe, MessagingPermission, Classroom, ClassroomAssignment, OrderList, Student, AttendanceRecord, Message, Conversation, Payment, WeeklyTuition, TeacherAttendanceRecord, TuitionPlan, PaymentRecord, MilkCount, WeeklyMenu, Rule, MainUser, RolePermission, SubUser, Invitation, RecipeIngredient, NutritionFact
from django.contrib.contenttypes.models import ContentType
from django.contrib.auth.decorators import login_required
from django.views.decorators.csrf import csrf_protect, csrf_exempt
from django.views.decorators.http import require_POST
from PIL import Image
from io import BytesIO
from django.urls import reverse, resolve, Resolver404
from botocore.exceptions import ClientError
from pytz import utc
from datetime import datetime, timedelta, date, time
from collections import defaultdict
from django.utils import timezone
from calendar import monthrange
from django.core.mail import send_mail
from django.urls import reverse
from django.core.exceptions import ValidationError
import bleach, calendar, boto3
from botocore.client import Config
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.utils.html import strip_tags
import requests
from django.http import HttpResponse
from django.views.decorators.clickjacking import xframe_options_exempt
from django.urls import get_resolver, reverse, NoReverseMatch
from django.views.decorators.http import require_http_methods

ALLOWED_TAGS = [
    'p', 'b', 'strong', 'i', 'em', 'u', 'ul', 'ol', 'li', 'br', 'span'
]
ALLOWED_ATTRIBUTES = {
    'a': ['href', 'rel', 'target'], 
    'span': ['style']
}
ALLOWED_STYLES = ['font-weight', 'font-style', 'text-decoration']

logger = logging.getLogger(__name__)

def public_or_login_required(view_func):
    """
    Decorator that allows access either via login or temporary token
    """
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        # Allow access if already authenticated (via login or temp token)
        if request.user.is_authenticated:
            return view_func(request, *args, **kwargs)
        
        # Otherwise redirect to login
        return login_required(view_func)(request, *args, **kwargs)
    
    return wrapper


def homepage(request):
    """Public homepage view for anonymous visitors."""
    if request.user.is_authenticated:
        return redirect('index')
    # Server-side remember-me: if a valid token cookie exists, log in and redirect immediately
    # so the homepage never renders for returning app users (eliminates the flash).
    token = request.COOKIES.get('tt_remember_token', '').strip()
    if token:
        User = get_user_model()
        try:
            matching_users = User.objects.filter(session_token=token)
            if matching_users.count() == 1:
                user = matching_users.first()
                login(request, user, backend='django.contrib.auth.backends.ModelBackend')
                return redirect('index')
        except ValueError:
            pass

        # Invalid or non-unique token: clear cookie and render homepage safely.
        response = render(request, 'tottimeapp/homepage.html', {})
        response.delete_cookie('tt_remember_token')
        return response
    return render(request, 'tottimeapp/homepage.html', {})

def get_user_for_view(request):
    """
    Returns the appropriate main_user for the current request.
    Checks for:
    1. Public access token (request.temp_main_user set by middleware)
    2. Linked account (main_account_owner_id)
    3. Current user
    """
    # Check if this is a public access request
    if hasattr(request, 'temp_main_user'):
        logger.info(f"Using temp_main_user from public access: {request.temp_main_user.id}")
        return request.temp_main_user
    
    user = request.user
    logger.info(f"get_user_for_view called for user: {user.id} ({user.username})")
    
    # If user has a main_account_owner and they are currently viewing as that account owner
    # This handles the "switch" functionality where users can view other locations
    if hasattr(user, 'main_account_owner') and user.main_account_owner:
        # Check if there's a session variable indicating which location they're viewing
        current_viewing_location = request.session.get('current_viewing_location')
        if current_viewing_location:
            try:
                main_user = MainUser.objects.get(id=current_viewing_location)
                logger.info(f"Using session location: {main_user.id} ({main_user.username})")
                return main_user
            except MainUser.DoesNotExist:
                pass
        
        # Default to main_account_owner if no session override
        main_user = user.main_account_owner
        logger.info(f"Returning main_account_owner: {main_user.id} ({main_user.username})")
        return main_user
    
    logger.info(f"Returning original user: {user.id} ({user.username})")
    return user


def normalize_inventory_category(category_value):
    """Normalize inventory category text for consistent tabs and filtering."""
    cleaned = re.sub(r'\s+', ' ', str(category_value or '')).strip()
    if not cleaned:
        return 'Other'

    # Treat common misc variants as one category.
    if cleaned.casefold().rstrip('.') == 'misc':
        return 'Misc'

    return cleaned


def parse_checkbox_value(value):
    return str(value or '').strip().lower() in {'1', 'true', 'on', 'yes'}


def build_inventory_side_dish_fields(post_data):
    is_side_dish = parse_checkbox_value(post_data.get('is_side_dish'))
    meal_period = (post_data.get('meal_period') or '').strip()
    valid_periods = {choice for choice, _label in Inventory.MEAL_PERIOD_CHOICES}
    populate_fields = {
        'populate_breakfast': False,
        'populate_am_snack': False,
        'populate_lunch': False,
        'populate_pm_snack': False,
    }

    if not is_side_dish:
        return {
            'is_side_dish': False,
            'meal_period': 'all',
            **populate_fields,
        }, None

    if meal_period == 'manual':
        populate_fields = {
            'populate_breakfast': parse_checkbox_value(post_data.get('populate_breakfast')),
            'populate_am_snack': parse_checkbox_value(post_data.get('populate_am_snack')),
            'populate_lunch': parse_checkbox_value(post_data.get('populate_lunch')),
            'populate_pm_snack': parse_checkbox_value(post_data.get('populate_pm_snack')),
        }
        selected_periods = [
            period for period in ['breakfast', 'am_snack', 'lunch', 'pm_snack']
            if populate_fields[f'populate_{period}']
        ]

        if not selected_periods:
            return None, 'Select at least one meal period for manual selection.'

        requested_order = [
            value.strip() for value in (post_data.get('manual_selection_order') or '').split(',')
            if value.strip() in selected_periods
        ]
        ordered_periods = []
        for period in requested_order + selected_periods:
            if period not in ordered_periods:
                ordered_periods.append(period)

        return {
            'is_side_dish': True,
            'meal_period': ordered_periods[0],
            **populate_fields,
        }, None

    if meal_period not in valid_periods:
        return None, 'Meal period is required for side dishes.'

    if meal_period == 'all':
        for key in populate_fields:
            populate_fields[key] = True
    else:
        populate_fields[f'populate_{meal_period}'] = True

    return {
        'is_side_dish': True,
        'meal_period': meal_period,
        **populate_fields,
    }, None

def get_recipe_ingredients(recipe):
    """
    Get ingredients for a recipe from the RecipeIngredient table.
    Returns list of tuples: [(ingredient_obj, quantity), ...]
    Works with any recipe model that has GenericRelation 'ingredients'.
    """
    if not recipe:
        return []
    
    # Get content type for this recipe's model
    content_type = ContentType.objects.get_for_model(recipe)
    
    # Query RecipeIngredient for this recipe
    recipe_ingredients = RecipeIngredient.objects.filter(
        content_type=content_type,
        object_id=recipe.id
    ).select_related('ingredient')
    
    # Return as list of tuples (ingredient, quantity)
    return [(ri.ingredient, ri.quantity) for ri in recipe_ingredients if ri.ingredient]

def save_recipe_ingredients(recipe, ingredient_ids, quantities):
    """
    Save ingredients for a recipe to the RecipeIngredient table.
    Deletes existing ingredients and creates new ones.
    
    Args:
        recipe: The recipe object (any model with GenericRelation 'ingredients')
        ingredient_ids: List of ingredient IDs from POST data
        quantities: List of quantities corresponding to each ingredient
    """
    if not recipe:
        return
    
    # Get content type for this recipe's model
    content_type = ContentType.objects.get_for_model(recipe)
    
    # Delete existing recipe ingredients
    RecipeIngredient.objects.filter(
        content_type=content_type,
        object_id=recipe.id
    ).delete()
    
    # Create new recipe ingredients
    for ingredient_id, quantity in zip(ingredient_ids, quantities):
        if ingredient_id and quantity:
            try:
                ingredient = Inventory.objects.get(id=ingredient_id)
                RecipeIngredient.objects.create(
                    content_type=content_type,
                    object_id=recipe.id,
                    ingredient=ingredient,
                    quantity=Decimal(quantity)
                )
            except (Inventory.DoesNotExist, ValueError):
                # Skip invalid ingredients or quantities
                pass

def check_permissions(request, required_permission_id=None):
    """
    Check user permissions and return context variables for links.
    """
    allow_access = True if required_permission_id is None else False
    permissions_context = {
        'show_weekly_menu': False,
        'show_infant_menu': False,
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
        'show_enrollment': False,
        'show_orientation': False,
        'show_todays_menu': False,
        'total_unread_count': 0,
    }

    # Prefer the MainUser.primary_group first; fall back to SubUser.group_id when absent.
    group_id = None
    main_user_id = None

    # Try primary_group on the user (works for MainUser instances)
    main_group_id = getattr(request.user, 'primary_group_id', None)
    if main_group_id:
        group_id = main_group_id
        main_user_id = getattr(request.user, 'id', None)
    else:
        # Fallback: try SubUser mapping
        try:
            sub_user = SubUser.objects.get(user=request.user)
            group_id = sub_user.group_id.id
            main_user_id = sub_user.main_user.id
        except SubUser.DoesNotExist:
            # No primary_group and not a SubUser: treat as main user with full access
            allow_access = True
            for key in permissions_context:
                permissions_context[key] = True

    # If we have a role mapping (group_id + main_user_id), evaluate permissions
    if group_id and main_user_id:
        # Check for required permission
        if required_permission_id:
            allow_access = RolePermission.objects.filter(
                role_id=group_id,
                permission_id=required_permission_id,
                yes_no_permission=True,
                main_user_id=main_user_id
            ).exists()

        permissions_ids = {
            'weekly_menu': 271,
            'infant_menu': 414,
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
            'enrollment': 416,
            'orientation': 450,
            'todays_menu': 555, 
        }

        for perm_key, perm_id in permissions_ids.items():
            permissions_context[f'show_{perm_key}'] = RolePermission.objects.filter(
                role_id=group_id,
                permission_id=perm_id,
                yes_no_permission=True,
                main_user_id=main_user_id
            ).exists()

        conversations = Conversation.objects.filter(
            Q(sender=request.user) | Q(recipient=request.user)
        ).annotate(
            unread_count=Count('messages', filter=Q(messages__recipient=request.user, messages__is_read=False))
        )
        total_unread_count = conversations.aggregate(total_unread=Sum('unread_count'))['total_unread'] or 0
        permissions_context['total_unread_count'] = total_unread_count

    if not allow_access:
        return redirect('no_access')

    return permissions_context

def sanitize_html(html_content):
    return bleach.clean(
        html_content,
        tags=ALLOWED_TAGS,
        attributes=ALLOWED_ATTRIBUTES,
        strip=True
    )

def app_redirect(request):
    permissions_context = check_permissions(request)
    if isinstance(permissions_context, HttpResponseRedirect):
        return permissions_context
    return render(request, 'app_redirect.html', permissions_context)

@login_required(login_url='/login/')
def index(request):
    required_permission_id = None
    permissions_context = check_permissions(request, required_permission_id)
    if isinstance(permissions_context, HttpResponseRedirect):
        return permissions_context

    user = get_user_for_view(request)
    # Check the MainUser.primary_group first for security-based redirects.
    # If no primary_group is present, fall back to SubUser.group_id.
    try:
        main_group_id = getattr(request.user, 'primary_group_id', None)
        if main_group_id == 2:
            return redirect('index_director')
        elif main_group_id == 3:
            return redirect('index_teacher')
        elif main_group_id == 4:
            return redirect('index_cook')
        elif main_group_id == 5:
            return redirect('index_parent')
        elif main_group_id == 7:
            return redirect('index_teacher_parent')
        elif main_group_id == 6:
            return redirect('index_free_user')
        elif main_group_id == 9:
            return redirect('index_cacfp')
    except Exception:
        # Be resilient to unexpected user objects; continue to SubUser check
        pass

    # Fallback: check SubUser.group_id if no primary_group redirect occurred
    try:
        sub_user = SubUser.objects.get(user=request.user)
        group_id = sub_user.group_id_id
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
        elif group_id == 9:
            return redirect('index_cacfp')
    except SubUser.DoesNotExist:
        pass

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
        count = attendance_records.filter(classroom_override=classroom.name).count()
        assignments = ClassroomAssignment.objects.filter(classroom=classroom)
        assigned_teachers = [
            assignment.mainuser or assignment.subuser for assignment in assignments
        ]
        base_ratio = classroom.ratios
        teacher_count = len(assigned_teachers)
        adjusted_ratio = base_ratio * (2 ** (teacher_count - 1)) if teacher_count > 0 else base_ratio
        classroom_cards[classroom.name] = {
            'id': classroom.id,
            'count': count,
            'ratio': adjusted_ratio
        }

    now = timezone.now()
    student_announcements = Announcement.objects.filter(
        user=user,
        recipient_type='student'
    ).filter(
        models.Q(expires_at__isnull=False) & models.Q(expires_at__gt=now)
    ).order_by('-created_at')

    teacher_announcements = Announcement.objects.filter(
        user=user,
        recipient_type='teacher'
    ).filter(
        models.Q(expires_at__isnull=False) & models.Q(expires_at__gt=now)
    ).order_by('-created_at')

    context = {
        'order_items': order_items,
        'classroom_cards': classroom_cards,
        'student_announcements': student_announcements,
        'teacher_announcements': teacher_announcements,
        **permissions_context,
    }
    return render(request, 'index.html', context)

@login_required(login_url='/login/')
def index_director(request):
    user = get_user_for_view(request)
    required_permission_id = None
    permissions_context = check_permissions(request, required_permission_id)
    if isinstance(permissions_context, HttpResponseRedirect):
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
        count = attendance_records.filter(classroom_override=classroom.name).count()
        assignments = ClassroomAssignment.objects.filter(
            classroom=classroom,
            unassigned_at__isnull=True
        )
        assigned_teachers = [
            assignment.mainuser or assignment.subuser
            for assignment in assignments
            if assignment.mainuser or assignment.subuser
        ]
        base_ratio = classroom.ratios
        teacher_count = len(assigned_teachers)
        adjusted_ratio = base_ratio * (2 ** (teacher_count - 1)) if teacher_count > 0 else base_ratio
        classroom_cards[classroom.name] = {
            'id': classroom.id,
            'count': count,
            'ratio': adjusted_ratio
        }

    now = timezone.now()
    student_announcements = Announcement.objects.filter(
        user=user,
        recipient_type='student'
    ).filter(
        models.Q(expires_at__isnull=True) | models.Q(expires_at__gt=now)
    ).order_by('-created_at')

    teacher_announcements = Announcement.objects.filter(
        user=user,
        recipient_type='teacher'
    ).filter(
        models.Q(expires_at__isnull=True) | models.Q(expires_at__gt=now)
    ).order_by('-created_at')

    context = {
        'order_items': order_items,
        'classroom_cards': classroom_cards,
        'student_announcements': student_announcements,
        'teacher_announcements': teacher_announcements,
        **permissions_context,
    }

    return render(request, 'index_director.html', context)

@login_required(login_url='/login/')
def index_teacher(request):
    required_permission_id = None  # No specific permission required for this page
    permissions_context = check_permissions(request, required_permission_id)
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
        count = attendance_records.filter(classroom_override=classroom.name).count()
        assignments = ClassroomAssignment.objects.filter(classroom=classroom)
        assigned_teachers = [
            assignment.mainuser or assignment.subuser for assignment in assignments
        ]
        base_ratio = classroom.ratios
        teacher_count = len(assigned_teachers)
        adjusted_ratio = base_ratio * (2 ** (teacher_count - 1)) if teacher_count > 0 else base_ratio
        classroom_cards[classroom.name] = {
            'id': classroom.id,
            'count': count,
            'ratio': adjusted_ratio
        }

    # Fetch active student and teacher announcements (not expired)
    now = timezone.now()
    student_announcements = Announcement.objects.filter(
        user=user,
        recipient_type='student'
    ).filter(
        models.Q(expires_at__isnull=False) & models.Q(expires_at__gt=now)
    ).order_by('-created_at')

    teacher_announcements = Announcement.objects.filter(
        user=user,
        recipient_type='teacher'
    ).filter(
        models.Q(expires_at__isnull=False) & models.Q(expires_at__gt=now)
    ).order_by('-created_at')

    context = {
        'classroom_cards': classroom_cards,
        'student_announcements': student_announcements,
        'teacher_announcements': teacher_announcements,
        **permissions_context,
    }
    return render(request, 'index_teacher.html', context)

@login_required(login_url='/login/')
def index_teacher_parent(request):
    required_permission_id = None  # No specific permission required for this page
    permissions_context = check_permissions(request, required_permission_id)
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
        count = attendance_records.filter(classroom_override=classroom.name).count()
        assignments = ClassroomAssignment.objects.filter(classroom=classroom)
        assigned_teachers = [
            assignment.mainuser or assignment.subuser for assignment in assignments
        ]
        base_ratio = classroom.ratios
        teacher_count = len(assigned_teachers)
        adjusted_ratio = base_ratio * (2 ** (teacher_count - 1)) if teacher_count > 0 else base_ratio
        classroom_cards[classroom.name] = {
            'id': classroom.id,
            'count': count,
            'ratio': adjusted_ratio
        }

    # Fetch active student and teacher announcements (not expired)
    now = timezone.now()
    student_announcements = Announcement.objects.filter(
        user=user,
        recipient_type='student'
    ).filter(
        models.Q(expires_at__isnull=False) & models.Q(expires_at__gt=now)
    ).order_by('-created_at')

    teacher_announcements = Announcement.objects.filter(
        user=user,
        recipient_type='teacher'
    ).filter(
        models.Q(expires_at__isnull=False) & models.Q(expires_at__gt=now)
    ).order_by('-created_at')
      # Get today's attendance snapshot data for students linked to this subuser
    today = timezone.localdate()
    snapshot_data = []
    
    # Check if this is a subuser (teacher-parent) and get their linked students
    try:
        subuser = SubUser.objects.get(user=request.user)
        linked_students = subuser.students.all()
        
        # Get attendance records for today for only the linked students
        todays_attendance = AttendanceRecord.objects.filter(
            sign_in_time__date=today,
            student__in=linked_students,
            user=subuser.main_user  # Use the main_user for the attendance records
        ).select_related('student', 'incident_report').order_by('-sign_in_time')
        
    except SubUser.DoesNotExist:
        # If not a subuser, show all students (fallback behavior)
        todays_attendance = AttendanceRecord.objects.filter(
            sign_in_time__date=today,
            user=user
        ).select_related('student', 'incident_report').order_by('-sign_in_time')
    
    for attendance in todays_attendance:
        snapshot_data.append({
            'student': attendance.student,
            'sign_in_time': attendance.sign_in_time,
            'sign_out_time': attendance.sign_out_time,
            'outside_time_out_1': attendance.outside_time_out_1,
            'outside_time_in_1': attendance.outside_time_in_1,  
            'outside_time_out_2': attendance.outside_time_out_2,
            'outside_time_in_2': attendance.outside_time_in_2,
            'incident_report': attendance.incident_report,
        })
    
    context = {
        'classroom_cards': classroom_cards,
        'student_announcements': student_announcements,
        'teacher_announcements': teacher_announcements,
        'snapshot_data': snapshot_data,
        **permissions_context,
    }
    return render(request, 'index_teacher_parent.html', context)

@login_required(login_url='/login/')
def index_cook(request):
    required_permission_id = None  # No specific permission required for this page
    permissions_context = check_permissions(request, required_permission_id)
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
        count = attendance_records.filter(classroom_override=classroom.name).count()
        assignments = ClassroomAssignment.objects.filter(classroom=classroom)
        assigned_teachers = [
            assignment.mainuser or assignment.subuser for assignment in assignments
        ]
        base_ratio = classroom.ratios
        teacher_count = len(assigned_teachers)
        adjusted_ratio = base_ratio * (2 ** (teacher_count - 1)) if teacher_count > 0 else base_ratio
        classroom_cards[classroom.name] = {
            'id': classroom.id,
            'count': count,
            'ratio': adjusted_ratio
        }

    # Fetch active student and teacher announcements (not expired)
    now = timezone.now()
    student_announcements = Announcement.objects.filter(
        user=user,
        recipient_type='student'
    ).filter(
        models.Q(expires_at__isnull=False) & models.Q(expires_at__gt=now)
    ).order_by('-created_at')

    teacher_announcements = Announcement.objects.filter(
        user=user,
        recipient_type='teacher'
    ).filter(
        models.Q(expires_at__isnull=False) & models.Q(expires_at__gt=now)
    ).order_by('-created_at')

    context = {
        'order_items': order_items,
        'classroom_cards': classroom_cards,
        'student_announcements': student_announcements,
        'teacher_announcements': teacher_announcements,
        **permissions_context,
    }
    return render(request, 'index_cook.html', context)

@login_required(login_url='/login/')
def index_parent(request):
    required_permission_id = None  # No specific permission required for this page
    permissions_context = check_permissions(request, required_permission_id)
    if isinstance(permissions_context, HttpResponseRedirect):
        return permissions_context

    # Use request.user to get the subuser
    try:
        subuser = SubUser.objects.get(user=request.user)
        students = subuser.students.all()
        main_user = subuser.main_user
    except SubUser.DoesNotExist:
        students = []
        main_user = request.user

    # Fetch only active student announcements (not expired) for the main user
    now = timezone.now()
    student_announcements = Announcement.objects.filter(
        user=main_user,
        recipient_type='student'
    ).filter(
        models.Q(expires_at__isnull=False) & models.Q(expires_at__gt=now)
    ).order_by('-created_at')

    today = timezone.localdate()
    snapshot_data = []
    for student in students:
        attendance = AttendanceRecord.objects.filter(
            student=student,
            sign_in_time__date=today
        ).order_by('-sign_in_time').first()
        if attendance:
            snapshot_data.append({
                'student': student,
                'sign_in_time': attendance.sign_in_time,
                'sign_out_time': attendance.sign_out_time,
                'outside_time_out_1': attendance.outside_time_out_1,
                'outside_time_in_1': attendance.outside_time_in_1,
                'outside_time_out_2': attendance.outside_time_out_2,
                'outside_time_in_2': attendance.outside_time_in_2,
                'incident_report': attendance.incident_report,
            })

    context = {
        'student_announcements': student_announcements,
        'snapshot_data': snapshot_data,
        **permissions_context,
    }
    return render(request, 'tottimeapp/index_parent.html', context)

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

@login_required(login_url='/login/')
def index_cacfp(request):
    required_permission_id = None  # No specific permission required for this page
    permissions_context = check_permissions(request, required_permission_id)
    if isinstance(permissions_context, HttpResponseRedirect):
        return permissions_context

    # prefer cookie first, then query param
    cookie_minimal = request.COOKIES.get('use_minimal_base') == '1'
    param_minimal = request.GET.get('minimal') == '1'
    use_minimal_base = param_minimal or cookie_minimal

    # If we don't yet know the client's viewport, return a tiny sniffing page that
    # sets the cookie and redirects immediately (prevents flashing the full base).
    if not (cookie_minimal or param_minimal):
        sniff_html = """<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
        <script>
        (function(){
            var w = window.innerWidth || document.documentElement.clientWidth || screen.width;
            var url = window.location.href;
            if (w < 1000) {
                // set cookie for future server-side decisions
                document.cookie = "use_minimal_base=1; path=/; max-age=" + (60*60*24*365) + ";";
                if (url.indexOf('minimal=1') === -1) {
                    url += (url.indexOf('?') === -1 ? '?' : '&') + 'minimal=1';
                }
                window.location.replace(url);
            } else {
                // ensure no minimal param and reload so server will serve full base
                url = url.replace(/([?&])minimal=1(&|$)/g, '$1').replace(/[?&]$/, '');
                window.location.replace(url);
            }
        })();
        </script>
        <style>html,body{height:100%;margin:0;background:#fff}</style>
        </head><body></body></html>"""
        return HttpResponse(sniff_html)

    if use_minimal_base:
        base_template = 'tottimeapp/base_minimal.html'
    else:
        base_template = 'tottimeapp/base.html'

    permissions_context['base_template'] = base_template

    response = render(request, 'tottimeapp/index_cacfp.html', permissions_context)

    # if query param present, persist preference for future requests
    if param_minimal:
        response.set_cookie('use_minimal_base', '1', max_age=60*60*24*365, httponly=False, path='/')

    return response

@require_POST
@login_required(login_url='/login/')
def add_announcement(request):
    title = request.POST.get('title')
    message = request.POST.get('message')
    expires_at = request.POST.get('expires_at')
    recipient_type = request.POST.get('recipient_type')
    user = get_user_for_view(request)

    from django.utils.dateparse import parse_datetime
    expires_at_parsed = parse_datetime(expires_at) if expires_at else None

    if not title or not message or not expires_at_parsed or recipient_type not in ['student', 'teacher']:
        return JsonResponse({'error': 'All fields are required.'}, status=400)

    Announcement.objects.create(
        user=user,
        title=title,
        message=message,
        expires_at=expires_at_parsed,
        recipient_type=recipient_type
    )
    return JsonResponse({'success': True})

@login_required
def policies(request):
    # Check permissions for the specific page
    required_permission_id = 416
    permissions_context = check_permissions(request, required_permission_id)
    # If check_permissions returns a redirect, return it immediately
    if isinstance(permissions_context, HttpResponseRedirect):
        return permissions_context

    main_user = get_user_for_view(request)

    try:
        company_account = CompanyAccountOwner.objects.get(main_account_owner=main_user)
        company = company_account.company

        # Get the enrollment template for this company and main_user
        enrollment_templates = EnrollmentTemplate.objects.filter(
            company=company,
            main_user=main_user,
            is_active=True
        ).order_by('template_name')
    except CompanyAccountOwner.DoesNotExist:
        enrollment_templates = EnrollmentTemplate.objects.none()
        company = None

    selected_template = None
    policies = []

    if enrollment_templates.count() == 1:
        selected_template = enrollment_templates.first()
        policies = EnrollmentPolicy.objects.filter(
            template=selected_template,
            main_user=main_user
        ).order_by('order', 'id')
    elif enrollment_templates.exists():
        # fallback: if multiple, pick the first (should not happen)
        selected_template = enrollment_templates.first()
        policies = EnrollmentPolicy.objects.filter(
            template=selected_template,
            main_user=main_user
        ).order_by('order', 'id')

    # Handle POST requests
    if request.method == 'POST':
        if not selected_template:
            messages.error(request, 'No enrollment template found for your center.')
            return redirect('policies')

        action = request.POST.get('action')

        if action == 'update_policies':
            updated_count = 0

            for policy in policies:
                title_key = f'policy_{policy.id}_title'
                content_key = f'policy_{policy.id}_content'
                order_key = f'policy_{policy.id}_order'

                new_title = request.POST.get(title_key)
                new_content = request.POST.get(content_key)
                new_order = request.POST.get(order_key)

                if new_title is not None and new_content is not None:
                    try:
                        policy.title = new_title
                        # Sanitize HTML content before saving
                        policy.content = sanitize_html(new_content)
                        policy.order = int(new_order) if new_order else 0
                        policy.save()
                        updated_count += 1
                    except ValueError:
                        messages.error(request, f'Invalid order value for policy "{policy.title}". Please enter a valid number.')
                        return redirect('policies')
                    except Exception as e:
                        messages.error(request, f'Error updating policy "{policy.title}": {str(e)}')
                        return redirect('policies')

            # Resequence policies to ensure consistent ordering
            resequence_policy_orders(selected_template, main_user)
            
            if updated_count > 0:
                messages.success(request, f'Successfully updated {updated_count} policies!')
            else:
                messages.info(request, 'No changes were made.')

        # In the 'add_policy' action:
        elif action == 'add_policy':
            # Get form data for new policy
            new_title = request.POST.get('new_policy_title')
            new_content = request.POST.get('new_policy_content')
            
            if not new_title or not new_content:
                messages.error(request, 'Please provide both title and content for the new policy.')
                return redirect('policies')
                
            try:
                # Check if a policy with this title already exists
                if EnrollmentPolicy.objects.filter(template=selected_template, title=new_title).exists():
                    messages.error(request, f'A policy with the title "{new_title}" already exists.')
                    return redirect('policies')
                    
                # Get the highest order number and add 1
                highest_order = EnrollmentPolicy.objects.filter(
                    template=selected_template,
                    main_user=main_user
                ).aggregate(Max('order'))['order__max']
                
                next_order = 0 if highest_order is None else highest_order + 1
                
                # Sanitize the HTML content before saving
                sanitized_content = sanitize_html(new_content)
                
                # Create new policy with sanitized content
                EnrollmentPolicy.objects.create(
                    main_user=main_user,
                    template=selected_template,
                    title=new_title,
                    content=sanitized_content,
                    order=next_order,
                    is_active=True
                )
                messages.success(request, f'Successfully added new policy: "{new_title}"')
                
                # Resequence to ensure we don't have gaps
                resequence_policy_orders(selected_template, main_user)
                
            except Exception as e:
                messages.error(request, f'Error adding new policy: {str(e)}')
                
        elif action == 'delete_policy':
            policy_id = request.POST.get('policy_id')
            if policy_id:
                try:
                    policy = EnrollmentPolicy.objects.get(id=policy_id, template=selected_template)
                    policy_title = policy.title
                    policy.delete()
                    
                    # Resequence policies after deletion to ensure no gaps in order
                    resequence_policy_orders(selected_template, main_user)
                    
                    messages.success(request, f'Successfully deleted policy: "{policy_title}"')
                except EnrollmentPolicy.DoesNotExist:
                    messages.error(request, 'Policy not found.')
                except Exception as e:
                    messages.error(request, f'Error deleting policy: {str(e)}')
            else:
                messages.error(request, 'No policy ID provided for deletion.')

        return redirect('policies')

    context = permissions_context.copy()
    context.update({
        'enrollment_templates': enrollment_templates,
        'selected_template': selected_template,
        'policies': policies,
        'company': company,
        'company_account': company_account,
        **permissions_context,
    })

    return render(request, 'tottimeapp/policies.html', context)

def resequence_policy_orders(template, main_user):
    """Resequence all policies to ensure they have sequential order numbers (zero-based)."""
    policies = EnrollmentPolicy.objects.filter(
        template=template,
        main_user=main_user,
        is_active=True
    ).order_by('order', 'id')
    
    # Resequence the orders (0, 1, 2, 3...)
    # We keep 0-based internally for database storage
    for index, policy in enumerate(policies):
        if policy.order != index:
            policy.order = index
            policy.save(update_fields=['order'])
            
    return policies

@csrf_exempt
def send_public_enrollment_link(request):
    if request.method == "POST":
        try:
            data = json.loads(request.body)
            email = data.get("email")
            link = data.get("link")
            if not email or not link:
                return JsonResponse({"success": False, "error": "Missing email or link."})
            send_mail(
                "Enrollment Link",
                f"Please fill out the enrollment form found here: {link}",
                "noreply@tottime.com",
                [email],
                fail_silently=False,
            )
            return JsonResponse({"success": True})
        except Exception as e:
            return JsonResponse({"success": False, "error": str(e)})
    return JsonResponse({"success": False, "error": "Invalid request."})

@public_or_login_required 
def enrollment(request):
    """
    Display enrollment submissions for the current user's facility,
    and provide public enrollment links for all active templates for this user's company/location.
    """
    required_permission_id = 416
    permissions_context = check_permissions(request, required_permission_id)
    if isinstance(permissions_context, HttpResponseRedirect):
        return permissions_context

    main_user = get_user_for_view(request)

    # Get all company locations for this main user (not just primary)
    company_locations = CompanyAccountOwner.objects.filter(main_account_owner=main_user)
    pass  # print(f"DEBUG: main_user.id={main_user.id}, username={main_user.username}")
    pass  # print(f"DEBUG: company_locations found: {[loc.id for loc in company_locations]}")

    # Get all active templates for all company locations
    if company_locations.exists():
        templates = EnrollmentTemplate.objects.filter(
            company__in=company_locations.values_list('company', flat=True),
            location__in=company_locations,
            is_active=True
        ).select_related('company', 'location')
        pass  # print(f"DEBUG: Found {templates.count()} templates for main_user.id={main_user.id}")
        for t in templates:
            pass  # print(f"DEBUG: Template id={t.id}, name={t.template_name}, location_id={t.location_id}, company_id={t.company_id}, is_active={t.is_active}")
        # Use first location for facility info (or aggregate if needed)
        first_location = company_locations.first()
        facility_info = {
            'name': first_location.location_name or first_location.company.name,
            'company_name': first_location.company.name,
            'full_address': f"{first_location.facility_address}, {first_location.full_facility_address}" if first_location.facility_address and first_location.full_facility_address else (first_location.facility_address or first_location.full_facility_address or ''),
        }
    else:
        templates = EnrollmentTemplate.objects.none()
        facility_info = {}
        pass  # print("DEBUG: No company_location found, templates queryset is empty.")

    # Submissions for this main_user
    submissions = EnrollmentSubmission.objects.filter(
        main_user=main_user
    ).select_related('template')

    # Handle status filtering
    status_filter = request.GET.get('status')
    show_all = request.GET.get('show_all')
    if show_all:
        pass
    elif status_filter:
        submissions = submissions.filter(status=status_filter)
    else:
        submissions = submissions.filter(status='enrolled')

    # Apply search filter
    search_query = request.GET.get('search', '').strip()
    if search_query:
        submissions = submissions.filter(
            Q(child_first_name__icontains=search_query) |
            Q(child_last_name__icontains=search_query) |
            Q(parent1_full_name__icontains=search_query)
        )

    # Order by child's name (last name, then first name)
    submissions = submissions.order_by('child_last_name', 'child_first_name', '-submitted_at')

    # Calculate statistics (for all submissions, not just the filtered ones)
    all_submissions = EnrollmentSubmission.objects.filter(main_user=main_user)
    total_submissions = all_submissions.count()
    new_submissions = all_submissions.filter(status='new').count()
    enrolled_submissions = all_submissions.filter(status='enrolled').count()
    archived_submissions = all_submissions.filter(status='archive').count()

    # Pagination
    paginator = Paginator(submissions, 10)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    is_public = request.GET.get('public') == 'true'
    if is_public:
        template_name = 'tottimeapp/enrollment_public.html'
    else:
        template_name = 'tottimeapp/enrollment.html'
    
    context = {
        'submissions': page_obj,
        **permissions_context,
        'page_obj': page_obj,
        'is_paginated': page_obj.has_other_pages(),
        'facility_info': facility_info,
        'templates': templates,  # Pass all templates for looping in template
        'total_submissions': total_submissions,
        'new_submissions': new_submissions,
        'enrolled_submissions': enrolled_submissions,
        'archived_submissions': archived_submissions,
    }

    return render(request, template_name, context)

@login_required
def enrollment_submission_detail(request, submission_id):
    """View detailed enrollment submission"""
    required_permission_id = None
    permissions_context = check_permissions(request, required_permission_id)
    if isinstance(permissions_context, HttpResponseRedirect):
        return permissions_context
    
    main_user = request.user
    
    submission = get_object_or_404(EnrollmentSubmission, id=submission_id)
    
    if request.method == 'POST':
        action = request.POST.get('action')
        
        if action == 'sign_and_enroll':
            staff_signature_data = request.POST.get('staff_signature_data')
            staff_signature_date = request.POST.get('staff_signature_date')
            
            if staff_signature_data and staff_signature_date:
                # Save signature
                submission.staff_signature = staff_signature_data
                submission.staff_signature_date = staff_signature_date
                
                # Update status to enrolled
                submission.status = 'enrolled'
                submission.status_changed_date = timezone.now()
                # Convert user object to string representation
                submission.status_changed_by = str(request.user)
                
                submission.save()
                
                messages.success(request, 'Document signed and status updated to enrolled successfully.')
                return redirect('enrollment_submission_detail', submission_id=submission_id)
            else:
                messages.error(request, 'Please provide both signature and date.')
        
        elif action == 'change_status':
            # Your existing status change logic
            new_status = request.POST.get('new_status')
            if new_status in ['new', 'enrolled', 'archive']:
                submission.status = new_status
                submission.status_changed_date = timezone.now()
                # Convert user object to string representation
                submission.status_changed_by = str(request.user)
                submission.save()
                messages.success(request, f'Status updated to {new_status}.')
                return redirect('enrollment_submission_detail', submission_id=submission_id)
    
    context = {
        'submission': submission,
        **permissions_context,
    }
    return render(request, 'tottimeapp/enrollment_submission_detail.html', context)

def public_enrollment(request, template_id=None, location_id=None):
    """
    Public enrollment form accessible without login
    """
    # Get the template if specified
    template = None
    if template_id:
        try:
            template = EnrollmentTemplate.objects.get(id=template_id, is_active=True)
        except EnrollmentTemplate.DoesNotExist:
            from django.http import Http404
            raise Http404("Enrollment form not found or is no longer available.")
    
    # Get facility info from CompanyAccountOwner
    facility_info = {}
    company_location = None
    
    if location_id:
        # Specific location requested
        try:
            company_location = CompanyAccountOwner.objects.get(id=location_id)
        except CompanyAccountOwner.DoesNotExist:
            from django.http import Http404
            raise Http404("Facility location not found.")
    elif template and template.location:
        # Get location from template
        company_location = template.location
    else:
        # Get primary location for the template's company
        if template:
            company_location = CompanyAccountOwner.objects.filter(
                company=template.company, 
                is_primary=True
            ).first()
        else:
            company_location = CompanyAccountOwner.objects.filter(is_primary=True).first()
    
    if company_location:
        facility_info = {
            'name': company_location.location_name or company_location.company.name,
            'company_name': company_location.company.name,
            'address': company_location.facility_address or '',
            'city': company_location.facility_city or '',
            'state': company_location.facility_state or '',
            'zip': company_location.facility_zip or '',
            'city_state_zip': company_location.full_facility_address,
            'county': company_location.facility_county or '',
            'full_address': f"{company_location.facility_address}, {company_location.full_facility_address}" if company_location.facility_address and company_location.full_facility_address else (company_location.facility_address or company_location.full_facility_address or ''),
        }
    else:
        # Use template's company info as fallback
        if template:
            facility_info = {
                'name': template.company.name,
                'company_name': template.company.name,
                'address': '',
                'city': '',
                'state': '',
                'zip': '',
                'city_state_zip': '',
                'county': '',
                'full_address': '',
            }
        else:
            facility_info = {
                'name': 'Child Care Facility',
                'company_name': 'Child Care Facility',
                'address': '',
                'city': '',
                'state': '',
                'zip': '',
                'city_state_zip': '',
                'county': '',
                'full_address': '',
            }
    
    if request.method == 'POST':
        try:
            # Get client IP address
            def get_client_ip(request):
                x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
                if x_forwarded_for:
                    ip = x_forwarded_for.split(',')[0]
                else:
                    ip = request.META.get('REMOTE_ADDR')
                return ip
            
            # Create enrollment submission
            submission = EnrollmentSubmission()
            
            # Set template and main_user - THIS IS THE KEY FIX
            submission.template = template
            
            # Determine main_user from multiple sources
            main_user_for_notification = None
            if template and template.main_user:
                # First priority: template's main_user
                submission.main_user = template.main_user
                main_user_for_notification = template.main_user
            elif company_location and company_location.main_account_owner:
                # Second priority: location's main_account_owner
                submission.main_user = company_location.main_account_owner
                main_user_for_notification = company_location.main_account_owner
            elif template and template.location and template.location.main_account_owner:
                # Third priority: template's location's main_account_owner
                submission.main_user = template.location.main_account_owner
                main_user_for_notification = template.location.main_account_owner
            else:
                # Fallback: None (public submission with no associated main_user)
                submission.main_user = None
                main_user_for_notification = None
            
            # [All the existing field assignments remain the same...]
            # Facility Information - populate from CompanyAccountOwner
            if company_location:
                submission.facility_name = facility_info['name']
                submission.facility_address = facility_info['full_address']
                submission.facility_city_state_zip = facility_info['city_state_zip']
                submission.facility_county = facility_info['county']
            
            # Child Information - Required fields
            child_first_name = request.POST.get('child_first_name', '').strip()
            child_last_name = request.POST.get('child_last_name', '').strip()
            
            if not child_first_name or not child_last_name:
                messages.error(request, 'Child first name and last name are required.')
                context = {
                    'facility_info': facility_info, 
                    'template': template,
                    'company_location': company_location
                }
                return render(request, 'tottimeapp/public_enrollment.html', context)
            
            submission.child_first_name = child_first_name
            submission.child_last_name = child_last_name
            submission.child_middle_initial = request.POST.get('child_middle_initial', '')
            submission.child_nick_name = request.POST.get('child_nick_name', '')
            
            # Convert date fields with error handling
            try:
                dob = request.POST.get('date_of_birth')
                if dob:
                    submission.date_of_birth = datetime.strptime(dob, '%Y-%m-%d').date()
                else:
                    messages.error(request, 'Date of birth is required.')
                    context = {
                        'facility_info': facility_info, 
                        'template': template,
                        'company_location': company_location
                    }
                    return render(request, 'tottimeapp/public_enrollment.html', context)
                
                enrollment_date = request.POST.get('enrollment_date')
                if enrollment_date:
                    submission.enrollment_date = datetime.strptime(enrollment_date, '%Y-%m-%d').date()
                else:
                    messages.error(request, 'Enrollment date is required.')
                    context = {
                        'facility_info': facility_info, 
                        'template': template,
                        'company_location': company_location
                    }
                    return render(request, 'tottimeapp/public_enrollment.html', context)
            except ValueError as e:
                messages.error(request, 'Invalid date format.')
                context = {
                    'facility_info': facility_info, 
                    'template': template,
                    'company_location': company_location
                }
                return render(request, 'tottimeapp/public_enrollment.html', context)
            
            submission.child_street_address = request.POST.get('child_street_address', '')
            submission.child_city_state_zip = request.POST.get('child_city_state_zip', '')
            
            # Parent Information - At least parent1 name is required
            parent1_name = request.POST.get('parent1_full_name', '').strip()
            if not parent1_name:
                messages.error(request, 'Parent/Guardian name is required.')
                context = {
                    'facility_info': facility_info, 
                    'template': template,
                    'company_location': company_location
                }
                return render(request, 'tottimeapp/public_enrollment.html', context)
            
            submission.parent1_full_name = parent1_name
            submission.parent1_home_phone = request.POST.get('parent1_home_phone', '')
            submission.parent1_work_phone = request.POST.get('parent1_work_phone', '')
            submission.parent1_other_phone = request.POST.get('parent1_other_phone', '')
            
            submission.parent2_full_name = request.POST.get('parent2_full_name', '')
            submission.parent2_home_phone = request.POST.get('parent2_home_phone', '')
            submission.parent2_work_phone = request.POST.get('parent2_work_phone', '')
            submission.parent2_other_phone = request.POST.get('parent2_other_phone', '')
            
            # Emergency Contacts
            submission.emergency1_name = request.POST.get('emergency1_name', '')
            submission.emergency1_relationship = request.POST.get('emergency1_relationship', '')
            submission.emergency1_address = request.POST.get('emergency1_address', '')
            submission.emergency1_city_state_zip = request.POST.get('emergency1_city_state_zip', '')
            submission.emergency1_phone = request.POST.get('emergency1_phone', '')
            submission.emergency1_family_code = request.POST.get('emergency1_family_code', '')
            
            submission.emergency2_name = request.POST.get('emergency2_name', '')
            submission.emergency2_relationship = request.POST.get('emergency2_relationship', '')
            submission.emergency2_address = request.POST.get('emergency2_address', '')
            submission.emergency2_city_state_zip = request.POST.get('emergency2_city_state_zip', '')
            submission.emergency2_phone = request.POST.get('emergency2_phone', '')
            submission.emergency2_family_code = request.POST.get('emergency2_family_code', '')
            
            # Schedule Information
            submission.enrolled_in_school = request.POST.get('enrolled_in_school', '')
            
            # Convert time fields with error handling
            try:
                regular_from = request.POST.get('regular_hours_from')
                if regular_from:
                    submission.regular_hours_from = datetime.strptime(regular_from, '%H:%M').time()
                
                regular_to = request.POST.get('regular_hours_to')
                if regular_to:
                    submission.regular_hours_to = datetime.strptime(regular_to, '%H:%M').time()
                
                dropin_from = request.POST.get('dropin_hours_from')
                if dropin_from:
                    submission.dropin_hours_from = datetime.strptime(dropin_from, '%H:%M').time()
                
                dropin_to = request.POST.get('dropin_hours_to')
                if dropin_to:
                    submission.dropin_hours_to = datetime.strptime(dropin_to, '%H:%M').time()
            except ValueError:
                # Time fields are optional, so we can continue
                pass
            
            # Arrays for attendance days and meals
            submission.attendance_days = request.POST.getlist('attendance_days')
            submission.meals = request.POST.getlist('meals')
            
            # Health Information
            submission.family_physician_name = request.POST.get('family_physician_name', '')
            submission.physician_address = request.POST.get('physician_address', '')
            submission.physician_city_state_zip = request.POST.get('physician_city_state_zip', '')
            submission.physician_telephone = request.POST.get('physician_telephone', '')
            
            submission.emergency_care_provider = request.POST.get('emergency_care_provider', '')
            submission.emergency_facility_address = request.POST.get('emergency_facility_address', '')
            submission.emergency_facility_city_state_zip = request.POST.get('emergency_facility_city_state_zip', '')
            submission.emergency_facility_telephone = request.POST.get('emergency_facility_telephone', '')
            
            submission.dental_care_provider_name = request.POST.get('dental_care_provider_name', '')
            submission.dental_provider_address = request.POST.get('dental_provider_address', '')
            submission.dental_provider_city_state_zip = request.POST.get('dental_provider_city_state_zip', '')
            submission.dental_provider_telephone = request.POST.get('dental_provider_telephone', '')
            
            submission.health_insurance_provider = request.POST.get('health_insurance_provider', '')
            submission.immunization_certificate = request.POST.get('immunization_certificate', '')
            submission.immunization_explanation = request.POST.get('immunization_explanation', '')
            submission.health_conditions = request.POST.get('health_conditions', '')
            submission.additional_comments = request.POST.get('additional_comments', '')
            
            # Pickup Information
            submission.pickup_child_name = request.POST.get('pickup_child_name', '')
            
            pickup_dob = request.POST.get('pickup_child_dob')
            if pickup_dob:
                try:
                    submission.pickup_child_dob = datetime.strptime(pickup_dob, '%Y-%m-%d').date()
                except ValueError:
                    pass  # Optional field
            
            submission.pickup_mother_name = request.POST.get('pickup_mother_name', '')
            submission.pickup_mother_cell = request.POST.get('pickup_mother_cell', '')
            submission.pickup_mother_work = request.POST.get('pickup_mother_work', '')
            submission.pickup_mother_email = request.POST.get('pickup_mother_email', '')
            
            submission.pickup_father_name = request.POST.get('pickup_father_name', '')
            submission.pickup_father_cell = request.POST.get('pickup_father_cell', '')
            submission.pickup_father_work = request.POST.get('pickup_father_work', '')
            submission.pickup_father_email = request.POST.get('pickup_father_email', '')
            
            submission.pickup_emergency1_name = request.POST.get('pickup_emergency1_name', '')
            submission.pickup_emergency1_phone = request.POST.get('pickup_emergency1_phone', '')
            submission.pickup_emergency2_name = request.POST.get('pickup_emergency2_name', '')
            submission.pickup_emergency2_phone = request.POST.get('pickup_emergency2_phone', '')
            
            # Child Info Section
            submission.mothers_ssn = request.POST.get('mothers_ssn', '')
            submission.mothers_email = request.POST.get('mothers_email', '')
            submission.mothers_employment = request.POST.get('mothers_employment', '')
            submission.fathers_email = request.POST.get('fathers_email', '')
            submission.fathers_employment = request.POST.get('fathers_employment', '')
            
            # Authorized Pickup Persons
            submission.pickup_person1_name = request.POST.get('pickup_person1_name', '')
            submission.pickup_person1_phone = request.POST.get('pickup_person1_phone', '')
            submission.pickup_person2_name = request.POST.get('pickup_person2_name', '')
            submission.pickup_person2_phone = request.POST.get('pickup_person2_phone', '')
            submission.pickup_person3_name = request.POST.get('pickup_person3_name', '')
            submission.pickup_person3_phone = request.POST.get('pickup_person3_phone', '')
            submission.pickup_person4_name = request.POST.get('pickup_person4_name', '')
            submission.pickup_person4_phone = request.POST.get('pickup_person4_phone', '')
            
            # After handling field_trip_permission_parent, add:
            submission.photo_permission_parent = request.POST.get('photo_permission_parent', '')
               
            # Signatures
            submission.parent_signature = request.POST.get('parent_signature_data', '')

            parent_sig_date = request.POST.get('parent_signature_date')  # Fixed: removed 'requests.'
            if parent_sig_date:
                try:
                    submission.parent_signature_date = datetime.strptime(parent_sig_date, '%Y-%m-%d').date()
                except ValueError:
                    pass

            # Add second parent signature handling
            submission.parent2_signature = request.POST.get('parent2_signature_data', '')

            parent2_sig_date = request.POST.get('parent2_signature_date')
            if parent2_sig_date:
                try:
                    submission.parent2_signature_date = datetime.strptime(parent2_sig_date, '%Y-%m-%d').date()
                except ValueError:
                    pass

            submission.staff_signature = request.POST.get('staff_signature_data', '')

            staff_sig_date = request.POST.get('staff_signature_date')
            if staff_sig_date:
                try:
                    submission.staff_signature_date = datetime.strptime(staff_sig_date, '%Y-%m-%d').date()
                except ValueError:
                    pass
            
            # Metadata
            submission.ip_address = get_client_ip(request)
            submission.status = 'new'  # Set default status to 'new'
            
            # Save to database
            submission.save()
            
            # Send notification email to MainUser
            try:
                # Determine admin email from the main_user_for_notification
                if main_user_for_notification and main_user_for_notification.email:
                    admin_email = main_user_for_notification.email
                    admin_name = f"{main_user_for_notification.first_name} {main_user_for_notification.last_name}".strip()
                    if not admin_name:
                        admin_name = main_user_for_notification.username
                    
                    # Create comprehensive email content
                    email_subject = f'New Enrollment Submission - {facility_info["name"]}'
                    
                    # Format attendance days nicely
                    attendance_days_formatted = ', '.join(submission.attendance_days) if submission.attendance_days else 'Not specified'
                    
                    # Format meals nicely
                    meals_formatted = ', '.join(submission.meals) if submission.meals else 'Not specified'
                    
                    email_body = f"""
Hello {admin_name},

A new enrollment submission has been received for {facility_info['name']}.

CHILD INFORMATION:
Child Name: {submission.child_first_name} {submission.child_last_name}
Date of Birth: {submission.date_of_birth}
Enrollment Date: {submission.enrollment_date}
Address: {submission.child_street_address}, {submission.child_city_state_zip}

PARENT/GUARDIAN INFORMATION:
Primary Parent: {submission.parent1_full_name}
Home Phone: {submission.parent1_home_phone or 'Not provided'}
Work Phone: {submission.parent1_work_phone or 'Not provided'}
Email: {submission.pickup_mother_email or submission.mothers_email or 'Not provided'}

{f"Second Parent: {submission.parent2_full_name}" if submission.parent2_full_name else ""}
{f"Second Parent Phone: {submission.parent2_home_phone}" if submission.parent2_home_phone else ""}

EMERGENCY CONTACTS:
1. {submission.emergency1_name} ({submission.emergency1_relationship}) - {submission.emergency1_phone}
2. {submission.emergency2_name} ({submission.emergency2_relationship}) - {submission.emergency2_phone}

SCHEDULE INFORMATION:
Attendance Days: {attendance_days_formatted}
Regular Hours: {f"{submission.regular_hours_from} to {submission.regular_hours_to}" if submission.regular_hours_from and submission.regular_hours_to else "Not specified"}
Meals: {meals_formatted}

HEALTH INFORMATION:
Family Physician: {submission.family_physician_name or 'Not provided'}
Health Conditions: {submission.health_conditions or 'None specified'}
Immunization Certificate: {submission.immunization_certificate or 'Not specified'}

SUBMISSION DETAILS:
Submission ID: #{submission.id}
Submitted At: {submission.submitted_at.strftime('%B %d, %Y at %I:%M %p')}
Status: New (Pending Review)

Please log into your TotTime dashboard to review the complete submission and update the enrollment status.

Best regards,
TotTime Enrollment System
                    """
                    
                    # Send the email
                    send_mail(
                        email_subject,
                        email_body,
                        'noreply@tottime.com',  # From email
                        [admin_email],          # To email (MainUser's email)
                        fail_silently=False,    # Raise exception if email fails
                    )
                    
                    pass  # print(f"Email notification sent successfully to {admin_email}")
                    
                else:
                    pass  # print(f"No email address found for notification. Main user: {main_user_for_notification}")
                    
            except Exception as email_error:
                pass  # print(f"Email notification failed: {email_error}")
                # Don't fail the submission if email fails
            
            messages.success(request, 'Enrollment form submitted successfully! We will contact you soon.')
            return redirect('public_enrollment_success')
            
        except Exception as e:
            pass  # print(f"Enrollment submission error: {e}")
            messages.error(request, 'There was an error submitting your form. Please try again.')
    
    # Get the policies for this template
    policies = []
    if template:
        policies = EnrollmentPolicy.objects.filter(template=template, is_active=True).order_by('order')
    
    context = {
        'facility_info': facility_info,
        'template': template,
        'company_location': company_location,
        'policies': policies,  # Add policies to the context
    }
    
    return render(request, 'tottimeapp/public_enrollment.html', context)

def public_enrollment_success(request):
    """
    Success page after enrollment submission
    """
    return render(request, 'tottimeapp/public_enrollment_success.html')

@login_required
def recipes(request):
    # Check permissions for the specific page
    required_permission_id = 267  # Permission ID for accessing recipes view
    permissions_context = check_permissions(request, required_permission_id)
    # If check_permissions returns a redirect, return it immediately
    if isinstance(permissions_context, HttpResponseRedirect):
        return permissions_context

    # prefer cookie first, then query param
    cookie_minimal = request.COOKIES.get('use_minimal_base') == '1'
    param_minimal = request.GET.get('minimal') == '1'
    use_minimal_base = param_minimal or cookie_minimal

    # If we don't yet know the client's viewport, return a tiny sniffing page that
    # sets the cookie and redirects immediately (prevents flashing the full base).
    if not (cookie_minimal or param_minimal):
        sniff_html = """<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
        <script>
        (function(){
            var w = window.innerWidth || document.documentElement.clientWidth || screen.width;
            var url = window.location.href;
            if (w < 1000) {
                document.cookie = "use_minimal_base=1; path=/; max-age=" + (60*60*24*365) + ";";
                if (url.indexOf('minimal=1') === -1) {
                    url += (url.indexOf('?') === -1 ? '?' : '&') + 'minimal=1';
                }
                window.location.replace(url);
            } else {
                url = url.replace(/([?&])minimal=1(&|$)/g, '$1').replace(/[?&]$/, '');
                window.location.replace(url);
            }
        })();
        </script>
        <style>html,body{height:100%;margin:0;background:#fff}</style>
        </head><body></body></html>"""
        return HttpResponse(sniff_html)

    # Choose base template
    base_template = 'tottimeapp/base_minimal.html' if use_minimal_base else 'tottimeapp/base.html'
    permissions_context['base_template'] = base_template

    response = render(request, 'tottimeapp/recipes.html', permissions_context)

    # persist preference when query param present
    if param_minimal:
        response.set_cookie('use_minimal_base', '1', max_age=60*60*24*365, httponly=False, path='/')

    return response

@login_required
def menu(request):
    required_permission_id = 271  # Permission ID for menu view
    permissions_context = check_permissions(request, required_permission_id)
    if isinstance(permissions_context, HttpResponseRedirect):
        return permissions_context

    # Use canonical main user for lookups (handles subusers)
    main_user = get_user_for_view(request)

    # Try to find a CompanyAccountOwner for the main_user, then fallback to company/primary
    company_account_owner = None
    if main_user:
        company_account_owner = CompanyAccountOwner.objects.select_related('company', 'main_account_owner') \
            .filter(main_account_owner=main_user) \
            .first()

    if not company_account_owner and getattr(main_user, 'company', None):
        company_account_owner = CompanyAccountOwner.objects.select_related('company') \
            .filter(company=main_user.company, is_primary=True) \
            .first()

    if company_account_owner:
        facility_name = company_account_owner.location_name or company_account_owner.company.name or "Not Set"
        sponsor_name = company_account_owner.company.name if company_account_owner.company else (main_user.company.name if getattr(main_user, 'company', None) else "Not Set")
    else:
        facility_name = "Not Set"
        sponsor_name = getattr(main_user, 'company').name if getattr(main_user, 'company', None) else "Not Set"

    permissions_context.update({
        'facility_name': facility_name,
        'sponsor_name': sponsor_name,
    })

    # --- minimal/base sniffing (same pattern as other views) ---
    cookie_minimal = request.COOKIES.get('use_minimal_base') == '1'
    param_minimal = request.GET.get('minimal') == '1'
    use_minimal_base = param_minimal or cookie_minimal

    if not (cookie_minimal or param_minimal):
        sniff_html = """<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
        <script>
        (function(){
            var w = window.innerWidth || document.documentElement.clientWidth || screen.width;
            var url = window.location.href;
            if (w < 1000) {
                document.cookie = "use_minimal_base=1; path=/; max-age=" + (60*60*24*365) + ";";
                if (url.indexOf('minimal=1') === -1) {
                    url += (url.indexOf('?') === -1 ? '?' : '&') + 'minimal=1';
                }
                window.location.replace(url);
            } else {
                url = url.replace(/([?&])minimal=1(&|$)/g, '$1').replace(/[?&]$/, '');
                window.location.replace(url);
            }
        })();
        </script>
        <style>html,body{height:100%;margin:0;background:#fff}</style>
        </head><body></body></html>"""
        return HttpResponse(sniff_html)

    base_template = 'tottimeapp/base_minimal.html' if use_minimal_base else 'tottimeapp/base.html'
    permissions_context['base_template'] = base_template

    # Provide inventory items (a-z) for client-side searchable selectors
    try:
        inventory_qs = Inventory.objects.filter(user_id=main_user.id).order_by(Lower('item')).values_list('item', flat=True).distinct()
        inventory_list = list(inventory_qs)
    except Exception:
        inventory_list = []
    permissions_context['inventory_items_json'] = json.dumps(inventory_list)
    permissions_context['use_inventory_selectors'] = bool(inventory_list)
    
    # Provide recipe data for autocomplete in menu cells
    try:
        # Main dish rows: recipes where standalone=False
        main_dish_recipes = list(Recipe.objects.filter(user=main_user, standalone=False).order_by(Lower('name')).values_list('name', flat=True).distinct())
        permissions_context['main_dish_recipes_json'] = json.dumps(main_dish_recipes)
        
        # Other rows: recipes where standalone=True + inventory items where is_side_dish=True
        standalone_recipes = list(Recipe.objects.filter(user=main_user, standalone=True).order_by(Lower('name')).values_list('name', flat=True).distinct())
        side_dish_inventory = list(Inventory.objects.filter(user=main_user, is_side_dish=True).order_by(Lower('item')).values_list('item', flat=True).distinct())
        other_items = sorted(set(standalone_recipes + side_dish_inventory))
        permissions_context['other_items_json'] = json.dumps(other_items)
    except Exception as e:
        permissions_context['main_dish_recipes_json'] = json.dumps([])
        permissions_context['other_items_json'] = json.dumps([])

    response = render(request, 'tottimeapp/weekly-menu.html', permissions_context)

    if param_minimal:
        response.set_cookie('use_minimal_base', '1', max_age=60*60*24*365, httponly=False, path='/')

    return response

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
    return render(request, 'privacy-policy.html')

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
    if request.user.is_authenticated:
        user = request.user
        user.session_token = uuid.uuid4()
        user.save(update_fields=['session_token'])
    logout(request)
    return redirect('index')

def auto_login_view(request):
    if request.method != 'POST':
        return JsonResponse({'success': False}, status=405)
    try:
        data = json.loads(request.body)
        token = str(data.get('token', '')).strip()
    except (ValueError, KeyError):
        return JsonResponse({'success': False}, status=400)

    if not token:
        return JsonResponse({'success': False}, status=400)

    User = get_user_model()
    try:
        matching_users = User.objects.filter(session_token=token)
        if matching_users.count() != 1:
            return JsonResponse({'success': False})
        user = matching_users.first()
    except ValueError:
        return JsonResponse({'success': False})

    login(request, user, backend='django.contrib.auth.backends.ModelBackend')
    return JsonResponse({'success': True})

@login_required
def inventory_list(request):
    # Check permissions for the specific page
    required_permission_id = 272  # Permission ID for inventory_list view
    permissions_context = check_permissions(request, required_permission_id)
    if isinstance(permissions_context, HttpResponseRedirect):
        return permissions_context

    # Get the user (MainUser) for filtering
    user = get_user_for_view(request)
    # Retrieve inventory data for the user and normalize categories to avoid duplicate tabs.
    inventory_items = list(Inventory.objects.filter(user_id=user.id))
    categories_map = {}
    for item in inventory_items:
        normalized_category = normalize_inventory_category(item.category)
        category_key = normalized_category.casefold()
        if category_key not in categories_map:
            categories_map[category_key] = normalized_category
        item.category = categories_map[category_key]
    categories = list(categories_map.values())
    preferred_category_order = [
        'Meat',
        'Dairy',
        'Fruits',
        'Vegetables',
        'Grains',
        'Breakfast',
        'Snacks',
        'Juice',
        'Infants',
        'Supplies',
        'Misc',
    ]
    preferred_category_map = {
        category.casefold(): index
        for index, category in enumerate(preferred_category_order)
    }
    categories.sort(
        key=lambda category: (
            0 if category.casefold() in preferred_category_map else 1,
            preferred_category_map.get(category.casefold(), float('inf')),
            category.casefold(),
        )
    )
    # Retrieve only rules for the current main user
    rules = Rule.objects.filter(user=user)
    # Get order items for shopping list and ordered items tabs
    order_items = OrderList.objects.filter(user=user)

    # --- Handle AJAX request for category filtering early (no sniffing) ---
    if request.headers.get('x-requested-with') == 'XMLHttpRequest':
        category_filter = normalize_inventory_category(request.GET.get('category'))
        category_filter_key = category_filter.casefold() if category_filter else ''
        filtered_items = inventory_items
        if category_filter:
            filtered_items = [
                item for item in inventory_items
                if normalize_inventory_category(item.category).casefold() == category_filter_key
            ]
        inventory_data = [
            {
                'id': item.id,
                'item': item.item,
                'quantity': item.quantity,
                'unit_type': item.unit_type,
                'category': item.category,
            }
            for item in filtered_items
        ]
        return JsonResponse({'inventory_items': inventory_data})

    # --- minimal-base preference sniffing ---
    cookie_minimal = request.COOKIES.get('use_minimal_base') == '1'
    param_minimal = request.GET.get('minimal') == '1'
    use_minimal_base = param_minimal or cookie_minimal

    # If we don't yet know the client's viewport, return a tiny sniffing page
    if not (cookie_minimal or param_minimal):
        sniff_html = """<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
        <script>
        (function(){
            var w = window.innerWidth || document.documentElement.clientWidth || screen.width;
            var url = window.location.href;
            if (w < 1000) {
                document.cookie = "use_minimal_base=1; path=/; max-age=" + (60*60*24*365) + ";";
                if (url.indexOf('minimal=1') === -1) {
                    url += (url.indexOf('?') === -1 ? '?' : '&') + 'minimal=1';
                }
                window.location.replace(url);
            } else {
                url = url.replace(/([?&])minimal=1(&|$)/g, '$1').replace(/[?&]$/, '');
                window.location.replace(url);
            }
        })();
        </script>
        <style>html,body{height:100%;margin:0;background:#fff}</style>
        </head><body></body></html>"""
        return HttpResponse(sniff_html)

    # Determine base template (popup overrides to public)
    popup = request.GET.get('popup')
    if popup == '1':
        base_template = 'tottimeapp/base_public.html'
        hide_inventory_controls = True
    else:
        base_template = 'tottimeapp/base_minimal.html' if use_minimal_base else 'tottimeapp/base.html'
        hide_inventory_controls = False

    # expose base_template for other context consumers
    permissions_context['base_template'] = base_template

    # Render the inventory list page
    response = render(request, 'tottimeapp/inventory_list.html', {
        'inventory_items': inventory_items,
        'categories': categories,
        'rules': rules,
        'order_items': order_items,
        'base_template': base_template,
        'hide_inventory_controls': hide_inventory_controls,
        **permissions_context,
    })

    # persist preference when query param present
    if param_minimal:
        response.set_cookie('use_minimal_base', '1', max_age=60*60*24*365, httponly=False, path='/')

    return response

@login_required
def infant_menu(request):
    required_permission_id = 414
    permissions_context = check_permissions(request, required_permission_id)
    if isinstance(permissions_context, HttpResponseRedirect):
        return permissions_context

    # Get the main user for this view
    user = get_user_for_view(request)
    # --- Ensure CompanyAccountOwner exists for this user ---
    from .models import Company, CompanyAccountOwner, MainUser
    try:
        main_user = MainUser.objects.get(id=user.id)
    except MainUser.DoesNotExist:
        return HttpResponseBadRequest("Main user not found.")

    owner = CompanyAccountOwner.objects.filter(main_account_owner=main_user, is_primary=True).first()
    if not owner:
        company = Company.objects.first()
        if not company:
            return HttpResponseBadRequest("No company found.")
        # Try to get any existing CompanyAccountOwner for this company/main_user
        owner = CompanyAccountOwner.objects.filter(company=company, main_account_owner=main_user).first()
        if not owner:
            owner = CompanyAccountOwner.objects.create(
                company=company,
                main_account_owner=main_user,
                location_name="Main Location",
                is_primary=True
            )
        else:
            # If found, update is_primary if needed
            if not owner.is_primary:
                owner.is_primary = True
                owner.save()

    company_name = owner.company.name
    location_name = owner.location_name or ""
    permissions_context['company_name'] = company_name
    permissions_context['location_name'] = location_name

    inventory_items = Inventory.objects.filter(category='Infants', user=user)
    permissions_context['inventory_items'] = inventory_items

    students = Student.objects.filter(main_user=user)
    permissions_context['students'] = students

    selected_student_id = request.GET.get('student')
    selected_week = request.GET.get('week')  # Format: 'YYYY-MM-DD' (Monday)

    if not selected_week:
        today = datetime.today()
        monday = today - timedelta(days=today.weekday())
        selected_week = monday.strftime('%Y-%m-%d')

    permissions_context['selected_student_id'] = int(selected_student_id) if selected_student_id else None
    permissions_context['selected_week'] = selected_week
    permissions_context['meal_types'] = ['breakfast', 'lunch', 'snack']

    selected_student = None
    if selected_student_id:
        try:
            selected_student = students.get(id=selected_student_id)
        except Student.DoesNotExist:
            selected_student = None

    permissions_context['selected_student'] = selected_student

    # Get month and year from selected week
    week_start = datetime.strptime(selected_week, '%Y-%m-%d')
    permissions_context['month'] = week_start.strftime('%B')
    permissions_context['year'] = week_start.year
    week_start = week_start - timedelta(days=week_start.weekday())  # force to Monday

    week_dates = [(week_start + timedelta(days=i)).date() for i in range(5)]  # Mon-Fri
    permissions_context['week_dates'] = week_dates

    # --- All available weeks for dropdown ---
    all_dates_qs = FeedRecord.objects.annotate(
        date_only=TruncDate('timestamp')
    ).values_list('date_only', flat=True).distinct()
    all_mondays = sorted(set(
        (d - timedelta(days=d.weekday())) for d in all_dates_qs if d is not None
    ), reverse=True)
    permissions_context['all_weeks'] = [
        {
            'value': monday.strftime('%Y-%m-%d'),
            'label': f"{monday.strftime('%b %d')} - {(monday + timedelta(days=4)).strftime('%b %d')}"
        }
        for monday in all_mondays
    ]

    feed_records = FeedRecord.objects.filter(
        student_id=selected_student_id,
        timestamp__date__gte=week_dates[0],
        timestamp__date__lte=week_dates[-1]
    ).order_by('timestamp') if selected_student_id else FeedRecord.objects.none()

    selected_student = None
    formula_name = ""
    if selected_student_id:
        try:
            selected_student = students.get(id=selected_student_id)
            formula_name = selected_student.formula_name or "IFIF Formula"  # <-- Pull from model, default if blank
        except Student.DoesNotExist:
            selected_student = None
            formula_name = "IFIF Formula"
    else:
        formula_name = "IFIF Formula"

    permissions_context['selected_student'] = selected_student
    permissions_context['formula_name'] = formula_name

    # Prepare inventory item names for fruit/vegetable matching
    inventory_names = set(item.item for item in inventory_items)

    menu_data = {day: {meal: {'formula': [], 'cereal': [], 'fruit': []} for meal in permissions_context['meal_types']} for day in week_dates}

    for record in feed_records:
        day = record.timestamp.date()
        if day in menu_data:
            meal = record.meal_type
            desc = (record.meal_description or '').strip()
            ounces = getattr(record, 'ounces', None)
            # Formula or Breast Milk (catch all variations)
            if (
                "ifif formula" in desc.lower()
                or "breast milk" in desc.lower()
            ):
                # Show -5oz if ounces < 5, otherwise show actual ounces
                if ounces is not None:
                    if ounces < 5:
                        menu_data[day][meal]['formula'].append(f"{desc} -5oz")
                    else:
                        menu_data[day][meal]['formula'].append(f"{desc} -{ounces}oz")
                else:
                    menu_data[day][meal]['formula'].append(desc)
            # Infant Cereal / Meat / Meat Alternate
            elif (
                desc.lower().startswith("infant cereal")
                or desc.lower() == "infant cereal"
                or desc == "Other"
                or "other" in desc.lower()
                or desc == "3Tbs of IFIC Oatmeal"
            ):
                menu_data[day][meal]['cereal'].append(desc)
            # Fruit / Vegetable (inventory match)
            elif desc in inventory_names:
                menu_data[day][meal]['fruit'].append(desc)
            # Other custom entries (not formula, not inventory, not infant cereal)
            else:
                menu_data[day][meal]['cereal'].append(desc)

    permissions_context['menu_data'] = menu_data

    # --- MOVE meal_counts calculation here, after menu_data is filled ---
    meal_counts = {}
    for meal in permissions_context['meal_types']:
        meal_counts[meal] = {}
        for category in ['formula', 'cereal', 'fruit']:
            count = 0
            for day in week_dates:
                count += len(menu_data[day][meal][category])
            meal_counts[meal][category] = count

    permissions_context['meal_counts'] = meal_counts

    return render(request, 'tottimeapp/infant_menu.html', permissions_context)

@login_required
def add_item(request):
    if request.method == 'POST':
        item_name = request.POST.get('item')
        category = request.POST.get('category')
        new_category = request.POST.get('new_category')
        quantity = request.POST.get('quantity')
        resupply = request.POST.get('resupply')
        barcode = request.POST.get('barcode')  # Retrieve the scanned barcode

        # Use the new category if provided
        if category == 'Other' and new_category:
            category = new_category
        category = normalize_inventory_category(category)

        # Check if the barcode already exists
        if barcode:
            existing_item = Inventory.objects.filter(user_id=get_user_for_view(request).id, barcode=barcode).first()
            if existing_item:
                return JsonResponse({'success': False, 'message': f'Item with barcode "{barcode}" already exists.'})

        # Get new unit fields from form
        unit_type = request.POST.get('unit_type')
        base_unit = request.POST.get('base_unit')
        unit_size = request.POST.get('unit_size')
        conversion_to_base = request.POST.get('conversion_to_base')
        custom_unit_label = request.POST.get('custom_unit_label')
        rule_id = request.POST.get('rule')
        side_dish_fields, side_dish_error = build_inventory_side_dish_fields(request.POST)

        if side_dish_error:
            return JsonResponse({'success': False, 'message': side_dish_error})

        # Map unit_type to base_unit if not explicitly provided
        unit_base_map = {
            'each': 'each',
            'lb': 'oz',
            'oz': 'oz',
            'g': 'g',
            'ml': 'ml',
            'l': 'ml',
            'gal': 'oz',
            'cup': 'cup',
            'tbsp': 'tbsp',
            'tsp': 'tsp',
            'slice': 'slice',
            'loaf': 'slice',
            'pack': 'each',
            'case': 'each'
        }
        if not base_unit and unit_type:
            base_unit = unit_base_map.get(unit_type, 'each')

        # Create the new inventory item with all fields
        new_item = Inventory.objects.create(
            user_id=get_user_for_view(request).id,
            item=item_name,
            category=category,
            quantity=quantity,
            resupply=resupply,
            barcode=barcode.strip().upper() if barcode else None,  # Normalize the barcode
            unit_type=unit_type,
            base_unit=base_unit,
            unit_size=unit_size if unit_size else 1,
            conversion_to_base=conversion_to_base if conversion_to_base else 1,
            custom_unit_label=custom_unit_label,
            rule_id=rule_id if rule_id else None,
            is_side_dish=side_dish_fields['is_side_dish'],
            meal_period=side_dish_fields['meal_period'],
            populate_breakfast=side_dish_fields['populate_breakfast'],
            populate_am_snack=side_dish_fields['populate_am_snack'],
            populate_lunch=side_dish_fields['populate_lunch'],
            populate_pm_snack=side_dish_fields['populate_pm_snack'],
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
        pass  # print(f"Scanned barcode: {barcode}")

        user = get_user_for_view(request)
        pass  # print(f"User ID: {user.id}")

        try:
            item = Inventory.objects.get(user=user, barcode=barcode)
            item.quantity += 1
            item.save()
            return JsonResponse({'success': True, 'message': f'Quantity for "{item.item}" updated successfully!'})
        except Inventory.DoesNotExist:
            return JsonResponse({'success': False, 'message': 'Item with this barcode not found.'})

    return JsonResponse({'success': False, 'message': 'Invalid request method.'})

@login_required
def edit_item_name(request, item_id):
    if request.method == 'POST':
        new_name = request.POST.get('new_name', '').strip()
        if not new_name:
            return JsonResponse({'success': False, 'message': 'Item name cannot be empty'})
        try:
            user = get_user_for_view(request)
            item = Inventory.objects.get(pk=item_id, user=user)
            item.item = new_name
            item.save()
            return JsonResponse({'success': True, 'message': 'Item name updated successfully'})
        except Inventory.DoesNotExist:
            return JsonResponse({'success': False, 'message': 'Item does not exist'})
    else:
        return JsonResponse({'success': False, 'message': 'Invalid request method'})

@login_required
def edit_inventory_item(request, item_id):
    if request.method != 'POST':
        return JsonResponse({'success': False, 'message': 'Invalid request method'})

    user = get_user_for_view(request)

    try:
        item = Inventory.objects.get(pk=item_id, user=user)
    except Inventory.DoesNotExist:
        return JsonResponse({'success': False, 'message': 'Item does not exist'})

    new_name = request.POST.get('item', '').strip()
    raw_category = request.POST.get('category', '').strip()
    unit_type = (request.POST.get('unit_type') or '').strip()
    unit_size = (request.POST.get('unit_size') or '').strip()
    rule_id = (request.POST.get('rule') or '').strip()
    quantity = request.POST.get('quantity')
    resupply = request.POST.get('resupply')
    side_dish_fields, side_dish_error = build_inventory_side_dish_fields(request.POST)

    if not new_name:
        return JsonResponse({'success': False, 'message': 'Item name cannot be empty'})
    if not raw_category:
        return JsonResponse({'success': False, 'message': 'Category is required'})
    category = normalize_inventory_category(raw_category)
    if quantity in [None, '']:
        return JsonResponse({'success': False, 'message': 'Current quantity is required'})
    if resupply in [None, '']:
        return JsonResponse({'success': False, 'message': 'Resupply threshold is required'})
    if side_dish_error:
        return JsonResponse({'success': False, 'message': side_dish_error})

    rule_obj = None
    if rule_id:
        rule_obj = Rule.objects.filter(id=rule_id, user=user).first()
        if not rule_obj:
            return JsonResponse({'success': False, 'message': 'Selected rule is invalid'})

    # Map unit_type to base_unit using the same logic as in the add_item view
    unit_base_map = {
        'each': 'each',
        'lb': 'oz',
        'oz': 'oz',
        'g': 'g',
        'ml': 'ml',
        'l': 'ml',
        'gal': 'oz',
        'cup': 'cup',
        'tbsp': 'tbsp',
        'tsp': 'tsp',
        'slice': 'slice',
        'loaf': 'slice',
        'pack': 'each',
        'case': 'each'
    }
    base_unit = unit_base_map.get(unit_type, 'each') if unit_type else None

    try:
        item.item = new_name
        item.category = category
        item.unit_type = unit_type or None
        item.base_unit = base_unit
        item.unit_size = unit_size if unit_size else 1
        item.rule = rule_obj
        item.quantity = quantity
        item.resupply = resupply
        item.is_side_dish = side_dish_fields['is_side_dish']
        item.meal_period = side_dish_fields['meal_period']
        item.populate_breakfast = side_dish_fields['populate_breakfast']
        item.populate_am_snack = side_dish_fields['populate_am_snack']
        item.populate_lunch = side_dish_fields['populate_lunch']
        item.populate_pm_snack = side_dish_fields['populate_pm_snack']
        item.save()
        return JsonResponse({'success': True, 'message': 'Inventory item updated successfully'})
    except IntegrityError:
        return JsonResponse({'success': False, 'message': 'An item with this name already exists'})
    except Exception as e:
        return JsonResponse({'success': False, 'message': f'Unable to update item: {str(e)}'})

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

    # If AJAX request, return JSON response
    if request.headers.get('x-requested-with') == 'XMLHttpRequest':
        return JsonResponse({'success': True, 'message': 'Item deleted successfully'})
    # Otherwise, redirect back to the inventory list page
    return redirect('inventory_list')

@login_required
def get_out_of_stock_items(request):
    user = get_user_for_view(request)
    out_of_stock_items = Inventory.objects.filter(user=user, quantity=0)
    data = [{'name': item.item} for item in out_of_stock_items]
    return JsonResponse(data, safe=False)

def order_soon_items_view(request):
    user = get_user_for_view(request)
    
    # Get the latest 5 menu entries for the user (representing the current week)
    latest_menus = WeeklyMenu.objects.filter(user=user).order_by('-date')[:5]
    
    if not latest_menus:
        # If no menus exist, return empty list
        return JsonResponse([], safe=False)
    
    # Dictionary to store ingredients and their total required quantities
    ingredient_requirements = {}
    
    # Helper function to get recipe ingredients and add to requirements
    def add_recipe_ingredients(recipe_name):
        if not recipe_name:
            return
        
        try:
            # Use .first() to handle potential duplicates gracefully
            recipe = Recipe.objects.filter(user=user, name=recipe_name).first()
            if not recipe:
                return
            ingredients = get_recipe_ingredients(recipe)
            
            for ingredient, qty in ingredients:
                if ingredient and qty:
                    if ingredient.id not in ingredient_requirements:
                        ingredient_requirements[ingredient.id] = {
                            'ingredient': ingredient,
                            'total_required': 0
                        }
                    ingredient_requirements[ingredient.id]['total_required'] += qty
        except Recipe.DoesNotExist:
            pass
    
    # Process each menu entry in the latest week
    for menu in latest_menus:
        # Define all menu fields
        menu_fields = [
            # AM Snack fields
            'am_fluid_milk',
            'am_fruit_veg',
            'am_bread',
            'am_additional',
            
            # AMS fields
            'ams_fluid_milk',
            'ams_fruit_veg',
            'ams_bread',
            'ams_meat',
            
            # Lunch fields
            'lunch_main_dish',
            'lunch_fluid_milk',
            'lunch_additional',
            'lunch_meat',
            'lunch_vegetable',
            'lunch_fruit',
            'lunch_grain',
            
            # PM Snack fields
            'pm_fluid_milk',
            'pm_fruit_veg',
            'pm_bread',
            'pm_meat',
        ]
        
        # Process all menu fields
        for field_name in menu_fields:
            recipe_name = getattr(menu, field_name, None)
            add_recipe_ingredients(recipe_name)
    
    # Filter ingredients where total_quantity is less than required quantity
    order_soon_items = []
    for ingredient_data in ingredient_requirements.values():
        ingredient = ingredient_data['ingredient']
        total_required = ingredient_data['total_required']
        
        # Compare against total_quantity instead of quantity
        if ingredient.total_quantity < total_required:
            order_soon_items.append({
                'name': ingredient.item,
                'current_qty': float(ingredient.total_quantity),  # Use total_quantity
                'required_qty': float(total_required),  # Convert Decimal to float
                'shortage': float(total_required) - float(ingredient.total_quantity)  # Both as float
            })
    
    # Sort by name
    order_soon_items.sort(key=lambda x: x['name'])
    
    return JsonResponse(order_soon_items, safe=False)

@login_required
def order_soon_items_api(request):
    try:
        user = get_user_for_view(request)
        pass  # print(f"User: {user}")
        
        # Get items where current quantity is at or below resupply threshold
        order_soon_items = Inventory.objects.filter(
            user=user,
            quantity__lte=F('resupply')
        ).values('item', 'quantity', 'resupply', 'unit_type')
        
        pass  # print(f"Raw queryset: {list(order_soon_items)}")
        
        items_data = []
        for item in order_soon_items:
            item_dict = {
                'name': item['item'],
                'current_quantity': float(item['quantity']) if item['quantity'] is not None else 0,
                'resupply_threshold': float(item['resupply']) if item['resupply'] is not None else 0,
                'units': item['unit_type'] or ''
            }
            items_data.append(item_dict)
            pass  # print(f"Item dict: {item_dict}")
        
        pass  # print(f"Final items_data: {items_data}")
        return JsonResponse(items_data, safe=False)
        
    except Exception as e:
        pass  # print(f"Error in order_soon_items_api: {str(e)}")
        import traceback
        traceback.print_exc()
        return JsonResponse({'error': str(e)}, status=500)

def fetch_ingredients(request):
    user = get_user_for_view(request)
    ingredients = Inventory.objects.filter(user_id=user.id).values('id', 'item', 'base_unit', 'unit_type')
    return JsonResponse({'ingredients': list(ingredients)})


def _is_checked(post_data, key):
    return str(post_data.get(key, '')).lower() in ('on', 'true', '1', 'yes')


def resolve_recipe_type_and_populate_flags(post_data):
    selected_recipe_type = (post_data.get('recipeType') or 'lunch').strip()
    user_selected_recipe_type = (post_data.get('recipeTypeUserSelected') or '').strip()
    valid_recipe_types = {choice for choice, _ in Recipe.RECIPE_TYPE_CHOICES}
    manual_selection_recipe_types = {'multiple', 'vegetable', 'fruit', 'whole_grain', 'fluid'}
    original_selected_recipe_type = selected_recipe_type

    if user_selected_recipe_type in valid_recipe_types or user_selected_recipe_type == 'multiple':
        selected_recipe_type = user_selected_recipe_type

    if selected_recipe_type not in valid_recipe_types and selected_recipe_type != 'multiple':
        selected_recipe_type = 'lunch'

    manual_flags = {
        'populate_breakfast': _is_checked(post_data, 'populateBreakfast'),
        'populate_am_snack': _is_checked(post_data, 'populateAMSnack'),
        'populate_lunch': _is_checked(post_data, 'populateLunch'),
        'populate_pm_snack': _is_checked(post_data, 'populatePMSnack'),
    }

    if selected_recipe_type == 'multiple':
        flags = manual_flags
        if not any(flags.values()):
            flags['populate_lunch'] = True

        if flags['populate_breakfast']:
            resolved_recipe_type = 'breakfast'
        elif flags['populate_am_snack']:
            resolved_recipe_type = 'am_snack'
        elif flags['populate_lunch']:
            resolved_recipe_type = 'lunch'
        elif flags['populate_pm_snack']:
            resolved_recipe_type = 'pm_snack'
        else:
            resolved_recipe_type = 'lunch'

        return resolved_recipe_type, flags

    if selected_recipe_type in manual_selection_recipe_types:
        return selected_recipe_type, manual_flags

    recipe_type_to_populate = {
        'lunch': {'populate_breakfast': False, 'populate_am_snack': False, 'populate_lunch': True, 'populate_pm_snack': False},
        'breakfast': {'populate_breakfast': True, 'populate_am_snack': False, 'populate_lunch': False, 'populate_pm_snack': False},
        'am_snack': {'populate_breakfast': False, 'populate_am_snack': True, 'populate_lunch': False, 'populate_pm_snack': False},
        'pm_snack': {'populate_breakfast': False, 'populate_am_snack': False, 'populate_lunch': False, 'populate_pm_snack': True},
        'am_pm_snack': {'populate_breakfast': False, 'populate_am_snack': True, 'populate_lunch': False, 'populate_pm_snack': True},
    }

    flags = recipe_type_to_populate.get(selected_recipe_type, recipe_type_to_populate['lunch'])
    return selected_recipe_type, flags

@login_required
def create_recipe(request):
    if request.method == 'POST':
        # Extract form data
        recipe_name = request.POST.get('recipeName')
        ingredient_prefixes = [
            'mainIngredient',
            'breakfastMainIngredient',
            'amIngredient',
            'pmIngredient',
            'fruitMainIngredient',
            'vegMainIngredient',
            'wgMainIngredient',
            'ingredient',
        ]
        qty_prefixes = [
            'qtyMainIngredient',
            'breakfastQtyMainIngredient',
            'amQty',
            'pmQty',
            'fruitQtyMainIngredient',
            'vegQtyMainIngredient',
            'wgQtyMainIngredient',
            'qty',
        ]

        main_ingredient_ids = []
        quantities = []
        for i in range(1, 21):
            ingredient_value = None
            qty_value = None

            for prefix in ingredient_prefixes:
                candidate = request.POST.get(f'{prefix}{i}')
                if candidate not in (None, ''):
                    ingredient_value = candidate
                    break

            for prefix in qty_prefixes:
                candidate = request.POST.get(f'{prefix}{i}')
                if candidate not in (None, ''):
                    qty_value = candidate
                    break

            main_ingredient_ids.append(ingredient_value)
            quantities.append(qty_value)

        instructions = request.POST.get('instructions')
        grain = request.POST.get('grain')
        meat_alternate = request.POST.get('meatAlternate')
        # Add missing fields
        fruit = request.POST.get('fruit')
        veg = request.POST.get('veg')
        meat = request.POST.get('meat')
        addfood = request.POST.get('addfood')
        fluid = request.POST.get('fluid')
        # Extract rule IDs for each possible field
        grain_rule_id = request.POST.get('grain_rule')
        addfood_rule_id = request.POST.get('addfood_rule')
        fluid_rule_id = request.POST.get('fluid_rule')
        veg_rule_id = request.POST.get('veg_rule')
        fruit_rule_id = request.POST.get('fruit_rule')
        meat_rule_id = request.POST.get('meat_rule')
        
        # Extract checkbox values for meal period availability and options
        recipe_type, populate_flags = resolve_recipe_type_and_populate_flags(request.POST)
        populate_breakfast = populate_flags['populate_breakfast']
        populate_am_snack = populate_flags['populate_am_snack']
        populate_lunch = populate_flags['populate_lunch']
        populate_pm_snack = populate_flags['populate_pm_snack']
        standalone = request.POST.get('standalone') == 'on'
        ignore_inventory = request.POST.get('ignoreInventory') == 'on'

        # Use get_user_for_view to get the correct user (main user or subuser)
        user = get_user_for_view(request)

        # Get Rule objects for each field if provided
        grain_rule = get_object_or_404(Rule, id=grain_rule_id) if grain_rule_id else None
        addfood_rule = get_object_or_404(Rule, id=addfood_rule_id) if addfood_rule_id else None
        fluid_rule = get_object_or_404(Rule, id=fluid_rule_id) if fluid_rule_id else None
        veg_rule = get_object_or_404(Rule, id=veg_rule_id) if veg_rule_id else None
        fruit_rule = get_object_or_404(Rule, id=fruit_rule_id) if fruit_rule_id else None
        meat_rule = get_object_or_404(Rule, id=meat_rule_id) if meat_rule_id else None

        # Create recipe instance (add other fields as needed)
        recipe = Recipe.objects.create(
            user=user,
            name=recipe_name,
            recipe_type=recipe_type,
            instructions=instructions,
            grain=grain,
            grain_rule=grain_rule,
            addfood=addfood,
            addfood_rule=addfood_rule,
            fluid=fluid,
            fluid_rule=fluid_rule,
            veg=veg,
            veg_rule=veg_rule,
            fruit=fruit,
            fruit_rule=fruit_rule,
            meat=meat,
            meat_rule=meat_rule,
            meat_alternate=meat_alternate,
            populate_breakfast=populate_breakfast,
            populate_am_snack=populate_am_snack,
            populate_lunch=populate_lunch,
            populate_pm_snack=populate_pm_snack,
            standalone=standalone,
            ignore_inventory=ignore_inventory
        )

        # Save main ingredients using helper function
        save_recipe_ingredients(recipe, main_ingredient_ids, quantities)

        from django.shortcuts import redirect
        return redirect(request.META.get('HTTP_REFERER', '/'))
    else:
        from django.http import HttpResponseNotAllowed
        return HttpResponseNotAllowed(['POST'])

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
        
        # Extract checkbox values for meal period availability and options
        populate_breakfast = request.POST.get('fruitPopulateBreakfast') == 'on'
        populate_am_snack = request.POST.get('fruitPopulateAMSnack') == 'on'
        populate_lunch = request.POST.get('fruitPopulateLunch') == 'on'
        populate_pm_snack = request.POST.get('fruitPopulatePMSnack') == 'on'
        standalone = request.POST.get('fruitStandalone') == 'on'
        ignore_inventory = request.POST.get('fruitIgnoreInventory') == 'on'

        # Create fruit recipe instance
        fruit_recipe = Recipe.objects.create(
            user=user,
            name=recipe_name,
            recipe_type='fruit',
            rule=rule,  # This will be None if no rule is selected
            populate_breakfast=populate_breakfast,
            populate_am_snack=populate_am_snack,
            populate_lunch=populate_lunch,
            populate_pm_snack=populate_pm_snack,
            standalone=standalone,
            ignore_inventory=ignore_inventory
        )

        # Save the ingredient using helper function
        save_recipe_ingredients(fruit_recipe, [ingredient_id], [quantity])

        from django.shortcuts import redirect
        return redirect(request.META.get('HTTP_REFERER', '/'))
    else:
        from django.http import HttpResponseNotAllowed
        return HttpResponseNotAllowed(['POST'])

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
        
        # Extract checkbox values for meal period availability and options
        populate_breakfast = request.POST.get('vegPopulateBreakfast') == 'on'
        populate_am_snack = request.POST.get('vegPopulateAMSnack') == 'on'
        populate_lunch = request.POST.get('vegPopulateLunch') == 'on'
        populate_pm_snack = request.POST.get('vegPopulatePMSnack') == 'on'
        standalone = request.POST.get('vegStandalone') == 'on'
        ignore_inventory = request.POST.get('vegIgnoreInventory') == 'on'

        # Create vegetable recipe instance
        veg_recipe = Recipe.objects.create(
            user=user,
            name=recipe_name,
            recipe_type='vegetable',
            rule=rule,  # This will be None if no rule is selected
            populate_breakfast=populate_breakfast,
            populate_am_snack=populate_am_snack,
            populate_lunch=populate_lunch,
            populate_pm_snack=populate_pm_snack,
            standalone=standalone,
            ignore_inventory=ignore_inventory
        )

        # Save the ingredient using helper function
        save_recipe_ingredients(veg_recipe, [ingredient_id], [quantity])

        from django.shortcuts import redirect
        return redirect(request.META.get('HTTP_REFERER', '/'))
    else:
        from django.http import HttpResponseNotAllowed
        return HttpResponseNotAllowed(['POST'])
    
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
        
        # Extract checkbox values for meal period availability and options
        populate_breakfast = request.POST.get('wgPopulateBreakfast') == 'on'
        populate_am_snack = request.POST.get('wgPopulateAMSnack') == 'on'
        populate_lunch = request.POST.get('wgPopulateLunch') == 'on'
        populate_pm_snack = request.POST.get('wgPopulatePMSnack') == 'on'
        standalone = request.POST.get('wgStandalone') == 'on'
        ignore_inventory = request.POST.get('wgIgnoreInventory') == 'on'

        # Create WG recipe instance
        wg_recipe = Recipe.objects.create(
            user=user,
            name=recipe_name,
            recipe_type='whole_grain',
            rule=rule,  # This will be None if no rule is selected
            populate_breakfast=populate_breakfast,
            populate_am_snack=populate_am_snack,
            populate_lunch=populate_lunch,
            populate_pm_snack=populate_pm_snack,
            standalone=standalone,
            ignore_inventory=ignore_inventory
        )

        # Save the ingredient using helper function
        save_recipe_ingredients(wg_recipe, [ingredient_id], [quantity])

        from django.shortcuts import redirect
        return redirect(request.META.get('HTTP_REFERER', '/'))
    else:
        from django.http import HttpResponseNotAllowed
        return HttpResponseNotAllowed(['POST'])

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
        
        # Extract checkbox values for meal period availability and options
        populate_breakfast = request.POST.get('breakfastPopulateBreakfast') == 'on'
        populate_am_snack = request.POST.get('breakfastPopulateAMSnack') == 'on'
        populate_lunch = request.POST.get('breakfastPopulateLunch') == 'on'
        populate_pm_snack = request.POST.get('breakfastPopulatePMSnack') == 'on'
        standalone = request.POST.get('breakfastStandalone') == 'on'
        ignore_inventory = request.POST.get('breakfastIgnoreInventory') == 'on'

        # Use get_user_for_view to get the correct user (main user or subuser)
        user = get_user_for_view(request)

        rule = Rule.objects.get(id=rule_id) if rule_id else None
        # Create breakfast recipe instance
        breakfast_recipe = Recipe.objects.create(
            user=user,
            name=recipe_name,
            recipe_type='breakfast',
            instructions=instructions,
            addfood=additional_food,
            rule=rule,
            populate_breakfast=populate_breakfast,
            populate_am_snack=populate_am_snack,
            populate_lunch=populate_lunch,
            populate_pm_snack=populate_pm_snack,
            standalone=standalone,
            ignore_inventory=ignore_inventory
        )

        # Save main ingredients using helper function
        save_recipe_ingredients(breakfast_recipe, main_ingredient_ids, quantities)

        from django.shortcuts import redirect
        return redirect(request.META.get('HTTP_REFERER', '/'))
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
        
        # Extract checkbox values for meal period availability and options
        populate_breakfast = request.POST.get('amPopulateBreakfast') == 'on'
        populate_am_snack = request.POST.get('amPopulateAMSnack') == 'on'
        populate_lunch = request.POST.get('amPopulateLunch') == 'on'
        populate_pm_snack = request.POST.get('amPopulatePMSnack') == 'on'
        standalone = request.POST.get('amStandalone') == 'on'
        ignore_inventory = request.POST.get('amIgnoreInventory') == 'on'

        # Use get_user_for_view to get the correct user (main user or subuser)
        user = get_user_for_view(request)

        rule = Rule.objects.get(id=rule_id) if rule_id else None

        # Create AM recipe instance
        am_recipe = Recipe.objects.create(
            user=user,
            name=recipe_name,
            recipe_type='am_snack',
            instructions=instructions,
            fluid=fluid,
            fruit_veg=fruit_veg,
            meat=meat,
            rule=rule,  # Set rule
            populate_breakfast=populate_breakfast,
            populate_am_snack=populate_am_snack,
            populate_lunch=populate_lunch,
            populate_pm_snack=populate_pm_snack,
            standalone=standalone,
            ignore_inventory=ignore_inventory
        )

        # Save main ingredients using helper function
        save_recipe_ingredients(am_recipe, main_ingredient_ids, quantities)

        from django.shortcuts import redirect
        return redirect(request.META.get('HTTP_REFERER', '/'))
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
        
        # Extract checkbox values for meal period availability and options
        populate_breakfast = request.POST.get('pmPopulateBreakfast') == 'on'
        populate_am_snack = request.POST.get('pmPopulateAMSnack') == 'on'
        populate_lunch = request.POST.get('pmPopulateLunch') == 'on'
        populate_pm_snack = request.POST.get('pmPopulatePMSnack') == 'on'
        standalone = request.POST.get('pmStandalone') == 'on'
        ignore_inventory = request.POST.get('pmIgnoreInventory') == 'on'

        # Use get_user_for_view to get the correct user (main user or subuser)
        user = get_user_for_view(request)

        rule = get_object_or_404(Rule, id=rule_id) if rule_id else None

        # Create PM recipe instance
        pm_recipe = Recipe.objects.create(
            user=user,
            name=recipe_name,
            recipe_type='pm_snack',
            instructions=instructions,
            fluid=fluid,
            fruit_veg=fruit_veg,
            meat=meat,
            rule=rule,  # Set rule
            populate_breakfast=populate_breakfast,
            populate_am_snack=populate_am_snack,
            populate_lunch=populate_lunch,
            populate_pm_snack=populate_pm_snack,
            standalone=standalone,
            ignore_inventory=ignore_inventory
        )

        # Save main ingredients using helper function
        save_recipe_ingredients(pm_recipe, main_ingredient_ids, quantities)

        from django.shortcuts import redirect
        return redirect(request.META.get('HTTP_REFERER', '/'))
    else:
        # If the request method is not POST, return error response
        return JsonResponse({'error': 'Method not allowed'}, status=405)
    
def fetch_recipes(request):
    # Use get_user_for_view to get the correct user (main user or subuser)
    user = get_user_for_view(request)

    # Retrieve only lunch recipes from the database for the identified user
    recipes = Recipe.objects.filter(user=user, recipe_type='lunch', archive=False).order_by('name').values('id', 'name')
    return JsonResponse({'recipes': list(recipes)})

@login_required
def fetch_rules(request):
    user = get_user_for_view(request)
    rules = Rule.objects.filter(user=user)
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
    veg_recipes = Recipe.objects.filter(user=user, recipe_type='vegetable', archive=False).order_by('name').values('id', 'name')
    return JsonResponse({'recipes': list(veg_recipes)})

@login_required
def fetch_wg_recipes(request):
    user = get_user_for_view(request)
    wg_recipes = Recipe.objects.filter(user=user, recipe_type='whole_grain', archive=False).order_by('name').values('id', 'name')
    return JsonResponse({'recipes': list(wg_recipes)})

def fetch_fruit_recipes(request):
    user = get_user_for_view(request)
    fruit_recipes = Recipe.objects.filter(user=user, recipe_type='fruit', archive=False).order_by('name').values('id', 'name')
    return JsonResponse({'recipes': list(fruit_recipes)})

def fetch_fluid_recipes(request):
    user = get_user_for_view(request)
    fluid_recipes = Recipe.objects.filter(user=user, recipe_type='fluid', archive=False).order_by('name').values('id', 'name')
    return JsonResponse({'recipes': list(fluid_recipes)})

def fetch_breakfast_recipes(request):
    user = get_user_for_view(request)
    breakfast_recipes = Recipe.objects.filter(user=user, recipe_type='breakfast', archive=False).order_by('name').values('id', 'name')
    return JsonResponse({'recipes': list(breakfast_recipes)})

@login_required
def fetch_am_recipes(request):
    user = get_user_for_view(request)
    from django.db.models import Q
    am_recipes = Recipe.objects.filter(user=user, archive=False).filter(Q(recipe_type='am_snack') | Q(recipe_type='am_pm_snack')).order_by('name').values('id', 'name')
    return JsonResponse({'recipes': list(am_recipes)})

def fetch_pm_recipes(request):
    user = get_user_for_view(request)
    from django.db.models import Q
    pm_recipes = Recipe.objects.filter(user=user, archive=False).filter(Q(recipe_type='pm_snack') | Q(recipe_type='am_pm_snack')).order_by('name').values('id', 'name')
    return JsonResponse({'recipes': list(pm_recipes)})

def fetch_archived_recipes(request):
    user = get_user_for_view(request)
    archived = Recipe.objects.filter(user=user, archive=True).order_by('recipe_type', 'name').values('id', 'name', 'recipe_type')
    return JsonResponse({'recipes': list(archived)})

def check_ingredients_availability(request, recipe):
    """Check if all ingredients in a recipe are available in sufficient quantities."""
    user = get_user_for_view(request)  # Get the user (main user or subuser)
    
    ingredients = get_recipe_ingredients(recipe)
    
    for ingredient, qty in ingredients:
        if ingredient and qty:
            # Check if the ingredient is available in the user's inventory
            if not Inventory.objects.filter(user=user, id=ingredient.id, quantity__gte=qty).exists():
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
            # Parse JSON data from the request body
            raw_body = request.body.decode('utf-8')
           
            data = json.loads(raw_body)
           
            # Determine week start from client if provided, otherwise default to next Monday
            week_dates = []
            week_start_str = data.get('week_start') or None
            if week_start_str:
                try:
                    # Expecting ISO YYYY-MM-DD
                    parsed = datetime.strptime(week_start_str, '%Y-%m-%d').date()
                    # Ensure parsed is a Monday; if not, compute the Monday of that week
                    if parsed.weekday() != 0:
                        parsed = parsed - timedelta(days=parsed.weekday())
                    week_dates = [(parsed + timedelta(days=i)) for i in range(5)]
                except Exception:
                    # Fallback to server-calculated next Monday
                    today = datetime.now()
                    next_monday = today + timedelta(days=(7 - today.weekday()))
                    week_dates = [(next_monday + timedelta(days=i)).date() for i in range(5)]
            else:
                # Create a list of the next week dates (Monday to Friday)
                today = datetime.now()
                next_monday = today + timedelta(days=(7 - today.weekday()))
                week_dates = [(next_monday + timedelta(days=i)).date() for i in range(5)]
           

            # Define the days of the week
            days_of_week = {
                'monday': 'Mon',
                'tuesday': 'Tue',
                'wednesday': 'Wed',
                'thursday': 'Thu',
                'friday': 'Fri'
            }

            user = get_user_for_view(request)
           
            # Ensure we're using the main account owner for saving menu data
            if hasattr(user, 'main_account_owner') and user.main_account_owner:
                # If this is a linked user, use their main account owner
                menu_user = user.main_account_owner
            else:
                # If this is the main account owner or regular user, use them directly
                menu_user = user
              
            # Get facility and sponsor names from the request data
            facility_name = data.get('facility_name', 'Default Facility')
            sponsor_name = data.get('sponsor_name', 'Default Sponsor')
            
            try:
                test_menu = WeeklyMenu.objects.create(
                    user=menu_user,
                    date=week_dates[0],
                    day_of_week='Mon',
                    facility=facility_name,
                    sponsor=sponsor_name,
                    am_fluid_milk='Test',
                    am_fruit_veg='Test',
                    am_bread='Test',
                    am_additional='Test'
                )
        
                test_menu.delete()  # Clean up the test
            except Exception as test_error:
                
                import traceback
                traceback.print_exc()
                return JsonResponse({'status': 'fail', 'error': f'Test creation failed: {str(test_error)}'}, status=500)

            for day_index, (day_key, day_abbr) in enumerate(days_of_week.items()):
                day_data = data.get(day_key, {})
                date_for_day = week_dates[day_index]
               # Check for existing menu first
                existing_menu = WeeklyMenu.objects.filter(
                    user=menu_user,
                    date=date_for_day,
                    day_of_week=day_abbr
                ).first()
                
                if existing_menu:
                    pass  # print(f"Found existing menu for {day_key}: {existing_menu.id}")
                else:
                    pass  # print(f"No existing menu found for {day_key}")

                try:
                    # Create or update the WeeklyMenu for each day
                    menu_obj, created = WeeklyMenu.objects.update_or_create(
                        user=menu_user,
                        date=date_for_day,
                        day_of_week=day_abbr,
                        defaults={
                            'facility': facility_name,
                            'sponsor': sponsor_name,
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
                    
                    action = "Created" if created else "Updated"

                    # Persist assigned rules for this day's menu (if provided)
                    try:
                        from .models import WeeklyMenuAssignedRule
                        assigned_rules_all = data.get('assigned_rules', {}) or {}
                        # Find rules keys that belong to this day (cell ids start with day name)
                        day_assigned = {cid: rid for cid, rid in assigned_rules_all.items() if cid.startswith(day_key)}
                        # Remove existing assigned rules for this day's cells on this weekly menu
                        WeeklyMenuAssignedRule.objects.filter(weekly_menu=menu_obj, cell_id__startswith=day_key).delete()
                        for cell_id, rule_id in day_assigned.items():
                            try:
                                rule_obj = Rule.objects.get(id=rule_id, user=menu_user)
                                WeeklyMenuAssignedRule.objects.create(weekly_menu=menu_obj, cell_id=cell_id, rule=rule_obj)
                            except Rule.DoesNotExist:
                                # skip invalid rule ids
                                continue
                    except Exception as ar_ex:
                        logger.warn('Failed to persist assigned rules: %s', ar_ex)
  

                except Exception as day_error:
                    import traceback
                    traceback.print_exc()
                    return JsonResponse({
                        'status': 'fail', 
                        'error': f'Error saving {day_key}: {str(day_error)}'
                    }, status=500)

            # Update last_used timestamps for all recipes in this menu to their specific day's date
            # This ensures cooldown tracking works correctly for consecutive future menus
            try:
                menu_week_start = week_dates[0]
                pass  # print(f"\n{'='*60}")
                pass  # print(f"🔄 SAVE_MENU TIMESTAMP UPDATE - Menu week: {menu_week_start}")
                pass  # print(f"{'='*60}")
                
                # Map recipe names to their specific day's date (first occurrence if recipe appears multiple days)
                recipe_to_date = {}
                
                # Extract all recipe names and their dates from the menu data
                for day_index, day_key in enumerate(days_of_week.keys()):
                    day_data = data.get(day_key, {})
                    date_for_day = week_dates[day_index]
                    
                    # Get all menu field values (breakfast, AM snack, lunch, PM snack)
                    for field_key, field_value in day_data.items():
                        if field_value and isinstance(field_value, str):
                            # Clean the value (remove "Out of stock" markers, etc.)
                            cleaned_value = field_value.strip()
                            if cleaned_value and not cleaned_value.startswith('❌'):
                                # Store first occurrence date for each recipe
                                if cleaned_value not in recipe_to_date:
                                    recipe_to_date[cleaned_value] = date_for_day
                
                pass  # print(f"📝 Extracted {len(recipe_to_date)} unique recipe names from menu data")
                
                # Update last_used for all recipes found in the menu
                if recipe_to_date:
                    from datetime import time
                    
                    updated_count = 0
                    skipped_count = 0
                    for recipe_name, recipe_date in recipe_to_date.items():
                        # Convert date to timezone-aware datetime (midnight on specific day)
                        recipe_datetime = django_timezone.make_aware(datetime.combine(recipe_date, time.min))
                        
                        # Find the recipe
                        recipe = Recipe.objects.filter(user=menu_user, name=recipe_name).first()
                        if recipe:
                            old_date = recipe.last_used
                            
                            # Only update if the new date is LATER than current timestamp
                            # This handles out-of-order menu saves (e.g., saving May 18 week after May 25 week)
                            if not old_date or recipe_datetime > old_date:
                                # Use QuerySet update() to bypass auto_now field
                                Recipe.objects.filter(id=recipe.id).update(last_used=recipe_datetime)
                                updated_count += 1
                                if updated_count <= 5:  # Show first 5 examples
                                    pass  # print(f"  • {recipe.name} on {recipe_date}: {old_date} → {recipe_datetime}")
                            else:
                                skipped_count += 1
                                if skipped_count <= 3:  # Show first 3 skipped examples
                                    pass  # print(f"  ⏭️ {recipe.name}: Keeping existing date {old_date.date() if old_date else 'None'} (newer than {recipe_date})")
                    
                    if updated_count > 0:
                        pass  # print(f"✅ Successfully updated last_used for {updated_count} recipes with their specific day dates")
                    if skipped_count > 0:
                        pass  # print(f"⏭️ Skipped {skipped_count} recipes that already have newer timestamps")
                    pass  # print(f"{'='*60}\n")
                else:
                    pass  # print(f"⚠️ No recipe names extracted from menu data")
                    pass  # print(f"{'='*60}\n")
            except Exception as timestamp_error:
                # Log but don't fail the save operation if timestamp update fails
                pass  # print(f"⚠️ Warning: Failed to update recipe timestamps: {str(timestamp_error)}")
                import traceback
                traceback.print_exc()

            pass  # print("Successfully saved all menu data")
            return JsonResponse({'status': 'success'}, status=200)

        except json.JSONDecodeError as e:
            pass  # print(f"JSON decode error: {str(e)}")
            return JsonResponse({'status': 'fail', 'error': 'Invalid JSON'}, status=400)

        except Exception as e:
            pass  # print(f"Unexpected error in save_menu: {str(e)}")
            pass  # print(f"Error type: {type(e).__name__}")
            import traceback
            traceback.print_exc()
            return JsonResponse({'status': 'fail', 'error': f'Unexpected error: {str(e)}'}, status=500)

    return JsonResponse({'status': 'fail', 'error': 'Invalid request method'}, status=400)

@login_required
@login_required
def archive_recipe(request, recipe_id):
    if request.method == 'POST':
        user = get_user_for_view(request)
        recipe = Recipe.objects.filter(pk=recipe_id, user=user).first()
        if not recipe:
            return JsonResponse({'status': 'error', 'message': 'Recipe not found'}, status=404)
        recipe.archive = True
        recipe.save(update_fields=['archive'])
        return JsonResponse({'status': 'success', 'message': f'"{recipe.name}" has been archived.'})
    return JsonResponse({'status': 'error', 'message': 'Invalid request method'}, status=405)


@login_required
def unarchive_recipe(request, recipe_id):
    if request.method == 'POST':
        user = get_user_for_view(request)
        recipe = Recipe.objects.filter(pk=recipe_id, user=user).first()
        if not recipe:
            return JsonResponse({'status': 'error', 'message': 'Recipe not found'}, status=404)
        recipe.archive = False
        recipe.save(update_fields=['archive'])
        return JsonResponse({'status': 'success', 'message': f'"{recipe.name}" has been unarchived.'})
    return JsonResponse({'status': 'error', 'message': 'Invalid request method'}, status=405)


def delete_recipe(request, recipe_id, category):
    if request.method == 'DELETE':
        user = get_user_for_view(request)
        # Map category to recipe_type filter — all recipes live in the Recipe model
        category_filter_map = {
            'lunch':     {'recipe_type': 'lunch'},
            'breakfast': {'recipe_type': 'breakfast'},
            'fruit':     {'recipe_type': 'fruit'},
            'veg':       {'recipe_type': 'vegetable'},
            'wg':        {'recipe_type': 'whole_grain'},
        }
        from django.db.models import Q
        if category in category_filter_map:
            filter_kwargs = {'pk': recipe_id, 'user': user, **category_filter_map[category]}
            recipe = Recipe.objects.filter(**filter_kwargs).first()
        elif category == 'am':
            recipe = Recipe.objects.filter(pk=recipe_id, user=user).filter(Q(recipe_type='am_snack') | Q(recipe_type='am_pm_snack')).first()
        elif category == 'pm':
            recipe = Recipe.objects.filter(pk=recipe_id, user=user).filter(Q(recipe_type='pm_snack') | Q(recipe_type='am_pm_snack')).first()
        else:
            return JsonResponse({'status': 'error', 'message': 'Invalid category'}, status=400)

        if not recipe:
            return JsonResponse({'status': 'error', 'message': f'{category.capitalize()} recipe not found'}, status=404)

        recipe.delete()
        return JsonResponse({'status': 'success', 'message': f'{category.capitalize()} recipe deleted successfully'})
    else:
        return JsonResponse({'status': 'error', 'message': 'Invalid request method'}, status=405)
    
@login_required
def order_list(request):
    if request.method == 'POST':
        item = request.POST.get('item', '')
        quantity = request.POST.get('quantity', 1)
        category = request.POST.get('category', 'Other')

        if item:
            user = request.user
            main_user = get_user_for_view(request)
            OrderList.objects.create(
                user=user,
                main_user=main_user,  # <-- Save the location
                item=item,
                quantity=quantity,
                category=category
            )
            return redirect('order_list')
        else:
            return HttpResponseBadRequest('Invalid form submission')
    else:
        user = request.user
        main_user = get_user_for_view(request)
        order_items = OrderList.objects.filter(user=user, main_user=main_user)
        return render(request, 'index.html', {'order_items': order_items})
    
@login_required
def shopping_list_api(request):
    if request.method == 'GET':
        user = request.user
        main_user = get_user_for_view(request)
        shopping_list_items = OrderList.objects.filter(user=user, main_user=main_user)
        serialized_items = [
            {
                'id': item.id,
                'name': item.item,
                'quantity': item.quantity,
                'ordered': item.ordered
            }
            for item in shopping_list_items
        ]
        return JsonResponse(serialized_items, safe=False)
    else:
        return HttpResponseNotAllowed(['GET'])
    
@login_required
def update_orders(request):
    if request.method == 'POST':
        item_ids = request.POST.getlist('items')
        try:
            user = request.user
            main_user = get_user_for_view(request)
            for item_id in item_ids:
                order_item = get_object_or_404(OrderList, id=item_id, user=user, main_user=main_user)
                order_item.ordered = True
                order_item.save()
                
                # Add ordered item to inventory automatically
                inventory_item, created = Inventory.objects.get_or_create(
                    user=main_user,
                    item=order_item.item,
                    defaults={
                        'quantity': order_item.quantity,
                        'category': order_item.category or 'Other',
                        'unit_type': 'each',
                        'base_unit': 'each',
                        'unit_size': 1,
                        'conversion_to_base': 1,
                        'resupply': 5,
                        'total_quantity': order_item.quantity,
                    }
                )
                if not created:
                    inventory_item.quantity += order_item.quantity
                    inventory_item.total_quantity += order_item.quantity
                    inventory_item.save()
            return JsonResponse({'success': True, 'message': 'Orders updated successfully'})
        except Exception as e:
            return JsonResponse({'success': False, 'error': str(e)}, status=500)
    else:
        return HttpResponseNotAllowed(['POST'])

@login_required
def update_shopping_item_status(request):
    if request.method == 'POST':
        import json
        data = json.loads(request.body)
        item_id = data.get('item_id')
        ordered = data.get('ordered')
        try:
            user = request.user
            main_user = get_user_for_view(request)
            order_item = get_object_or_404(OrderList, id=item_id, user=user, main_user=main_user)
            order_item.ordered = ordered
            order_item.save()
            return JsonResponse({'success': True, 'message': 'Status updated successfully'})
        except Exception as e:
            return JsonResponse({'success': False, 'error': str(e)}, status=500)
    else:
        return HttpResponseNotAllowed(['POST'])

@login_required
def delete_shopping_item(request, item_id):
    if request.method == 'DELETE':
        try:
            user = request.user
            main_user = get_user_for_view(request)
            order_item = get_object_or_404(OrderList, id=item_id, user=user, main_user=main_user)
            order_item.delete()
            return JsonResponse({'success': True, 'message': 'Item deleted successfully'})
        except Exception as e:
            return JsonResponse({'success': False, 'error': str(e)}, status=500)
    else:
        return HttpResponseNotAllowed(['DELETE'])

@login_required
def delete_shopping_items(request):
    if request.method == 'POST':
        user = request.user
        main_user = get_user_for_view(request)
        item_ids = request.POST.getlist('items[]')
        OrderList.objects.filter(id__in=item_ids, user=user, main_user=main_user).delete()
        return redirect('order_list')
    else:
        return HttpResponseNotAllowed(['POST'])

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
    
    # Get the appropriate main user for filtering
    main_user = get_user_for_view(request)
    
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
    
    # Filter attendance records by date
    attendance_records = AttendanceRecord.objects.filter(sign_in_time__date=selected_date)

    # Build student options for manual insert of completely missed records
    insert_students = Student.objects.filter(main_user=main_user)
    
    # If a classroom is selected, filter by original classroom OR any classroom override
    if selected_classroom:
        try:
            classroom_obj = Classroom.objects.get(id=selected_classroom)
            classroom_name = classroom_obj.name

            insert_students = insert_students.filter(classroom_id=selected_classroom)
            
            attendance_records = attendance_records.filter(
                Q(classroom_id=selected_classroom) |
                Q(classroom_override_1=classroom_name) |
                Q(classroom_override_2=classroom_name) |
                Q(classroom_override_3=classroom_name) |
                Q(classroom_override_4=classroom_name)
            )
        except Classroom.DoesNotExist:
            # If classroom doesn't exist, just filter by classroom_id
            insert_students = insert_students.filter(classroom_id=selected_classroom)
            attendance_records = attendance_records.filter(classroom_id=selected_classroom)

    existing_student_ids = attendance_records.values_list('student_id', flat=True)
    insert_students = insert_students.exclude(id__in=existing_student_ids).order_by('first_name', 'last_name')
    
    # Filter classrooms by main user - try common FK field names
    classrooms = None
    attempts = [
        ('user', False),
        ('main_user', False),
        ('mainuser', False),
        ('owner', False),
        ('user_id', True),
        ('main_user_id', True),
        ('mainuser_id', True),
        ('owner_id', True),
    ]
    for field_name, is_id in attempts:
        try:
            if is_id:
                kwargs = {field_name: main_user.id}
            else:
                kwargs = {field_name: main_user}
            classrooms = Classroom.objects.filter(**kwargs)
            break
        except FieldError:
            classrooms = None
            continue
    
    # If no matching field found, return empty queryset
    if classrooms is None:
        logger.warning("No matching FK field found on Classroom; returning empty queryset.")
        classrooms = Classroom.objects.none()
    
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
        'feeds': FeedRecord.objects.filter(
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
    feed_students = set(
        FeedRecord.objects.filter(
            student__in=attendance_records.values_list('student', flat=True),
            timestamp__date=selected_date
        ).values_list('student_id', flat=True)
    )
    # Render the attendance record page
    return render(request, 'attendance_record.html', {
        'attendance_records': attendance_records,
        'insert_students': insert_students,
        'classrooms': classrooms,
        'selected_date': selected_date,
        'selected_classroom': selected_classroom,
        'column_visibility': column_visibility,
        'diaper_change_students': diaper_change_students,
        'feed_students': feed_students,
        **permissions_context,
    })

@login_required
@require_POST
def update_attendance_times(request):
    try:
        data = json.loads(request.body)
        updates = data.get('updates', [])
        main_user = get_user_for_view(request)
        
        for update in updates:
            record_id = update.get('record_id')
            field = update.get('field')
            value = update.get('value')
            
            try:
                record = AttendanceRecord.objects.get(id=record_id, user=main_user)
                
                # Convert empty string to None
                if value == '':
                    value = None
                elif value:
                    # Parse datetime string and make it aware
                    dt = datetime.fromisoformat(value)
                    value = timezone.make_aware(dt)
                
                # Update the field
                setattr(record, field, value)
                record.save()
                
            except AttendanceRecord.DoesNotExist:
                return JsonResponse({'success': False, 'error': f'Record {record_id} not found'})
        
        return JsonResponse({'success': True})
        
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})


@login_required
@require_POST
def insert_attendance_record(request):
    try:
        data = json.loads(request.body)
        main_user = get_user_for_view(request)

        student_id = data.get('student_id')
        date_str = data.get('date')
        sign_in_time_str = data.get('sign_in_time')
        sign_out_time_str = data.get('sign_out_time')
        classroom_id = data.get('classroom_id')

        if not student_id or not date_str or not sign_in_time_str:
            return JsonResponse({'success': False, 'error': 'Student, date, and sign-in time are required.'})

        try:
            student = Student.objects.get(id=student_id, main_user=main_user)
        except Student.DoesNotExist:
            return JsonResponse({'success': False, 'error': 'Student not found for this account.'})

        if AttendanceRecord.objects.filter(student=student, user=main_user, sign_in_time__date=date_str).exists():
            return JsonResponse({'success': False, 'error': 'Attendance record already exists for this student on the selected date.'})

        try:
            sign_in_naive = datetime.strptime(f"{date_str} {sign_in_time_str}", "%Y-%m-%d %H:%M")
            sign_in_dt = timezone.make_aware(sign_in_naive, timezone.get_current_timezone())
        except ValueError:
            return JsonResponse({'success': False, 'error': 'Invalid sign-in time format.'})

        sign_out_dt = None
        if sign_out_time_str:
            try:
                sign_out_naive = datetime.strptime(f"{date_str} {sign_out_time_str}", "%Y-%m-%d %H:%M")
                sign_out_dt = timezone.make_aware(sign_out_naive, timezone.get_current_timezone())
            except ValueError:
                return JsonResponse({'success': False, 'error': 'Invalid sign-out time format.'})

            if sign_out_dt < sign_in_dt:
                return JsonResponse({'success': False, 'error': 'Sign-out time cannot be before sign-in time.'})

        classroom = None
        if classroom_id:
            try:
                classroom = Classroom.objects.get(id=classroom_id, user=main_user)
            except Classroom.DoesNotExist:
                return JsonResponse({'success': False, 'error': 'Selected classroom was not found.'})

        AttendanceRecord.objects.create(
            user=main_user,
            student=student,
            sign_in_time=sign_in_dt,
            sign_out_time=sign_out_dt,
            classroom=classroom or student.classroom,
        )

        return JsonResponse({'success': True})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})

@login_required
def daily_attendance(request):
    # Check permissions for the specific page
    required_permission_id = 274  # Permission ID for daily_attendance view
    permissions_context = check_permissions(request, required_permission_id)
    # If check_permissions returns a redirect, return it immediately
    if isinstance(permissions_context, HttpResponseRedirect):
        return permissions_context
    # Fetch attendance data
    today = date.today()
    user = get_user_for_view(request)
    students = Student.objects.all().order_by('first_name')
    attendance_records = AttendanceRecord.objects.filter(sign_in_time__date=today, user=user)
    # Get classroom names from Classroom model
    classroom_options = Classroom.objects.filter(user=user).values_list('name', flat=True)
    attendance_data = {}
    relative_counts = {}
    assigned_teachers = {}
    adjusted_ratios = {}
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

        # Fetch assigned teachers for the classroom
        assignments = ClassroomAssignment.objects.filter(classroom=classroom)
        assigned_teachers[classroom.id] = [
            assignment.mainuser or assignment.subuser for assignment in assignments
        ]

        # Calculate adjusted ratios based on the number of assigned teachers
        base_ratio = classroom.ratios
        teacher_count = len(assigned_teachers[classroom.id])
        adjusted_ratios[classroom.id] = base_ratio * (2 ** (teacher_count - 1)) if teacher_count > 0 else base_ratio
    # Add empty classrooms if there are no records
    for classroom in Classroom.objects.filter(user=user):
        if classroom not in attendance_data:
            attendance_data[classroom] = []
            relative_counts[classroom] = 0  # No students signed in
    # Fetch available teachers
    if isinstance(user, MainUser):
        # Get all MainUsers who are either the current MainUser or linked via SubUser
        available_teachers = MainUser.objects.filter(
            models.Q(id=user.id) |  # Current MainUser
            models.Q(id__in=SubUser.objects.filter(
                main_user=user,
                group_id_id__in=[1, 2, 3, 4, 7]  # Filter SubUsers by group_id_id
            ).values_list('user_id', flat=True))
        )
    else:
        # If the user is a SubUser, get the MainUser and all SubUsers linked to the same MainUser
        available_teachers = MainUser.objects.filter(
            models.Q(id=user.main_user.id) |  # MainUser of the SubUser
            models.Q(id__in=SubUser.objects.filter(
                main_user=user.main_user,
                group_id_id__in=[1, 2, 3, 4, 7]  # Filter SubUsers by group_id_id
            ).values_list('user_id', flat=True))
        )
    # Exclude teachers already assigned to any classroom
    assigned_teacher_ids = ClassroomAssignment.objects.values_list('mainuser_id', flat=True).distinct()
    available_teachers = available_teachers.exclude(id__in=assigned_teacher_ids)
    # Render the template with all required context
    return render(request, 'daily_attendance.html', {
        'attendance_records': attendance_records,
        'relative_counts': relative_counts,
        'students': students,
        'available_teachers': available_teachers,
        'classroom_options': classroom_options,
        'attendance_data': attendance_data,
        'assigned_teachers': assigned_teachers,
        'adjusted_ratios': adjusted_ratios,  # Pass adjusted ratios to the template
        **permissions_context,  # Include permission flags dynamically
    })

@login_required
def classroom(request):
    required_permission_id = 274
    permissions_context = check_permissions(request, required_permission_id)
    if isinstance(permissions_context, HttpResponseRedirect):
        return permissions_context

    try:
        main_user = get_user_for_view(request)
        classrooms = None

        attempts = [
            ('user', False),
            ('main_user', False),
            ('mainuser', False),
            ('owner', False),
            ('user_id', True),
            ('main_user_id', True),
            ('mainuser_id', True),
            ('owner_id', True),
        ]
        for field_name, is_id in attempts:
            try:
                kwargs = {field_name: (main_user.id if is_id else main_user)}
                classrooms = Classroom.objects.filter(**kwargs)
                break
            except FieldError:
                classrooms = None
                continue

        if classrooms is None:
            logger.warning("No matching FK field found on Classroom; returning empty queryset.")
            classrooms = Classroom.objects.none()

        selected_classroom_id = request.GET.get('classroom_id')
        status_filter = request.GET.get('status', 'signed_in')

        if not selected_classroom_id:
            assigned_classroom = ClassroomAssignment.objects.filter(mainuser=main_user).first()
            if assigned_classroom:
                selected_classroom_id = assigned_classroom.classroom.id

        selected_classroom = None
        if selected_classroom_id:
            selected_classroom = classrooms.filter(id=selected_classroom_id).first()

        other_classroom_students = Student.objects.none()
        if selected_classroom:
            other_classroom_students = (
                Student.objects.filter(main_user=main_user, status='active')
                .exclude(classroom_id=selected_classroom.id)
                .exclude(attendancerecord__sign_out_time__isnull=True)
                .select_related('classroom')
                .order_by('first_name', 'last_name')
                .distinct()
            )

        today = timezone.localdate()

        # Students with an open record that did not start today (red banner)
        unsigned_records = AttendanceRecord.objects.filter(
            sign_out_time__isnull=True
        ).exclude(
            sign_in_time__date=today
        )
        students_not_signed_out = set(unsigned_records.values_list('student_id', flat=True))

        # Annotations
        active_qs = AttendanceRecord.objects.filter(
            student=OuterRef('pk'),
            sign_out_time__isnull=True
        )

        if selected_classroom_id:
            # Base roster: assigned to selected classroom, excluding those currently overridden elsewhere
            students_in_classroom = list(
                Student.objects.filter(classroom_id=selected_classroom_id)
                .annotate(is_signed_in=Exists(active_qs))
                .exclude(
                    Exists(
                        AttendanceRecord.objects.filter(
                            student=OuterRef('pk'),
                            classroom_override__isnull=False,
                            sign_out_time__isnull=True
                        )
                    )
                )
            )
            try:
                selected_class_name = Classroom.objects.get(id=selected_classroom_id).name
            except Classroom.DoesNotExist:
                selected_class_name = None

            # Add students currently overridden into this classroom (active override)
            override_students_active = []
            if selected_class_name:
                override_students_active = list(
                    Student.objects.filter(
                        attendancerecord__classroom_override=selected_class_name,
                        attendancerecord__sign_out_time__isnull=True
                    ).annotate(is_signed_in=Exists(active_qs))
                )

            combined = {s.id: s for s in students_in_classroom}
            for s in override_students_active:
                combined[s.id] = s
            all_students = list(combined.values())

        else:
            # Teacher-wide roster across all assigned classrooms, excluding active overrides elsewhere
            assigned_students = list(
                Student.objects.filter(classroom__assignments__mainuser=main_user)
                .annotate(is_signed_in=Exists(active_qs))
                .exclude(
                    Exists(
                        AttendanceRecord.objects.filter(
                            student=OuterRef('pk'),
                            classroom_override__isnull=False,
                            sign_out_time__isnull=True
                        )
                    )
                )
            )
            assigned_class_names = [s.classroom.name for s in assigned_students if s.classroom]

            # Add students currently overridden into any of the teacher’s classes
            override_students_active = []
            if assigned_class_names:
                override_students_active = list(
                    Student.objects.filter(
                        attendancerecord__classroom_override__in=assigned_class_names,
                        attendancerecord__sign_out_time__isnull=True
                    ).annotate(is_signed_in=Exists(active_qs))
                )

            combined = {s.id: s for s in assigned_students}
            for s in override_students_active:
                combined[s.id] = s
            all_students = list(combined.values())

        # Flags
        for student in all_students:
            student.not_signed_out_yesterday = student.id in students_not_signed_out

        # Filters
        if status_filter == 'signed_in':
            filtered_students = [s for s in all_students if s.is_signed_in]
        elif status_filter == 'signed_out':
            filtered_students = [s for s in all_students if not s.is_signed_in]
        else:
            filtered_students = list(all_students)

        # Sort: signed-in first, then name
        filtered_students.sort(key=lambda s: (-int(bool(s.is_signed_in)), s.last_name, s.first_name))

        inventory_items = list(
            Inventory.objects.filter(
                category='Infants',
                user=main_user
            ).exclude(
                Q(item__icontains='oatmeal') |
                Q(item__icontains='formula') |
                Q(item__icontains='snack')
            ).values_list('item', flat=True).order_by('item')
        )
        permissions_context['inventory_items'] = inventory_items

        show_red_flag = any(s.not_signed_out_yesterday for s in all_students)

    except MainUser.DoesNotExist:
        filtered_students = []
        classrooms = Classroom.objects.none()
        selected_classroom = None
        other_classroom_students = Student.objects.none()
        status_filter = 'signed_in'
        show_red_flag = False

    return render(request, 'classroom.html', {
        'assigned_students': filtered_students,
        'classrooms': classrooms,
        'classroom': selected_classroom,
        'other_classroom_students': other_classroom_students,
        'status_filter': status_filter,
        'show_red_flag': show_red_flag,
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
            'parent_signature': incident.parent_signature,  # Add this line
            'id': incident.id,
        })
    except IncidentReport.DoesNotExist:
        return JsonResponse({'error': 'Not found'}, status=404)

@require_POST
@login_required
def sign_incident_report(request, report_id):
    signature = request.POST.get('signature')
    try:
        report = IncidentReport.objects.get(id=report_id)
        report.parent_signature = signature
        report.save()
        return JsonResponse({'success': True})
    except IncidentReport.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Report not found'}, status=404)
    
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
def add_feed(request):
    if request.method == 'POST':
        student_id = request.POST.get('student_id')
        timestamp = request.POST.get('timestamp')
        meal_type = request.POST.get('meal_type')
        meal_description = request.POST.get('meal_description')
        notes = request.POST.get('notes')
        ounces = request.POST.get('ounces') or None

        # Remove ounces from meal_description for formula/breast milk
        if meal_description:
            desc_lower = meal_description.lower()
            if "ifif formula" in desc_lower or "breast milk" in desc_lower:
                # Strip any trailing " - Xoz" or similar
                import re
                meal_description = re.sub(r"\s*-\s*\d+\s*oz$", "", meal_description, flags=re.IGNORECASE).strip()

        try:
            student = Student.objects.get(id=student_id)
            # Accept both "YYYY-MM-DDTHH:MM" and "YYYY-MM-DD HH:MM"
            if timestamp and "T" in timestamp:
                ts = datetime.strptime(timestamp, "%Y-%m-%dT%H:%M")
            else:
                ts = datetime.strptime(timestamp, "%Y-%m-%d %H:%M")
            ts = timezone.make_aware(ts)
            FeedRecord.objects.create(
                student=student,
                fed_by=request.user,
                timestamp=ts,
                meal_type=meal_type,
                meal_description=meal_description,
                notes=notes,
                ounces=ounces if ounces else None
            )
            return JsonResponse({'status': 'success'})
        except Exception as e:
            return JsonResponse({'status': 'error', 'message': str(e)})
    return JsonResponse({'status': 'error', 'message': 'Invalid request'})

@login_required
def feeds_for_student(request):
    student_id = request.GET.get('student_id')
    date = request.GET.get('date')
    try:
        feeds = FeedRecord.objects.filter(
            student_id=student_id,
            timestamp__date=date
        ).order_by('timestamp')
        data = [{
            'time': feed.timestamp.strftime('%I:%M %p'),
            'meal_type': feed.meal_type,
            'meal_description': feed.meal_description,
            'notes': feed.notes
        } for feed in feeds]
        return JsonResponse({'feeds': data})
    except Exception as e:
        return JsonResponse({'feeds': [], 'error': str(e)}, status=400)
    
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

    main_user = get_user_for_view(request)

    # FIX: Student FK is `main_user`, Classroom FK is `user`
    student = get_object_or_404(Student, id=student_id, main_user=main_user)
    classrooms = Classroom.objects.filter(user=main_user).order_by('name')
    previous_page = request.POST.get('previous_page', request.META.get('HTTP_REFERER', '/'))

    if request.method == 'POST':
        first_name = request.POST.get('firstName')
        last_name = request.POST.get('lastName')
        dob = request.POST.get('dob')
        code = request.POST.get('code')
        classroom_id = request.POST.get('classroom')
        profile_picture = request.FILES.get('profile_picture')
        status = request.POST.get('status')
        formula_name = request.POST.get('formula_name')

        if not first_name or not last_name:
            return render(request, 'tottimeapp/edit_student.html', {
                'student': student,
                'classrooms': classrooms,
                'error': 'First and last name are required.',
                'previous_page': previous_page,
                **permissions_context,
            })

        classroom = get_object_or_404(Classroom, id=classroom_id, user=main_user)

        student.first_name = first_name
        student.last_name = last_name

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
        student.formula_name = formula_name

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
            student = Student.objects.get(id=student_id, main_user=user)
            classroom = Classroom.objects.get(id=classroom_id, user=user) if classroom_id else student.classroom

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
                    user=user,
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
                    user=user,
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
        sign_in_time_str = request.POST.get('sign_in_time')  # "HH:MM"

        if student_id:
            student = get_object_or_404(Student, pk=student_id)
            today_date = timezone.now().date()

            if sign_in_time_str:
                try:
                    time_obj = datetime.strptime(sign_in_time_str, '%H:%M').time()
                    sign_in_datetime = timezone.make_aware(datetime.combine(today_date, time_obj))
                except ValueError:
                    return JsonResponse({'success': False, 'error': 'Invalid time format. Use HH:MM.'}, status=400)
            else:
                sign_in_datetime = timezone.now()

            # Block if there is an open record today (no sign_out_time yet)
            has_open_today = AttendanceRecord.objects.filter(
                student=student,
                sign_in_time__date=today_date,
                sign_out_time__isnull=True
            ).exists()
            if has_open_today:
                return JsonResponse(
                    {'success': False, 'error': 'Student is already signed in today and has not signed out.'},
                    status=409
                )

            assigned_user = get_user_for_view(request)

            with transaction.atomic():
                AttendanceRecord.objects.create(
                    user=assigned_user,
                    student=student,
                    sign_in_time=sign_in_datetime
                )
            return JsonResponse({'success': True})

    return JsonResponse({'success': False}, status=400)

@login_required
def delete_attendance(request):
    if request.method == 'POST':
        main_user = get_user_for_view(request)
        record_id = request.POST.get('id')
        if record_id:
            try:
                record = AttendanceRecord.objects.get(pk=record_id, user=main_user)
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
    
    # Get the appropriate main user for filtering
    main_user = get_user_for_view(request)
    
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
    
    # Filter classrooms by main user - try common FK field names
    classrooms = None
    attempts = [
        ('user', False),
        ('main_user', False),
        ('mainuser', False),
        ('owner', False),
        ('user_id', True),
        ('main_user_id', True),
        ('mainuser_id', True),
        ('owner_id', True),
    ]
    for field_name, is_id in attempts:
        try:
            if is_id:
                kwargs = {field_name: main_user.id}
            else:
                kwargs = {field_name: main_user}
            classrooms = Classroom.objects.filter(**kwargs)
            break
        except FieldError:
            classrooms = None
            continue
    
    # If no matching field found, return empty queryset
    if classrooms is None:
        logger.warning("No matching FK field found on Classroom; returning empty queryset.")
        classrooms = Classroom.objects.none()
    
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
        formula_name = request.POST.get('formula_name')  # <-- Get formula name

        try:
            main_user = get_user_for_view(request)
            classroom = Classroom.objects.get(id=classroom_id)

            # Generate a unique 4-digit code for the student
            code = None
            while not code or Student.objects.filter(main_user=main_user, code=code).exists():
                code = str(random.randint(1000, 9999))

            # Create the student
            student = Student(
                first_name=first_name,
                last_name=last_name,
                date_of_birth=date_of_birth,
                code=code,
                classroom=classroom,
                main_user=main_user,
                formula_name=formula_name  # <-- Pass formula name
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

    # Get the appropriate main user for filtering
    main_user = get_user_for_view(request)

    # Get filter parameters from the request
    classroom_id = request.GET.get('classroom')
    search_query = request.GET.get('search', '').strip()
    status_filter = request.GET.get('status', 'active')  # Default to 'active'

    # Fetch the list of students filtered by main_user, with optional additional filtering
    students = Student.objects.select_related('classroom').filter(
        main_user=main_user,
        status=status_filter
    ).order_by('last_name', 'first_name')
    
    if classroom_id:
        students = students.filter(classroom_id=classroom_id)
    if search_query:
        students = students.filter(
            Q(first_name__icontains=search_query) | Q(last_name__icontains=search_query)
        )

    # Fetch all classrooms for the filter dropdown, filtered by main_user
    classrooms = None
    attempts = [
        ('user', False),
        ('main_user', False),
        ('mainuser', False),
        ('owner', False),
        ('user_id', True),
        ('main_user_id', True),
        ('mainuser_id', True),
        ('owner_id', True),
    ]
    for field_name, is_id in attempts:
        try:
            if is_id:
                kwargs = {field_name: main_user.id}
            else:
                kwargs = {field_name: main_user}
            classrooms = Classroom.objects.filter(**kwargs)
            break
        except FieldError:
            classrooms = None
            continue
    
    if classrooms is None:
        logger.warning("No matching FK field found on Classroom; returning empty queryset.")
        classrooms = Classroom.objects.none()

    return render(request, 'tottimeapp/classroom_options.html', {
        **permissions_context,  # Include permission flags dynamically
        'students': students,  # Pass the filtered list of students to the template
        'classrooms': classrooms,  # Pass the list of classrooms for the dropdown
        'selected_classroom': classroom_id,  # Keep track of the selected classroom
        'search_query': search_query,  # Keep track of the search query
        'active_tab': 'students', 
        'selected_status': status_filter,  # Keep track of the selected status
    })

@login_required
def classroom_options_classrooms(request):
    # Check permissions for the specific page
    permissions_context = check_permissions(request)
    if isinstance(permissions_context, HttpResponseRedirect):
        return permissions_context

    # Determine which main user to show data for
    main_user = get_user_for_view(request)

    # Get filter parameters from the request
    search_query = request.GET.get('search', '').strip()

    # Base queryset with prefetches
    base_qs = Classroom.objects.prefetch_related('assignments__subuser__user', 'assignments__mainuser')

    # Try a sequence of likely FK names so we filter by the correct owner field.
    classrooms = None
    attempts = [
        ('user', False),
        ('main_user', False),
        ('mainuser', False),
        ('owner', False),
        ('user_id', True),
        ('main_user_id', True),
        ('mainuser_id', True),
        ('owner_id', True),
    ]
    for field_name, is_id in attempts:
        try:
            if is_id:
                kwargs = {field_name: main_user.id}
            else:
                kwargs = {field_name: main_user}
            classrooms = base_qs.filter(**kwargs)
            # If no FieldError was raised, we've applied a valid filter (even if it returns empty)
            break
        except FieldError:
            classrooms = None
            continue

    # If none of the attempted fields exist, avoid leaking data by returning empty queryset
    if classrooms is None:
        logger.warning("No matching FK field found on Classroom; returning empty queryset.")
        classrooms = base_qs.none()

    # Apply name search filter if provided
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
            'id': classroom.id,
            'name': classroom.name,
            'ratios': classroom.ratios,
            'color': classroom.color,
            'teachers': ', '.join(assigned_teachers) if assigned_teachers else 'No teachers currrently assigned to this classroom.',
        })

    return render(request, 'tottimeapp/classroom_options_classrooms.html', {
        **permissions_context,
        'classroom_data': classroom_data,
        'active_tab': 'classrooms',
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

    # Filter subusers based on the selected status and exclude group IDs 5 (Parent), 8 (Inactive), and 9 (CACFP Only)
    if user_status == 'active':
        subusers = subusers.exclude(group_id__id__in=[5, 8, 9])  # Exclude parents, inactive users, and CACFP Only (group ID 9)
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
        'active_tab': 'teachers',
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
        'active_tab': 'parents',
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

    # Determine current viewing main user (location/owner)
    main_user = get_user_for_view(request)

    # Fetch classrooms for this main user only
    classrooms = Classroom.objects.filter(user=main_user).order_by('name')

    # Fetch all group IDs except for "Owner" (group_id=1) and exclude group_id=5 and group_id=6
    editable_groups = Group.objects.exclude(id__in=[1, 5, 6])

    # Determine if the teacher is the main account holder (Owner)
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
        if not code or not code.isdigit() or not (1000 <= int(code) <= 9999):
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

        # Update classroom assignment (validate it belongs to current main user)
        if classroom_id:
            classroom = get_object_or_404(Classroom, id=classroom_id, user=main_user)
            ClassroomAssignment.objects.update_or_create(
                mainuser=teacher,
                defaults={'classroom': classroom}
            )

        # Update group ID if not the Owner
        if not is_owner and group_id:
            try:
                group = Group.objects.get(id=group_id)
                subuser.group_id = group
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

def assign_rules_to_week(user, days_count=5, used_main_recipes=None, estimated_daily_students=1, force_ignore_inventory=False):
    """
    Process all rules at the WEEK level and determine which recipe appears on which day in which meal period.
    
    This implements the day-based rule system where:
    - weekly_qty=5 means "appears on 5 different DAYS" (not 5 total appearances)
    - For each day needing a rule:
      1. Randomly pick a recipe with that rule
      2. Check recipe's populate_* flags
      3. Randomly pick an eligible meal period for that recipe
      4. Assign it to that day + meal period
    
    Args:
        user: User object
        days_count: Number of days in the week (default 5)
        used_main_recipes: Set of recipe IDs already used in main dish rows (for deduplication)
    
    Returns:
        tuple: (assignments_dict, promoted_recipe_ids, used_main_recipes)
        - assignments_dict = {
            'breakfast': {day_idx: [recipe, ...], ...},
            'am_snack': {day_idx: [recipe, ...], ...},
            'lunch': {day_idx: [recipe, ...], ...},
            'pm_snack': {day_idx: [recipe, ...], ...}
          }
        - promoted_recipe_ids = set of recipe IDs that were promoted from standalone
        - used_main_recipes = updated set of recipe IDs used in main dish rows
    """
    # Track recipes that are promoted from standalone to non-standalone
    promoted_recipe_ids = set()
    
    # Initialize used_main_recipes if not provided
    if used_main_recipes is None:
        used_main_recipes = set()
    
    # Helper to check if recipe has sufficient inventory
    def has_recipe_name_inventory_fallback(recipe):
        if not recipe or not getattr(recipe, 'name', None):
            return False

        # Exact match first
        item = Inventory.objects.filter(user=user, item=recipe.name).first()

        # Fallback: normalized label match for display variants
        # (e.g., parentheses differences like "1% Milk" vs "1% Milk (unflavored)").
        if not item:
            def _norm_label(text):
                return re.sub(r'[^a-z0-9]+', '', re.sub(r'\([^)]*\)', '', str(text or '').casefold()))

            target_norm = _norm_label(recipe.name)
            if target_norm:
                for candidate in Inventory.objects.filter(user=user):
                    if _norm_label(candidate.item) == target_norm:
                        item = candidate
                        break

        if not item:
            return False
        conv_to_base = item.conversion_to_base or 1
        inventory_units = item.total_quantity or item.quantity or 0
        available_base = inventory_units * conv_to_base
        portion_per_student = item.unit_size if item.unit_size and item.unit_size > 0 else 1
        required_base = portion_per_student * estimated_daily_students
        return available_base >= required_base

    def has_sufficient_inventory(recipe):
        """Check if recipe has enough inventory for all ingredients.
        Returns True if recipe.ignore_inventory is True or all ingredients are sufficient.
        Returns False if any ingredient is insufficient."""
        try:
            # Global override from generate_full_menu: skip inventory checks entirely
            if force_ignore_inventory:
                return True

            # Check if recipe should ignore inventory tracking
            if getattr(recipe, 'ignore_inventory', False):
                return True
            
            # Get all ingredients for this recipe
            ingredients_list = list(recipe.ingredients.all().select_related('ingredient'))
            if not ingredients_list:
                return has_recipe_name_inventory_fallback(recipe)
            
            # Check each ingredient
            has_checkable_ingredient = False
            for recipe_ing in ingredients_list:
                if not recipe_ing.ingredient:
                    continue

                # Interpret recipe quantity in the ingredient's base unit (smallest unit)
                per_portion_base = recipe_ing.quantity if recipe_ing.quantity else 0
                if per_portion_base <= 0:
                    continue

                has_checkable_ingredient = True

                conv_to_base = recipe_ing.ingredient.conversion_to_base or 1

                # Prefer total_quantity, but fall back to quantity when total_quantity is empty/zero.
                inventory_units = recipe_ing.ingredient.total_quantity or recipe_ing.ingredient.quantity or 0
                available_base = inventory_units * conv_to_base

                # Required amount in base units for all students
                required_base = per_portion_base * estimated_daily_students
                if available_base < required_base:
                    return False

            if not has_checkable_ingredient:
                return has_recipe_name_inventory_fallback(recipe)
            
            # All ingredients are sufficient
            return True
        except Exception as e:
            pass  # print(f"Error checking inventory for '{recipe.name}': {str(e)}")
            return True
    
    # Helper to get and format ingredient list for a recipe
    def get_recipe_ingredients_debug(recipe):
        """Get ingredients for a recipe and return formatted string with inventory availability"""
        try:
            ingredients_list = list(recipe.ingredients.all().select_related('ingredient'))
            if not ingredients_list:
                return "No ingredients linked (using recipe-name inventory fallback)"
            
            ingredient_details = []
            has_insufficient = False
            
            for recipe_ing in ingredients_list:
                if recipe_ing.ingredient:
                    per_portion_base = recipe_ing.quantity if recipe_ing.quantity else 0
                    conv_to_base = recipe_ing.ingredient.conversion_to_base or 1
                    inventory_units = recipe_ing.ingredient.total_quantity or recipe_ing.ingredient.quantity or 0
                    available_base = inventory_units * conv_to_base
                    required_base = per_portion_base * estimated_daily_students
                    units = recipe_ing.ingredient.base_unit or 'units'
                    
                    # Check if there's enough inventory
                    if required_base > 0:
                        if available_base >= required_base:
                            status = "✓"  # Sufficient
                        else:
                            status = "✗"  # Insufficient
                            has_insufficient = True
                    else:
                        status = "?"  # Unknown requirement
                    
                    ingredient_details.append(
                        f"{recipe_ing.ingredient.item} "
                        f"[per-portion: {per_portion_base} {units}, "
                        f"students: {estimated_daily_students}, "
                        f"requires: {required_base} {units}, "
                        f"current qty: {available_base} {units}] {status}"
                    )
                else:
                    ingredient_details.append("(Unlinked ingredient)")
            
            result = ", ".join(ingredient_details)
            if has_insufficient:
                result = "⚠️ INSUFFICIENT INVENTORY - " + result
            
            return result
        except Exception as e:
            return f"Error fetching ingredients: {str(e)}"
    
    # Get all recipes that have at least one component rule with weekly_qty
    all_recipes = Recipe.objects.filter(user=user, archive=False)

    def get_all_rules_for_recipe(r):
        """Return a set of Rule objects attached via any component field."""
        rule_objs = set()
        for fk_name in (
            'grain_rule', 'fruit_rule', 'veg_rule',
            'meat_rule', 'fluid_rule', 'addfood_rule'
        ):
            rule_obj = getattr(r, fk_name, None)
            if rule_obj and getattr(rule_obj, 'weekly_qty', None):
                rule_objs.add(rule_obj)
        return rule_objs

    # Determine which meal periods the user actually serves (has non-standalone recipes for)
    # This prevents rule assignments to periods the user doesn't serve
    user_serves_breakfast = all_recipes.filter(
        populate_breakfast=True,
        standalone=False
    ).exists() or all_recipes.filter(
        recipe_type='breakfast',
        standalone=False
    ).exists()
    
    user_serves_am_snack = all_recipes.filter(
        populate_am_snack=True,
        recipe_type__in=['am_snack', 'am_pm_snack'],
        standalone=False
    ).exists()
    
    user_serves_lunch = all_recipes.filter(
        populate_lunch=True,
        standalone=False
    ).exists() or all_recipes.filter(
        recipe_type='lunch',
        standalone=False
    ).exists()
    
    user_serves_pm_snack = all_recipes.filter(
        populate_pm_snack=True,
        recipe_type__in=['pm_snack', 'am_pm_snack'],
        standalone=False
    ).exists()
    
    pass  # print(f"🍽️  User meal period availability:")
    pass  # print(f"   Breakfast: {'✓' if user_serves_breakfast else '✗'}")
    pass  # print(f"   AM Snack: {'✓' if user_serves_am_snack else '✗'}")
    pass  # print(f"   Lunch: {'✓' if user_serves_lunch else '✗'}")
    pass  # print(f"   PM Snack: {'✓' if user_serves_pm_snack else '✗'}")

    # Group recipes by each rule they reference
    rule_to_recipes = {}
    for recipe in all_recipes:
        for rule_obj in get_all_rules_for_recipe(recipe):
            rule_id = rule_obj.id
            if rule_id not in rule_to_recipes:
                rule_to_recipes[rule_id] = {
                    'rule': rule_obj,
                    'recipes': []
                }
            rule_to_recipes[rule_id]['recipes'].append(recipe)
    
    # Track which days have been assigned for each rule
    rule_days_assigned = {rule_id: set() for rule_id in rule_to_recipes.keys()}
    
    # Final assignments: {meal_period: {day_idx: [recipe1, recipe2, ...]}}
    # Multiple rules can assign to the same day/period (e.g., veg + fruit both in lunch)
    assignments = {
        'breakfast': {},
        'am_snack': {},
        'lunch': {},
        'pm_snack': {}
    }
    
    # Process each rule
    for rule_id, rule_data in rule_to_recipes.items():
        rule = rule_data['rule']
        recipes = rule_data['recipes']
        weekly_qty = rule.weekly_qty
        daily = rule.daily
        
        pass  # print(f"DEBUG: Processing rule '{rule.rule}' (weekly_qty={weekly_qty}, daily={daily})")
        pass  # print(f"  Available recipes: {[r.name for r in recipes]}")
        
        # Separate standalone and non-standalone recipes
        non_standalone_recipes = [r for r in recipes if not getattr(r, 'standalone', False)]
        standalone_recipes = [r for r in recipes if getattr(r, 'standalone', False)]
        
        # If a rule has ONLY standalone recipes, use them for rule assignment
        # (e.g., Toast/Bread should fill breakfast bread row to satisfy Whole Grain rule)
        # This is different from Phase 3 standalone placement which only fills when main content exists
        if not non_standalone_recipes and standalone_recipes:
            pass  # print(f"  ℹ️  Rule '{rule.rule}' has only standalone recipes - will use for main row placement")
            non_standalone_recipes = standalone_recipes  # Use standalones as main recipes for this rule
        elif not non_standalone_recipes:
            pass  # print(f"  ⚠️  Rule '{rule.rule}' has no recipes - skipping")
            continue
        
        # Determine which days need this rule
        if daily:
            # Daily rules: appear sequentially starting from day 0
            primary_days = list(range(min(weekly_qty, days_count)))
        else:
            # Non-daily rules: randomly select days
            primary_days = random.sample(range(days_count), min(weekly_qty, days_count))
        
        # Create a fallback list of all days for retry logic
        all_days = list(range(days_count))
        random.shuffle(all_days)
        
        # Track how many days we still need to assign for this rule
        assignments_needed = min(weekly_qty, days_count)
        assignments_made = 0
        
        # Try primary days first, then fallback to any available day
        days_to_try = primary_days + [d for d in all_days if d not in primary_days]
        
        for day_idx in days_to_try:
            if assignments_made >= assignments_needed:
                break  # Rule is satisfied
                
            if day_idx in rule_days_assigned[rule_id]:
                continue  # Already assigned this rule to this day
            
            # Try non-standalone recipes first (filter by inventory first)
            shuffled_recipes = [r for r in non_standalone_recipes if has_sufficient_inventory(r)]
            random.shuffle(shuffled_recipes)
            
            # Try each recipe until we find one with an eligible meal period
            placed = False
            for recipe in shuffled_recipes:
                # DEDUPLICATION: Skip if this recipe has already been used in a main dish row
                if recipe.id in used_main_recipes:
                    pass  # print(f"  Skipping '{recipe.name}' - already used in main dish row this week")
                    continue
                
                # Determine which meal periods this recipe can go into
                eligible_periods = []

                # Breakfast: any recipe explicitly flagged for breakfast OR with recipe_type='breakfast'
                # ONLY if user serves breakfast
                if user_serves_breakfast and (recipe.populate_breakfast or recipe.recipe_type == 'breakfast'):
                    eligible_periods.append('breakfast')

                # AM snack: only AM-specific, shared AM/PM, or whole-grain
                # ONLY if user serves AM snack
                if user_serves_am_snack and (recipe.populate_am_snack or recipe.recipe_type in ['am_snack', 'am_pm_snack']) and recipe.recipe_type in ['am_snack', 'am_pm_snack', 'whole_grain']:
                    eligible_periods.append('am_snack')

                # Lunch: any recipe explicitly flagged for lunch OR with recipe_type='lunch'
                # ONLY if user serves lunch
                if user_serves_lunch and (recipe.populate_lunch or recipe.recipe_type == 'lunch'):
                    eligible_periods.append('lunch')

                # PM snack: only PM-specific, shared AM/PM, or whole-grain
                # ONLY if user serves PM snack
                if user_serves_pm_snack and (recipe.populate_pm_snack or recipe.recipe_type in ['pm_snack', 'am_pm_snack']) and recipe.recipe_type in ['pm_snack', 'am_pm_snack', 'whole_grain']:
                    eligible_periods.append('pm_snack')
                
                if not eligible_periods:
                    continue
                
                random.shuffle(eligible_periods)
                for period in eligible_periods:
                    # Allow multiple rules to assign to same day/period (they'll go to different fields)
                    if day_idx not in assignments[period]:
                        assignments[period][day_idx] = []
                    assignments[period][day_idx].append(recipe)
                    rule_days_assigned[rule_id].add(day_idx)
                    
                    # Track this recipe as used in main dish row (will be placed in bread/bread2/meal_name/bread3)
                    used_main_recipes.add(recipe.id)
                    pass  # print(f"  Assigned '{recipe.name}' to {period} on day {day_idx} (tracked as used)")
                    
                    # DEBUG: Show ingredients for this recipe
                    ingredients_str = get_recipe_ingredients_debug(recipe)
                    print(f"    🥘 INGREDIENTS: {ingredients_str}")
                    
                    placed = True
                    assignments_made += 1
                    break
                
                if placed:
                    break
            
            # If non-standalone didn't work, try remaining standalone recipes (filter by inventory first)
            if not placed and standalone_recipes:
                shuffled_standalone = [r for r in standalone_recipes if has_sufficient_inventory(r)]
                random.shuffle(shuffled_standalone)
                
                for recipe in shuffled_standalone:
                    # DEDUPLICATION: Skip if this recipe has already been used in a main dish row
                    if recipe.id in used_main_recipes:
                        pass  # print(f"  Skipping standalone '{recipe.name}' - already used in main dish row this week")
                        continue
                    
                    eligible_periods = []
                    if user_serves_breakfast and (recipe.populate_breakfast or recipe.recipe_type == 'breakfast'):
                        eligible_periods.append('breakfast')
                    if user_serves_am_snack and (recipe.populate_am_snack or recipe.recipe_type in ['am_snack', 'am_pm_snack']) and recipe.recipe_type in ['am_snack', 'am_pm_snack', 'whole_grain']:
                        eligible_periods.append('am_snack')
                    if user_serves_lunch and (recipe.populate_lunch or recipe.recipe_type == 'lunch'):
                        eligible_periods.append('lunch')
                    if user_serves_pm_snack and (recipe.populate_pm_snack or recipe.recipe_type in ['pm_snack', 'am_pm_snack']) and recipe.recipe_type in ['pm_snack', 'am_pm_snack', 'whole_grain']:
                        eligible_periods.append('pm_snack')
                    
                    if not eligible_periods:
                        continue
                    
                    random.shuffle(eligible_periods)
                    for period in eligible_periods:
                        # Allow multiple rules to assign to same day/period
                        if day_idx not in assignments[period]:
                            assignments[period][day_idx] = []
                        assignments[period][day_idx].append(recipe)
                        rule_days_assigned[rule_id].add(day_idx)
                        
                        # Track this recipe as used in main dish row
                        used_main_recipes.add(recipe.id)
                        pass  # print(f"  Assigned standalone '{recipe.name}' to {period} on day {day_idx} (tracked as used)")
                        
                        # DEBUG: Show ingredients for this recipe
                        ingredients_str = get_recipe_ingredients_debug(recipe)
                        pass  # print(f"    🥘 INGREDIENTS: {ingredients_str}")
                        
                        placed = True
                        assignments_made += 1
                        break
                    
                    if placed:
                        break
            
            # If standalone recipes didn't work, try side dishes from inventory with this rule
            if not placed:
                # Query side dishes that have this rule and are in stock
                side_dishes = list(Inventory.objects.filter(
                    user=user,
                    rule_id=rule_id,
                    is_side_dish=True,
                    total_quantity__gt=0  # Only in-stock items
                ))
                
                if side_dishes:
                    random.shuffle(side_dishes)
                    pass  # print(f"  Trying {len(side_dishes)} side dish(es) from inventory for rule '{rule.rule}'")
                    
                    for side_dish in side_dishes:
                        # Side dishes can be placed in any meal period the user serves
                        # Determine eligible periods based on meal_period field, user's served periods, AND populate_* permissions
                        eligible_periods = []
                        
                        if user_serves_breakfast and side_dish.meal_period in ['all', 'breakfast'] and side_dish.populate_breakfast:
                            eligible_periods.append('breakfast')
                        if user_serves_am_snack and side_dish.meal_period in ['all', 'am_snack'] and side_dish.populate_am_snack:
                            eligible_periods.append('am_snack')
                        if user_serves_lunch and side_dish.meal_period in ['all', 'lunch'] and side_dish.populate_lunch:
                            eligible_periods.append('lunch')
                        if user_serves_pm_snack and side_dish.meal_period in ['all', 'pm_snack'] and side_dish.populate_pm_snack:
                            eligible_periods.append('pm_snack')
                        
                        if not eligible_periods:
                            continue
                        
                        random.shuffle(eligible_periods)
                        for period in eligible_periods:
                            # Create a pseudo-recipe object for the side dish to maintain consistency
                            # This allows the rest of the code to treat it like a recipe
                            class SideDishRecipe:
                                def __init__(self, side_dish):
                                    self.name = side_dish.item
                                    self.id = f"side_dish_{side_dish.id}"  # String ID to differentiate
                                    self.is_side_dish = True
                                    self.inventory_item = side_dish
                                    self.standalone = True
                                    self.ignore_inventory = True  # Already checked quantity above
                                    # Add recipe_type based on rule or default to 'vegetable'
                                    # Side dishes are typically fruits/vegetables
                                    self.recipe_type = 'vegetable'  # Default
                                    # Add rule attributes (all None except the one that matched)
                                    self.grain_rule = None
                                    self.fruit_rule = None
                                    self.veg_rule = None
                                    self.meat_rule = None
                                    self.fluid_rule = None
                                    self.addfood_rule = None
                                    # Mirror Django FK *_id attributes used in placement logic.
                                    self.grain_rule_id = None
                                    self.fruit_rule_id = None
                                    self.veg_rule_id = None
                                    self.meat_rule_id = None
                                    self.fluid_rule_id = None
                                    self.addfood_rule_id = None
                                    # Set the matching rule based on rule_id
                                    if side_dish.rule:
                                        # Determine which type of rule this is by checking rule name or default to veg
                                        rule_name_lower = side_dish.rule.rule.lower()
                                        if 'fruit' in rule_name_lower or 'berry' in rule_name_lower:
                                            self.fruit_rule = side_dish.rule
                                            self.fruit_rule_id = side_dish.rule.id
                                            self.recipe_type = 'fruit'
                                        elif 'veg' in rule_name_lower or 'vegetable' in rule_name_lower:
                                            self.veg_rule = side_dish.rule
                                            self.veg_rule_id = side_dish.rule.id
                                            self.recipe_type = 'vegetable'
                                        elif 'grain' in rule_name_lower or 'whole grain' in rule_name_lower:
                                            self.grain_rule = side_dish.rule
                                            self.grain_rule_id = side_dish.rule.id
                                            self.recipe_type = 'whole_grain'
                                        else:
                                            # Default to veg_rule for side dishes
                                            self.veg_rule = side_dish.rule
                                            self.veg_rule_id = side_dish.rule.id
                                    # Add other attributes that might be accessed
                                    self.addfood = None
                                    self.grain = None
                                    self.meat = None
                                    self.fluid = None
                                    self.fruit = None
                                    self.veg = None
                                    # Use actual populate permissions from inventory item
                                    self.populate_breakfast = side_dish.populate_breakfast
                                    self.populate_am_snack = side_dish.populate_am_snack
                                    self.populate_lunch = side_dish.populate_lunch
                                    self.populate_pm_snack = side_dish.populate_pm_snack
                            
                            side_dish_recipe = SideDishRecipe(side_dish)
                            
                            # Allow multiple rules to assign to same day/period
                            if day_idx not in assignments[period]:
                                assignments[period][day_idx] = []
                            assignments[period][day_idx].append(side_dish_recipe)
                            rule_days_assigned[rule_id].add(day_idx)
                            
                            # Track this side dish as used (using string ID)
                            used_main_recipes.add(side_dish_recipe.id)
                            pass  # print(f"  Assigned side dish '{side_dish.item}' to {period} on day {day_idx} (tracked as used)")
                            pass  # print(f"    🥗 SIDE DISH: {side_dish.item} [available: {side_dish.total_quantity} {side_dish.units or 'units'}]")
                            
                            placed = True
                            assignments_made += 1
                            break
                        
                        if placed:
                            break
        
        # Check if rule was fully satisfied
        if assignments_made < assignments_needed:
            pass  # print(f"  ❌ WARNING: Only placed {assignments_made}/{assignments_needed} assignments for rule '{rule.rule}'")
        else:
            pass  # print(f"  ✅ Rule '{rule.rule}' SATISFIED: {assignments_made}/{assignments_needed} assignments made")
    
    return assignments, promoted_recipe_ids, used_main_recipes


def select_recipes_with_rules(recipes, days_count=5, rule_tracker=None):
    """Legacy helper used by older generate_*_menu views.

    It selects one recipe per day, trying to honor any attached Rule.weekly_qty
    by spreading rule-based recipes across the week, and then filling remaining
    days with non-rule recipes. This keeps those endpoints working without
    impacting the newer generate_full_menu flow.
    """
    # Ensure we always return a fixed-length list, even with no recipes.
    if not recipes:
        return [None] * days_count

    selected_recipes = [None] * days_count

    # Partition recipes into those with a component rule that has weekly_qty
    # and those without such a rule.
    rule_recipes = {}
    no_rule_recipes = []

    for r in recipes:
        # Check all component rule fields
        has_rule = False
        for fk_name in ('grain_rule', 'fruit_rule', 'veg_rule', 'meat_rule', 'fluid_rule', 'addfood_rule'):
            rule_obj = getattr(r, fk_name, None)
            weekly_qty = getattr(rule_obj, "weekly_qty", None) if rule_obj else None
            if rule_obj and weekly_qty:
                rule_recipes.setdefault(rule_obj.id, []).append(r)
                has_rule = True
                break  # Only need to find one rule per recipe for this legacy function
        
        if not has_rule:
            no_rule_recipes.append(r)

    # Randomize available day indices so rule-based placements are spread.
    available_days = list(range(days_count))
    random.shuffle(available_days)

    # First, place recipes that are tied to rules with a weekly quantity.
    for rule_id, r_list in rule_recipes.items():
        if not r_list:
            continue
        
        # Get weekly_qty from the first recipe's component rules
        weekly_qty = 0
        for r in r_list:
            for fk_name in ('grain_rule', 'fruit_rule', 'veg_rule', 'meat_rule', 'fluid_rule', 'addfood_rule'):
                rule_obj = getattr(r, fk_name, None)
                if rule_obj and rule_obj.id == rule_id:
                    weekly_qty = getattr(rule_obj, "weekly_qty", 0) or 0
                    break
            if weekly_qty > 0:
                break
        
        if weekly_qty <= 0:
            continue

        for _ in range(min(weekly_qty, days_count)):
            if not available_days:
                break
            day_idx = available_days.pop()
            selected_recipes[day_idx] = random.choice(r_list)

            # Optionally track usage in a simple counter dict, if provided.
            if isinstance(rule_tracker, dict):
                rule_tracker[rule_id] = rule_tracker.get(rule_id, 0) + 1

    # Fill any remaining unassigned days with non-rule recipes if available,
    # otherwise fall back to the full recipe list.
    fallback_pool = no_rule_recipes or recipes
    if fallback_pool:
        for day_idx in range(days_count):
            if selected_recipes[day_idx] is None:
                selected_recipes[day_idx] = random.choice(fallback_pool)

    return selected_recipes


def select_recipes_for_meal_period(recipes, meal_period_name, days_count, pre_assignments):
    """
    Select recipes for a specific meal period based on pre-assigned day requirements.
    
    Args:
        recipes: List of Recipe objects eligible for this meal period
        meal_period_name: 'breakfast', 'am_snack', 'lunch', or 'pm_snack'
        days_count: Number of days (usually 5)
        pre_assignments: dict {day_idx: recipe} - recipes already assigned by rules
    
    Returns:
        List of selected recipes (one per day, may contain None)
    """
    selected_recipes = [None] * days_count
    
    # First, apply pre-assignments from rules
    for day_idx, recipe in pre_assignments.items():
        selected_recipes[day_idx] = recipe
    
    # Fill remaining days with recipes without any component rule that has weekly_qty
    def has_any_weekly_rule(r):
        for fk_name in (
            'grain_rule', 'fruit_rule', 'veg_rule',
            'meat_rule', 'fluid_rule', 'addfood_rule'
        ):
            rule_obj = getattr(r, fk_name, None)
            if rule_obj and getattr(rule_obj, 'weekly_qty', None):
                return True
        return False

    recipes_without_rules = [r for r in recipes if not has_any_weekly_rule(r)]
    for day_idx in range(days_count):
        if selected_recipes[day_idx] is None and recipes_without_rules:
            selected_recipes[day_idx] = random.choice(recipes_without_rules)
    
    return selected_recipes

def select_meals_for_days(recipes, user):
    """Select available lunch recipes per day, placing them based on recipe_type."""
    days_of_week = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]
    menu_data = {}

    # Cache inventory snapshot by Inventory.id
    inventory = {item.id: item for item in Inventory.objects.filter(user=user)}

    # Initialize empty menu data
    for day in days_of_week:
        menu_data[day] = {
            'meal_name': '',
            'grain': '',
            'meat_alternate': '',
            'vegetable': '',
            'fruit3': ''
        }

    # Use rule-based selection to get recipes for each day
    selected_recipes = select_recipes_with_rules(recipes, days_count=5)
    
    for day_idx, day in enumerate(days_of_week):
        selected_meal = selected_recipes[day_idx]
        
        # Verify ingredient availability for Monday/Tuesday
        if selected_meal and day in ["Monday", "Tuesday"]:
            if not check_ingredients_availability(selected_meal, user, inventory, exclude_zero_quantity=True):
                # Try to find an alternative
                available_meals = [
                    r for r in recipes
                    if r != selected_meal and check_ingredients_availability(r, user, inventory, exclude_zero_quantity=True)
                ]
                if available_meals:
                    selected_meal = random.choice(available_meals)
                else:
                    selected_meal = None
        
        # Subtract ingredients from inventory
        if selected_meal:
            subtract_ingredients_from_inventory(selected_meal, inventory)
            
            # Place recipe based on its type
            recipe_type = selected_meal.recipe_type
            
            if recipe_type == 'lunch':
                # Main lunch dish
                menu_data[day]['meal_name'] = selected_meal.name
                menu_data[day]['grain'] = selected_meal.grain or ""
                menu_data[day]['meat_alternate'] = selected_meal.meat_alternate or ""
            elif recipe_type == 'whole_grain':
                # Goes in grain row
                if not menu_data[day]['grain']:
                    menu_data[day]['grain'] = selected_meal.name
            elif recipe_type == 'vegetable':
                # Goes in vegetable row
                if not menu_data[day]['vegetable']:
                    menu_data[day]['vegetable'] = selected_meal.name
            elif recipe_type == 'fruit':
                # Goes in fruit row
                if not menu_data[day]['fruit3']:
                    menu_data[day]['fruit3'] = selected_meal.name
    
    # Fill empty meal_name cells with default
    for day in days_of_week:
        if not menu_data[day]['meal_name']:
            menu_data[day]['meal_name'] = "No available meal"

    return menu_data

def check_ingredients_availability(recipe, user, inventory, exclude_zero_quantity=False):
    """Check if the ingredients for a recipe are available in the inventory."""
    ingredients = get_recipe_ingredients(recipe)
    
    if not ingredients:
        return True
    
    for idx, (ingredient, qty) in enumerate(ingredients, 1):
        if ingredient:
            item = inventory.get(ingredient.id, None)
            if item:
                if exclude_zero_quantity and item.quantity == 0:
                    return False
                if item.quantity < (qty or 0):
                    return False
            else:
                return False
    
    return True

def subtract_ingredients_from_inventory(recipe, inventory):
    """Subtract the ingredients used in a recipe from the inventory."""
    ingredients = get_recipe_ingredients(recipe)
    
    for ingredient, qty in ingredients:
        if ingredient:
            item = inventory.get(ingredient.id, None)
            if item:
                item.quantity -= (qty or 0)
                item.save()

def get_filtered_recipes(user, model, recent_days=14):
    """Filter recipes not used in the last `recent_days` days."""
    all_recipes = list(model.objects.filter(user=user))
    cutoff_date = timezone.now() - timedelta(days=recent_days)
    recent_recipes = model.objects.filter(user=user, last_used__gte=cutoff_date)
    filtered = [recipe for recipe in all_recipes if recipe not in recent_recipes]
    
    # If all recipes are filtered out (e.g., newly imported recipes all have same timestamp),
    # return all recipes to avoid empty menu
    if len(filtered) == 0 and len(all_recipes) > 0:
        return all_recipes
    
    return filtered

@login_required
def generate_full_menu(request):
    """
    Generate ALL meals (breakfast, AM snack, lunch, PM snack) in a single request.
    
    CORRECT FLOW:
    1. Assign NON-standalone recipes with rules to specific days/periods
    2. Generate menu normally, filling remaining slots randomly
    3. Count rule satisfaction in final menu
    4. Add standalone recipes to Additional Food ONLY if rule count < weekly_qty
    """
    user = get_user_for_view(request)
    days_of_week = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]
    
    # Get the week start date (Monday) for the menu being generated
    # This can come from the request or default to next Monday
    week_start_str = request.POST.get('week_start') or request.GET.get('week_start')
    if week_start_str:
        try:
            week_start_date = datetime.strptime(week_start_str, '%Y-%m-%d').date()
        except ValueError:
            # If invalid format, compute next Monday from today
            from datetime import date, timedelta
            today = date.today()
            days_until_monday = (7 - today.weekday()) % 7
            if days_until_monday == 0:
                days_until_monday = 7  # If today is Monday, get next Monday
            week_start_date = today + timedelta(days=days_until_monday)
    else:
        # No week provided, compute next Monday from today
        from datetime import date, timedelta
        today = date.today()
        days_until_monday = (7 - today.weekday()) % 7
        if days_until_monday == 0:
            days_until_monday = 7  # If today is Monday, get next Monday
        week_start_date = today + timedelta(days=days_until_monday)
    
    pass  # print(f"📅 Generating menu for week starting: {week_start_date}")
    
    # Get estimated daily students for scaling ingredient quantities (per-portion * students)
    estimated_daily_students_raw = request.POST.get('estimated_daily_students')
    try:
        estimated_daily_students = int(estimated_daily_students_raw) if estimated_daily_students_raw is not None else 1
        if estimated_daily_students <= 0:
            estimated_daily_students = 1
    except (TypeError, ValueError):
        estimated_daily_students = 1

    # Check if user wants to ignore inventory constraints
    # This is set when user confirms they want to continue despite out-of-stock warnings
    force_ignore_inventory = request.POST.get('ignore_inventory') == 'true'

    # High-level generation debug summary
    print(
        f"[MENU DEBUG] Starting full menu generation: "
        f"week_start={week_start_date}, "
        f"estimated_daily_students={estimated_daily_students}, "
        f"ignore_inventory={force_ignore_inventory}"
    )
    
    # Calculate 2-week cooldown window for lunch main-dish filtering.
    from datetime import timedelta
    two_weeks_before = week_start_date - timedelta(days=14)
    two_weeks_after = week_start_date + timedelta(days=14)
    
    # Initialize tracking for main dish recipe deduplication across the week
    used_main_recipes = set()

    # Build similarity exclusion helper: returns IDs of all recipes sharing a group with the given recipe
    _similarity_groups = list(
        RecipeSimilarityGroup.objects
        .filter(user=user)
        .prefetch_related('recipes')
    )
    def _get_similarity_excluded_ids(recipe_id):
        """Return IDs of all recipes that cannot appear in the same week as recipe_id."""
        excluded = set()
        for group in _similarity_groups:
            member_ids = {r.id for r in group.recipes.all()}
            if recipe_id in member_ids:
                excluded |= member_ids - {recipe_id}
        return excluded

    similarity_excluded_ids = set()  # Updated as recipes are selected
    
    # STEP 1: Assign NON-standalone recipes with rules (standalones are skipped)
    rule_assignments, promoted_recipe_ids, used_main_recipes = assign_rules_to_week(
        user,
        days_count=5,
        used_main_recipes=used_main_recipes,
        estimated_daily_students=estimated_daily_students,
        force_ignore_inventory=force_ignore_inventory,
    )
    
    # STEP 1.5: Query fluid_rule recipes for special mandatory daily placement
    # Fluid rule is special: weekly_qty=10 means minimum 10 instances (5 breakfast + 5 lunch)
    # Breakfast/Lunch: MUST appear every day
    # AM/PM Snack: ONLY if main snack exists AND fluid row is blank
    fluid_rule_recipes = list(Recipe.objects.filter(
        user=user,
        archive=False,
        fluid_rule__isnull=False,
        standalone=True  # Fluid recipes are typically standalone
    ).select_related('fluid_rule'))
    
    pass  # print(f"DEBUG: Found {len(fluid_rule_recipes)} fluid_rule recipes for daily placement")
    if fluid_rule_recipes:
        pass  # print(f"  Fluid recipes: {[r.name for r in fluid_rule_recipes]}")
    
    # Helper to check if recipe has any weekly rule
    def has_weekly_rule(recipe):
        return any([
            (recipe.grain_rule and recipe.grain_rule.weekly_qty),
            (recipe.fruit_rule and recipe.fruit_rule.weekly_qty),
            (recipe.veg_rule and recipe.veg_rule.weekly_qty),
            (recipe.meat_rule and recipe.meat_rule.weekly_qty),
            (recipe.fluid_rule and recipe.fluid_rule.weekly_qty),
            (recipe.addfood_rule and recipe.addfood_rule.weekly_qty),
        ])

    # Choose rule id for recipe title cells ONLY when an ingredient with a
    # rule matches the recipe title (e.g., Cheerios recipe title -> Cheerios ingredient rule).
    def get_recipe_title_rule_id(recipe):
        if not recipe or not recipe.name:
            return None

        def _norm(text):
            return re.sub(r'\s+', ' ', str(text or '').strip().casefold())

        def _loosely_same(a, b):
            na, nb = _norm(a), _norm(b)
            if not na or not nb:
                return False
            return na == nb

        recipe_name = recipe.name
        component_rule_pairs = [
            (recipe.grain, recipe.grain_rule_id),
            (recipe.fruit, recipe.fruit_rule_id),
            (recipe.veg, recipe.veg_rule_id),
            (recipe.fluid, recipe.fluid_rule_id),
            (recipe.meat, recipe.meat_rule_id),
            (recipe.addfood, recipe.addfood_rule_id),
        ]
        for component_value, rule_id in component_rule_pairs:
            if rule_id and _loosely_same(component_value, recipe_name):
                return rule_id

        for ing, _qty in get_recipe_ingredients(recipe):
            if not ing:
                continue
            if getattr(ing, 'rule_id', None) and _loosely_same(getattr(ing, 'item', ''), recipe_name):
                return ing.rule_id

    def _normalized_name(value):
        return re.sub(r'\s+', ' ', str(value or '').strip().casefold())

    def _is_same_as_recipe_name(recipe, component_value):
        if not recipe or not getattr(recipe, 'name', None) or not component_value:
            return False
        return _normalized_name(component_value) == _normalized_name(recipe.name)

    def _first_distinct_component(recipe, *component_values):
        for component_value in component_values:
            if component_value and not _is_same_as_recipe_name(recipe, component_value):
                return component_value
        return ''

    def _first_distinct_component_with_rule(recipe, component_rule_pairs):
        for component_value, rule_id in component_rule_pairs:
            if component_value and not _is_same_as_recipe_name(recipe, component_value):
                return component_value, rule_id
        return '', None

        return None
    
    # Helper to check if recipe has sufficient inventory
    def has_recipe_name_inventory_fallback(recipe):
        if not recipe or not getattr(recipe, 'name', None):
            return False

        # Exact match first
        item = Inventory.objects.filter(user=user, item=recipe.name).first()

        # Fallback: normalized label match for display variants
        # (e.g., parentheses differences like "1% Milk" vs "1% Milk (unflavored)").
        if not item:
            def _norm_label(text):
                return re.sub(r'[^a-z0-9]+', '', re.sub(r'\([^)]*\)', '', str(text or '').casefold()))

            target_norm = _norm_label(recipe.name)
            if target_norm:
                for candidate in Inventory.objects.filter(user=user):
                    if _norm_label(candidate.item) == target_norm:
                        item = candidate
                        break

        if not item:
            return False
        conv_to_base = item.conversion_to_base or 1
        inventory_units = item.total_quantity or item.quantity or 0
        available_base = inventory_units * conv_to_base
        portion_per_student = item.unit_size if item.unit_size and item.unit_size > 0 else 1
        required_base = portion_per_student * estimated_daily_students
        return available_base >= required_base

    def has_sufficient_inventory(recipe):
        """Check if recipe has enough inventory for all ingredients.
        Returns True if recipe.ignore_inventory is True or all ingredients are sufficient.
        Returns False if any ingredient is insufficient."""
        try:
            # Check if global inventory override is enabled (user confirmed to ignore inventory)
            if force_ignore_inventory:
                return True
            
            # Check if recipe should ignore inventory tracking
            if getattr(recipe, 'ignore_inventory', False):
                return True
            
            # Get all ingredients for this recipe
            ingredients_list = list(recipe.ingredients.all().select_related('ingredient'))
            if not ingredients_list:
                return has_recipe_name_inventory_fallback(recipe)
            
            # Check each ingredient
            has_checkable_ingredient = False
            for recipe_ing in ingredients_list:
                if not recipe_ing.ingredient:
                    continue

                # Interpret recipe quantity in the ingredient's base unit (smallest unit)
                per_portion_base = recipe_ing.quantity if recipe_ing.quantity else 0
                if per_portion_base <= 0:
                    continue

                has_checkable_ingredient = True

                conv_to_base = recipe_ing.ingredient.conversion_to_base or 1

                # Prefer total_quantity, but fall back to quantity when total_quantity is empty/zero.
                inventory_units = recipe_ing.ingredient.total_quantity or recipe_ing.ingredient.quantity or 0
                available_base = inventory_units * conv_to_base

                # Required amount in base units for all students
                required_base = per_portion_base * estimated_daily_students
                if available_base < required_base:
                    return False

            if not has_checkable_ingredient:
                return has_recipe_name_inventory_fallback(recipe)
            
            # All ingredients are sufficient
            return True
        except Exception as e:
            pass  # print(f"Error checking inventory for '{recipe.name}': {str(e)}")
            return True
    
    # Helper to get and format ingredient list for a recipe
    def get_recipe_ingredients_debug(recipe):
        """Get ingredients for a recipe and return formatted string with inventory availability"""
        try:
            ingredients_list = list(recipe.ingredients.all().select_related('ingredient'))
            if not ingredients_list:
                return "No ingredients linked (using recipe-name inventory fallback)"
            
            ingredient_details = []
            has_insufficient = False
            
            for recipe_ing in ingredients_list:
                if recipe_ing.ingredient:
                    per_portion_base = recipe_ing.quantity if recipe_ing.quantity else 0
                    conv_to_base = recipe_ing.ingredient.conversion_to_base or 1
                    inventory_units = recipe_ing.ingredient.total_quantity or recipe_ing.ingredient.quantity or 0
                    available_base = inventory_units * conv_to_base
                    required_base = per_portion_base * estimated_daily_students
                    units = recipe_ing.ingredient.base_unit or 'units'
                    
                    # Check if there's enough inventory
                    if required_base > 0:
                        if available_base >= required_base:
                            status = "✓"  # Sufficient
                        else:
                            status = "✗"  # Insufficient
                            has_insufficient = True
                    else:
                        status = "?"  # Unknown requirement
                    
                    # Debug-style text: "recipe has 1 portion of X but requires X for N students; current qty is X"
                    ingredient_details.append(
                        f"{recipe_ing.ingredient.item} "
                        f"[per-portion: {per_portion_base} {units}, students: {estimated_daily_students}, "
                        f"requires: {required_base} {units}, current qty: {available_base} {units}] {status}"
                    )
                else:
                    ingredient_details.append("(Unlinked ingredient)")
            
            result = ", ".join(ingredient_details)
            if has_insufficient:
                result = "⚠️ INSUFFICIENT INVENTORY - " + result
            
            return result
        except Exception as e:
            return f"Error fetching ingredients: {str(e)}"
    
    # STEP 2: Generate each meal period using the pre-assignments
    
    # === BREAKFAST GENERATION ===
    breakfast_data = {}
    for day in days_of_week:
        breakfast_data[day] = {
            'fluid_milk': '', 'fluid_milk_rule_id': None,
            'bread': '', 'bread_rule_id': None,
            'add1': '', 'add1_rule_id': None,
            'fruit': '', 'fruit_rule_id': None
        }
    
    # FLUID RULE PLACEMENT (MANDATORY DAILY): Place fluid_rule recipes in milk row EVERY day
    # Fluid rows use inventory-item portion checks (unit_size), not recipe ingredient math.
    if fluid_rule_recipes:
        fluid_recipe = fluid_rule_recipes[0]  # Use first fluid recipe
        for day in days_of_week:
            if fluid_recipe.populate_breakfast and has_recipe_name_inventory_fallback(fluid_recipe):
                breakfast_data[day]['fluid_milk'] = fluid_recipe.name
                breakfast_data[day]['fluid_milk_rule_id'] = fluid_recipe.fluid_rule_id
                pass  # print(f"  Placed fluid recipe '{fluid_recipe.name}' in {day} breakfast milk")
    
    # Get pre-assigned breakfast recipes from rules
    breakfast_rule_recipes = rule_assignments['breakfast']
    
    # Separate standalone recipes for Phase 3 processing
    standalone_breakfast_recipes = {}
    
    # PHASE 1: Place rule-based recipes (including promoted standalone recipes)
    for day_idx, recipes_list in breakfast_rule_recipes.items():
        if not recipes_list:
            continue
        
        day = days_of_week[day_idx]
        
        # Process each recipe assigned to this day
        for recipe in recipes_list:
            recipe_type = recipe.recipe_type
            is_standalone = getattr(recipe, 'standalone', False)
            
            # Special handling for standalone recipes:
            # - Standalone WITH fruit_rule/veg_rule: Place in main fruit/veg row (frees Additional Food for grain)
            # - Standalone whole_grain: ONLY goes to Additional Food (never main bread row)
            # - Other standalone: Defer to Phase 3
            if is_standalone:
                # Check if this standalone recipe has a fruit_rule or veg_rule (regardless of recipe_type)
                has_fruit_or_veg_rule = (
                    (hasattr(recipe, 'fruit_rule') and recipe.fruit_rule) or
                    (hasattr(recipe, 'veg_rule') and recipe.veg_rule)
                )
                
                if has_fruit_or_veg_rule:
                    # Standalone with fruit/veg rule → place in fruit row only when
                    # the recipe is fruit/vegetable typed or has explicit fruit/veg content.
                    fruit_or_veg_value = _first_distinct_component(
                        recipe,
                        getattr(recipe, 'fruit', None),
                        getattr(recipe, 'veg', None),
                    )
                    can_fill_fruit_row = (
                        recipe_type in ['fruit', 'vegetable'] or bool(fruit_or_veg_value)
                    )
                    if can_fill_fruit_row:
                        if not breakfast_data[day]['fruit']:
                            breakfast_data[day]['fruit'] = fruit_or_veg_value or recipe.name
                        # Don't defer to Phase 3
                        continue
                elif recipe_type == 'whole_grain':
                    # Standalone grain → ONLY Additional Food (never main bread row)
                    if not breakfast_data[day]['add1']:
                        breakfast_data[day]['add1'] = recipe.name
                    # Don't defer to Phase 3
                    continue
                else:
                    # Other standalone recipes → Defer to Phase 3
                    if day_idx not in standalone_breakfast_recipes:
                        standalone_breakfast_recipes[day_idx] = []
                    standalone_breakfast_recipes[day_idx].append(recipe)
                    continue
            
            # Non-standalone recipe placement
            if recipe_type in ['fruit', 'vegetable']:
                # Only place if fruit cell is empty (no cramming multiple rules)
                if not breakfast_data[day]['fruit']:
                    breakfast_data[day]['fruit'] = recipe.name
            elif recipe_type == 'whole_grain':
                # Non-standalone WG: side component only, never main bread row.
                if not breakfast_data[day]['add1']:
                    breakfast_data[day]['add1'] = recipe.name
            elif recipe_type == 'breakfast':
                if not breakfast_data[day]['bread']:  # Only if empty
                    # Use recipe.name to show actual recipe name, not generic grain field
                    breakfast_data[day]['bread'] = recipe.name
                    breakfast_data[day]['bread_rule_id'] = get_recipe_title_rule_id(recipe)
                # Keep add1 aligned to this same breakfast recipe for this day.
                add_component, add_rule_id = _first_distinct_component_with_rule(
                    recipe,
                    [
                        (recipe.grain, recipe.grain_rule_id),
                        (recipe.addfood, recipe.addfood_rule_id),
                    ]
                )
                breakfast_data[day]['add1'] = add_component
                breakfast_data[day]['add1_rule_id'] = add_rule_id

                fruit_component = _first_distinct_component(recipe, recipe.fruit, recipe.veg)
                if fruit_component and not breakfast_data[day]['fruit']:
                    breakfast_data[day]['fruit'] = fruit_component
                    breakfast_data[day]['fruit_rule_id'] = recipe.fruit_rule_id or recipe.veg_rule_id
    
    # PHASE 2: Fill remaining empty cells with recipes without weekly rules AND NOT standalone
    # 1. Fill empty bread cells with breakfast recipes only (no weekly rules, not standalone)
    breakfast_all = list(Recipe.objects.filter(
        user=user, archive=False, populate_breakfast=True, recipe_type='breakfast'
    ).select_related('grain_rule', 'addfood_rule'))
    
    # DEBUG: Show ALL breakfast recipes BEFORE filtering
    pass  # print(f"\n🔍 DEBUG: ALL breakfast recipes BEFORE Phase 2 filtering:")
    for r in breakfast_all:
        has_rule = has_weekly_rule(r)
        rule_qty = r.grain_rule.weekly_qty if r.grain_rule else "N/A"
        pass  # print(f"   - {r.name} (type={r.recipe_type}, standalone={r.standalone}, has_rule={has_rule}, weekly_qty={rule_qty})")
    
    # When bypassing inventory, be more aggressive - include recipes with weekly rules too
    if force_ignore_inventory:
        # Allow recipes with weekly rules when bypassing inventory (but still exclude standalone)
        breakfast_recipes_no_rules = [r for r in breakfast_all if not r.standalone]
        pass  # print(f"   🔓 BYPASSING INVENTORY: Expanded pool to include recipes with weekly rules")
    else:
        # Normal filtering: no weekly rules, not standalone
        breakfast_recipes_no_rules = [r for r in breakfast_all if not has_weekly_rule(r) and not r.standalone]

    # Fallback: if nothing is flagged to populate breakfast, use any breakfast recipes
    if not breakfast_recipes_no_rules:
        breakfast_all = list(Recipe.objects.filter(
            user=user, archive=False, recipe_type='breakfast'
        ).select_related('grain_rule', 'addfood_rule'))
        if force_ignore_inventory:
            breakfast_recipes_no_rules = [r for r in breakfast_all if not r.standalone]
        else:
            breakfast_recipes_no_rules = [r for r in breakfast_all if not has_weekly_rule(r) and not r.standalone]
    
    # DEBUG: Show which recipes passed the filter for Phase 2
    pass  # print(f"\n🍞 BREAKFAST PHASE 2: Available recipes for bread row (no rules, not standalone):")
    for r in breakfast_recipes_no_rules:
        pass  # print(f"   - {r.name} (type={r.recipe_type}, standalone={r.standalone}, has_rule={has_weekly_rule(r)})")
    
    pass  # print(f"   After filtering: {len(breakfast_recipes_no_rules)} recipes available")
    
    # INVENTORY CHECK: Filter out recipes with insufficient inventory
    # NOTE: This can be bypassed when force_ignore_inventory is True (user confirmed override)
    breakfast_passed_inventory = []
    breakfast_failed_inventory = []
    
    if force_ignore_inventory:
        # When bypassing inventory, include ALL recipes regardless of inventory status
        breakfast_passed_inventory = breakfast_recipes_no_rules
    else:
        # Normal inventory checking
        for r in breakfast_recipes_no_rules:
            if has_sufficient_inventory(r):
                breakfast_passed_inventory.append(r)
            else:
                breakfast_failed_inventory.append(r)

        if breakfast_failed_inventory:
            print(
                f"[MENU DEBUG] Breakfast inventory filter: "
                f"{len(breakfast_failed_inventory)} recipe(s) failed inventory checks; "
                f"examples: {[r.name for r in breakfast_failed_inventory[:5]]}"
            )
            for r in breakfast_failed_inventory[:3]:
                # Detailed per-ingredient reason for a few failures
                print(
                    f"[MENU DEBUG]   Breakfast inventory failure for '{r.name}': "
                    f"{get_recipe_ingredients_debug(r)}"
                )
    
    breakfast_recipes_no_rules = breakfast_passed_inventory

    for day_idx, day in enumerate(days_of_week):
        if not breakfast_data[day]['bread'] and breakfast_recipes_no_rules:
            candidate_count = len(breakfast_recipes_no_rules)
            recipe = random.choice(breakfast_recipes_no_rules)
            
            # Decision debug for this day/row
            print(
                f"[MENU DEBUG] Breakfast {day} bread: selected recipe '{recipe.name}' "
                f"(id={recipe.id}, type={recipe.recipe_type}) "
                f"from {candidate_count} candidate(s) after rules/dedup/inventory filters."
            )
            
            if recipe.recipe_type == 'breakfast':
                # Use recipe.name to show actual recipe, not generic grain field
                breakfast_data[day]['bread'] = recipe.name
                breakfast_data[day]['bread_rule_id'] = get_recipe_title_rule_id(recipe)
                # Keep add1 aligned to this same breakfast recipe for this day.
                add_component, add_rule_id = _first_distinct_component_with_rule(
                    recipe,
                    [
                        (recipe.grain, recipe.grain_rule_id),
                        (recipe.addfood, recipe.addfood_rule_id),
                    ]
                )
                breakfast_data[day]['add1'] = add_component
                breakfast_data[day]['add1_rule_id'] = add_rule_id
                # Use any fruit/veg defined on the main breakfast recipe
                # to populate the fruit row before falling back to separate
                # fruit/veg recipes.
                fruit_component = _first_distinct_component(recipe, recipe.fruit, recipe.veg)
                if fruit_component and not breakfast_data[day]['fruit']:
                    breakfast_data[day]['fruit'] = fruit_component
            # breakfast-only pool for main bread row; whole_grain is handled in add1.
    
    # Fill remaining empty cells with recipes without weekly rules AND NOT standalone
    # 2. Fill empty fruit cells with fruit/veg recipes (no weekly rules, not standalone)
    fruit_veg_all = list(Recipe.objects.filter(
        user=user, archive=False, populate_breakfast=True, recipe_type__in=['fruit', 'vegetable']
    ).select_related('fruit_rule', 'veg_rule'))
    # Allow standalone fruit/veg for breakfast; only filter out recipes with weekly rules here
    fruit_veg_no_rules = [r for r in fruit_veg_all if not has_weekly_rule(r)]

    if not fruit_veg_no_rules:
        # Fallback: still restrict to populate_breakfast=True so lunch-only sides
        # like Instant Garlic Mashed Potatoes are not used at breakfast
        fruit_veg_all = list(Recipe.objects.filter(
            user=user, archive=False, populate_breakfast=True, recipe_type__in=['fruit', 'vegetable']
        ).select_related('fruit_rule', 'veg_rule'))
        fruit_veg_no_rules = [r for r in fruit_veg_all if not has_weekly_rule(r)]
    
    # When bypassing inventory, be more aggressive in filling fruit cells
    if force_ignore_inventory and not fruit_veg_no_rules:
        # Expand to include recipes with weekly rules if necessary (still breakfast-tagged)
        fruit_veg_no_rules = list(fruit_veg_all)
        pass  # print(f"   🔓 Bypassing inventory: expanded to {len(fruit_veg_no_rules)} fruit/veg recipes (includes weekly rules)")
    
    for day_idx, day in enumerate(days_of_week):
        if not breakfast_data[day]['fruit'] and fruit_veg_no_rules:
            recipe = random.choice(fruit_veg_no_rules)
            breakfast_data[day]['fruit'] = recipe.name
            print(
                f"[MENU DEBUG] Breakfast {day} fruit: filled with '{recipe.name}' "
                f"from fruit/veg pool after filters."
            )

    # Set default if still empty (but only when NOT bypassing inventory)
    if not force_ignore_inventory:
        for day in days_of_week:
            if not breakfast_data[day]['bread']:
                breakfast_data[day]['bread'] = "No available breakfast option"
    
    # PHASE 3: Process standalone recipes ONLY in days that have main breakfast recipes
    for day_idx, recipes_list in standalone_breakfast_recipes.items():
        day = days_of_week[day_idx]
        
        # Only place standalone recipes if there's a main breakfast recipe
        if not breakfast_data[day]['bread'] or breakfast_data[day]['bread'] == "No available breakfast option":
            pass  # print(f"  Skipping {len(recipes_list)} standalone recipe(s) for {day} breakfast - no main recipe")
            continue
        
        # Process each standalone recipe - LIMIT: only place if target cell is empty (no cramming)
        for recipe in recipes_list:
            recipe_type = recipe.recipe_type
            
            # INVENTORY CHECK: Side-component standalones use inventory-item unit_size checks.
            if recipe_type in ['fruit', 'vegetable', 'whole_grain']:
                if not has_recipe_name_inventory_fallback(recipe):
                    pass  # print(f"  Skipping standalone '{recipe.name}' for {day} breakfast - insufficient inventory")
                    continue
            
            # Place standalone recipe in appropriate field ONLY if empty
            if recipe_type in ['fruit', 'vegetable']:
                if not breakfast_data[day]['fruit']:  # Only if empty
                    breakfast_data[day]['fruit'] = recipe.name
                # Skip if fruit cell already has content (no cramming)
            elif recipe_type == 'whole_grain':
                # Standalone WG goes to add food ONLY if empty
                if not breakfast_data[day]['add1']:
                    breakfast_data[day]['add1'] = recipe.name
                # Skip if Additional Food already has content (no cramming)
            elif recipe_type == 'breakfast':
                # Skip standalone breakfast recipes if bread is occupied
                pass
    # === AM SNACK GENERATION ===
    am_snack_data = {}
    for day in days_of_week:
        # add3: Additional Food (Optional) for AM snack
        am_snack_data[day] = {
            'choose1': '', 'choose1_rule_id': None,
            'fruit2': '', 'fruit2_rule_id': None,
            'bread2': '', 'bread2_rule_id': None,
            'meat1': '', 'meat1_rule_id': None,
            'add3': '', 'add3_rule_id': None
        }
    
    am_snack_rule_recipes = rule_assignments['am_snack']
    
    # Separate standalone recipes for Phase 3 processing
    standalone_am_snack_recipes = {}
    
    # PHASE 1: Place rule-based recipes (including promoted standalone recipes)
    for day_idx, recipes_list in am_snack_rule_recipes.items():
        if not recipes_list:
            continue
            
        day = days_of_week[day_idx]
        
        # Process each recipe assigned to this day
        for recipe in recipes_list:
            is_standalone = getattr(recipe, 'standalone', False)
            is_snack_wg = recipe.recipe_type == 'whole_grain'

            # Special handling for standalone recipes:
            # - Standalone WITH fruit_rule/veg_rule: Place in main fruit/veg row (frees Additional Food for grain)
            # - Standalone whole_grain: ONLY goes to Additional Food
            # - Other standalone: Defer to Phase 3
            if is_standalone:
                # Check if this standalone recipe has a fruit_rule or veg_rule (regardless of recipe_type)
                has_fruit_or_veg_rule = (
                    (hasattr(recipe, 'fruit_rule') and recipe.fruit_rule) or
                    (hasattr(recipe, 'veg_rule') and recipe.veg_rule)
                )
                
                if has_fruit_or_veg_rule:
                    # Standalone with fruit/veg rule → place in fruit row only when
                    # the recipe is fruit/vegetable typed or has explicit fruit/veg content.
                    fruit_or_veg_value = _first_distinct_component(
                        recipe,
                        getattr(recipe, 'fruit', None),
                        getattr(recipe, 'veg', None),
                    )
                    can_fill_fruit_row = (
                        recipe.recipe_type in ['fruit', 'vegetable'] or bool(fruit_or_veg_value)
                    )
                    if can_fill_fruit_row:
                        if not am_snack_data[day]['fruit2']:
                            am_snack_data[day]['fruit2'] = fruit_or_veg_value or recipe.name
                        continue
                else:
                    # ALL other standalone recipes (including whole_grain) → Defer to Phase 3
                    # This ensures they go through the has_snack_content check and won't be
                    # placed in empty snack periods that aren't being served
                    if day_idx not in standalone_am_snack_recipes:
                        standalone_am_snack_recipes[day_idx] = []
                    standalone_am_snack_recipes[day_idx].append(recipe)
                    continue
            
            # Non-standalone recipe placement
            # Fluid always overwrites
            if recipe.fluid:
                am_snack_data[day]['choose1'] = recipe.fluid
                am_snack_data[day]['choose1_rule_id'] = recipe.fluid_rule_id

            # Bread/grain content - WG items go to add food 
            if is_snack_wg or recipe.grain:
                # Use recipe.name for WG items to show variety; for non-WG skip values
                # that duplicate the recipe title.
                display_name = recipe.name if is_snack_wg else _first_distinct_component(recipe, recipe.grain)
                # WG items go to Additional Food
                if is_snack_wg:
                    # Always place in add food to not block main snack
                    if display_name and not am_snack_data[day]['add3']:
                        am_snack_data[day]['add3'] = display_name
                else:
                    # For snack recipes, grain is an extra component -> Additional Food.
                    if display_name and not am_snack_data[day]['add3']:
                        am_snack_data[day]['add3'] = display_name

            # Meat content - always place in meat row
            if recipe.meat:
                if not am_snack_data[day]['meat1']:
                    am_snack_data[day]['meat1'] = recipe.meat
                elif not am_snack_data[day]['add3']:
                    am_snack_data[day]['add3'] = recipe.meat

            # Fruit/veg content - ALWAYS place in fruit row
            fruit_or_veg = _first_distinct_component(recipe, recipe.fruit, recipe.veg)
            if fruit_or_veg:
                if not am_snack_data[day]['fruit2']:
                    am_snack_data[day]['fruit2'] = fruit_or_veg
                elif not am_snack_data[day]['add3']:
                    am_snack_data[day]['add3'] = fruit_or_veg
    
    # PHASE 2: Fill remaining days with snack recipes without weekly rules AND NOT standalone.
    # For the main snack row (bread2), exclude side-only recipe types.
    am_snack_all = list(Recipe.objects.filter(
        user=user,
        archive=False,
        populate_am_snack=True,
    ).select_related('grain_rule', 'fruit_rule', 'veg_rule', 'meat_rule', 'fluid_rule', 'addfood_rule'))
    am_snack_all = [
        r for r in am_snack_all
        if r.recipe_type not in ['fruit', 'vegetable', 'whole_grain', 'fluid']
    ]
    
    # When bypassing inventory, include recipes with weekly rules (but still exclude standalone)
    if force_ignore_inventory:
        am_snack_no_rules = [r for r in am_snack_all if not r.standalone]
        pass  # print(f"   🔓 BYPASSING INVENTORY: Expanded AM snack pool to include recipes with weekly rules")
    else:
        am_snack_no_rules = [r for r in am_snack_all if not has_weekly_rule(r) and not r.standalone]

    # Fallback: if the populate flag yielded nothing with weekly rules filtered out,
    # relax the weekly-rule filter so at least something gets placed.
    if not am_snack_no_rules and am_snack_all:
        if force_ignore_inventory:
            am_snack_no_rules = [r for r in am_snack_all if not r.standalone]
        else:
            am_snack_no_rules = [r for r in am_snack_all if not r.standalone]

    # Ultimate fallback: use any AM-type recipe for this user.
    if not am_snack_no_rules:
        am_snack_all = list(Recipe.objects.filter(
            user=user,
            archive=False,
            recipe_type__in=['am_snack', 'am_pm_snack']
        ).select_related('grain_rule', 'fruit_rule', 'veg_rule', 'meat_rule', 'fluid_rule', 'addfood_rule'))
        if force_ignore_inventory:
            am_snack_no_rules = [r for r in am_snack_all if not r.standalone]
        else:
            am_snack_no_rules = [r for r in am_snack_all if not has_weekly_rule(r) and not r.standalone]
    
    am_snack_before_filters = am_snack_no_rules[:]

    # Count days that still need a main AM snack dish after Phase 1
    days_needing_am_snack = sum(1 for day in days_of_week if not am_snack_data[day]['bread2'])

    # If the non-weekly-rule pool is smaller than the days that need filling, supplement
    if len(am_snack_no_rules) < days_needing_am_snack and am_snack_all:
        supplemental = [
            r for r in am_snack_all
            if not r.standalone
            and r.id not in {x.id for x in am_snack_no_rules}
        ]
        if supplemental:
            am_snack_no_rules = am_snack_no_rules + supplemental
            print(
                f"[MENU DEBUG] AM snack Phase 2 supplement: added {len(supplemental)} weekly-rule "
                f"recipe(s) to reach {len(am_snack_no_rules)} candidate(s) for {days_needing_am_snack} unfilled days."
            )

    if len(am_snack_no_rules) < days_needing_am_snack and am_snack_before_filters:
        reuse_candidates = [
            r for r in am_snack_before_filters
            if r.id not in {x.id for x in am_snack_no_rules}
        ]
        if reuse_candidates:
            am_snack_no_rules = am_snack_no_rules + reuse_candidates
            print(
                f"[MENU DEBUG] AM snack Phase 2 dedup relax: re-added {len(reuse_candidates)} "
                f"previously-used recipe(s) to cover {days_needing_am_snack} unfilled day(s)."
            )

    print(
        f"[MENU DEBUG] AM snack Phase 2: {len(am_snack_no_rules)} recipe(s) "
        f"available after meal-specific filters."
    )
    
    # INVENTORY CHECK: Filter out recipes with insufficient inventory
    # NOTE: This can be bypassed when force_ignore_inventory is True (user confirmed override)
    am_passed_inventory = []
    am_failed_inventory = []
    
    if force_ignore_inventory:
        # When bypassing inventory, include ALL recipes regardless of inventory status
        am_passed_inventory = am_snack_no_rules
    else:
        # Normal inventory checking
        for r in am_snack_no_rules:
            if has_sufficient_inventory(r):
                am_passed_inventory.append(r)
            else:
                am_failed_inventory.append(r)

        if am_failed_inventory:
            print(
                f"[MENU DEBUG] AM snack inventory filter: "
                f"{len(am_failed_inventory)} recipe(s) failed inventory checks; "
                f"examples: {[r.name for r in am_failed_inventory[:5]]}"
            )
            for r in am_failed_inventory[:3]:
                print(
                    f"[MENU DEBUG]   AM snack inventory failure for '{r.name}': "
                    f"{get_recipe_ingredients_debug(r)}"
                )
    
    am_snack_no_rules = am_passed_inventory

    for day_idx, day in enumerate(days_of_week):
        if not am_snack_data[day]['bread2'] and am_snack_no_rules:
            candidate_count = len(am_snack_no_rules)
            recipe = random.choice(am_snack_no_rules)
            
            am_snack_data[day]['choose1'] = recipe.fluid or ""
            if recipe.fluid:
                am_snack_data[day]['choose1_rule_id'] = recipe.fluid_rule_id
            # Use recipe.name for main content (not generic recipe.grain component)
            am_snack_data[day]['bread2'] = recipe.name
            am_snack_data[day]['bread2_rule_id'] = get_recipe_title_rule_id(recipe)
            if not am_snack_data[day]['add3']:
                add_component, add_rule_id = _first_distinct_component_with_rule(
                    recipe,
                    [
                        (recipe.grain, recipe.grain_rule_id),
                        (recipe.addfood, recipe.addfood_rule_id),
                    ]
                )
                am_snack_data[day]['add3'] = add_component
                am_snack_data[day]['add3_rule_id'] = add_rule_id
            am_snack_data[day]['meat1'] = recipe.meat or ""
            fruit_component = _first_distinct_component(recipe, recipe.fruit, recipe.veg)
            if fruit_component:
                am_snack_data[day]['fruit2'] = fruit_component
                am_snack_data[day]['fruit2_rule_id'] = recipe.fruit_rule_id or recipe.veg_rule_id

            print(
                f"[MENU DEBUG] AM snack {day} bread2: selected recipe '{recipe.name}' "
                f"(id={recipe.id}, type={recipe.recipe_type}) "
                f"from {candidate_count} candidate(s) after rules/dedup/inventory filters."
            )
    
    # FLUID RULE PLACEMENT (CONDITIONAL): Place fluid_rule recipes in choose1 ONLY if:
    # - populate_am_snack is True for the fluid recipe
    # - Main snack dish (bread2) has content
    # - Fluid row (choose1) is BLANK
    # NEVER overwrite existing fluid content
    if fluid_rule_recipes:
        fluid_recipe = fluid_rule_recipes[0]
        if fluid_recipe.populate_am_snack and has_recipe_name_inventory_fallback(fluid_recipe):
            for day in days_of_week:
                has_main_content = am_snack_data[day]['bread2']
                fluid_is_blank = not am_snack_data[day]['choose1']
                if has_main_content and fluid_is_blank:
                    am_snack_data[day]['choose1'] = fluid_recipe.name
                    am_snack_data[day]['choose1_rule_id'] = fluid_recipe.fluid_rule_id
                    pass  # print(f"  Placed fluid recipe '{fluid_recipe.name}' in {day} AM snack (conditional)")
    
    # PHASE 3: Process standalone recipes ONLY if the AM snack period has main content
    # (If all AM snack fields are empty, user isn't serving AM snack this week)
    for day_idx, recipes_list in standalone_am_snack_recipes.items():
        day = days_of_week[day_idx]
        
        # Check if AM snack period has any main content (choose1, bread2, meat1, fruit2)
        # If all are empty, user isn't serving this snack period
        has_snack_content = any([
            am_snack_data[day]['choose1'],
            am_snack_data[day]['bread2'],
            am_snack_data[day]['meat1'],
            am_snack_data[day]['fruit2']
        ])
        
        if not has_snack_content:
            pass  # print(f"  Skipping {len(recipes_list)} standalone recipe(s) for {day} AM snack - snack period not being served")
            continue
        
        # Process each standalone recipe - LIMIT: only place if target cell is empty (no cramming)
        for recipe in recipes_list:
            is_snack_wg = recipe.recipe_type == 'whole_grain'
            
            # INVENTORY CHECK: Side-component standalones use inventory-item unit_size checks.
            if recipe.fluid or is_snack_wg or recipe.recipe_type in ['fruit', 'vegetable']:
                if not has_recipe_name_inventory_fallback(recipe):
                    pass  # print(f"  Skipping standalone '{recipe.name}' for {day} AM snack - insufficient inventory")
                    continue
            
            # Place standalone recipe in appropriate field ONLY if empty
            if recipe.fluid and not am_snack_data[day]['choose1']:
                am_snack_data[day]['choose1'] = recipe.fluid
                am_snack_data[day]['choose1_rule_id'] = recipe.fluid_rule_id

            if is_snack_wg or recipe.grain:
                grain_or_name = recipe.grain or recipe.name
                # Standalone/WG items go to add food ONLY if empty
                if not am_snack_data[day]['add3']:
                    am_snack_data[day]['add3'] = grain_or_name
                    # Track rule ID for add3: use grain_rule if grain exists
                    if recipe.grain and recipe.grain_rule_id:
                        am_snack_data[day]['add3_rule_id'] = recipe.grain_rule_id

            elif recipe.meat:
                if not am_snack_data[day]['add3']:
                    am_snack_data[day]['add3'] = recipe.meat

            elif recipe.fruit or recipe.veg:
                fruit_or_veg = recipe.fruit or recipe.veg
                if not am_snack_data[day]['fruit2']:
                    am_snack_data[day]['fruit2'] = fruit_or_veg
    
    # === LUNCH GENERATION ===
    lunch_data = {}
    for day in days_of_week:
        lunch_data[day] = {
            'meal_name': '', 'meal_name_rule_id': None,
            'lunch_milk': '', 'lunch_milk_rule_id': None,
            'grain': '', 'grain_rule_id': None,
            'meat_alternate': '', 'meat_alternate_rule_id': None,
            'vegetable': '', 'vegetable_rule_id': None,
            'fruit3': '', 'fruit3_rule_id': None,
            'add2': '', 'add2_rule_id': None
        }
    
    # FLUID RULE PLACEMENT (MANDATORY DAILY): Place fluid_rule recipes in lunchmilk row EVERY day
    # Fluid rows use inventory-item portion checks (unit_size), not recipe ingredient math.
    if fluid_rule_recipes:
        fluid_recipe = fluid_rule_recipes[0]  # Use first fluid recipe
        for day in days_of_week:
            if fluid_recipe.populate_lunch and has_recipe_name_inventory_fallback(fluid_recipe):
                lunch_data[day]['lunch_milk'] = fluid_recipe.name
                lunch_data[day]['lunch_milk_rule_id'] = fluid_recipe.fluid_rule_id
                pass  # print(f"  Placed fluid recipe '{fluid_recipe.name}' in {day} lunch milk")

    # Pre-resolve main lunch recipes (standalone recipes are excluded from being primary mains)
    main_lunch_qs = Recipe.objects.filter(
        user=user,
        archive=False,
        populate_lunch=True,
        recipe_type='lunch',
        standalone=False,
    )

    # Fallback: if no lunch recipes are flagged to populate_lunch, use any
    # non-standalone lunch recipes for this user so we still get real mains.
    if not main_lunch_qs.exists():
        main_lunch_qs = Recipe.objects.filter(
            user=user,
            archive=False,
            recipe_type='lunch',
            standalone=False,
        )
    all_main_lunch_recipes = list(main_lunch_qs)

    lunch_rule_recipes = rule_assignments['lunch']

    # Track fruit/veg component names placed in fruit3/vegetable across ALL days.
    # When a main-dish component would repeat a name already placed, we skip it
    # (leave the cell empty) so Phase 5 and the side-dish pool can provide variety.
    _fruit3_week_names = set()
    _veg_week_names = set()

    # Separate standalone recipes for Phase 3 processing
    standalone_lunch_recipes = {}
    
    # PHASE 1: Place rule-based recipes (including promoted standalone recipes)
    # Split into two passes to ensure main dishes are placed before checking grain row placement
    
    # PASS 1: Process main dishes and non-whole_grain recipes first
    for day_idx, recipes_list in lunch_rule_recipes.items():
        if not recipes_list:
            continue
            
        day = days_of_week[day_idx]
        
        # Process each recipe assigned to this day (except standalone whole_grain - save for Pass 2)
        for recipe in recipes_list:
            recipe_type = recipe.recipe_type
            is_standalone = getattr(recipe, 'standalone', False)
            
            # Skip standalone whole_grain recipes - they'll be processed in Pass 2
            if is_standalone and recipe_type == 'whole_grain':
                continue
            
            # Special handling for standalone recipes:
            # - Standalone WITH fruit_rule/veg_rule: Place in main fruit/veg rows (frees Additional Food for grain)
            # - Other standalone: Defer to Phase 3
            if is_standalone:
                # Check if this standalone recipe has rules (regardless of recipe_type)
                has_veg_rule = hasattr(recipe, 'veg_rule') and recipe.veg_rule
                has_fruit_rule = hasattr(recipe, 'fruit_rule') and recipe.fruit_rule
                
                if has_veg_rule:
                    # Standalone with veg_rule → Main vegetable row (regardless of recipe_type)
                    if not lunch_data[day]['vegetable']:
                        lunch_data[day]['vegetable'] = recipe.name
                        lunch_data[day]['vegetable_rule_id'] = recipe.veg_rule_id
                    continue
                elif has_fruit_rule:
                    # Standalone with fruit_rule → Main fruit3 row (regardless of recipe_type)
                    if not lunch_data[day]['fruit3']:
                        lunch_data[day]['fruit3'] = recipe.name
                        lunch_data[day]['fruit3_rule_id'] = recipe.fruit_rule_id
                    continue
                else:
                    # Other standalone recipes → Defer to Phase 3
                    if day_idx not in standalone_lunch_recipes:
                        standalone_lunch_recipes[day_idx] = []
                    standalone_lunch_recipes[day_idx].append(recipe)
                    continue
            
            # Non-standalone recipe placement
            if recipe_type == 'lunch':
                # Main lunch dish
                lunch_data[day]['meal_name'] = recipe.name
                lunch_data[day]['meal_name_rule_id'] = get_recipe_title_rule_id(recipe)
                # If the main lunch recipe has a grain component (e.g. CN Pizza crust),
                # fill the grain row directly so no separate whole_grain side is added.
                grain_component = recipe.grain or ""
                if grain_component and not lunch_data[day]['grain']:
                    lunch_data[day]['grain'] = grain_component
                    if recipe.grain_rule_id:
                        lunch_data[day]['grain_rule_id'] = recipe.grain_rule_id
                lunch_data[day]['meat_alternate'] = recipe.meat_alternate or ""
                # If the main lunch recipe already specifies a vegetable and/or
                # fruit, use those to populate the corresponding rows before
                # relying on separate veg/fruit rule or standalone recipes.
                veg_component = _first_distinct_component(recipe, recipe.veg)
                fruit_component = _first_distinct_component(recipe, recipe.fruit)
                if veg_component and not lunch_data[day]['vegetable'] and veg_component not in _veg_week_names:
                    lunch_data[day]['vegetable'] = veg_component
                    lunch_data[day]['vegetable_rule_id'] = recipe.veg_rule_id
                    _veg_week_names.add(veg_component)
                if fruit_component and not lunch_data[day]['fruit3'] and fruit_component not in _fruit3_week_names:
                    lunch_data[day]['fruit3'] = fruit_component
                    lunch_data[day]['fruit3_rule_id'] = recipe.fruit_rule_id
                    _fruit3_week_names.add(fruit_component)
                # Track similarity exclusions so Phase 2 / fallback won't pick a
                # similar recipe into the same week.
                similarity_excluded_ids |= _get_similarity_excluded_ids(recipe.id)
            elif recipe_type == 'whole_grain':
                # Grain rule recipes: ONLY to Additional Food (never main grain row per user requirement)
                if not lunch_data[day]['add2']:
                    lunch_data[day]['add2'] = recipe.name
            elif recipe_type == 'vegetable':
                # Vegetable goes in vegetable row (only if empty)
                if not lunch_data[day]['vegetable']:
                    lunch_data[day]['vegetable'] = recipe.name
                    if recipe.veg_rule_id:
                        lunch_data[day]['vegetable_rule_id'] = recipe.veg_rule_id
            elif recipe_type == 'fruit':
                # Fruit goes in fruit row (only if empty)
                if not lunch_data[day]['fruit3']:
                    lunch_data[day]['fruit3'] = recipe.name
                    if recipe.fruit_rule_id:
                        lunch_data[day]['fruit3_rule_id'] = recipe.fruit_rule_id
    
    # Fill remaining empty cells with recipes without weekly rules
    # 1. Main lunch dishes (no weekly rules, non-standalone only)
    lunch_all = list(main_lunch_qs.select_related('grain_rule', 'fruit_rule', 'veg_rule', 'meat_rule'))
    
    # When bypassing inventory, include recipes with weekly rules
    if force_ignore_inventory:
        lunch_recipes_no_rules = lunch_all  # All recipes from main_lunch_qs
        pass  # print(f"   🔓 BYPASSING INVENTORY: Expanded lunch pool to include recipes with weekly rules")
    else:
        lunch_recipes_no_rules = [r for r in lunch_all if not has_weekly_rule(r)]
    
    # DEDUPLICATION: Filter out already-used main dish recipes and similarity-excluded recipes
    lunch_before_dedup = lunch_recipes_no_rules[:]
    lunch_recipes_no_rules = [r for r in lunch_recipes_no_rules if r.id not in used_main_recipes and r.id not in similarity_excluded_ids]
    days_needing_lunch = sum(1 for day in days_of_week if not lunch_data[day]['meal_name'])
    if len(lunch_recipes_no_rules) < days_needing_lunch and lunch_before_dedup:
        reuse_candidates = [
            r for r in lunch_before_dedup
            if r.id not in {x.id for x in lunch_recipes_no_rules}
        ]
        if reuse_candidates:
            lunch_recipes_no_rules = lunch_recipes_no_rules + reuse_candidates
            print(
                f"[MENU DEBUG] Lunch Phase 2 dedup relax: re-added {len(reuse_candidates)} "
                f"previously-used recipe(s) to cover {days_needing_lunch} unfilled day(s)."
            )
    print(
        f"[MENU DEBUG] Lunch Phase 2: {len(lunch_recipes_no_rules)} main lunch recipe(s) "
        f"available after excluding already-used mains."
    )
    
    # 2-WEEK COOLDOWN: Filter out recipes used within 2 weeks of the menu week
    # NOTE: This constraint is ALWAYS enforced, even when force_ignore_inventory is True
    # (cooldown window calculated at start: two_weeks_before and two_weeks_after)
    # Filter out recipes where last_used falls within the 2-week window
    lunch_recipes_before_cooldown = len(lunch_recipes_no_rules)
    lunch_recipes_no_rules = [
        r for r in lunch_recipes_no_rules 
        if not r.last_used or r.last_used.date() < two_weeks_before or r.last_used.date() > two_weeks_after
    ]
    
    if lunch_recipes_before_cooldown > len(lunch_recipes_no_rules):
        pass  # print(f"   🕐 2-week cooldown: filtered out {lunch_recipes_before_cooldown - len(lunch_recipes_no_rules)} recently used recipes")
        pass  # print(f"      (excluding recipes used between {two_weeks_before} and {two_weeks_after})")
    
    # INVENTORY CHECK: Filter out recipes with insufficient inventory
    # NOTE: This can be bypassed when force_ignore_inventory is True (user confirmed override)
    lunch_passed_inventory = []
    lunch_failed_inventory = []
    
    if force_ignore_inventory:
        # When bypassing inventory, include ALL recipes regardless of inventory status
        lunch_passed_inventory = lunch_recipes_no_rules
    else:
        # Normal inventory checking
        for r in lunch_recipes_no_rules:
            if has_sufficient_inventory(r):
                lunch_passed_inventory.append(r)
            else:
                lunch_failed_inventory.append(r)

        if lunch_failed_inventory:
            print(
                f"[MENU DEBUG] Lunch inventory filter: "
                f"{len(lunch_failed_inventory)} recipe(s) failed inventory checks; "
                f"examples: {[r.name for r in lunch_failed_inventory[:5]]}"
            )
            for r in lunch_failed_inventory[:3]:
                print(
                    f"[MENU DEBUG]   Lunch inventory failure for '{r.name}': "
                    f"{get_recipe_ingredients_debug(r)}"
                )
    
    lunch_recipes_no_rules = lunch_passed_inventory
    
    for day_idx, day in enumerate(days_of_week):
        if not lunch_data[day]['meal_name'] and lunch_recipes_no_rules:
            candidate_count = len(lunch_recipes_no_rules)
            recipe = random.choice(lunch_recipes_no_rules)
            
            # Track this recipe as used
            used_main_recipes.add(recipe.id)
            similarity_excluded_ids |= _get_similarity_excluded_ids(recipe.id)
            # Remove only when we still have enough unique recipes to cover remaining days.
            remaining_unfilled_days = sum(1 for d in days_of_week if not lunch_data[d]['meal_name'])
            if len(lunch_recipes_no_rules) > remaining_unfilled_days:
                lunch_recipes_no_rules = [r for r in lunch_recipes_no_rules if r.id != recipe.id]
            
            lunch_data[day]['meal_name'] = recipe.name
            lunch_data[day]['meal_name_rule_id'] = get_recipe_title_rule_id(recipe)
            # If the main lunch recipe has a grain component (e.g. CN Pizza crust),
            # fill the grain row directly so no separate whole_grain side is added.
            grain_component = recipe.grain or ""
            if grain_component and not lunch_data[day]['grain']:
                lunch_data[day]['grain'] = grain_component
                if recipe.grain_rule_id:
                    lunch_data[day]['grain_rule_id'] = recipe.grain_rule_id
            lunch_data[day]['meat_alternate'] = recipe.meat_alternate or ""
            # Prefer any veg/fruit that are part of the main lunch recipe
            # over later standalone side selections.
            veg_component = _first_distinct_component(recipe, recipe.veg)
            fruit_component = _first_distinct_component(recipe, recipe.fruit)
            if veg_component and not lunch_data[day]['vegetable'] and veg_component not in _veg_week_names:
                lunch_data[day]['vegetable'] = veg_component
                lunch_data[day]['vegetable_rule_id'] = recipe.veg_rule_id
                _veg_week_names.add(veg_component)
            if fruit_component and not lunch_data[day]['fruit3'] and fruit_component not in _fruit3_week_names:
                lunch_data[day]['fruit3'] = fruit_component
                lunch_data[day]['fruit3_rule_id'] = recipe.fruit_rule_id
                _fruit3_week_names.add(fruit_component)

            print(
                f"[MENU DEBUG] Lunch {day} main dish: selected recipe '{recipe.name}' "
                f"(id={recipe.id}, type={recipe.recipe_type}) "
                f"from {candidate_count} candidate(s) after rules/dedup/cooldown/inventory filters."
            )
    
    # PASS 2: Process standalone whole_grain recipes NOW that all main dishes are placed
    for day_idx, recipes_list in lunch_rule_recipes.items():
        if not recipes_list:
            continue
            
        day = days_of_week[day_idx]
        
        # Process only standalone whole_grain recipes
        for recipe in recipes_list:
            recipe_type = recipe.recipe_type
            is_standalone = getattr(recipe, 'standalone', False)
            
            # Only process standalone whole_grain recipes
            if is_standalone and recipe_type == 'whole_grain':
                # Standalone grain: prioritize Grain row if main dish exists, otherwise Additional Food
                if lunch_data[day]['meal_name'] and not lunch_data[day]['grain']:
                    # Main dish exists and grain row empty → place in Grain row
                    lunch_data[day]['grain'] = recipe.name
                    # Track rule ID if recipe has grain_rule
                    if recipe.grain_rule_id:
                        lunch_data[day]['grain_rule_id'] = recipe.grain_rule_id
                elif not lunch_data[day]['add2']:
                    # No main dish or grain row filled → place in Additional Food
                    lunch_data[day]['add2'] = recipe.name
                    # Track rule ID if recipe has grain_rule
                    if recipe.grain_rule_id:
                        lunch_data[day]['add2_rule_id'] = recipe.grain_rule_id
    
    # 2. Whole grain items (no weekly rules, not standalone)
    wg_all = list(Recipe.objects.filter(
        user=user, archive=False, populate_lunch=True, recipe_type='whole_grain'
    ).select_related('grain_rule'))
    
    # DEBUG: Show ALL whole_grain recipes for lunch
    pass  # print(f"\n🔍 DEBUG: ALL whole_grain recipes for lunch BEFORE Phase 2 filtering:")
    for r in wg_all:
        has_rule = has_weekly_rule(r)
        rule_qty = r.grain_rule.weekly_qty if r.grain_rule else "N/A"
        pass  # print(f"   - {r.name} (standalone={r.standalone}, has_rule={has_rule}, weekly_qty={rule_qty})")
    
    wg_no_rules = [r for r in wg_all if not has_weekly_rule(r) and not r.standalone]
    
    # DEBUG: Show which whole_grain recipes passed the filter
    pass  # print(f"\n🌾 LUNCH PHASE 2: Available whole_grain recipes for grain row (no rules, not standalone):")
    for r in wg_no_rules:
        pass  # print(f"   - {r.name} (standalone={r.standalone}, has_rule={has_weekly_rule(r)})")
    
    # Track used whole grain recipes to promote variety
    wg_used_names = set()
    for day_idx, day in enumerate(days_of_week):
        if not lunch_data[day]['grain'] and wg_no_rules:
            # Prefer unused recipes for variety
            unused_wg = [r for r in wg_no_rules if r.name not in wg_used_names]
            selected = random.choice(unused_wg if unused_wg else wg_no_rules)
            pass  # print(f"   📍 Selected '{selected.name}' for {day} lunch grain row")
            lunch_data[day]['grain'] = selected.name
            # Track rule ID if recipe has grain_rule
            if selected.grain_rule_id:
                lunch_data[day]['grain_rule_id'] = selected.grain_rule_id
            wg_used_names.add(selected.name)
    
    # As a final fallback, if any day is still missing a main dish but
    # there are eligible lunch recipes, fill from the full main_lunch set
    # (ignoring weekly_qty) so "No available meal" is only used when
    # there truly are no usable lunch recipes.
    if all_main_lunch_recipes:
        # Filter out already-used recipes, apply 2-week cooldown (ALWAYS enforced), AND check inventory (can be bypassed)
        available_lunch_fallback = [
            r for r in all_main_lunch_recipes 
            if r.id not in used_main_recipes
            and r.id not in similarity_excluded_ids
            and (not r.last_used or r.last_used.date() < two_weeks_before or r.last_used.date() > two_weeks_after)
            and has_sufficient_inventory(r)
        ]
        print(
            f"[MENU DEBUG] Lunch fallback pool: {len(available_lunch_fallback)} "
            f"recipe(s) available after cooldown & inventory checks."
        )
        
        for day in days_of_week:
            if not lunch_data[day]['meal_name'] and available_lunch_fallback:
                recipe = random.choice(available_lunch_fallback)
                
                # Track this recipe as used
                used_main_recipes.add(recipe.id)
                similarity_excluded_ids |= _get_similarity_excluded_ids(recipe.id)
                # Remove from available pool to prevent reuse
                available_lunch_fallback = [r for r in available_lunch_fallback if r.id != recipe.id]
                
                lunch_data[day]['meal_name'] = recipe.name
                lunch_data[day]['meal_name_rule_id'] = get_recipe_title_rule_id(recipe)
                # If the main lunch recipe has a grain component (e.g. CN Pizza crust),
                # fill the grain row directly so no separate whole_grain side is added.
                grain_component = recipe.grain or ""
                if grain_component and not lunch_data[day]['grain']:
                    lunch_data[day]['grain'] = grain_component
                    if recipe.grain_rule_id:
                        lunch_data[day]['grain_rule_id'] = recipe.grain_rule_id
                if not lunch_data[day]['meat_alternate']:
                    lunch_data[day]['meat_alternate'] = recipe.meat_alternate or ""
                # As a last resort, also bring over any veg/fruit defined on
                # this main lunch recipe if those cells are still empty.
                veg_component = _first_distinct_component(recipe, recipe.veg)
                fruit_component = _first_distinct_component(recipe, recipe.fruit)
                if veg_component and not lunch_data[day]['vegetable'] and veg_component not in _veg_week_names:
                    lunch_data[day]['vegetable'] = veg_component
                    lunch_data[day]['vegetable_rule_id'] = recipe.veg_rule_id
                    _veg_week_names.add(veg_component)
                if fruit_component and not lunch_data[day]['fruit3'] and fruit_component not in _fruit3_week_names:
                    lunch_data[day]['fruit3'] = fruit_component
                    lunch_data[day]['fruit3_rule_id'] = recipe.fruit_rule_id
                    _fruit3_week_names.add(fruit_component)

                print(
                    f"[MENU DEBUG] Lunch {day} main dish: used FALLBACK recipe '{recipe.name}' "
                    f"(id={recipe.id}, type={recipe.recipe_type}) after rules/cooldown/inventory left "
                    f"no primary candidates for this day."
                )

    # Mark any remaining empty main dish cells with out of stock warning
    # BUT only if user hasn't confirmed to ignore inventory (force_ignore_inventory)
    if not force_ignore_inventory:
        for day_idx, day in enumerate(days_of_week):
            if not breakfast_data[day]['bread']:
                breakfast_data[day]['bread'] = "❌ Out of stock"
                print(
                    f"[MENU DEBUG] Breakfast {day} bread: marked OUT OF STOCK – "
                    f"no breakfast bread recipe remained after rules, deduplication, "
                    f"and inventory filters."
                )
        
        for day_idx, day in enumerate(days_of_week):
            if not am_snack_data[day]['bread2']:
                am_snack_data[day]['bread2'] = "❌ Out of stock"
                print(
                    f"[MENU DEBUG] AM snack {day} bread2: marked OUT OF STOCK – "
                    f"no AM snack grain recipe remained after rules, deduplication, "
                    f"and inventory filters."
                )
        
        # Set default if meal_name is still empty
        for day in days_of_week:
            if not lunch_data[day]['meal_name']:
                lunch_data[day]['meal_name'] = "❌ Out of stock"
                print(
                    f"[MENU DEBUG] Lunch {day} main dish: marked OUT OF STOCK – "
                    f"no lunch main recipe remained after rules, cooldown, "
                    f"deduplication, and inventory filters."
                )
    
    # PHASE 3: Process standalone recipes ONLY in days that have main lunch recipes
    for day_idx, recipes_list in standalone_lunch_recipes.items():
        day = days_of_week[day_idx]
        
        # Only place standalone recipes if there's a main lunch dish
        if not lunch_data[day]['meal_name']:
            pass  # print(f"  Skipping {len(recipes_list)} standalone recipe(s) for {day} lunch - no main recipe")
            continue
        
        # Process each standalone recipe - LIMIT: only place if target cell is empty (no cramming)
        for recipe in recipes_list:
            recipe_type = recipe.recipe_type
            
            # INVENTORY CHECK: Side-component standalones use inventory-item unit_size checks.
            if recipe_type in ['fruit', 'vegetable', 'whole_grain']:
                if not has_recipe_name_inventory_fallback(recipe):
                    pass  # print(f"  Skipping standalone '{recipe.name}' for {day} lunch - insufficient inventory")
                    continue
            
            # Place standalone recipe in appropriate field ONLY if empty
            if recipe_type == 'lunch':
                # Skip standalone lunch items if main dish is occupied
                pass
            elif recipe_type == 'whole_grain':
                # Standalone WG: place in add food ONLY if empty
                if not lunch_data[day]['add2']:
                    lunch_data[day]['add2'] = recipe.name
            elif recipe_type == 'vegetable':
                # Standalone vegetable: place ONLY if vegetable row is empty
                if not lunch_data[day]['vegetable']:
                    lunch_data[day]['vegetable'] = recipe.name
                    if recipe.veg_rule_id:
                        lunch_data[day]['vegetable_rule_id'] = recipe.veg_rule_id
            elif recipe_type == 'fruit':
                # Standalone fruit: place ONLY if fruit row is empty
                if not lunch_data[day]['fruit3']:
                    lunch_data[day]['fruit3'] = recipe.name
                    if recipe.fruit_rule_id:
                        lunch_data[day]['fruit3_rule_id'] = recipe.fruit_rule_id

    # === PM SNACK GENERATION ===
    pm_snack_data = {}
    for day in days_of_week:
        # add4: Additional Food (Optional) for PM snack
        pm_snack_data[day] = {
            'choose2': '', 'choose2_rule_id': None,
            'fruit4': '', 'fruit4_rule_id': None,
            'bread3': '', 'bread3_rule_id': None,
            'meat3': '', 'meat3_rule_id': None,
            'add4': '', 'add4_rule_id': None
        }
    
    pm_snack_rule_recipes = rule_assignments['pm_snack']
    
    # Separate standalone recipes for Phase 3 processing
    standalone_pm_snack_recipes = {}
    
    # PHASE 1: Place rule-based recipes (including promoted standalone recipes)
    for day_idx, recipes_list in pm_snack_rule_recipes.items():
        if not recipes_list:
            continue
            
        day = days_of_week[day_idx]
        
        # Process each recipe assigned to this day
        for recipe in recipes_list:
            is_standalone = getattr(recipe, 'standalone', False)
            is_snack_wg = recipe.recipe_type == 'whole_grain'

            # Special handling for standalone recipes:
            # - Standalone WITH fruit_rule/veg_rule: Place in main fruit/veg row (frees Additional Food for grain)
            # - Standalone whole_grain: ONLY goes to Additional Food
            # - Other standalone: Defer to Phase 3
            if is_standalone:
                # Check if this standalone recipe has a fruit_rule or veg_rule (regardless of recipe_type)
                has_fruit_or_veg_rule = (
                    (hasattr(recipe, 'fruit_rule') and recipe.fruit_rule) or
                    (hasattr(recipe, 'veg_rule') and recipe.veg_rule)
                )
                
                if has_fruit_or_veg_rule:
                    # Standalone with fruit/veg rule → place in fruit row only when
                    # the recipe is fruit/vegetable typed or has explicit fruit/veg content.
                    fruit_or_veg_value = _first_distinct_component(
                        recipe,
                        getattr(recipe, 'fruit', None),
                        getattr(recipe, 'veg', None),
                    )
                    can_fill_fruit_row = (
                        recipe.recipe_type in ['fruit', 'vegetable'] or bool(fruit_or_veg_value)
                    )
                    if can_fill_fruit_row:
                        if not pm_snack_data[day]['fruit4']:
                            pm_snack_data[day]['fruit4'] = fruit_or_veg_value or recipe.name
                        continue
                else:
                    # ALL other standalone recipes (including whole_grain) → Defer to Phase 3
                    # This ensures they go through the has_snack_content check and won't be
                    # placed in empty snack periods that aren't being served
                    if day_idx not in standalone_pm_snack_recipes:
                        standalone_pm_snack_recipes[day_idx] = []
                    standalone_pm_snack_recipes[day_idx].append(recipe)
                    continue
            
            # Non-standalone recipe placement
            # Fluid always overwrites
            if recipe.fluid:
                pm_snack_data[day]['choose2'] = recipe.fluid
                pm_snack_data[day]['choose2_rule_id'] = recipe.fluid_rule_id

            # Bread/grain content - WG items go to add food
            if is_snack_wg or recipe.grain:
                # Use recipe.name for WG items to show variety; for non-WG skip values
                # that duplicate the recipe title.
                display_name = recipe.name if is_snack_wg else _first_distinct_component(recipe, recipe.grain)
                # WG items go to Additional Food
                if is_snack_wg:
                    # Always place in add food to not block main snack
                    if display_name and not pm_snack_data[day]['add4']:
                        pm_snack_data[day]['add4'] = display_name
                else:
                    # For snack recipes, grain is an extra component -> Additional Food.
                    if display_name and not pm_snack_data[day]['add4']:
                        pm_snack_data[day]['add4'] = display_name

            # Meat content - always place in meat row
            if recipe.meat:
                if not pm_snack_data[day]['meat3']:
                    pm_snack_data[day]['meat3'] = recipe.meat
                elif not pm_snack_data[day]['add4']:
                    pm_snack_data[day]['add4'] = recipe.meat

            # Fruit/veg content - ALWAYS place in fruit row
            fruit_or_veg = _first_distinct_component(recipe, recipe.fruit, recipe.veg)
            if fruit_or_veg:
                if not pm_snack_data[day]['fruit4']:
                    pm_snack_data[day]['fruit4'] = fruit_or_veg
                elif not pm_snack_data[day]['add4']:
                    pm_snack_data[day]['add4'] = fruit_or_veg
    
    # Fill remaining days with snack recipes without weekly rules AND NOT standalone.
    # For the main snack row (bread3), exclude side-only recipe types.
    pm_snack_all = list(Recipe.objects.filter(
        user=user,
        archive=False,
        populate_pm_snack=True,
    ).select_related('grain_rule', 'fruit_rule', 'veg_rule', 'meat_rule', 'fluid_rule', 'addfood_rule'))
    pm_snack_all = [
        r for r in pm_snack_all
        if r.recipe_type not in ['fruit', 'vegetable', 'whole_grain', 'fluid']
    ]
    
    # PM snack main rows should remain eligible for pm_snack/am_pm_snack recipes,
    # even if they carry weekly rules (e.g., Sunchips with a grain rule).
    if force_ignore_inventory:
        pm_snack_no_rules = [r for r in pm_snack_all if not r.standalone]
        pass  # print(f"   🔓 BYPASSING INVENTORY: Expanded PM snack pool to include recipes with weekly rules")
    else:
        pm_snack_no_rules = [
            r for r in pm_snack_all
            if not r.standalone
            and (
                not has_weekly_rule(r)
                or r.recipe_type in ['pm_snack', 'am_pm_snack']
            )
        ]

    # Fallback: if the populate flag yielded nothing with weekly rules filtered out,
    # relax the weekly-rule filter so at least something gets placed.
    if not pm_snack_no_rules and pm_snack_all:
        if force_ignore_inventory:
            pm_snack_no_rules = [r for r in pm_snack_all if not r.standalone]
        else:
            pm_snack_no_rules = [r for r in pm_snack_all if not r.standalone]

    # Ultimate fallback: use any PM-type recipe for this user.
    if not pm_snack_no_rules:
        pm_snack_all = list(Recipe.objects.filter(
            user=user,
            archive=False,
            recipe_type__in=['pm_snack', 'am_pm_snack']
        ).select_related('grain_rule', 'fruit_rule', 'veg_rule', 'meat_rule', 'fluid_rule', 'addfood_rule'))
        if force_ignore_inventory:
            pm_snack_no_rules = [r for r in pm_snack_all if not r.standalone]
        else:
            pm_snack_no_rules = [r for r in pm_snack_all if not has_weekly_rule(r) and not r.standalone]
    
    # DEDUPLICATION: Filter out already-used main dish recipes.
    # Keep PM snack-typed recipes eligible for PM main rows even if they were
    # referenced earlier by rule assignment in non-main slots.
    total_pm_candidates = len(pm_snack_no_rules)
    pm_snack_before_dedup = pm_snack_no_rules[:]
    pm_snack_no_rules = [
        r for r in pm_snack_no_rules
        if (
            r.id not in used_main_recipes
            or r.recipe_type in ['pm_snack', 'am_pm_snack']
        )
    ]
    filtered_out = [r for r in pm_snack_before_dedup if r.id in used_main_recipes]

    # Count days that still need a main PM snack dish after Phase 1
    days_needing_pm_snack = sum(1 for day in days_of_week if not pm_snack_data[day]['bread3'])

    # If the non-weekly-rule pool is smaller than the days that need filling, supplement
    # with weekly-rule recipes so we don't leave days blank. Weekly-rule recipes were
    # filtered to avoid double-counting with Phase 1, but if Phase 1 placed them only in
    # add4/fruit4 slots (not as bread3), Phase 2 still needs them to fill the main dish row.
    if len(pm_snack_no_rules) < days_needing_pm_snack and pm_snack_all:
        supplemental = [
            r for r in pm_snack_all
            if not r.standalone
            and r.id not in used_main_recipes
            and r.id not in {x.id for x in pm_snack_no_rules}
        ]
        if supplemental:
            pm_snack_no_rules = pm_snack_no_rules + supplemental
            print(
                f"[MENU DEBUG] PM snack Phase 2 supplement: added {len(supplemental)} weekly-rule "
                f"recipe(s) to reach {len(pm_snack_no_rules)} candidate(s) for {days_needing_pm_snack} unfilled days."
            )

    if len(pm_snack_no_rules) < days_needing_pm_snack and pm_snack_before_dedup:
        reuse_candidates = [
            r for r in pm_snack_before_dedup
            if r.id not in {x.id for x in pm_snack_no_rules}
        ]
        if reuse_candidates:
            pm_snack_no_rules = pm_snack_no_rules + reuse_candidates
            print(
                f"[MENU DEBUG] PM snack Phase 2 dedup relax: re-added {len(reuse_candidates)} "
                f"previously-used recipe(s) to cover {days_needing_pm_snack} unfilled day(s)."
            )

    print(
        f"[MENU DEBUG] PM snack Phase 2: {total_pm_candidates} candidate recipe(s) "
        f"before deduplication; excluded {len(filtered_out)} already-used mains; "
        f"{len(pm_snack_no_rules)} candidate(s) remain."
    )
    
    # INVENTORY CHECK: Filter out recipes with insufficient inventory
    # NOTE: This can be bypassed when force_ignore_inventory is True (user confirmed override)
    pm_passed_inventory = []
    pm_failed_inventory = []
    
    if force_ignore_inventory:
        # When bypassing inventory, include ALL recipes regardless of inventory status
        pm_passed_inventory = pm_snack_no_rules
    else:
        # Normal inventory checking
        for r in pm_snack_no_rules:
            if has_sufficient_inventory(r):
                pm_passed_inventory.append(r)
            else:
                pm_failed_inventory.append(r)

        if pm_failed_inventory:
            print(
                f"[MENU DEBUG] PM snack inventory filter: "
                f"{len(pm_failed_inventory)} recipe(s) failed inventory checks; "
                f"examples: {[r.name for r in pm_failed_inventory[:5]]}"
            )
            for r in pm_failed_inventory[:3]:
                print(
                    f"[MENU DEBUG]   PM snack inventory failure for '{r.name}': "
                    f"{get_recipe_ingredients_debug(r)}"
                )
    
    pm_snack_no_rules = pm_passed_inventory

    # Enforce weekly uniqueness for PM snack main row by recipe name.
    used_pm_bread_names = {
        str(pm_snack_data[d].get('bread3', '')).strip()
        for d in days_of_week
        if str(pm_snack_data[d].get('bread3', '')).strip()
        and 'Out of stock' not in str(pm_snack_data[d].get('bread3', ''))
    }
    
    for day_idx, day in enumerate(days_of_week):
        if not pm_snack_data[day]['bread3'] and pm_snack_no_rules:
            candidates_for_day = [r for r in pm_snack_no_rules if r.name not in used_pm_bread_names]
            if not candidates_for_day:
                print(
                    f"[MENU DEBUG] PM snack {day} bread3: no unique recipe name left for this week; "
                    f"leaving empty to avoid repeats."
                )
                continue

            candidate_count = len(candidates_for_day)
            recipe = random.choice(candidates_for_day)
            
            # Track this recipe as used
            used_main_recipes.add(recipe.id)
            used_pm_bread_names.add(recipe.name)
            # Remove only when we still have enough unique recipes to cover remaining days.
            remaining_unfilled_days = sum(1 for d in days_of_week if not pm_snack_data[d]['bread3'])
            if len(pm_snack_no_rules) > remaining_unfilled_days:
                pm_snack_no_rules = [r for r in pm_snack_no_rules if r.id != recipe.id]
            
            pm_snack_data[day]['choose2'] = recipe.fluid or ""
            if recipe.fluid:
                pm_snack_data[day]['choose2_rule_id'] = recipe.fluid_rule_id
            # Use recipe.name for main content (not generic recipe.grain component)
            pm_snack_data[day]['bread3'] = recipe.name
            pm_snack_data[day]['bread3_rule_id'] = get_recipe_title_rule_id(recipe)
            if not pm_snack_data[day]['add4']:
                add_component, add_rule_id = _first_distinct_component_with_rule(
                    recipe,
                    [
                        (recipe.grain, recipe.grain_rule_id),
                        (recipe.addfood, recipe.addfood_rule_id),
                    ]
                )
                pm_snack_data[day]['add4'] = add_component
                pm_snack_data[day]['add4_rule_id'] = add_rule_id
            pm_snack_data[day]['meat3'] = recipe.meat or ""
            fruit_component = _first_distinct_component(recipe, recipe.fruit, recipe.veg)
            if fruit_component:
                pm_snack_data[day]['fruit4'] = fruit_component
                pm_snack_data[day]['fruit4_rule_id'] = recipe.fruit_rule_id or recipe.veg_rule_id

            print(
                f"[MENU DEBUG] PM snack {day} bread3: selected recipe '{recipe.name}' "
                f"(id={recipe.id}, type={recipe.recipe_type}) "
                f"from {candidate_count} candidate(s) after rules/dedup/inventory filters."
            )
    
    # FLUID RULE PLACEMENT (CONDITIONAL): Place fluid_rule recipes in choose2 ONLY if:
    # - populate_pm_snack is True for the fluid recipe
    # - Main snack dish (bread3) has content
    # - Fluid row (choose2) is BLANK
    # NEVER overwrite existing fluid content
    if fluid_rule_recipes:
        fluid_recipe = fluid_rule_recipes[0]
        if fluid_recipe.populate_pm_snack and has_recipe_name_inventory_fallback(fluid_recipe):
            for day in days_of_week:
                has_main_content = pm_snack_data[day]['bread3']
                fluid_is_blank = not pm_snack_data[day]['choose2']
                if has_main_content and fluid_is_blank:
                    pm_snack_data[day]['choose2'] = fluid_recipe.name
                    pm_snack_data[day]['choose2_rule_id'] = fluid_recipe.fluid_rule_id
                    pass  # print(f"  Placed fluid recipe '{fluid_recipe.name}' in {day} PM snack (conditional)")
    
    # PHASE 3: Process standalone recipes ONLY if the PM snack period has main content
    # (If all PM snack fields are empty, user isn't serving PM snack this week)
    for day_idx, recipes_list in standalone_pm_snack_recipes.items():
        day = days_of_week[day_idx]
        
        # Check if PM snack period has any main content (choose2, bread3, meat3, fruit4)
        # If all are empty, user isn't serving this snack period
        has_snack_content = any([
            pm_snack_data[day]['choose2'],
            pm_snack_data[day]['bread3'],
            pm_snack_data[day]['meat3'],
            pm_snack_data[day]['fruit4']
        ])
        
        if not has_snack_content:
            pass  # print(f"  Skipping {len(recipes_list)} standalone recipe(s) for {day} PM snack - snack period not being served")
            continue
        
        # Process each standalone recipe - LIMIT: only place if target cell is empty (no cramming)
        for recipe in recipes_list:
            is_snack_wg = recipe.recipe_type == 'whole_grain'
            
            # INVENTORY CHECK: Side-component standalones use inventory-item unit_size checks.
            if recipe.fluid or is_snack_wg or recipe.recipe_type in ['fruit', 'vegetable']:
                if not has_recipe_name_inventory_fallback(recipe):
                    pass  # print(f"  Skipping standalone '{recipe.name}' for {day} PM snack - insufficient inventory")
                    continue
            
            # Place standalone recipe in appropriate field ONLY if empty
            if recipe.fluid and not pm_snack_data[day]['choose2']:
                pm_snack_data[day]['choose2'] = recipe.fluid
                pm_snack_data[day]['choose2_rule_id'] = recipe.fluid_rule_id

            if is_snack_wg or recipe.grain:
                grain_or_name = recipe.grain or recipe.name
                # Standalone/WG items go to add food ONLY if empty
                if not pm_snack_data[day]['add4']:
                    pm_snack_data[day]['add4'] = grain_or_name
                    # Track rule ID for add4: use grain_rule if grain exists
                    if recipe.grain and recipe.grain_rule_id:
                        pm_snack_data[day]['add4_rule_id'] = recipe.grain_rule_id

            elif recipe.meat:
                if not pm_snack_data[day]['meat3']:
                    pm_snack_data[day]['meat3'] = recipe.meat
                
            elif recipe.fruit or recipe.veg:
                fruit_or_veg = recipe.fruit or recipe.veg
                if not pm_snack_data[day]['fruit4']:
                    pm_snack_data[day]['fruit4'] = fruit_or_veg
    
    # Mark any remaining empty PM snack main dish cells with out of stock warning
    # This is needed so that the side dish filling logic can detect PM snack has content
    # BUT only if user hasn't confirmed to ignore inventory (force_ignore_inventory)
    if not force_ignore_inventory:
        for day_idx, day in enumerate(days_of_week):
            if not pm_snack_data[day]['bread3']:
                pm_snack_data[day]['bread3'] = "❌ Out of stock"
                pass  # print(f"   ⚠️ WARNING: No PM snack recipes available for {day} due to insufficient inventory")
    
    # Don't add "Out of stock" warnings to cells - missing rules will be shown in alert above table
    
    # Determine which meal periods the user actually serves (has non-standalone recipes for)
    # This is used both for filtering out-of-stock warnings and for side dish placement
    all_recipes = Recipe.objects.filter(user=user, archive=False)
    
    user_serves_breakfast = all_recipes.filter(
        populate_breakfast=True,
        standalone=False
    ).exists() or all_recipes.filter(
        recipe_type='breakfast',
        standalone=False
    ).exists()
    
    user_serves_am_snack = all_recipes.filter(
        populate_am_snack=True,
        recipe_type__in=['am_snack', 'am_pm_snack'],
        standalone=False
    ).exists()
    
    user_serves_lunch = all_recipes.filter(
        populate_lunch=True,
        standalone=False
    ).exists() or all_recipes.filter(
        recipe_type='lunch',
        standalone=False
    ).exists()
    
    user_serves_pm_snack = all_recipes.filter(
        populate_pm_snack=True,
        recipe_type__in=['pm_snack', 'am_pm_snack'],
        standalone=False
    ).exists()
    
    pass  # print(f"🍽️  User serves: Breakfast={'✓' if user_serves_breakfast else '✗'}, AM Snack={'✓' if user_serves_am_snack else '✗'}, Lunch={'✓' if user_serves_lunch else '✗'}, PM Snack={'✓' if user_serves_pm_snack else '✗'}")

    # FINAL VALIDATION: every populated cell must resolve to a recipe reference and pass
    # inventory checks, unless that recipe has ignore_inventory=True or global override is on.
    # This guarantees rule placements, standalones, and main-dish/component fills all follow
    # the same inventory policy.
    PLACEHOLDER_VALUES = {
        "No available breakfast option",
        "No available meal",
    }

    recipe_lookup_cache = {}
    side_dish_lookup_cache = {}

    def get_recipe_by_name_cached(name):
        key = (name or '').strip()
        if not key:
            return None
        if key in recipe_lookup_cache:
            return recipe_lookup_cache[key]
        recipe_lookup_cache[key] = Recipe.objects.filter(user=user, archive=False, name=key).first()
        return recipe_lookup_cache[key]

    def get_side_dish_by_name_cached(name):
        key = (name or '').strip()
        if not key:
            return None
        if key in side_dish_lookup_cache:
            return side_dish_lookup_cache[key]
        side_dish_lookup_cache[key] = Inventory.objects.filter(
            user=user,
            item=key,
            is_side_dish=True,
        ).first()
        return side_dish_lookup_cache[key]

    def is_cell_inventory_valid(cell_value):
        value = str(cell_value or '').strip()
        if not value:
            return True
        if "Out of stock" in value or value in PLACEHOLDER_VALUES:
            return True
        if force_ignore_inventory:
            return True

        recipe = get_recipe_by_name_cached(value)
        if recipe:
            if getattr(recipe, 'ignore_inventory', False):
                return True
            return has_sufficient_inventory(recipe)

        # Support direct side-dish inventory items that are not represented as recipes.
        side_dish = get_side_dish_by_name_cached(value)
        if side_dish:
            conv_to_base = side_dish.conversion_to_base or 1
            inventory_units = side_dish.total_quantity or side_dish.quantity or 0
            available_base = inventory_units * conv_to_base
            portion_per_student = side_dish.unit_size if side_dish.unit_size and side_dish.unit_size > 0 else 1
            required_base = portion_per_student * estimated_daily_students
            return available_base >= required_base

        # Unknown values are left untouched; main rows are normalized later.
        return True

    def validate_meal_cells(meal_name, meal_data, fields):
        for day in days_of_week:
            for field in fields:
                cell_value = meal_data[day].get(field, '')
                if is_cell_inventory_valid(cell_value):
                    continue

                meal_data[day][field] = "❌ Out of stock ❌"
                rule_id_key = f"{field}_rule_id"
                if rule_id_key in meal_data[day]:
                    meal_data[day][rule_id_key] = None
                print(
                    f"[MENU DEBUG] {meal_name} {day} {field}: replaced '{cell_value}' "
                    f"with OUT OF STOCK after final inventory validation."
                )

    # Only validate main-dish anchor rows here; component rows can contain
    # ingredient labels (not recipe names), which should not be recipe-validated.
    validate_meal_cells('Breakfast', breakfast_data, ['bread'])
    validate_meal_cells('AM snack', am_snack_data, ['bread2'])
    validate_meal_cells('Lunch', lunch_data, ['meal_name'])
    validate_meal_cells('PM snack', pm_snack_data, ['bread3'])

    # Re-assert mandatory main rows after final validation so they are never blank.
    if not force_ignore_inventory:
        for day in days_of_week:
            if not breakfast_data[day]['bread'] or breakfast_data[day]['bread'] == "No available breakfast option":
                breakfast_data[day]['bread'] = "❌ Out of stock"
            if not am_snack_data[day]['bread2']:
                am_snack_data[day]['bread2'] = "❌ Out of stock"
            if not lunch_data[day]['meal_name'] or lunch_data[day]['meal_name'] == "No available meal":
                lunch_data[day]['meal_name'] = "❌ Out of stock"
            if not pm_snack_data[day]['bread3']:
                pm_snack_data[day]['bread3'] = "❌ Out of stock"
    
    # Check for out-of-stock items (before returning response)
    # Track each specific item that's out of stock with meal period and component name
    # BUT only if user hasn't confirmed to ignore inventory (force_ignore_inventory)
    out_of_stock_items = []
    
    # Only check for out-of-stock items if inventory is NOT being force-ignored
    print(f"🔍 Before checking out of stock - force_ignore_inventory={force_ignore_inventory}")
    if not force_ignore_inventory:
        # Check each day for out-of-stock markers in main dish fields
        for day in days_of_week:
            # Check breakfast bread (main component)
            if breakfast_data[day]['bread'] and "Out of stock" in breakfast_data[day]['bread']:
                out_of_stock_items.append({
                    'day': day,
                    'meal': 'Breakfast',
                    'component': 'Bread or Bread Alternate(s)'
                })
            
            # Check AM snack bread (main component)
            if am_snack_data[day]['bread2'] and "Out of stock" in am_snack_data[day]['bread2']:
                out_of_stock_items.append({
                    'day': day,
                    'meal': 'AM Snack',
                    'component': 'Bread or Bread Alternate(s)'
                })
            
            # Check lunch main dish
            if lunch_data[day]['meal_name'] and "Out of stock" in lunch_data[day]['meal_name']:
                out_of_stock_items.append({
                    'day': day,
                    'meal': 'Lunch',
                    'component': 'Main Dish'
                })
            
            # Check PM snack bread (main component)
            if pm_snack_data[day]['bread3'] and "Out of stock" in pm_snack_data[day]['bread3']:
                out_of_stock_items.append({
                    'day': day,
                    'meal': 'PM Snack',
                    'component': 'Bread or Bread Alternate(s)'
                })
    
    # FILTER: Remove out-of-stock items for meal periods the user doesn't serve
    # This prevents warnings for AM/PM snacks if the user never serves those periods
    if out_of_stock_items:
        filtered_items = []
        for item in out_of_stock_items:
            if item['meal'] == 'Breakfast' and user_serves_breakfast:
                filtered_items.append(item)
            elif item['meal'] == 'AM Snack' and user_serves_am_snack:
                filtered_items.append(item)
            elif item['meal'] == 'Lunch' and user_serves_lunch:
                filtered_items.append(item)
            elif item['meal'] == 'PM Snack' and user_serves_pm_snack:
                filtered_items.append(item)
        
        out_of_stock_items = filtered_items
        pass  # print(f"🔍 FILTERED out-of-stock items to exclude non-served meal periods: {len(out_of_stock_items)} items")
    
    # CLEANUP: Remove Additional Food from meal periods that have no main content
    # This prevents promoted standalones from appearing in empty meal periods
    
    for day in days_of_week:
        # Breakfast: if no bread (main content), clear add1 (Additional Food)
        if not breakfast_data[day]['bread'] and breakfast_data[day]['add1']:
            breakfast_data[day]['add1'] = ''
        
        # AM Snack: if no main content (choose1, bread2, meat1, fruit2), clear add3
        has_am_snack_main = any([
            am_snack_data[day]['choose1'],
            am_snack_data[day]['bread2'],
            am_snack_data[day]['meat1'],
            am_snack_data[day]['fruit2']
        ])
        if not has_am_snack_main and am_snack_data[day]['add3']:
            am_snack_data[day]['add3'] = ''
        
        # Lunch: if no meal_name (main content), clear add2 (Additional Food)
        if not lunch_data[day]['meal_name'] and lunch_data[day]['add2']:
            lunch_data[day]['add2'] = ''
        
        # PM Snack: if no main content (choose2, bread3, meat3, fruit4), clear add4
        has_pm_snack_main = any([
            pm_snack_data[day]['choose2'],
            pm_snack_data[day]['bread3'],
            pm_snack_data[day]['meat3'],
            pm_snack_data[day]['fruit4']
        ])
        if not has_pm_snack_main and pm_snack_data[day]['add4']:
            pm_snack_data[day]['add4'] = ''
    
    # POST-PROCESSING: Count rule satisfaction and fill gaps with standalone recipes
    # This is the correct moment to add standalones - AFTER main menu is generated
    
    def get_recipe_rules(recipe):
        """Get all rules attached to a recipe."""
        rules = []
        for attr in ['grain_rule', 'fruit_rule', 'veg_rule', 'meat_rule', 'fluid_rule', 'addfood_rule']:
            rule = getattr(recipe, attr, None)
            if rule and rule.weekly_qty:
                rules.append(rule)
        return rules
    
    # Count how many DAYS each rule appears in the generated menu
    # (weekly_qty means "appears on N different days")
    rule_day_counts = {}  # {rule_id: set of day_indices}
    
    def _track_rule_day(rule_obj, day_idx):
        if not rule_obj:
            return
        if rule_obj.id not in rule_day_counts:
            rule_day_counts[rule_obj.id] = set()
        rule_day_counts[rule_obj.id].add(day_idx)

    def _track_rule_day_id(rule_id, day_idx):
        if not rule_id:
            return
        if rule_id not in rule_day_counts:
            rule_day_counts[rule_id] = set()
        rule_day_counts[rule_id].add(day_idx)

    def _preferred_rule_attr_for_field(field_name):
        if field_name in {'fluid_milk', 'lunch_milk', 'choose1', 'choose2'}:
            return 'fluid_rule'
        if field_name in {'fruit', 'fruit2', 'fruit3', 'fruit4'}:
            return 'fruit_rule'
        if field_name == 'vegetable':
            return 'veg_rule'
        if field_name in {'grain', 'bread', 'bread2', 'bread3'}:
            return 'grain_rule'
        if field_name in {'add1', 'add3', 'add4'}:
            return 'grain_rule'
        if field_name == 'add2':
            return 'addfood_rule'
        return None

    def _resolve_recipe_for_field(recipe_name, field_name):
        candidates = list(Recipe.objects.filter(user=user, archive=False, name=recipe_name))
        if not candidates:
            return None

        preferred_attr = _preferred_rule_attr_for_field(field_name)
        if preferred_attr:
            preferred = [r for r in candidates if getattr(r, preferred_attr, None)]
            if preferred:
                return preferred[0]

        with_any_rule = [r for r in candidates if get_recipe_rules(r)]
        if with_any_rule:
            return with_any_rule[0]

        return candidates[0]

    whole_grain_rule = Rule.objects.filter(user=user, rule__iexact='Whole Grain').first()
    # Only the dedicated lunch grain row should trigger the whole-grain safety fallback.
    # 'bread', 'bread2', 'bread3' hold main dish recipes (any type) and must NOT
    # auto-count as Whole Grain — that causes the rule to appear satisfied before
    # the add3/add4 grain side-dish filler has a chance to run.
    whole_grain_fields = {'grain'}
    whole_grain_non_count_fields = {'bread', 'bread2', 'bread3'}

    def check_recipe_in_cell(recipe_name, day_idx, field_name=None, explicit_rule_id=None):
        """Count rule occurrences for one rendered cell.
        Uses field-aware recipe resolution to avoid wrong matches when names are duplicated."""
        # Prefer explicit rule ids tracked at placement time; they are the authoritative source.
        if explicit_rule_id:
            _track_rule_day_id(explicit_rule_id, day_idx)
            return

        value = str(recipe_name or '').strip()
        if not value or "Out of stock" in value or value in {"No available breakfast option", "No available meal"}:
            return

        # Side dish rules should always count when the rendered cell is an inventory side dish.
        side_dish = Inventory.objects.filter(user=user, item=value, is_side_dish=True).first()
        counted = False
        if side_dish and side_dish.rule:
            if not (
                whole_grain_rule
                and side_dish.rule.id == whole_grain_rule.id
                and field_name in whole_grain_non_count_fields
            ):
                _track_rule_day(side_dish.rule, day_idx)
            counted = True

        recipe = _resolve_recipe_for_field(value, field_name)
        if recipe:
            rules = get_recipe_rules(recipe)
            for rule in rules:
                if (
                    whole_grain_rule
                    and rule.id == whole_grain_rule.id
                    and field_name in whole_grain_non_count_fields
                ):
                    continue
                _track_rule_day(rule, day_idx)
                counted = True
            if rules:
                return

        # Final fallback: count rule from same-name inventory item for ANY cell.
        # This allows inventory-driven rule fulfillment (not just side-dish/component rows)
        # to contribute accurately to insufficiency checks.
        inventory_item = Inventory.objects.filter(user=user, item=value).select_related('rule').first()
        if inventory_item and inventory_item.rule:
            if not (
                whole_grain_rule
                and inventory_item.rule.id == whole_grain_rule.id
                and field_name in whole_grain_non_count_fields
            ):
                _track_rule_day(inventory_item.rule, day_idx)
                counted = True

        # Safety fallback: grain-designated rows should satisfy Whole Grain when the
        # cell is visibly filled but rule metadata is missing on recipe/inventory.
        if not counted and field_name in whole_grain_fields and whole_grain_rule:
            _track_rule_day(whole_grain_rule, day_idx)
    
    # Scan ALL *_rule_id fields across ALL meal periods to count rule appearances
    for day_idx, day in enumerate(days_of_week):
        for data_dict in [breakfast_data[day], am_snack_data[day], lunch_data[day], pm_snack_data[day]]:
            for key, val in data_dict.items():
                if key.endswith('_rule_id') and val:
                    _track_rule_day_id(val, day_idx)
    
    # For each rule, check if it needs more appearances
    all_rules = Rule.objects.filter(user=user, weekly_qty__gt=0)
    for rule in all_rules:
        current_count = len(rule_day_counts.get(rule.id, set()))
        needed_count = rule.weekly_qty
        
        if current_count >= needed_count:
            pass  # print(f"✅ Rule '{rule.rule}' satisfied: appears on {current_count}/{needed_count} days")
            continue
        
        # SPECIAL CASE: Fluid rules are handled by mandatory daily placement
        # They should NEVER be added to Additional Food rows in post-processing
        # Check if any recipe with this rule has fluid_rule set
        is_fluid_rule = False
        for recipe in Recipe.objects.filter(user=user, archive=False):
            if hasattr(recipe, 'fluid_rule') and recipe.fluid_rule and recipe.fluid_rule.id == rule.id:
                is_fluid_rule = True
                break
        
        if is_fluid_rule:
            pass  # print(f"⚠️  Rule '{rule.rule}' is a fluid rule - skipping post-processing (handled by mandatory daily placement)")
            continue
        
        # Rule needs more appearances - Phase 3 fills from recipe candidates, Phase 4 from inventory side dishes
        gap = needed_count - current_count
        pass  # print(f"⚠️  Rule '{rule.rule}' needs {gap} more appearances ({current_count}/{needed_count})")

        # PHASE 3: Find ALL recipe candidates for this rule via a single indexed query.
        # Includes standalone of any type PLUS non-standalone veg/fruit/grain side recipes.
        # Non-standalone main dish types (lunch, breakfast, snack) are handled in Phase 1/2 only.
        from django.db.models import Q as _Q
        rule_candidate_recipes = list(Recipe.objects.filter(
            user=user
        ).filter(
            _Q(grain_rule_id=rule.id) | _Q(fruit_rule_id=rule.id) | _Q(veg_rule_id=rule.id) |
            _Q(meat_rule_id=rule.id) | _Q(fluid_rule_id=rule.id) | _Q(addfood_rule_id=rule.id)
        ).filter(
            _Q(standalone=True) | _Q(recipe_type__in=('vegetable', 'fruit', 'whole_grain'))
        ).select_related('grain_rule', 'fruit_rule', 'veg_rule', 'meat_rule', 'fluid_rule', 'addfood_rule'))

        # INVENTORY CHECK for Phase 3 candidates
        standalone_with_inventory = []
        for recipe in rule_candidate_recipes:
            # Skip inventory check for fluid rules
            if hasattr(recipe, 'fluid_rule') and recipe.fluid_rule:
                standalone_with_inventory.append(recipe)
                continue
            if force_ignore_inventory:
                standalone_with_inventory.append(recipe)
                continue
            if has_recipe_name_inventory_fallback(recipe):
                standalone_with_inventory.append(recipe)
        # standalone_with_inventory may be empty — Phase 4 (side-dish inventory) still runs below.

        # Find days that don't have this rule yet
        days_without_rule = [i for i in range(len(days_of_week)) if i not in rule_day_counts.get(rule.id, set())]
        
        # Add Phase 3 recipe candidates to fill rule gaps
        # - Grain rule: Additional Food only
        # - Fruit/veg rules: Main fruit/veg rows (if empty), then Additional Food
        # - Other rules: Additional Food
        added = 0
        for day_idx in days_without_rule:
            if added >= gap:
                break
            if not standalone_with_inventory:
                break

            day = days_of_week[day_idx]
            recipe = random.choice(standalone_with_inventory)
            
            # Check what kind of rule this recipe has
            has_veg_rule = hasattr(recipe, 'veg_rule') and recipe.veg_rule
            has_fruit_rule = hasattr(recipe, 'fruit_rule') and recipe.fruit_rule
            has_grain_rule = hasattr(recipe, 'grain_rule') and recipe.grain_rule
            
            placed = False
            
            # VEG RULE: Place in vegetable row (not Additional Food)
            if has_veg_rule:
                # Try lunch vegetable row first (check permission)
                if recipe.populate_lunch and lunch_data[day]['meal_name'] and not lunch_data[day]['vegetable']:
                    lunch_data[day]['vegetable'] = recipe.name
                    lunch_data[day]['vegetable_rule_id'] = recipe.veg_rule_id
                    placed = True
                    added += 1
                    pass  # print(f"  Added '{recipe.name}' to lunch vegetable row on {day}")
                # Try breakfast fruit row as fallback (fruit/veg are same row, check permission)
                elif recipe.populate_breakfast and breakfast_data[day]['bread'] and not breakfast_data[day]['fruit']:
                    breakfast_data[day]['fruit'] = recipe.name
                    breakfast_data[day]['fruit_rule_id'] = recipe.veg_rule_id
                    placed = True
                    added += 1
                    pass  # print(f"  Added '{recipe.name}' to breakfast fruit row on {day}")
            
            # FRUIT RULE: Place in fruit row (not Additional Food)
            elif has_fruit_rule:
                # Try lunch fruit row first (check permission)
                if recipe.populate_lunch and lunch_data[day]['meal_name'] and not lunch_data[day]['fruit3']:
                    lunch_data[day]['fruit3'] = recipe.name
                    lunch_data[day]['fruit3_rule_id'] = recipe.fruit_rule_id
                    placed = True
                    added += 1
                    pass  # print(f"  Added '{recipe.name}' to lunch fruit row on {day}")
                # Try breakfast fruit row as fallback (check permission)
                elif recipe.populate_breakfast and breakfast_data[day]['bread'] and not breakfast_data[day]['fruit']:
                    breakfast_data[day]['fruit'] = recipe.name
                    breakfast_data[day]['fruit_rule_id'] = recipe.fruit_rule_id
                    placed = True
                    added += 1
                    pass  # print(f"  Added '{recipe.name}' to breakfast fruit row on {day}")
            
            # GRAIN RULE: For lunch, prioritize Grain row; for breakfast, use Additional Food
            elif has_grain_rule:
                # Try lunch Grain row FIRST (dedicated grain component, check permission)
                if recipe.populate_lunch and lunch_data[day]['meal_name'] and not lunch_data[day]['grain']:
                    lunch_data[day]['grain'] = recipe.name
                    lunch_data[day]['grain_rule_id'] = recipe.grain_rule_id
                    placed = True
                    added += 1
                    pass  # print(f"  Added '{recipe.name}' to lunch Grain row on {day}")
                # Try breakfast Additional Food (check permission)
                elif not placed and recipe.populate_breakfast and breakfast_data[day]['bread'] and not breakfast_data[day]['add1']:
                    breakfast_data[day]['add1'] = recipe.name
                    breakfast_data[day]['add1_rule_id'] = recipe.grain_rule_id
                    placed = True
                    added += 1
                    pass  # print(f"  Added '{recipe.name}' to breakfast Additional Food on {day}")
                # Try lunch Additional Food (if Grain row already filled, check permission)
                elif not placed and recipe.populate_lunch and lunch_data[day]['meal_name'] and not lunch_data[day]['add2']:
                    lunch_data[day]['add2'] = recipe.name
                    lunch_data[day]['add2_rule_id'] = recipe.grain_rule_id
                    placed = True
                    added += 1
                    pass  # print(f"  Added '{recipe.name}' to lunch Additional Food on {day} (Grain row already filled)")
            
            # OTHER RULES: Additional Food
            else:
                # Try breakfast Additional Food (check permission)
                if recipe.populate_breakfast and breakfast_data[day]['bread'] and not breakfast_data[day]['add1']:
                    breakfast_data[day]['add1'] = recipe.name
                    breakfast_data[day]['add1_rule_id'] = rule.id
                    placed = True
                    added += 1
                    pass  # print(f"  Added '{recipe.name}' to breakfast Additional Food on {day}")
                # Try lunch Additional Food (check permission)
                elif not placed and recipe.populate_lunch and lunch_data[day]['meal_name'] and not lunch_data[day]['add2']:
                    lunch_data[day]['add2'] = recipe.name
                    lunch_data[day]['add2_rule_id'] = rule.id
                    placed = True
                    added += 1
                    pass  # print(f"  Added '{recipe.name}' to lunch Additional Food on {day}")
            
            if placed:
                # Mark this day as having the rule
                if rule.id not in rule_day_counts:
                    rule_day_counts[rule.id] = set()
                rule_day_counts[rule.id].add(day_idx)
        
        if added > 0:
            pass  # print(f"✅ Rule '{rule.rule}' now satisfied: {current_count + added}/{needed_count} days")
        elif added == 0 and gap > 0:
            pass  # print(f"  ⚠️ Could not fill all gaps - no empty Additional Food slots available")

        # If standalone recipes could not fully satisfy this rule, try side-dish inventory
        # items that are explicitly linked to the same rule.
        remaining_gap = needed_count - len(rule_day_counts.get(rule.id, set()))
        if remaining_gap > 0:
            side_dish_candidates = list(
                Inventory.objects.filter(user=user, is_side_dish=True, rule_id=rule.id).select_related('rule')
            )
            if side_dish_candidates:
                for day_idx in range(len(days_of_week)):
                    if remaining_gap <= 0:
                        break
                    if day_idx in rule_day_counts.get(rule.id, set()):
                        continue

                    day = days_of_week[day_idx]
                    placed = False

                    random.shuffle(side_dish_candidates)
                    for side_dish in side_dish_candidates:
                        if not force_ignore_inventory:
                            conv_to_base = float(side_dish.conversion_to_base or 1)
                            inventory_units = float(side_dish.total_quantity or side_dish.quantity or 0)
                            available_base = inventory_units * conv_to_base
                            portion_per_student = float(side_dish.unit_size or 0)
                            required_base = portion_per_student * estimated_daily_students
                            if portion_per_student > 0 and available_base < required_base:
                                continue

                        category_text = str(side_dish.category or '').lower()
                        is_veg = 'vegetable' in category_text
                        is_fruit = 'fruit' in category_text

                        if side_dish.populate_lunch and lunch_data[day]['meal_name']:
                            if is_veg and not lunch_data[day]['vegetable']:
                                lunch_data[day]['vegetable'] = side_dish.item
                                lunch_data[day]['vegetable_rule_id'] = rule.id
                                placed = True
                            elif is_fruit and not lunch_data[day]['fruit3']:
                                lunch_data[day]['fruit3'] = side_dish.item
                                lunch_data[day]['fruit3_rule_id'] = rule.id
                                placed = True
                            elif not is_fruit and not is_veg and not lunch_data[day]['add2']:
                                lunch_data[day]['add2'] = side_dish.item
                                lunch_data[day]['add2_rule_id'] = rule.id
                                placed = True

                        # Fruit/veg items fall back to the breakfast fruit row — never to add1
                        if not placed and (is_fruit or is_veg) and side_dish.populate_breakfast and breakfast_data[day]['bread'] and not breakfast_data[day]['fruit']:
                            breakfast_data[day]['fruit'] = side_dish.item
                            breakfast_data[day]['fruit_rule_id'] = rule.id
                            placed = True

                        # Non-fruit/veg items (and absolute last resort) fall to add slots
                        if not placed and not is_fruit and not is_veg and side_dish.populate_breakfast and breakfast_data[day]['bread'] and not breakfast_data[day]['add1']:
                            breakfast_data[day]['add1'] = side_dish.item
                            breakfast_data[day]['add1_rule_id'] = rule.id
                            placed = True

                        if not placed and not is_fruit and not is_veg and side_dish.populate_am_snack and am_snack_data[day]['bread2'] and not am_snack_data[day]['add3']:
                            am_snack_data[day]['add3'] = side_dish.item
                            am_snack_data[day]['add3_rule_id'] = rule.id
                            placed = True

                        if not placed and not is_fruit and not is_veg and side_dish.populate_pm_snack and pm_snack_data[day]['bread3'] and not pm_snack_data[day]['add4']:
                            pm_snack_data[day]['add4'] = side_dish.item
                            pm_snack_data[day]['add4_rule_id'] = rule.id
                            placed = True

                        if placed:
                            _track_rule_day_id(rule.id, day_idx)
                            remaining_gap -= 1
                            break

    # === PHASE 5: RANDOM FILLER FOR REMAINING EMPTY VEG/FRUIT CELLS (RECIPE POOL) ===
    # Phase 5A (force_ignore_inventory=False / "leave as is"):
    #   Only fill remaining empty cells if ALL non-fluid rules are already satisfied.
    #   If any rule still has a gap, leave cells empty — Phase 6 will report the missing flag.
    # Phase 5B (force_ignore_inventory=True / "yes continue generating"):
    #   Always fill remaining empty cells after rule-gap attempts above.

    # Pre-compute fluid rule IDs to exclude from satisfaction check
    _phase5_fluid_rule_ids = set()
    for _r5 in Recipe.objects.filter(user=user, archive=False):
        if hasattr(_r5, 'fluid_rule') and _r5.fluid_rule:
            _phase5_fluid_rule_ids.add(_r5.fluid_rule_id)

    _all_rules_satisfied = all(
        len(rule_day_counts.get(r.id, set())) >= r.weekly_qty
        for r in all_rules
        if r.id not in _phase5_fluid_rule_ids
    )
    # _should_fill_random is also checked inside the inventory side-dish fill loop below
    _should_fill_random = force_ignore_inventory or _all_rules_satisfied

    if _should_fill_random:
        # Lunch vegetable row: pool = all populate_lunch vegetable recipes with inventory.
        # Phase 5B: include any recipe; Phase 5A: exclude recipes with an unsatisfied weekly rule.
        veg_all = list(Recipe.objects.filter(
            user=user, populate_lunch=True, recipe_type='vegetable'
        ).select_related('veg_rule'))
        if force_ignore_inventory:
            veg_pool = veg_all
        else:
            veg_pool = [r for r in veg_all if not has_weekly_rule(r) and has_sufficient_inventory(r)]

        veg_used_names = set(
            str(lunch_data[day].get('vegetable', '') or '').strip()
            for day in days_of_week
            if lunch_data[day].get('vegetable') and 'Out of stock' not in str(lunch_data[day].get('vegetable'))
        )
        for day_idx, day in enumerate(days_of_week):
            if lunch_data[day]['meal_name'] and not lunch_data[day]['vegetable'] and veg_pool:
                unused_veg = [r for r in veg_pool if r.name not in veg_used_names]
                # Only fill with unused recipes; leave remaining days empty for inventory side dishes
                if unused_veg:
                    selected = random.choice(unused_veg)
                    lunch_data[day]['vegetable'] = selected.name
                    if selected.veg_rule_id:
                        lunch_data[day]['vegetable_rule_id'] = selected.veg_rule_id
                    print(
                        f"[MENU DEBUG] Lunch {day} vegetable: Phase 5 filler '{selected.name}' "
                        f"(id={selected.id}, standalone={selected.standalone}, "
                        f"veg_rule_id={selected.veg_rule_id}) from {len(unused_veg)} candidate(s)."
                    )
                    veg_used_names.add(selected.name)

        # Lunch fruit row: pool = all populate_lunch fruit recipes with inventory.
        fruit_all = list(Recipe.objects.filter(
            user=user, populate_lunch=True, recipe_type='fruit'
        ).select_related('fruit_rule'))
        if force_ignore_inventory:
            fruit_pool = fruit_all
        else:
            fruit_pool = [r for r in fruit_all if not has_weekly_rule(r) and has_sufficient_inventory(r)]

        fruit_used_names = set(
            str(lunch_data[day].get('fruit3', '') or '').strip()
            for day in days_of_week
            if lunch_data[day].get('fruit3') and 'Out of stock' not in str(lunch_data[day].get('fruit3'))
        )
        for day_idx, day in enumerate(days_of_week):
            if lunch_data[day]['meal_name'] and not lunch_data[day]['fruit3'] and fruit_pool:
                unused_fruit = [r for r in fruit_pool if r.name not in fruit_used_names]
                # Only fill with unused recipes; leave remaining days empty for inventory side dishes
                if unused_fruit:
                    selected = random.choice(unused_fruit)
                    lunch_data[day]['fruit3'] = selected.name
                    if selected.fruit_rule_id:
                        lunch_data[day]['fruit3_rule_id'] = selected.fruit_rule_id
                    fruit_used_names.add(selected.name)

    # missing_rules is computed in Phase 6 (final re-scan after side-dish fill completes).
    missing_rules = []
    
    # === FILL BLANK FRUIT/VEG FIELDS WITH SIDE DISHES ===
    # After all rule processing, fill remaining blank fruit/vegetable fields
    # with randomly selected inventory items marked as side dishes (NO DUPLICATES)
    pass  # print("\n🥗 FILLING BLANK FRUIT/VEG FIELDS WITH SIDE DISHES")
    
    # Note: user_serves_* variables were already calculated earlier for out-of-stock filtering
    # and are reused here to prevent side dish placement in periods the user doesn't serve
    pass  # print(f"   🍽️  Checking meal period availability for side dish placement:")
    pass  # print(f"      Breakfast: {'✓' if user_serves_breakfast else '✗'}")
    pass  # print(f"      AM Snack: {'✓' if user_serves_am_snack else '✗'}")
    pass  # print(f"      Lunch: {'✓' if user_serves_lunch else '✗'}")
    pass  # print(f"      PM Snack: {'✓' if user_serves_pm_snack else '✗'}")
    
    # Get side dish inventory items for this user that can serve at least one day's estimate
    available_side_dishes = []
    side_dish_remaining_base = {}
    for side_dish in Inventory.objects.filter(user=user, is_side_dish=True):
        conv_to_base = side_dish.conversion_to_base or 1
        inventory_units = side_dish.total_quantity or side_dish.quantity or 0
        available_base = inventory_units * conv_to_base
        portion_per_student = side_dish.unit_size if side_dish.unit_size and side_dish.unit_size > 0 else 1
        required_base = portion_per_student * estimated_daily_students
        if force_ignore_inventory or available_base >= required_base:
            available_side_dishes.append(side_dish)
            side_dish_remaining_base[side_dish.id] = available_base
    last_selected_by_slot = {
        'breakfast_fruit': None,
        'am_snack_fruit2': None,
        'am_snack_add3': None,
        'lunch_vegetable': None,
        'lunch_fruit3': None,
        'pm_snack_fruit4': None,
        'pm_snack_add4': None,
    }

    # Remaining rule deficit map (daily appearances). Used to avoid over-filling
    # grain side dishes once the related rule is already satisfied.
    required_days_by_rule_id = {rule.id: rule.weekly_qty for rule in all_rules}

    def _remaining_rule_days(rule_id):
        required = required_days_by_rule_id.get(rule_id)
        if not required:
            return 0
        current = len(rule_day_counts.get(rule_id, set()))
        return max(required - current, 0)

    def _side_dish_rule_text(side_dish):
        return str(getattr(getattr(side_dish, 'rule', None), 'rule', '') or '').lower()

    def _is_fruit_or_veg_side_dish(side_dish):
        category_text = str(getattr(side_dish, 'category', '') or '').lower()
        rule_text = _side_dish_rule_text(side_dish)
        return (
            'fruit' in category_text
            or 'vegetable' in category_text
            or 'juice' in category_text
            or 'fruit' in rule_text
            or 'veg' in rule_text
            or 'vegetable' in rule_text
            or 'berry' in rule_text
        )

    def _is_grain_side_dish(side_dish):
        category_text = str(getattr(side_dish, 'category', '') or '').lower()
        rule_text = _side_dish_rule_text(side_dish)
        return (
            'grain' in category_text
            or 'grain' in rule_text
            or 'whole grain' in rule_text
        )

    def _required_base_for_side_dish(side_dish):
        portion_per_student = side_dish.unit_size if side_dish.unit_size and side_dish.unit_size > 0 else 1
        return portion_per_student * estimated_daily_students

    def _can_reserve_side_dish(side_dish):
        if force_ignore_inventory:
            return True
        return side_dish_remaining_base.get(side_dish.id, 0) >= _required_base_for_side_dish(side_dish)

    def _reserve_side_dish(side_dish):
        if force_ignore_inventory:
            return True
        required_base = _required_base_for_side_dish(side_dish)
        current_base = side_dish_remaining_base.get(side_dish.id, 0)
        if current_base < required_base:
            return False
        side_dish_remaining_base[side_dish.id] = current_base - required_base
        return True

    # Week-level used names per slot — exhausted before repeating
    _week_used_by_slot = {}

    def _pick_side_dish(candidates, slot_key, day_used_names, group_used=None):
        """Exhaust all options before repeating within a category (fruit, veg, grain).
        group_used: shared mutable set across ALL slots of the same type (e.g. all fruit slots).
        Items already in group_used are deprioritized to the repeat tier so every unique
        option appears once before anything repeats."""
        if not candidates:
            return None
        week_used = _week_used_by_slot.setdefault(slot_key, set())
        _group = group_used if group_used is not None else week_used
        # Fresh tier: not yet used in ANY same-type slot this week AND not used today
        fresh = [
            sd for sd in candidates
            if sd.item not in _group and sd.item not in day_used_names
            and _can_reserve_side_dish(sd)
        ]
        if fresh:
            chosen = random.choice(fresh)
            if _reserve_side_dish(chosen):
                week_used.add(chosen.item)
                _group.add(chosen.item)
                return chosen
        # Repeat tier: all fresh options exhausted — prefer items not used today
        preferred = [
            sd for sd in candidates
            if sd.item not in day_used_names and _can_reserve_side_dish(sd)
        ]
        if preferred:
            chosen = random.choice(preferred)
            if _reserve_side_dish(chosen):
                week_used.add(chosen.item)
                _group.add(chosen.item)
                return chosen
        repeat_ok = [sd for sd in candidates if _can_reserve_side_dish(sd)]
        if repeat_ok:
            chosen = random.choice(repeat_ok)
            if _reserve_side_dish(chosen):
                return chosen
        return None
    
    if available_side_dishes:
        pass  # print(f"   Found {len(available_side_dishes)} side dish items in inventory")

        # Shared week-level sets that span ALL fruit/veg slots so every unique option
        # is used at least once before anything repeats across breakfast, snack, and lunch.
        _global_fruit_week_used = set()
        _global_veg_week_used = set()
        for _seed_day in days_of_week:
            for _fv in [
                breakfast_data[_seed_day].get('fruit'),
                am_snack_data[_seed_day].get('fruit2'),
                lunch_data[_seed_day].get('fruit3'),
                pm_snack_data[_seed_day].get('fruit4'),
            ]:
                _fv = str(_fv or '').strip()
                if _fv and 'Out of stock' not in _fv:
                    _global_fruit_week_used.add(_fv)
            _vv = str(lunch_data[_seed_day].get('vegetable', '') or '').strip()
            if _vv and 'Out of stock' not in _vv:
                _global_veg_week_used.add(_vv)

        for day_idx, day in enumerate(days_of_week):
            day_used_names = {
                str(breakfast_data[day].get('fruit', '')).strip(),
                str(breakfast_data[day].get('add1', '')).strip(),
                str(am_snack_data[day].get('fruit2', '')).strip(),
                str(am_snack_data[day].get('add3', '')).strip(),
                str(lunch_data[day].get('vegetable', '')).strip(),
                str(lunch_data[day].get('fruit3', '')).strip(),
                str(pm_snack_data[day].get('fruit4', '')).strip(),
                str(pm_snack_data[day].get('add4', '')).strip(),
            }
            day_used_names = {v for v in day_used_names if v and 'Out of stock' not in v}

            # Breakfast: Fill blank fruit field ONLY if breakfast is being served AND has main content
            # Phase 5 condition: only fill random cells if all rules are satisfied (or continue generating)
            if _should_fill_random and user_serves_breakfast and breakfast_data[day]['bread'] and breakfast_data[day]['bread'].strip() and not breakfast_data[day]['fruit']:
                candidates = [sd for sd in available_side_dishes if sd.populate_breakfast]
                side_dish = _pick_side_dish(candidates, 'breakfast_fruit', day_used_names, group_used=_global_fruit_week_used)
                if side_dish:
                    breakfast_data[day]['fruit'] = side_dish.item
                    breakfast_data[day]['fruit_rule_id'] = side_dish.rule_id
                    day_used_names.add(side_dish.item)
                    last_selected_by_slot['breakfast_fruit'] = side_dish.item
                    pass  # print(f"   📍 {day} breakfast fruit: {side_dish.item}")
                elif not force_ignore_inventory:
                    breakfast_data[day]['fruit'] = "❌ Out of stock ❌"
                    pass  # print(f"   ⚠️ {day} breakfast fruit: Out of stock (no eligible side dish after same-day/back-to-back rules)")
            
            # AM Snack: Fill blank fruit2 field ONLY if user serves AM snack AND has main content
            # Check if there's actual main content (not just empty strings)
            has_am_snack_content = any([
                am_snack_data[day]['choose1'] and am_snack_data[day]['choose1'].strip(),
                am_snack_data[day]['bread2'] and am_snack_data[day]['bread2'].strip(),
                am_snack_data[day]['meat1'] and am_snack_data[day]['meat1'].strip()
            ])
            
            if _should_fill_random and user_serves_am_snack and has_am_snack_content and not am_snack_data[day]['fruit2']:
                candidates = [
                    sd for sd in available_side_dishes
                    if sd.populate_am_snack and _is_fruit_or_veg_side_dish(sd)
                ]
                side_dish = _pick_side_dish(candidates, 'am_snack_fruit2', day_used_names, group_used=_global_fruit_week_used)
                if side_dish:
                    am_snack_data[day]['fruit2'] = side_dish.item
                    am_snack_data[day]['fruit2_rule_id'] = side_dish.rule_id
                    day_used_names.add(side_dish.item)
                    last_selected_by_slot['am_snack_fruit2'] = side_dish.item
                    pass  # print(f"   📍 {day} AM snack fruit: {side_dish.item}")
                elif not force_ignore_inventory:
                    am_snack_data[day]['fruit2'] = "❌ Out of stock ❌"
                    pass  # print(f"   ⚠️ {day} AM snack fruit: Out of stock (no eligible side dish after same-day/back-to-back rules)")

            # AM Snack: Fill blank add3 with grain side dishes, but only while
            # the linked grain rule still needs additional day appearances.
            if user_serves_am_snack and has_am_snack_content and not am_snack_data[day]['add3']:
                candidates = [
                    sd for sd in available_side_dishes
                    if sd.populate_am_snack
                    and _is_grain_side_dish(sd)
                    and sd.rule_id
                    and _remaining_rule_days(sd.rule_id) > 0
                    and day_idx not in rule_day_counts.get(sd.rule_id, set())
                ]
                side_dish = _pick_side_dish(candidates, 'am_snack_add3', day_used_names)
                if side_dish:
                    am_snack_data[day]['add3'] = side_dish.item
                    am_snack_data[day]['add3_rule_id'] = side_dish.rule_id
                    _track_rule_day_id(side_dish.rule_id, day_idx)
                    day_used_names.add(side_dish.item)
                    last_selected_by_slot['am_snack_add3'] = side_dish.item
                    pass  # print(f"   📍 {day} AM snack add3: {side_dish.item}")
            
            # Lunch: Fill blank vegetable and/or fruit3 fields ONLY if user serves lunch AND has main content
            # Phase 5 condition: only fill random cells if all rules are satisfied (or continue generating)
            if _should_fill_random and user_serves_lunch and lunch_data[day]['meal_name'] and lunch_data[day]['meal_name'].strip():
                if not lunch_data[day]['vegetable']:
                    # Only select items with "Vegetable" category for the vegetable field
                    candidates = [sd for sd in available_side_dishes 
                                 if sd.populate_lunch 
                                 and 'vegetable' in sd.category.lower()]
                    side_dish = _pick_side_dish(candidates, 'lunch_vegetable', day_used_names, group_used=_global_veg_week_used)
                    if side_dish:
                        lunch_data[day]['vegetable'] = side_dish.item
                        lunch_data[day]['vegetable_rule_id'] = side_dish.rule_id
                        day_used_names.add(side_dish.item)
                        last_selected_by_slot['lunch_vegetable'] = side_dish.item
                        pass  # print(f"   📍 {day} lunch vegetable: {side_dish.item}")
                    elif not force_ignore_inventory:
                        lunch_data[day]['vegetable'] = "❌ Out of stock ❌"
                        pass  # print(f"   ⚠️ {day} lunch vegetable: Out of stock (no eligible vegetable side dish after same-day/back-to-back rules)")
                
                if not lunch_data[day]['fruit3']:
                    # Only select items with "Fruit" category for the fruit field
                    candidates = [sd for sd in available_side_dishes 
                                 if sd.populate_lunch 
                                 and 'fruit' in sd.category.lower()]
                    side_dish = _pick_side_dish(candidates, 'lunch_fruit3', day_used_names, group_used=_global_fruit_week_used)
                    if side_dish:
                        lunch_data[day]['fruit3'] = side_dish.item
                        lunch_data[day]['fruit3_rule_id'] = side_dish.rule_id
                        day_used_names.add(side_dish.item)
                        last_selected_by_slot['lunch_fruit3'] = side_dish.item
                        pass  # print(f"   📍 {day} lunch fruit: {side_dish.item}")
                    elif not force_ignore_inventory:
                        lunch_data[day]['fruit3'] = "❌ Out of stock ❌"
                        pass  # print(f"   ⚠️ {day} lunch fruit: Out of stock (no eligible fruit side dish after same-day/back-to-back rules)")
            
            # PM Snack: Fill blank fruit4 field ONLY if user serves PM snack AND has main content
            # Check if there's actual main content (not just empty strings)
            has_pm_snack_content = any([
                pm_snack_data[day]['choose2'] and pm_snack_data[day]['choose2'].strip(),
                pm_snack_data[day]['bread3'] and pm_snack_data[day]['bread3'].strip(),
                pm_snack_data[day]['meat3'] and pm_snack_data[day]['meat3'].strip()
            ])
            
            if _should_fill_random and user_serves_pm_snack and has_pm_snack_content and not pm_snack_data[day]['fruit4']:
                candidates = [
                    sd for sd in available_side_dishes
                    if sd.populate_pm_snack and _is_fruit_or_veg_side_dish(sd)
                ]
                side_dish = _pick_side_dish(candidates, 'pm_snack_fruit4', day_used_names, group_used=_global_fruit_week_used)
                if side_dish:
                    pm_snack_data[day]['fruit4'] = side_dish.item
                    pm_snack_data[day]['fruit4_rule_id'] = side_dish.rule_id
                    day_used_names.add(side_dish.item)
                    last_selected_by_slot['pm_snack_fruit4'] = side_dish.item
                    pass  # print(f"   📍 {day} PM snack fruit: {side_dish.item}")
                elif not force_ignore_inventory:
                    pm_snack_data[day]['fruit4'] = "❌ Out of stock ❌"
                    pass  # print(f"   ⚠️ {day} PM snack fruit: Out of stock (no eligible side dish after same-day/back-to-back rules)")

            # PM Snack: Fill blank add4 with grain side dishes, but only while
            # the linked grain rule still needs additional day appearances.
            if user_serves_pm_snack and has_pm_snack_content and not pm_snack_data[day]['add4']:
                candidates = [
                    sd for sd in available_side_dishes
                    if sd.populate_pm_snack
                    and _is_grain_side_dish(sd)
                    and sd.rule_id
                    and _remaining_rule_days(sd.rule_id) > 0
                    and day_idx not in rule_day_counts.get(sd.rule_id, set())
                ]
                side_dish = _pick_side_dish(candidates, 'pm_snack_add4', day_used_names)
                if side_dish:
                    pm_snack_data[day]['add4'] = side_dish.item
                    pm_snack_data[day]['add4_rule_id'] = side_dish.rule_id
                    _track_rule_day_id(side_dish.rule_id, day_idx)
                    day_used_names.add(side_dish.item)
                    last_selected_by_slot['pm_snack_add4'] = side_dish.item
                    pass  # print(f"   📍 {day} PM snack add4: {side_dish.item}")
    else:
        pass  # print("   No side dish items found in inventory")

    # FINAL INVENTORY RECONCILIATION (CUMULATIVE):
    # Validate every populated cell at the very end of generation and reserve inventory
    # across the week so the same stock cannot be reused infinitely by multiple cells.
    remaining_inventory_base = None
    if not force_ignore_inventory:
        inventory_items = Inventory.objects.filter(user=user)
        remaining_inventory_base = {}
        for item in inventory_items:
            conv_to_base = item.conversion_to_base or 1
            inventory_units = item.total_quantity or item.quantity or 0
            remaining_inventory_base[item.id] = inventory_units * conv_to_base

        recipe_lookup_cache = {}
        side_dish_lookup_cache = {}
        inventory_item_lookup_cache = {}
        recipe_name_inventory_cache = {}

        def _norm_label(text):
            base = re.sub(r'\s+', ' ', str(text or '').strip().casefold())
            no_paren = re.sub(r'\([^)]*\)', '', base)
            slug_base = re.sub(r'[^a-z0-9]+', '', base)
            slug_no_paren = re.sub(r'[^a-z0-9]+', '', no_paren)
            return slug_base, slug_no_paren

        inventory_norm_map = {}
        for inv_item in inventory_items:
            key_full, key_no_paren = _norm_label(inv_item.item)
            if key_full and key_full not in inventory_norm_map:
                inventory_norm_map[key_full] = inv_item
            if key_no_paren and key_no_paren not in inventory_norm_map:
                inventory_norm_map[key_no_paren] = inv_item

        def _preferred_recipe_types_for_field(field_name):
            if field_name in {'fluid_milk', 'lunch_milk', 'choose1', 'choose2'}:
                return ['fluid']
            if field_name in {'vegetable'}:
                return ['vegetable']
            if field_name in {'fruit', 'fruit2', 'fruit3', 'fruit4'}:
                return ['fruit']
            if field_name in {'grain'}:
                return ['whole_grain']
            if field_name in {'meal_name'}:
                return ['lunch']
            return []

        def _get_recipe_for_cell_value(cell_value, field_name=None):
            key = (str(cell_value or '').strip())
            if not key:
                return None
            if "Out of stock" in key:
                return None
            if key in {"No available breakfast option", "No available meal"}:
                return None

            cache_key = (key, field_name or '')
            if cache_key in recipe_lookup_cache:
                return recipe_lookup_cache[cache_key]

            candidates = list(Recipe.objects.filter(user=user, archive=False, name=key))
            if not candidates:
                recipe_lookup_cache[cache_key] = None
                return None

            preferred_types = _preferred_recipe_types_for_field(field_name)
            if preferred_types:
                preferred = [r for r in candidates if getattr(r, 'recipe_type', None) in preferred_types]
                if preferred:
                    recipe_lookup_cache[cache_key] = preferred[0]
                    return preferred[0]

            with_rules = [r for r in candidates if any([
                getattr(r, 'grain_rule_id', None),
                getattr(r, 'fruit_rule_id', None),
                getattr(r, 'veg_rule_id', None),
                getattr(r, 'meat_rule_id', None),
                getattr(r, 'fluid_rule_id', None),
                getattr(r, 'addfood_rule_id', None),
            ])]
            chosen = with_rules[0] if with_rules else candidates[0]
            recipe_lookup_cache[cache_key] = chosen
            return chosen

        def _get_side_dish_for_cell_value(cell_value):
            key = (str(cell_value or '').strip())
            if not key:
                return None
            if "Out of stock" in key:
                return None
            if key in {"No available breakfast option", "No available meal"}:
                return None
            if key in side_dish_lookup_cache:
                return side_dish_lookup_cache[key]
            side_dish_lookup_cache[key] = Inventory.objects.filter(
                user=user,
                item=key,
                is_side_dish=True,
            ).first()
            return side_dish_lookup_cache[key]

        def _get_inventory_item_for_cell_value(cell_value):
            key = (str(cell_value or '').strip())
            if not key:
                return None
            if "Out of stock" in key:
                return None
            if key in {"No available breakfast option", "No available meal"}:
                return None

            if key in inventory_item_lookup_cache:
                return inventory_item_lookup_cache[key]

            # Fast exact lookup first
            item = Inventory.objects.filter(user=user, item=key).first()
            if not item:
                # Fallback to normalized matching for display variants
                norm_full, norm_no_paren = _norm_label(key)
                item = inventory_norm_map.get(norm_full) or inventory_norm_map.get(norm_no_paren)

            inventory_item_lookup_cache[key] = item
            return item

        def _reserve_recipe_name_inventory_fallback(recipe):
            if not recipe or not getattr(recipe, 'name', None):
                return False
            key = recipe.name
            if key in recipe_name_inventory_cache:
                item = recipe_name_inventory_cache[key]
            else:
                item = _get_inventory_item_for_cell_value(key)
                recipe_name_inventory_cache[key] = item

            if not item:
                return False

            conv_to_base = item.conversion_to_base or 1
            portion_per_student = item.unit_size if item.unit_size and item.unit_size > 0 else 1
            required_base = portion_per_student * estimated_daily_students
            available_base = remaining_inventory_base.get(item.id, 0)
            if available_base < required_base:
                return False
            remaining_inventory_base[item.id] = available_base - required_base
            return True

        def _reserve_inventory_for_recipe(recipe):
            if not recipe:
                return False
            if getattr(recipe, 'ignore_inventory', False):
                return True

            ingredients = list(recipe.ingredients.all().select_related('ingredient'))
            if not ingredients:
                return _reserve_recipe_name_inventory_fallback(recipe)

            checks = []
            has_checkable_ingredient = False
            for recipe_ing in ingredients:
                ingredient = recipe_ing.ingredient
                per_portion_base = recipe_ing.quantity if recipe_ing.quantity else 0

                if not ingredient or per_portion_base <= 0:
                    continue

                has_checkable_ingredient = True

                required_base = per_portion_base * estimated_daily_students
                available_base = remaining_inventory_base.get(ingredient.id, 0)
                checks.append((ingredient.id, required_base, available_base))

                if available_base < required_base:
                    return False

            if not has_checkable_ingredient:
                return _reserve_recipe_name_inventory_fallback(recipe)

            for ingredient_id, required_base, _available_base in checks:
                remaining_inventory_base[ingredient_id] = remaining_inventory_base.get(ingredient_id, 0) - required_base

            return True

        def _reserve_inventory_for_side_dish(side_dish):
            if not side_dish:
                return False

            conv_to_base = side_dish.conversion_to_base or 1
            portion_per_student = side_dish.unit_size if side_dish.unit_size and side_dish.unit_size > 0 else 1
            required_base = portion_per_student * estimated_daily_students
            available_base = remaining_inventory_base.get(side_dish.id, 0)

            if available_base < required_base:
                return False

            remaining_inventory_base[side_dish.id] = available_base - required_base
            return True

        def _reserve_inventory_for_item(item):
            if not item:
                return False

            portion_per_student = item.unit_size if item.unit_size and item.unit_size > 0 else 1
            required_base = portion_per_student * estimated_daily_students
            available_base = remaining_inventory_base.get(item.id, 0)
            if available_base < required_base:
                return False

            remaining_inventory_base[item.id] = available_base - required_base
            return True

        def _reconcile_cells(meal_name, meal_data, field_names):
            optional_fields = {'add1', 'add2', 'add3', 'add4'}
            unit_size_fields = {
                'fluid_milk', 'choose1', 'lunch_milk', 'choose2',
                'fruit', 'fruit2', 'vegetable', 'fruit3', 'fruit4',
                'grain', 'add1', 'add3', 'add4'
            }

            anchor_field_by_meal = {
                'Breakfast': 'bread',
                'AM snack': 'bread2',
                'Lunch': 'meal_name',
                'PM snack': 'bread3',
            }

            component_fields_by_meal = {
                'Breakfast': {'fruit', 'add1'},
                'AM snack': {'fruit2', 'choose1', 'add3', 'meat1'},
                'Lunch': {'lunch_milk', 'vegetable', 'fruit3', 'grain', 'meat_alternate', 'add2'},
                'PM snack': {'fruit4', 'choose2', 'add4', 'meat3'},
            }

            def _component_values_from_recipe(recipe_obj):
                if not recipe_obj:
                    return set()
                values = {
                    str(recipe_obj.fluid or '').strip(),
                    str(recipe_obj.fruit or '').strip(),
                    str(recipe_obj.veg or '').strip(),
                    str(recipe_obj.grain or '').strip(),
                    str(recipe_obj.meat or '').strip(),
                    str(recipe_obj.meat_alternate or '').strip(),
                    str(recipe_obj.addfood or '').strip(),
                }
                return {v for v in values if v}

            def _normalize_component_label(text):
                label = re.sub(r'[^a-z0-9]+', '', str(text or '').strip().casefold())
                if label.endswith('s') and len(label) > 3:
                    return label[:-1]
                return label

            def _component_matches(value, components):
                target = _normalize_component_label(value)
                if not target:
                    return False
                return any(_normalize_component_label(c) == target for c in components)

            for day in days_of_week:
                anchor_field = anchor_field_by_meal.get(meal_name)
                anchor_value = str(meal_data[day].get(anchor_field, '') or '').strip() if anchor_field else ''
                anchor_recipe = _get_recipe_for_cell_value(anchor_value, anchor_field) if anchor_value else None
                anchor_components = _component_values_from_recipe(anchor_recipe)

                for field in field_names:
                    value = meal_data[day].get(field, '')
                    value_str = str(value or '').strip()
                    if not value_str or "Out of stock" in value_str:
                        continue

                    # Component labels copied from the same day's main recipe should
                    # not consume inventory a second time.
                    if field in component_fields_by_meal.get(meal_name, set()) and _component_matches(value_str, anchor_components):
                        continue

                    recipe = _get_recipe_for_cell_value(value_str, field)
                    side_dish = _get_side_dish_for_cell_value(value_str)

                    if field in unit_size_fields:
                        # Component rows (fluid/fruit/veg/grain/add) reserve by inventory unit_size
                        # for inventory side dishes, but still use recipe ingredients when an
                        # actual recipe is present in the cell.
                        if side_dish:
                            is_valid = _reserve_inventory_for_side_dish(side_dish)
                        elif recipe:
                            is_valid = _reserve_inventory_for_recipe(recipe)
                        else:
                            inventory_item = _get_inventory_item_for_cell_value(value_str)
                            if not inventory_item and recipe:
                                inventory_item = _get_inventory_item_for_cell_value(recipe.name)
                            is_valid = _reserve_inventory_for_item(inventory_item)
                    else:
                        # Main rows keep recipe ingredient quantity checks.
                        if recipe:
                            is_valid = _reserve_inventory_for_recipe(recipe)
                        elif side_dish:
                            is_valid = _reserve_inventory_for_side_dish(side_dish)
                        else:
                            inventory_item = _get_inventory_item_for_cell_value(value_str)
                            is_valid = _reserve_inventory_for_item(inventory_item)

                    if not is_valid:
                        # Optional add-food rows should remain blank when unavailable,
                        # not display an out-of-stock warning.
                        if field in optional_fields:
                            meal_data[day][field] = ""
                        else:
                            meal_data[day][field] = "❌ Out of stock ❌"
                        rule_field = f"{field}_rule_id"
                        if rule_field in meal_data[day]:
                            meal_data[day][rule_field] = None
                        print(
                            f"[MENU DEBUG] {meal_name} {day} {field}: final cumulative inventory check failed "
                            f"for '{value_str}', {'cleared optional field' if field in optional_fields else 'marked OUT OF STOCK'}."
                        )

        # Reconcile all visible meal rows against inventory and reserve cumulatively.
        _reconcile_cells('Breakfast', breakfast_data, ['fluid_milk', 'fruit', 'bread', 'add1'])
        _reconcile_cells('AM snack', am_snack_data, ['choose1', 'fruit2', 'bread2', 'meat1', 'add3'])
        _reconcile_cells('Lunch', lunch_data, ['meal_name', 'lunch_milk', 'vegetable', 'fruit3', 'grain', 'meat_alternate', 'add2'])
        _reconcile_cells('PM snack', pm_snack_data, ['choose2', 'fruit4', 'bread3', 'meat3', 'add4'])

        # After reconciliation, try to refill lunch fruit/vegetable gaps from side-dish
        # inventory before final rule recount. This avoids persistent blanks/out-of-stock
        # when other side-dish items still have capacity.
        lunch_side_dishes = list(
            Inventory.objects.filter(user=user, is_side_dish=True, populate_lunch=True).select_related('rule')
        )

        def _can_reserve_remaining(side_dish):
            conv_to_base = float(side_dish.conversion_to_base or 1)
            portion_per_student = float(side_dish.unit_size or 0)
            required_base = portion_per_student * estimated_daily_students
            available_base = float(remaining_inventory_base.get(side_dish.id, 0))
            return required_base == 0 or available_base >= required_base

        def _reserve_remaining(side_dish):
            conv_to_base = float(side_dish.conversion_to_base or 1)
            portion_per_student = float(side_dish.unit_size or 0)
            required_base = portion_per_student * estimated_daily_students
            if required_base == 0:
                return True
            available_base = float(remaining_inventory_base.get(side_dish.id, 0))
            if available_base < required_base:
                return False
            remaining_inventory_base[side_dish.id] = available_base - required_base
            return True

        def _current_rule_day_counts_from_cells():
            current_counts = {}
            for scan_day_idx, scan_day in enumerate(days_of_week):
                for data_dict in [breakfast_data[scan_day], am_snack_data[scan_day], lunch_data[scan_day], pm_snack_data[scan_day]]:
                    for key, val in data_dict.items():
                        if key.endswith('_rule_id') and val:
                            current_counts.setdefault(val, set()).add(scan_day_idx)
            return current_counts

        def _prioritize_rule_gap_side_dishes(candidates, day_idx):
            if not candidates:
                return []

            current_counts = _current_rule_day_counts_from_cells()
            prioritized = [
                sd for sd in candidates
                if sd.rule_id
                and day_idx not in current_counts.get(sd.rule_id, set())
                and any(r.id == sd.rule_id and len(current_counts.get(sd.rule_id, set())) < r.weekly_qty for r in all_rules)
            ]
            # Return prioritized items first, then remaining — never exclude non-rule items entirely
            remaining = [sd for sd in candidates if sd not in prioritized]
            return prioritized + remaining if prioritized else candidates

        # Collect names already placed this week for variety tracking in Phase 4
        def _placed_names_for_phase4(data_dict, field_key):
            return {
                str(data_dict[d].get(field_key, '') or '').strip()
                for d in days_of_week
                if str(data_dict[d].get(field_key, '') or '').strip()
                and 'Out of stock' not in str(data_dict[d].get(field_key, '') or '')
            }
        _phase4_veg_used = _placed_names_for_phase4(lunch_data, 'vegetable')
        _phase4_fruit_used = _placed_names_for_phase4(lunch_data, 'fruit3')

        for day in days_of_week:
            if not lunch_data[day]['meal_name'] or 'Out of stock' in str(lunch_data[day]['meal_name']):
                continue

            day_idx = days_of_week.index(day)

            veg_val = str(lunch_data[day].get('vegetable', '') or '')
            if not veg_val or 'Out of stock' in veg_val:
                veg_candidates = [
                    sd for sd in lunch_side_dishes
                    if 'vegetable' in str(sd.category or '').lower() and _can_reserve_remaining(sd)
                ]
                # Phase 4: always try rule-bearing side dishes for rule gaps
                rule_priority_veg = _prioritize_rule_gap_side_dishes(veg_candidates, day_idx)
                # Only use the full (non-rule) fallback pool when Phase 5 random fill is allowed
                if not _should_fill_random:
                    veg_candidates = [sd for sd in veg_candidates if sd.rule_id]
                else:
                    veg_candidates = rule_priority_veg
                if veg_candidates:
                    unused = [sd for sd in veg_candidates if sd.item not in _phase4_veg_used]
                    chosen = random.choice(unused if unused else veg_candidates)
                    if _reserve_remaining(chosen):
                        lunch_data[day]['vegetable'] = chosen.item
                        lunch_data[day]['vegetable_rule_id'] = chosen.rule_id
                        _phase4_veg_used.add(chosen.item)

            fruit_val = str(lunch_data[day].get('fruit3', '') or '')
            if not fruit_val or 'Out of stock' in fruit_val:
                fruit_candidates = [
                    sd for sd in lunch_side_dishes
                    if 'fruit' in str(sd.category or '').lower() and _can_reserve_remaining(sd)
                ]
                # Phase 4: always try rule-bearing side dishes for rule gaps
                rule_priority_fruit = _prioritize_rule_gap_side_dishes(fruit_candidates, day_idx)
                if not _should_fill_random:
                    fruit_candidates = [sd for sd in fruit_candidates if sd.rule_id]
                else:
                    fruit_candidates = rule_priority_fruit
                if fruit_candidates:
                    unused = [sd for sd in fruit_candidates if sd.item not in _phase4_fruit_used]
                    chosen = random.choice(unused if unused else fruit_candidates)
                    if _reserve_remaining(chosen):
                        lunch_data[day]['fruit3'] = chosen.item
                        lunch_data[day]['fruit3_rule_id'] = chosen.rule_id
                        _phase4_fruit_used.add(chosen.item)

        for day in days_of_week:
            if not breakfast_data[day]['bread'] or "Out of stock" in str(breakfast_data[day]['bread']):
                breakfast_data[day]['bread'] = "❌ Out of stock"
            if not am_snack_data[day]['bread2'] or "Out of stock" in str(am_snack_data[day]['bread2']):
                am_snack_data[day]['bread2'] = "❌ Out of stock"
            if not lunch_data[day]['meal_name'] or "Out of stock" in str(lunch_data[day]['meal_name']):
                lunch_data[day]['meal_name'] = "❌ Out of stock"
            if not pm_snack_data[day]['bread3'] or "Out of stock" in str(pm_snack_data[day]['bread3']):
                pm_snack_data[day]['bread3'] = "❌ Out of stock"
    
    # === RE-SCAN ALL CELLS TO COUNT RULES (INCLUDING NEWLY PLACED SIDE DISHES) ===
    # Pure *_rule_id scan: count only explicitly assigned rule IDs. No name lookups or
    # field-name special-casing. If placement code sets the rule_id, it counts; otherwise it doesn't.
    rule_day_counts = {}
    for day_idx, day in enumerate(days_of_week):
        for data_dict in [breakfast_data[day], am_snack_data[day], lunch_data[day], pm_snack_data[day]]:
            for key, val in data_dict.items():
                if key.endswith('_rule_id') and val:
                    _track_rule_day_id(val, day_idx)

    # Recalculate missing_rules based on updated rule_day_counts.
    # Ignore-inventory mode should never show insufficiency warnings.
    missing_rules = []
    if not force_ignore_inventory:
        for rule in all_rules:
            current_count = len(rule_day_counts.get(rule.id, set()))
            needed_count = rule.weekly_qty

            # Skip fluid rules (handled separately)
            is_fluid_rule = False
            for recipe in Recipe.objects.filter(user=user, archive=False):
                if hasattr(recipe, 'fluid_rule') and recipe.fluid_rule and recipe.fluid_rule.id == rule.id:
                    is_fluid_rule = True
                    break

            if is_fluid_rule:
                continue

            if current_count < needed_count:
                gap = needed_count - current_count
                missing_rules.append({
                    'rule': rule.rule,
                    'current': current_count,
                    'required': needed_count,
                    'gap': gap
                })
                pass  # print(f"❌ FINAL MISSING RULE: '{rule.rule}' appears {current_count}/{needed_count} days (missing {gap})")
    
    # Return all meal data in a single response
    # Debug: Log breakfast data to see if it contains out-of-stock markers
    print("🔍 BREAKFAST DATA BEING RETURNED:")
    for day in days_of_week:
        print(f"  {day}: bread={breakfast_data[day]['bread']}")
    
    print(f"🔍 OUT OF STOCK ITEMS COUNT: {len(out_of_stock_items)}")
    if out_of_stock_items:
        for item in out_of_stock_items:
            print(f"  - {item['day']} {item['meal']}: {item['component']}")
    
    return JsonResponse({
        'breakfast': breakfast_data,
        'am_snack': am_snack_data,
        'lunch': lunch_data,
        'pm_snack': pm_snack_data,
        'missing_rules': missing_rules,  # Pass missing rules to frontend
        'out_of_stock_items': out_of_stock_items  # Pass detailed out-of-stock items for confirmation dialog
    })

def generate_menu(request):
    user = get_user_for_view(request)  # Get the correct user context
    days_of_week = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]
    
    # Initialize global rule tracker in session (shared across all meal generation endpoints)
    # This ensures weekly_qty is enforced across ALL meal periods
    if 'menu_generation_rule_tracker' not in request.session:
        request.session['menu_generation_rule_tracker'] = {}
    rule_tracker = request.session['menu_generation_rule_tracker']
    
    # Initialize empty menu data
    menu_data = {}
    for day in days_of_week:
        menu_data[day] = {
            'meal_name': '',
            'grain': '',
            'meat_alternate': '',
            'vegetable': '',
            'fruit3': ''
        }
    
    # Separate recipe selection by type for complete menu coverage
    # 1. Main lunch dishes
    lunch_recipes = list(Recipe.objects.filter(user=user, archive=False, populate_lunch=True, recipe_type='lunch'))
    # Fallback: if nothing is flagged to populate lunch, use any lunch recipes
    if not lunch_recipes:
        lunch_recipes = list(Recipe.objects.filter(user=user, archive=False, recipe_type='lunch'))
    if lunch_recipes:
        selected_lunch = select_recipes_with_rules(lunch_recipes, days_count=5, rule_tracker=rule_tracker)
        for day_idx, day in enumerate(days_of_week):
            if selected_lunch[day_idx]:
                recipe = selected_lunch[day_idx]
                menu_data[day]['meal_name'] = recipe.name
                menu_data[day]['grain'] = recipe.grain or ""
                menu_data[day]['meat_alternate'] = recipe.meat_alternate or ""
    
    # 2. Whole grain items (fill grain row if not already filled by lunch recipe)
    wg_recipes = list(Recipe.objects.filter(user=user, archive=False, populate_lunch=True, recipe_type='whole_grain'))
    if not wg_recipes:
        wg_recipes = list(Recipe.objects.filter(user=user, archive=False, recipe_type='whole_grain'))
    if wg_recipes:
        selected_wg = select_recipes_with_rules(wg_recipes, days_count=5, rule_tracker=rule_tracker)
        for day_idx, day in enumerate(days_of_week):
            if selected_wg[day_idx] and not menu_data[day]['grain']:
                menu_data[day]['grain'] = selected_wg[day_idx].name
    
    # 3. Vegetable items
    veg_recipes = list(Recipe.objects.filter(user=user, archive=False, populate_lunch=True, recipe_type='vegetable'))
    if not veg_recipes:
        veg_recipes = list(Recipe.objects.filter(user=user, archive=False, recipe_type='vegetable'))
    if veg_recipes:
        selected_veg = select_recipes_with_rules(veg_recipes, days_count=5, rule_tracker=rule_tracker)
        for day_idx, day in enumerate(days_of_week):
            if selected_veg[day_idx]:
                menu_data[day]['vegetable'] = selected_veg[day_idx].name
    
    # 4. Fruit items
    fruit_recipes = list(Recipe.objects.filter(user=user, archive=False, populate_lunch=True, recipe_type='fruit'))
    if not fruit_recipes:
        fruit_recipes = list(Recipe.objects.filter(user=user, archive=False, recipe_type='fruit'))
    if fruit_recipes:
        selected_fruit = select_recipes_with_rules(fruit_recipes, days_count=5, rule_tracker=rule_tracker)
        for day_idx, day in enumerate(days_of_week):
            if selected_fruit[day_idx]:
                menu_data[day]['fruit3'] = selected_fruit[day_idx].name
    
    # Fill empty meal_name cells with default
    for day in days_of_week:
        if not menu_data[day]['meal_name']:
            menu_data[day]['meal_name'] = "No available meal"
    
    # Save updated rule tracker back to session
    request.session['menu_generation_rule_tracker'] = rule_tracker
    request.session.modified = True
    request.session.save()  # Force immediate save for sequential requests
    
    return JsonResponse(menu_data)

@login_required
def generate_snack_menu(request, populate_field, fluid_key, fruit_key, bread_key, meat_key):
    user = get_user_for_view(request)
    snack_data = {}
    days_of_week = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]
    
    # Get shared rule tracker from session
    if 'menu_generation_rule_tracker' not in request.session:
        request.session['menu_generation_rule_tracker'] = {}
    rule_tracker = request.session['menu_generation_rule_tracker']
    
    # Initialize empty snack data
    for day in days_of_week:
        snack_data[day] = {
            fluid_key: "",
            fruit_key: "",
            bread_key: "",
            meat_key: ""
        }
    
    # 1. Main snack items.
    # Use different recipe_type pools for AM vs PM snacks so they
    # don't share the same recipes unless marked as AM/PM shared.
    if populate_field == 'populate_am_snack':
        snack_types = ['am_snack', 'am_pm_snack']
    elif populate_field == 'populate_pm_snack':
        snack_types = ['pm_snack', 'am_pm_snack']
    else:
        snack_types = ['am_snack', 'pm_snack', 'am_pm_snack']

    snack_type_recipes = list(Recipe.objects.filter(
        user=user,
        archive=False,
        **{populate_field: True},
        recipe_type__in=snack_types
    ))

    # Fallback: if no snack recipes are flagged for this period,
    # use any snack-type recipes for the user in the same pool.
    if not snack_type_recipes:
        snack_type_recipes = list(Recipe.objects.filter(
            user=user,
            archive=False,
            recipe_type__in=snack_types
        ))

    if snack_type_recipes:
        selected_snacks = select_recipes_with_rules(snack_type_recipes, days_count=5, rule_tracker=rule_tracker)
        for day_idx, day in enumerate(days_of_week):
            if selected_snacks[day_idx]:
                recipe = selected_snacks[day_idx]
                snack_data[day][fluid_key] = recipe.fluid or ""
                snack_data[day][bread_key] = recipe.name
                snack_data[day][meat_key] = recipe.meat or ""
                # Also populate fruit if recipe has it
                if recipe.fruit or recipe.veg:
                    snack_data[day][fruit_key] = recipe.fruit or recipe.veg
    
    # 2. Fruit/vegetable items (fill fruit row if not already filled)
    fruit_veg_recipes = list(Recipe.objects.filter(
        user=user,
        archive=False,
        **{populate_field: True},
        recipe_type__in=['fruit', 'vegetable']
    ))

    # Fallback: if no fruit/veg are flagged for this snack period,
    # use any fruit/veg recipes for the user.
    if not fruit_veg_recipes:
        fruit_veg_recipes = list(Recipe.objects.filter(
            user=user,
            archive=False,
            recipe_type__in=['fruit', 'vegetable']
        ))

    if fruit_veg_recipes:
        selected_fruit_veg = select_recipes_with_rules(fruit_veg_recipes, days_count=5, rule_tracker=rule_tracker)
        for day_idx, day in enumerate(days_of_week):
            if selected_fruit_veg[day_idx] and not snack_data[day][fruit_key]:
                snack_data[day][fruit_key] = selected_fruit_veg[day_idx].name
    
    # 3. Whole grain items (fill bread row if not already filled)
    wg_recipes = list(Recipe.objects.filter(
        user=user,
        archive=False,
        **{populate_field: True},
        recipe_type='whole_grain'
    ))

    # Fallback: if no whole grains are flagged for this snack period,
    # use any whole-grain recipes for the user.
    if not wg_recipes:
        wg_recipes = list(Recipe.objects.filter(
            user=user,
            archive=False,
            recipe_type='whole_grain'
        ))

    if wg_recipes:
        selected_wg = select_recipes_with_rules(wg_recipes, days_count=5, rule_tracker=rule_tracker)
        for day_idx, day in enumerate(days_of_week):
            if selected_wg[day_idx] and not snack_data[day][bread_key]:
                snack_data[day][bread_key] = selected_wg[day_idx].name
    
    # Save updated rule tracker back to session
    request.session['menu_generation_rule_tracker'] = rule_tracker
    request.session.modified = True
    request.session.save()  # Force immediate save for sequential requests
    
    return JsonResponse(snack_data)

def generate_am_menu(request):
    return generate_snack_menu(request, 'populate_am_snack', 'choose1', 'fruit2', 'bread2', 'meat1')

def generate_pm_menu(request):
    return generate_snack_menu(request, 'populate_pm_snack', 'choose2', 'fruit4', 'bread3', 'meat3')

@login_required
def generate_breakfast_menu(request):
    user = get_user_for_view(request)
    breakfast_data = {}
    days_of_week = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]
    
    # CLEAR rule tracker at the start of a new menu generation cycle
    # (breakfast is called first, so we reset here)
    request.session['menu_generation_rule_tracker'] = {}
    rule_tracker = request.session['menu_generation_rule_tracker']
    
    # Initialize empty breakfast data
    for day in days_of_week:
        breakfast_data[day] = {'bread': '', 'add1': '', 'fruit': ''}
    
    # 1. Main breakfast items
    breakfast_recipes = list(Recipe.objects.filter(user=user, archive=False, populate_breakfast=True, recipe_type='breakfast'))
    # Fallback: if nothing is flagged to populate breakfast, use any breakfast recipes
    if not breakfast_recipes:
        breakfast_recipes = list(Recipe.objects.filter(user=user, archive=False, recipe_type='breakfast'))
    if breakfast_recipes:
        selected_breakfast = select_recipes_with_rules(breakfast_recipes, days_count=5, rule_tracker=rule_tracker)
        for day_idx, day in enumerate(days_of_week):
            if selected_breakfast[day_idx]:
                recipe = selected_breakfast[day_idx]
                breakfast_data[day]['bread'] = recipe.name
                breakfast_data[day]['add1'] = recipe.addfood or ""
    
    # 2. Whole grain items (fill bread row if not already filled, otherwise add1)
    wg_recipes = list(Recipe.objects.filter(user=user, archive=False, populate_breakfast=True, recipe_type='whole_grain'))
    if not wg_recipes:
        wg_recipes = list(Recipe.objects.filter(user=user, archive=False, recipe_type='whole_grain'))
    if wg_recipes:
        selected_wg = select_recipes_with_rules(wg_recipes, days_count=5, rule_tracker=rule_tracker)
        for day_idx, day in enumerate(days_of_week):
            if selected_wg[day_idx]:
                if not breakfast_data[day]['bread']:
                    breakfast_data[day]['bread'] = selected_wg[day_idx].name
                elif not breakfast_data[day]['add1']:
                    breakfast_data[day]['add1'] = selected_wg[day_idx].name
    
    # 3. Fruit/vegetable items
    fruit_veg_recipes = list(Recipe.objects.filter(
        user=user, 
        archive=False,
        populate_breakfast=True, 
        recipe_type__in=['fruit', 'vegetable']
    ))
    if not fruit_veg_recipes:
        fruit_veg_recipes = list(Recipe.objects.filter(
            user=user,
            archive=False,
            recipe_type__in=['fruit', 'vegetable']
        ))
    if fruit_veg_recipes:
        selected_fruit_veg = select_recipes_with_rules(fruit_veg_recipes, days_count=5, rule_tracker=rule_tracker)
        for day_idx, day in enumerate(days_of_week):
            if selected_fruit_veg[day_idx]:
                breakfast_data[day]['fruit'] = selected_fruit_veg[day_idx].name
    
    # Fill empty cells with defaults
    for day in days_of_week:
        if not breakfast_data[day]['bread']:
            breakfast_data[day]['bread'] = "No available breakfast option"
    
    # Save updated rule tracker back to session
    request.session['menu_generation_rule_tracker'] = rule_tracker
    request.session.modified = True
    request.session.save()  # Force immediate save for sequential requests
    
    return JsonResponse(breakfast_data)

@login_required
def generate_fruit_menu(request):
    """One Berry at breakfast per week; lunch fruit excludes Juice/Raisins and never uses Berry."""
    user = get_user_for_view(request)
    fruit_menu_data = {}
    days = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]

    all_fruits = list(
        Inventory.objects.filter(user=user, category="Fruits", total_quantity__gt=0)
        .values_list('item', flat=True)
    )
    fruits_with_qty = list(
        Inventory.objects.filter(user=user, category="Fruits", quantity__gt=0)
        .values_list('item', flat=True)
    )

    berry_rule = Rule.objects.filter(user=user, rule__iexact="Berry").first()
    berry_candidates = []
    if berry_rule:
        berry_candidates = list(
            Inventory.objects.filter(user=user, category="Fruits", rule=berry_rule, total_quantity__gt=0)
            .values_list('item', flat=True)
        )

    used = set()
    def pick(candidates):
        pool = [n for n in candidates if n not in used]
        if not pool:
            return "NO FRUIT AVAILABLE" if not candidates else random.choice(candidates)
        choice = random.choice(pool)
        used.add(choice)
        return choice

    # Choose a single day to apply Berry at breakfast
    berry_day = None
    if berry_candidates:
        shuffled = days[:]
        random.shuffle(shuffled)
        for d in shuffled:
            if d in ["Monday", "Tuesday"]:
                if any(b in fruits_with_qty for b in berry_candidates):
                    berry_day = d
                    break
            else:
                berry_day = d
                break

    for day in days:
        day_data = {}
        breakfast_pool = fruits_with_qty if day in ["Monday", "Tuesday"] else all_fruits

        if berry_day == day:
            berry_pool = [b for b in berry_candidates if b in breakfast_pool] or berry_candidates
            breakfast = pick(berry_pool) if berry_pool else "NO FRUIT AVAILABLE"
        else:
            non_berry_pool = [f for f in breakfast_pool if f not in berry_candidates]
            breakfast = pick(non_berry_pool) if non_berry_pool else pick(breakfast_pool)

        day_data['fruit'] = breakfast

        lunch_base = all_fruits if day not in ["Monday", "Tuesday"] else fruits_with_qty
        lunch_pool = [
            f for f in lunch_base
            if "Juice" not in f and "Raisins" not in f and f not in berry_candidates
        ]
        day_data['fruit3'] = pick(lunch_pool) if lunch_pool else pick(lunch_base)

        fruit_menu_data[day] = day_data

    return JsonResponse(fruit_menu_data)

def get_fruits(request):
    fruits = Inventory.objects.filter(category='Fruits').values_list('item', flat=True)
    return JsonResponse(list(fruits), safe=False)

@login_required
def generate_vegetable_menu(request):
    """Schedule exactly one Yellow Vegetable, one Leafy Green, and one Bean across lunch; fill other days normally."""
    user = get_user_for_view(request)
    vegetable_menu_data = {}
    days = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]

    all_veg = list(
        Inventory.objects.filter(user=user, category="Vegetables", total_quantity__gt=0)
        .values_list('item', flat=True)
    )
    veg_with_qty = list(
        Inventory.objects.filter(user=user, category="Vegetables", quantity__gt=0)
        .values_list('item', flat=True)
    )

    subgroup_names = ["Yellow Vegetable", "Leafy Green", "Bean"]
    subgroup_items = {}
    for rn in subgroup_names:
        r = Rule.objects.filter(user=user, rule__iexact=rn).first()
        if r:
            subgroup_items[rn] = list(
                Inventory.objects.filter(user=user, category="Vegetables", rule=r, total_quantity__gt=0)
                .values_list('item', flat=True)
            )
        else:
            subgroup_items[rn] = []

    used = set()
    def pick(candidates):
        pool = [n for n in candidates if n not in used]
        if not pool:
            return "NO VEGETABLE AVAILABLE" if not candidates else random.choice(candidates)
        choice = random.choice(pool)
        used.add(choice)
        return choice

    available_days = days[:]
    random.shuffle(available_days)
    subgroup_day_map = {}
    for rn, items in subgroup_items.items():
        if not items:
            continue
        chosen_day = None
        for d in available_days:
            if d in ["Monday", "Tuesday"]:
                if any(v in veg_with_qty for v in items):
                    chosen_day = d
                    break
            else:
                chosen_day = d
                break
        if chosen_day:
            subgroup_day_map[chosen_day] = rn
            available_days.remove(chosen_day)

    for day in days:
        pool = veg_with_qty if day in ["Monday", "Tuesday"] else all_veg
        if day in subgroup_day_map and subgroup_items.get(subgroup_day_map[day]):
            rn = subgroup_day_map[day]
            subgroup_pool = [v for v in subgroup_items[rn] if v in pool] or subgroup_items[rn]
            vegetable = pick(subgroup_pool) if subgroup_pool else "NO VEGETABLE AVAILABLE"
        else:
            non_used_pool = [v for v in pool if v not in used]
            vegetable = pick(non_used_pool) if non_used_pool else pick(pool)
        vegetable_menu_data[day] = {'vegetable': vegetable}

    return JsonResponse(vegetable_menu_data)

@login_required
def fetch_inventory_rules(request):
    user = get_user_for_view(request)

    def _normalize(s: str) -> str:
        return re.sub(r'\s+', ' ', re.sub(r'[^\w%+ ]+', ' ', (s or '').lower())).strip()

    def _tokens(s: str):
        return {t for t in _normalize(s).split() if t and t not in {'the','a','an','of'}}

    def loosely_same(a: str, b: str) -> bool:
        na, nb = _normalize(a), _normalize(b)
        if not na or not nb:
            return False
        if na == nb or na in nb or nb in na:
            return True
        ta, tb = _tokens(a), _tokens(b)
        if not ta or not tb:
            return False
        overlap = len(ta & tb)
        jaccard = overlap / len(ta | tb)
        return overlap >= 2 or jaccard >= 0.6

    inv_qs = (Inventory.objects
              .filter(user=user, rule__isnull=False)
              .select_related('rule')
              .values('item','rule__gradient_start','rule__gradient_end','rule__text_color','rule__rule'))
    item_rule_map = {}
    for inv in inv_qs:
        item_rule_map[inv['item']] = {
            'gradient_start': inv['rule__gradient_start'],
            'gradient_end': inv['rule__gradient_end'],
            'text_color': inv['rule__text_color'],
            'rule_label': inv['rule__rule'],
        }

    def add_recipe_styles(recipe_type_filter, slot):
        from django.db.models import Q
        if isinstance(recipe_type_filter, list):
            query = Q()
            for rt in recipe_type_filter:
                query |= Q(recipe_type=rt)
            qs = Recipe.objects.filter(user=user).filter(query)
        else:
            qs = Recipe.objects.filter(user=user, recipe_type=recipe_type_filter)
        
        for recipe in qs:
            # Get ingredients from RecipeIngredient table
            ingredients = get_recipe_ingredients(recipe)
            
            # Get ingredients that have rules
            ruled_ingrs = [ing for ing, qty in ingredients if ing and ing.rule]

            # Always map ingredient names
            for inv in ruled_ingrs:
                item_rule_map.setdefault(inv.item, {
                    'gradient_start': inv.rule.gradient_start,
                    'gradient_end': inv.rule.gradient_end,
                    'text_color': inv.rule.text_color,
                    'rule_label': inv.rule.rule,
                })

            # Only color recipe name on loose match
            name_matched = False
            if recipe.name:
                for inv in ruled_ingrs:
                    if loosely_same(recipe.name, inv.item):
                        item_rule_map.setdefault(recipe.name, {
                            'gradient_start': inv.rule.gradient_start,
                            'gradient_end': inv.rule.gradient_end,
                            'text_color': inv.rule.text_color,
                            'rule_label': inv.rule.rule,
                        })
                        name_matched = True
                        break

    add_recipe_styles('breakfast', 'breakfast')
    add_recipe_styles(['am_snack', 'am_pm_snack'], 'am')
    add_recipe_styles(['pm_snack', 'am_pm_snack'], 'pm')

    # Lunch: color Grain based on match or grain_rule; main dish stays uncolored
    lunch_qs = Recipe.objects.filter(user=user, recipe_type='lunch').select_related('grain_rule')
    
    for r in lunch_qs:
        if not r.grain:
            continue
        
        # Get ingredients from RecipeIngredient table
        ingredients = get_recipe_ingredients(r)
        ruled_ingrs = [ing for ing, qty in ingredients if ing and ing.rule]
        
        style = None
        for inv in ruled_ingrs:
            if loosely_same(r.grain, inv.item):
                style = {
                    'gradient_start': inv.rule.gradient_start,
                    'gradient_end': inv.rule.gradient_end,
                    'text_color': inv.rule.text_color,
                    'rule_label': inv.rule.rule,
                }
                break
        # If no ingredient match, use grain_rule if present
        if not style and r.grain_rule:
            style = {
                'gradient_start': r.grain_rule.gradient_start,
                'gradient_end': r.grain_rule.gradient_end,
                'text_color': r.grain_rule.text_color,
                'rule_label': r.grain_rule.rule,
            }
        if style:
            item_rule_map.setdefault(r.grain, style)

    # Apply per-component rule FKs for all recipes
    all_recipes = Recipe.objects.filter(user=user).select_related(
        'grain_rule', 'fruit_rule', 'veg_rule', 'meat_rule', 'fluid_rule', 'addfood_rule'
    )
    for r in all_recipes:
        if r.grain and r.grain_rule:
            item_rule_map[r.grain] = {
                'gradient_start': r.grain_rule.gradient_start,
                'gradient_end': r.grain_rule.gradient_end,
                'text_color': r.grain_rule.text_color,
                'rule_label': r.grain_rule.rule,
            }
        if r.fruit and r.fruit_rule:
            item_rule_map[r.fruit] = {
                'gradient_start': r.fruit_rule.gradient_start,
                'gradient_end': r.fruit_rule.gradient_end,
                'text_color': r.fruit_rule.text_color,
                'rule_label': r.fruit_rule.rule,
            }
        if r.veg and r.veg_rule:
            item_rule_map[r.veg] = {
                'gradient_start': r.veg_rule.gradient_start,
                'gradient_end': r.veg_rule.gradient_end,
                'text_color': r.veg_rule.text_color,
                'rule_label': r.veg_rule.rule,
            }
        if r.meat and r.meat_rule:
            item_rule_map[r.meat] = {
                'gradient_start': r.meat_rule.gradient_start,
                'gradient_end': r.meat_rule.gradient_end,
                'text_color': r.meat_rule.text_color,
                'rule_label': r.meat_rule.rule,
            }
        if r.fluid and r.fluid_rule:
            item_rule_map[r.fluid] = {
                'gradient_start': r.fluid_rule.gradient_start,
                'gradient_end': r.fluid_rule.gradient_end,
                'text_color': r.fluid_rule.text_color,
                'rule_label': r.fluid_rule.rule,
            }
        if r.addfood and r.addfood_rule:
            item_rule_map[r.addfood] = {
                'gradient_start': r.addfood_rule.gradient_start,
                'gradient_end': r.addfood_rule.gradient_end,
                'text_color': r.addfood_rule.text_color,
                'rule_label': r.addfood_rule.rule,
            }
        
        # Map recipe name to rule color for ANY recipe that has a rule FK set
        # Check all possible rule FKs in priority order
        if r.name:
            assigned_rule = None
            # Priority: grain_rule > fruit_rule > veg_rule > meat_rule > fluid_rule > addfood_rule
            if r.grain_rule:
                assigned_rule = r.grain_rule
            elif r.fruit_rule:
                assigned_rule = r.fruit_rule
            elif r.veg_rule:
                assigned_rule = r.veg_rule
            elif r.meat_rule:
                assigned_rule = r.meat_rule
            elif r.fluid_rule:
                assigned_rule = r.fluid_rule
            elif r.addfood_rule:
                assigned_rule = r.addfood_rule
            
            # If any rule is assigned, map the recipe name to that rule's colors
            if assigned_rule:
                item_rule_map[r.name] = {
                    'gradient_start': assigned_rule.gradient_start,
                    'gradient_end': assigned_rule.gradient_end,
                    'text_color': assigned_rule.text_color,
                    'rule_label': assigned_rule.rule,
                }

    # Ensure all rules are represented in legend
    all_rules = Rule.objects.filter(user=user)
    existing_labels = {v.get('rule_label') for v in item_rule_map.values() if isinstance(v, dict)}
    for rule in all_rules:
        if rule.rule not in existing_labels:
            item_rule_map[f"__rule__{rule.id}"] = {
                'gradient_start': rule.gradient_start,
                'gradient_end': rule.gradient_end,
                'text_color': rule.text_color,
                'rule_label': rule.rule,
            }

    return JsonResponse({'item_rules': item_rule_map})


@login_required
def list_rules(request):
    """Return JSON list of rule objects for current user (id, rule, gradient_start, gradient_end, text_color)."""
    user = get_user_for_view(request)
    qs = Rule.objects.filter(user=user).values('id', 'rule', 'gradient_start', 'gradient_end', 'text_color')
    return JsonResponse(list(qs), safe=False)

@login_required
def get_wg_candidates(request):
    user = get_user_for_view(request)
    wg_rule = Rule.objects.filter(user=user, rule__iexact="Whole Grain").first()
    if not wg_rule:
        return JsonResponse({'weekly_qty': 0, 'candidates': []})

    qs = (Recipe.objects
          .filter(user=user, recipe_type='whole_grain', grain_rule=wg_rule))
    out = []
    for w in qs:
        style = {
            'gradient_start': wg_rule.gradient_start,
            'gradient_end': wg_rule.gradient_end,
            'text_color': wg_rule.text_color,
            'rule_label': wg_rule.rule,
        }
        out.append({
            'name': w.name,
            'break_only': False,  # Recipe model doesn't have these fields for lunch recipes
            'am_only': False,
            'lunch_only': False,
            'pm_only': False,
            'style': style,
        })
    return JsonResponse({'weekly_qty': wg_rule.weekly_qty, 'candidates': out})

@login_required
def check_missing_rules(request):
    """
    Check which rules don't have recipes assigned to fulfill them.
    Returns list of rules with a 'missing' flag indicating if no recipes exist.
    """
    user = get_user_for_view(request)
    
    # Get all rules for the user with weekly_qty > 0
    all_rules = Rule.objects.filter(user=user, weekly_qty__gt=0).order_by('rule')
    
    missing_rules = []
    fulfilled_rules = []
    
    for rule in all_rules:
        # Check if any recipes exist with this rule in any component field.
        recipes_with_rule = Recipe.objects.filter(
            user=user
        ).filter(
            models.Q(grain_rule=rule) |
            models.Q(fruit_rule=rule) |
            models.Q(veg_rule=rule) |
            models.Q(meat_rule=rule) |
            models.Q(fluid_rule=rule) |
            models.Q(addfood_rule=rule)
        ).count()

        # Also count inventory side dishes carrying the rule.
        # These can satisfy rule placement even when no Recipe row has that rule.
        inventory_with_rule = Inventory.objects.filter(
            user=user,
            rule=rule,
            is_side_dish=True,
        ).count()
        inventory_with_rule_in_stock = Inventory.objects.filter(
            user=user,
            rule=rule,
            is_side_dish=True,
            total_quantity__gt=0,
        ).count()

        # A rule is considered "assigned" if it is attached to at least one
        # recipe OR at least one inventory side dish.
        assignment_count = recipes_with_rule + inventory_with_rule
        
        rule_data = {
            'id': rule.id,
            'rule': rule.rule,
            'weekly_qty': rule.weekly_qty,
            'gradient_start': rule.gradient_start,
            'gradient_end': rule.gradient_end,
            'text_color': rule.text_color,
            'recipe_count': recipes_with_rule,
            'inventory_count': inventory_with_rule,
            'inventory_in_stock_count': inventory_with_rule_in_stock,
            'assignment_count': assignment_count,
        }
        
        if assignment_count == 0:
            missing_rules.append(rule_data)
        else:
            fulfilled_rules.append(rule_data)
    
    return JsonResponse({
        'missing_rules': missing_rules,
        'fulfilled_rules': fulfilled_rules,
        'total_rules': len(missing_rules) + len(fulfilled_rules)
    })

@login_required
def past_menus(request):
    user = get_user_for_view(request)  # Get the appropriate user (main user or subuser's main user)
    required_permission_id = 271  # Permission ID for weekly_menu
    permissions_context = check_permissions(request, required_permission_id)
    if isinstance(permissions_context, HttpResponseRedirect):
        return permissions_context

    # Fetch all unique Monday dates from the WeeklyMenu model for the logged-in user, ordered by date in descending order
    monday_dates = WeeklyMenu.objects.filter(day_of_week='Mon', user=user).values_list('date', flat=True).distinct().order_by('-date')

    # Generate date ranges only for valid Mondays, including the year
    date_ranges = []
    for monday in monday_dates:
        friday = monday + timedelta(days=4)
        if friday > monday:
            date_range_str = f"{monday.strftime('%b %d, %Y')} - {friday.strftime('%b %d, %Y')}"
            date_ranges.append(date_range_str)

    # Fetch all available dates for mobile date picker
    all_dates = WeeklyMenu.objects.filter(user=user).values_list('date', flat=True).distinct().order_by('-date')

    selected_menu_data = None
    selected_range = None
    selected_date = None
    selected_monday_str = None
    selected_friday_str = None

    # On initial GET load, prefer the Monday of the current week (if present),
    # otherwise fall back to the latest available Monday.
    if request.method != 'POST':
        try:
            today = datetime.now().date()
            # Monday is weekday 0
            current_week_monday = today - timedelta(days=today.weekday())

            # If we have a WeeklyMenu for the current week's Monday, use that.
            if WeeklyMenu.objects.filter(date=current_week_monday, user=user).exists():
                start_date = current_week_monday
            else:
                # fall back to the latest monday in the DB for this user
                start_date = monday_dates.first()

            if start_date:
                end_date = start_date + timedelta(days=4)
                selected_menu_data = WeeklyMenu.objects.filter(date__range=[start_date, end_date], user=user).order_by('date')
                selected_range = f"{start_date.strftime('%b %d, %Y')} - {end_date.strftime('%b %d, %Y')}"
                selected_date = None
                selected_monday_str = start_date.strftime('%Y-%m-%d')
                selected_friday_str = end_date.strftime('%Y-%m-%d')
        except Exception:
            selected_menu_data = None

    if request.method == 'POST':
        # Check for mobile date picker input
        mobile_date = request.POST.get('mobileDateSelect')
        if mobile_date:
            try:
                selected_date = datetime.strptime(mobile_date, '%Y-%m-%d').date()
                selected_menu_data = WeeklyMenu.objects.filter(date=selected_date, user=user).order_by('date')
                selected_monday_str = selected_date.strftime('%Y-%m-%d')
                selected_friday_str = (selected_date + timedelta(days=4)).strftime('%Y-%m-%d')
            except Exception:
                selected_menu_data = None
        # Check for desktop date range select
        else:
            selected_range = request.POST.get('dateRangeSelect')
            if selected_range:
                try:
                    start_date_str, end_date_str = selected_range.split(' - ')
                    start_date = datetime.strptime(start_date_str.strip(), '%b %d, %Y')
                    end_date = datetime.strptime(end_date_str.strip(), '%b %d, %Y')
                    selected_menu_data = WeeklyMenu.objects.filter(date__range=[start_date, end_date], user=user).order_by('date')
                    selected_monday_str = start_date.strftime('%Y-%m-%d')
                    selected_friday_str = end_date.strftime('%Y-%m-%d')
                except Exception:
                    selected_menu_data = None

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
            # Persist any assigned rules sent from the form as JSON
            try:
                from .models import WeeklyMenuAssignedRule, Rule
                assigned_rules_json = request.POST.get('assigned_rules_json', '{}')
                assigned_rules_all = json.loads(assigned_rules_json or '{}')
                weekday_keys = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday']
                for i, menu in enumerate(selected_menu_data):
                    day_key = weekday_keys[i] if i < len(weekday_keys) else ''
                    if not day_key:
                        continue
                    # grab only assignments that belong to this weekday
                    day_assigned = {cid: val for cid, val in assigned_rules_all.items() if cid.startswith(day_key)}
                    # remove previous assignments for this weekly_menu and weekday
                    WeeklyMenuAssignedRule.objects.filter(weekly_menu=menu, cell_id__startswith=day_key).delete()
                    for cell_id, val in day_assigned.items():
                        # If the posted value is a dict-like, treat it as manual_color_data
                        if isinstance(val, dict):
                            WeeklyMenuAssignedRule.objects.create(
                                weekly_menu=menu,
                                cell_id=cell_id,
                                rule=None,
                                manual_color_data=val
                            )
                        else:
                            # Try to interpret as a rule id (int or numeric string)
                            try:
                                rid = int(val)
                                try:
                                    rule_obj = Rule.objects.get(id=rid, user=user)
                                    WeeklyMenuAssignedRule.objects.create(weekly_menu=menu, cell_id=cell_id, rule=rule_obj)
                                except Rule.DoesNotExist:
                                    # skip invalid rule ids
                                    continue
                            except (TypeError, ValueError):
                                # not a rule id and not a dict - skip
                                continue
            except Exception as persist_ex:
                logger.warn('Failed to persist assigned rules from past-menus form: %s', persist_ex)
            # Don't redirect - just re-render with the current selection maintained

    # Build a mapping of assigned rules for the selected menus so past-menus can render colors
    assigned_rules_json = '{}'
    try:
        if selected_menu_data:
            menu_qs = list(selected_menu_data)
            from .models import WeeklyMenuAssignedRule
            assigned_qs = WeeklyMenuAssignedRule.objects.filter(weekly_menu__in=menu_qs).select_related('rule')
            assigned_map = {}
            for a in assigned_qs:
                # If this assignment references a Rule FK, use its colors.
                if a.rule:
                    r = a.rule
                    assigned_map[a.cell_id.lower()] = {
                        'id': r.id,
                        'rule_label': r.rule,
                        'gradient_start': r.gradient_start,
                        'gradient_end': r.gradient_end,
                        'text_color': r.text_color,
                    }
                # Otherwise, if manual_color_data exists, include those values.
                elif a.manual_color_data:
                    m = a.manual_color_data or {}
                    assigned_map[a.cell_id.lower()] = {
                        'id': None,
                        'rule_label': m.get('label') if isinstance(m, dict) else None,
                        'gradient_start': m.get('gradient_start') if isinstance(m, dict) else None,
                        'gradient_end': m.get('gradient_end') if isinstance(m, dict) else None,
                        'text_color': m.get('text_color') if isinstance(m, dict) else None,
                    }
            assigned_rules_json = json.dumps(assigned_map)
    except Exception:
        assigned_rules_json = '{}'

    # Build list of all rules for legend display (include gradient colors and text color)
    rules_list_json = '[]'
    try:
        from .models import Rule
        import json as _json
        rules_qs = Rule.objects.filter(user=user).values('id', 'rule', 'gradient_start', 'gradient_end', 'text_color')
        rules_list_json = _json.dumps(list(rules_qs))
    except Exception:
        rules_list_json = '[]'

    context = {
        'date_ranges': date_ranges,
        'all_dates': all_dates,
        'selected_menu_data': selected_menu_data,
        'selected_range': selected_range,
        'selected_date': selected_date,
        'selected_monday_str': selected_monday_str,
        'selected_friday_str': selected_friday_str,
        'assigned_rules_json': assigned_rules_json,
        'rules_list_json': rules_list_json,
        **permissions_context,
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
    error_message = ""

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
            
            try:
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
                    'tottimeapp@gmail.com',
                    [email],
                    fail_silently=False,
                )
                success_message = "Invitation email sent successfully."
                logger.info(f"Invitation sent successfully to {email} by user {request.user.id}")
                
            except Exception as e:
                logger.error(f"Failed to send invitation to {email} by user {request.user.id}: {str(e)}")
                error_message = f"Failed to send invitation: {str(e)}"
                # Delete the invitation if email failed
                if 'invitation' in locals():
                    invitation.delete()
        else:
            error_message = "Please check the form data."
    else:
        form = InvitationForm()

    return render(request, 'send-invitations.html', {
        'form': form,
        'success_message': success_message,
        'error_message': error_message,
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
    groups = (
        Group.objects
        .exclude(name="Free User")
        .exclude(id__in=[8, 9])
        .exclude(name__iexact="CACFP Only")
        .order_by('name')
    )
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
    required_permission_id = 157
    permissions_context = check_permissions(request, required_permission_id)
    if isinstance(permissions_context, HttpResponseRedirect):
        return permissions_context

    main_user = get_user_for_view(request)

    if request.method == "POST":
        for key, value in request.POST.items():
            if key.startswith("permission_"):
                parts = key.split("_")
                if len(parts) == 3:
                    permission_id, group_id = int(parts[1]), int(parts[2])
                    try:
                        role_permission = RolePermission.objects.get(
                            role_id=group_id,
                            permission_id=permission_id,
                            main_user=main_user
                        )
                        role_permission.yes_no_permission = value == "True"
                        role_permission.save()
                    except RolePermission.DoesNotExist:
                        # Create if not exists
                        RolePermission.objects.create(
                            role_id=group_id,
                            permission_id=permission_id,
                            yes_no_permission=value == "True",
                            main_user=main_user
                        )
        return redirect('permissions')

    groups = Group.objects.exclude(id__in=[8, 9]).exclude(name__in=["Owner", "Parent", "Free User"]).order_by('name')

    role_permissions = defaultdict(list)
    for group in groups:
        group_role_id = group.id
        role_permissions_for_group = RolePermission.objects.filter(
            role_id=group_role_id,
            main_user=main_user
        ).order_by('permission__name')
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
        **permissions_context,
    })

@login_required
def save_permissions(request):
    if request.method == "POST":
        main_user = get_user_for_view(request)
        for key, value in request.POST.items():
            if key.startswith("permission_"):
                parts = key.split("_")
                if len(parts) == 3:
                    permission_id, group_id = int(parts[1]), int(parts[2])
                    try:
                        # Filter by main_user!
                        role_permissions = RolePermission.objects.filter(
                            role_id=group_id,
                            permission_id=permission_id,
                            main_user=main_user
                        )
                        if role_permissions.exists():
                            # Update all (should only be one if unique_together is set)
                            for role_permission in role_permissions:
                                role_permission.yes_no_permission = value == "True"
                                role_permission.save()
                        else:
                            RolePermission.objects.create(
                                role_id=group_id,
                                permission_id=permission_id,
                                yes_no_permission=value == "True",
                                main_user=main_user
                            )
                    except Exception as e:
                        pass  # Optionally log error
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
    pass  # print(data)  # Log the entire response to see the error message from Square
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

@login_required
@csrf_exempt
def switch_account(request):
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            account_owner_id = data.get('account_owner_id')
            current_path = data.get('current_path')  # optional
            # Verify user has permission to switch
            if not request.user.can_switch:
                return JsonResponse({'success': False, 'error': 'Permission denied'})

            # Verify the account owner exists and is in the same company
            if request.user.company:
                account_owner = get_object_or_404(
                    CompanyAccountOwner,
                    main_account_owner_id=account_owner_id,
                    company=request.user.company
                )

                new_main_account_owner = get_object_or_404(MainUser, id=account_owner_id)

                # Update the user's main_account_owner_id
                request.user.main_account_owner_id = account_owner_id
                request.user.save()

                # Update SubUser.main_user if applicable
                try:
                    subuser = SubUser.objects.get(user=request.user)
                    if subuser.can_switch:
                        subuser.main_user = new_main_account_owner
                        subuser.save()
                except SubUser.DoesNotExist:
                    pass

                # Decide whether current page is valid for new_main_account_owner.
                redirect_url = None
                if current_path:
                    try:
                        match = resolve(current_path)
                        url_name = match.url_name or match.view_name
                        kwargs = match.kwargs
                        # check known views that are tied to a main_user/classroom/theme
                        if url_name == 'classroom_themes':
                            classroom_id = kwargs.get('classroom_id') or kwargs.get('pk') or kwargs.get('id')
                            from .models import Classroom
                            if not Classroom.objects.filter(id=classroom_id, user=new_main_account_owner).exists():
                                redirect_url = reverse('curriculum')
                        elif url_name == 'theme_activities':
                            theme_id = kwargs.get('theme_id') or kwargs.get('pk') or kwargs.get('id')
                            from .models import CurriculumTheme
                            if not CurriculumTheme.objects.filter(id=theme_id, main_user=new_main_account_owner).exists():
                                redirect_url = reverse('curriculum')
                        # add more url_name checks here if you have other per-main-user pages
                    except Resolver404:
                        # unknown path -> fall back to safe landing
                        redirect_url = reverse('curriculum')
                    except Exception:
                        # any unexpected error -> return safe landing
                        redirect_url = reverse('curriculum')

                response_payload = {'success': True}
                if redirect_url:
                    response_payload['redirect_url'] = redirect_url
                return JsonResponse(response_payload)
            else:
                return JsonResponse({'success': False, 'error': 'No company associated'})
        except Exception as e:
            return JsonResponse({'success': False, 'error': str(e)})

    return JsonResponse({'success': False, 'error': 'Invalid request method'})

@login_required
def staff_orientation(request):
    # Check permissions for the specific page
    required_permission_id = 450  # Permission ID for "billing"
    permissions_context = check_permissions(request, required_permission_id)
    if isinstance(permissions_context, HttpResponseRedirect):
        return permissions_context
    
    # Get the main user
    main_user = get_user_for_view(request)
    
    orientation_items = {}
    for category, _ in OrientationItem.CATEGORY_CHOICES:
        orientation_items[category] = OrientationItem.objects.filter(category=category).order_by('order')
    
    # Get orientations in progress using main_user instead of request.user
    orientations = StaffOrientation.objects.filter(
        main_user=main_user,
        is_completed=False
    )
    
    context = {
        'orientation_items': orientation_items,
        'orientations': orientations,
        'title': 'Staff Orientation',
        **permissions_context
    }
    
    return render(request, 'tottimeapp/staff_orientation.html', context)

@login_required
def start_orientation(request):
    """Start a new orientation using a staff name input"""
    if request.method == 'POST':
        try:
            # Get the main user
            main_user = get_user_for_view(request)
            
            # Properly decode the JSON data
            data = json.loads(request.body)
            staff_name = data.get('staff_name', '').strip()
            
            if not staff_name:
                return JsonResponse({'status': 'error', 'message': 'Staff name is required'})
                
            # Create a new orientation with staff_name and main_user
            orientation = StaffOrientation.objects.create(
                user=request.user,
                main_user=main_user,
                staff_name=staff_name,
                start_date=timezone.now().date()
            )
            
            # Create progress entries for all orientation items
            items = OrientationItem.objects.all()
            progress_items = []
            
            for item in items:
                progress_items.append(OrientationProgress(
                    orientation=orientation,
                    item=item
                ))
            
            if progress_items:  # Make sure there are items before bulk create
                OrientationProgress.objects.bulk_create(progress_items)
            
            return JsonResponse({'status': 'success', 'orientation_id': orientation.id})
            
        except json.JSONDecodeError:
            return JsonResponse({'status': 'error', 'message': 'Invalid JSON data'})
        except Exception as e:
            # Log the actual error
            pass  # print(f"Error creating orientation: {str(e)}")
            return JsonResponse({'status': 'error', 'message': f'Server error: {str(e)}'})
            
    return JsonResponse({'status': 'error', 'message': 'Invalid request method'})

@login_required
def update_progress(request, orientation_id, progress_id):
    """Update an individual progress item"""
    if request.method == 'POST':
        # Get the main user
        main_user = get_user_for_view(request)
        
        progress = get_object_or_404(
            OrientationProgress, 
            id=progress_id,
            orientation__id=orientation_id,
            orientation__main_user=main_user  # Use main_user instead of request.user
        )
        
        date_covered = request.POST.get('date_covered')
        date_completed = request.POST.get('date_completed')
        initialed_text = request.POST.get('initialed', '')  # Get the initials text
        notes = request.POST.get('notes', '')
        
        if date_covered:
            progress.date_covered = date_covered
        
        if date_completed:
            progress.date_completed = date_completed
            
        progress.initialed = bool(initialed_text)  # Set to True if initials exist
        progress.initialed_text = initialed_text   # Store the actual initials
        progress.notes = notes
        progress.save()
        
        # Check if all items are completed
        all_completed = not OrientationProgress.objects.filter(
            orientation__id=orientation_id,
            date_completed__isnull=True
        ).exists()
        
        if all_completed:
            orientation = progress.orientation
            orientation.is_completed = True
            orientation.completed_date = timezone.now().date()
            orientation.save()
        
        return JsonResponse({'status': 'success'})
        
    return JsonResponse({'status': 'error', 'message': 'Invalid request method'})

@login_required
def delete_orientation(request, orientation_id):
    """Delete an orientation and its related progress items"""
    if request.method == 'POST':
        try:
            # Get the main user
            main_user = get_user_for_view(request)
            
            # Get the orientation and verify ownership using main_user
            orientation = get_object_or_404(StaffOrientation, id=orientation_id, main_user=main_user)
            
            # Store the name for the success message
            staff_name = orientation.staff_name
            
            # Delete the orientation (will cascade delete progress items)
            orientation.delete()
            
            return JsonResponse({
                'status': 'success',
                'message': f'Orientation for {staff_name} has been deleted'
            })
            
        except Exception as e:
            return JsonResponse({
                'status': 'error',
                'message': f'Error deleting orientation: {str(e)}'
            })
    
    return JsonResponse({
        'status': 'error',
        'message': 'Invalid request method'
    })

@login_required
def class_score_form(request):
    """Display and process the classroom score form"""
    # Check permissions for the specific page
    required_permission_id = 450  # Permission ID for "billing"
    permissions_context = check_permissions(request, required_permission_id)
    if isinstance(permissions_context, HttpResponseRedirect):
        return permissions_context
    
    user = request.user
    main_user = get_user_for_view(request)
    
    # Get all standard categories with their criteria for the appropriate user
    categories = StandardCategory.objects.filter(main_user=main_user).prefetch_related('criteria')
    
    if request.method == 'POST':
        # Create a new score sheet
        score_sheet = ClassroomScoreSheet(
            user=user,
            main_user=main_user,
            room_name=request.POST.get('room_name'),
            age_range=request.POST.get('age_range'),
            date_of_observation=request.POST.get('date_of_observation'),
            time_start=request.POST.get('time_start'),
            time_end=request.POST.get('time_end'),
            teachers_initials=request.POST.get('teachers_initials'),
            assessor_name=request.POST.get('assessor_name')
        )
        score_sheet.save()
        
        # Process each score item
        for key, value in request.POST.items():
            if key.startswith('score_'):
                criteria_id = key.split('_')[1]
                try:
                    criteria = StandardCriteria.objects.get(id=criteria_id)
                    points = int(value) if value else 0
                    comment = request.POST.get(f'comment_{criteria_id}', '')
                    
                    ScoreItem.objects.create(
                        score_sheet=score_sheet,
                        criteria=criteria,
                        points_earned=points,
                        comments=comment
                    )
                except (StandardCriteria.DoesNotExist, ValueError):
                    continue
        
        messages.success(request, "Classroom score sheet saved successfully!")
        return HttpResponseRedirect(reverse('view_score_sheet', args=[score_sheet.id]))
    
    context = {
        'categories': categories,
        'title': 'Create Classroom Score Sheet',
        **permissions_context
    }
    
    return render(request, 'tottimeapp/class_score.html', context)

@login_required
def view_score_sheet(request, sheet_id):
    """View a completed score sheet"""
    # Check permissions for the specific page
    required_permission_id = 450  # Permission ID for "billing"
    permissions_context = check_permissions(request, required_permission_id)
    if isinstance(permissions_context, HttpResponseRedirect):
        return permissions_context
    
    main_user = get_user_for_view(request)
    score_sheet = get_object_or_404(ClassroomScoreSheet, id=sheet_id, main_user=main_user)
    score_items = score_sheet.score_items.all().select_related('criteria__category')
    
    # Group score items by category
    categories = defaultdict(list)
    for item in score_items:
        categories[item.criteria.category].append(item)
    
    # Calculate summary by category
    summary = []
    for category, items in categories.items():
        earned = sum(item.points_earned for item in items)
        available = sum(item.criteria.points_available for item in items)
        
        # Calculate percentage here instead of in the template
        percentage = 0
        if available > 0:
            percentage = round((earned / available) * 100)
            
        summary.append({
            'category': category,
            'earned': earned,
            'available': available,
            'percentage': percentage
        })
    
    context = {
        'score_sheet': score_sheet,
        'categories': dict(categories),
        'summary': summary,
        'total_earned': score_sheet.get_total_score(),
        'total_available': score_sheet.get_total_available(),
        'percentage': score_sheet.get_percentage(),
        'title': 'Classroom Score Details',
        **permissions_context
    }
    
    return render(request, 'tottimeapp/view_score_sheet.html', context)

@login_required
def score_sheet_list(request):
    """List all score sheets for the user"""
    # Check permissions for the specific page
    required_permission_id = 450  # Permission ID for "billing"
    permissions_context = check_permissions(request, required_permission_id)
    if isinstance(permissions_context, HttpResponseRedirect):
        return permissions_context
    
    # Get the main user
    main_user = get_user_for_view(request)
    
    # Get sheets for this user
    sheets = ClassroomScoreSheet.objects.filter(main_user=main_user).order_by('-date_of_observation')
    
    context = {
        'sheets': sheets,
        'title': 'Classroom Score Sheets',
        **permissions_context  # Unpack permissions context
    }
    
    return render(request, 'tottimeapp/score_sheet_list.html', context)

@login_required
def resources(request):
    """
    View to display all resources available to the user.
    Always shows resources for the main_user returned by get_user_for_view.
    Only shows general resources (filters out ABC Quality resources).
    """
    required_permission_id = 450  # Permission ID for "orientation"
    permissions_context = check_permissions(request, required_permission_id)
    if isinstance(permissions_context, HttpResponseRedirect):
        return permissions_context

    main_user = get_user_for_view(request)

    # Filter to show only general resources (not ABC Quality resources)
    resources = Resource.objects.filter(
        main_user=main_user
    ).exclude(
        resource_type='abc_quality'
    ).order_by('-uploaded_at')

    context = {
        'resources': resources,
        **permissions_context
    }
    return render(request, 'tottimeapp/resources.html', context)

@login_required
def upload_resource(request):
    """Handle resource upload"""
    if request.method == 'POST':
        title = request.POST.get('title')
        description = request.POST.get('description', '')
        file = request.FILES.get('file')
        
        if not file:
            messages.error(request, 'No file was uploaded!')
            return redirect('resources')
        
        # Check if file is PDF
        if not file.name.endswith('.pdf'):
            messages.error(request, 'Only PDF files are allowed!')
            return redirect('resources')
            
        # Check file size (limit to 10MB)
        if file.size > 10 * 1024 * 1024:
            messages.error(request, 'File size too large! Maximum size is 10MB.')
            return redirect('resources')
        
        # Determine the main user for account owners
        main_user = request.user
        if not request.user.is_account_owner and request.user.main_account_owner:
            main_user = request.user.main_account_owner
            
        # Create resource
        resource = Resource(
            user=request.user,
            main_user=main_user,
            title=title,
            description=description,
            file=file,
            resource_type='general'  # Explicitly set to 'general'
        )
        resource.save()
        
        messages.success(request, f'Resource "{title}" uploaded successfully!')
        return redirect('resources')
        
    return redirect('resources')

@login_required
def view_resource(request, resource_id):
    """View for displaying a resource"""
    try:
        resource = Resource.objects.get(pk=resource_id)
        
        # Security check - only allow access if:
        # 1. User owns the resource
        # 2. Resource is public
        # 3. User is account owner and resource belongs to linked user
        can_access = (
            resource.user == request.user or 
            resource.is_public or
            (request.user.is_account_owner and resource.user.main_account_owner == request.user)
        )
        
        if not can_access:
            messages.error(request, "You don't have permission to access this resource.")
            return redirect('resources')
            
        # Redirect to the file on S3
        return redirect(resource.file.url)
        
    except Resource.DoesNotExist:
        messages.error(request, "Resource not found.")
        return redirect('resources')

@login_required
def delete_resource(request, resource_id):
    """Delete a resource"""
    # Store the referring page to redirect back after deletion
    referer = request.META.get('HTTP_REFERER')
    
    try:
        resource = Resource.objects.get(pk=resource_id)
        
        # Security check - only allow deletion if:
        # 1. User owns the resource
        # 2. User is the account owner and resource belongs to linked user
        can_delete = (
            resource.user == request.user or 
            (request.user.is_account_owner and resource.user.main_account_owner == request.user)
        )
        
        if not can_delete:
            messages.error(request, "You don't have permission to delete this resource.")
            if referer and 'abc_quality' in referer:
                return redirect('abc_quality')
            return redirect('resources')
            
        # Store resource details before deletion
        title = resource.title
        resource_type = resource.resource_type
        
        # Delete the file and record
        resource.file.delete(save=False)  # Delete the file from S3
        resource.delete()  # Delete the database record
        
        messages.success(request, f'Resource "{title}" deleted successfully.')
        
        # Redirect based on resource type or referring URL
        if referer and 'abc_quality' in referer:
            return redirect('abc_quality')
        elif resource_type == 'abc_quality':
            return redirect('abc_quality')
        else:
            return redirect('resources')
        
    except Resource.DoesNotExist:
        messages.error(request, "Resource not found.")
        
        # Redirect based on referring URL
        if referer and 'abc_quality' in referer:
            return redirect('abc_quality')
        return redirect('resources')
    
def public_resource_signature(request, uuid):
    """View for public users to view and sign a resource"""
    # Get the main resource using the UUID
    main_resource = get_object_or_404(Resource, share_uuid=uuid)
    
    # Check for additional resource IDs in query parameters
    additional_ids = request.GET.get('additional_ids', '')
    resources = [main_resource]
    
    if additional_ids:
        # Get all resources
        resource_ids = [int(id) for id in additional_ids.split(',') if id.isdigit()]
        additional_resources = Resource.objects.filter(id__in=resource_ids).exclude(id=main_resource.id)
        resources = [main_resource] + list(additional_resources)
    
    if request.method == 'POST':
        # Handle form submission
        signature_data = request.POST.get('signature_data')
        signer_name = request.POST.get('signer_name')
        signer_email = request.POST.get('signer_email')
        
        # Get client IP
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip_address = x_forwarded_for.split(',')[0]
        else:
            ip_address = request.META.get('REMOTE_ADDR')
        
        # Create signature records for each resource
        for resource in resources:
            signature = ResourceSignature(
                resource=resource,
                signature_data=signature_data,
                signer_name=signer_name,
                signer_email=signer_email,
                ip_address=ip_address
            )
            signature.save()
        
        # Redirect to the confirmation page with all resource IDs
        additional_ids_param = ''
        if len(resources) > 1:
            additional_ids_param = f"?additional_ids={additional_ids}"
            
        return redirect(f"{reverse('signature_confirmation', kwargs={'uuid': uuid})}{additional_ids_param}")
    
    # Display the signature page with all resources
    return render(request, 'tottimeapp/public_pdf.html', {
        'resources': resources,
        'main_resource': main_resource
    })

def signature_confirmation(request, uuid):
    """
    View for displaying a confirmation page after a user has signed a resource.
    """
    # Get the main resource using the UUID
    main_resource = get_object_or_404(Resource, share_uuid=uuid)
    
    # Check for additional resource IDs in query parameters
    additional_ids = request.GET.get('additional_ids', '')
    resources = [main_resource]
    
    if additional_ids:
        # Get all resources
        resource_ids = [int(id) for id in additional_ids.split(',') if id.isdigit()]
        additional_resources = Resource.objects.filter(id__in=resource_ids).exclude(id=main_resource.id)
        resources = [main_resource] + list(additional_resources)
    
    return render(request, 'tottimeapp/signature_confirmation.html', {
        'resources': resources,
        'main_resource': main_resource
    })

@login_required
def send_signature_request(request):
    """Handle sending signature/print request emails for multiple resources"""
    if request.method == 'POST':
        resource_ids = request.POST.get('resource_ids', '').split(',')
        recipient_email = request.POST.get('recipient_email')
        email_message = request.POST.get('email_message', '')
        is_print_request = request.POST.get('is_print_request') == 'true'
        
        if not resource_ids or not recipient_email:
            return JsonResponse({'success': False, 'error': 'Missing required parameters'})
        
        try:
            # Get the resources
            resources = Resource.objects.filter(pk__in=resource_ids)
            
            # Check if we found all requested resources
            if len(resources) != len(resource_ids):
                return JsonResponse({'success': False, 'error': 'Some resources could not be found'})
            
            # Build the email message
            if is_print_request:
                subject = f"Forms to Print: {len(resources)} Document(s)"
            else:
                subject = f"Signature Request: {len(resources)} Document(s)"
            
            # Get the first resource for the main URL
            first_resource = resources.first()
            
            # Build the signature URL or download links for print
            current_site = get_current_site(request)
            
            if is_print_request:
                message = f"""
Hello,

You have received forms to print, complete by hand, and return:

"""
                # List all documents in the email
                for i, resource in enumerate(resources, 1):
                    message += f"{i}. {resource.title}\n"
                
                message += f"""
Please download, print, and complete these forms. 
The forms are attached to this email for your convenience.

"""
            else:
                # Create URL with resource IDs as query parameters
                resource_ids_param = ",".join([str(r.id) for r in resources])
                signature_url = f"https://{current_site.domain}{reverse('public_resource_signature', kwargs={'uuid': first_resource.share_uuid})}?additional_ids={resource_ids_param}"
                
                message = f"""
Hello,

You have received a signature request for the following documents:

"""
                # List all documents in the email
                for i, resource in enumerate(resources, 1):
                    message += f"{i}. {resource.title}\n"
                
                message += f"""
Please review and sign these documents using the link below:
{signature_url}

"""
            
            if email_message:
                message += f"\nMessage from sender:\n{email_message}\n"
                
            message += f"\nRegards,\n{request.user.get_full_name() or request.user.username}"
            
            # Send the email with attachments for print requests
            from django.core.mail import EmailMessage
            
            email = EmailMessage(
                subject,
                message,
                None,  # Use DEFAULT_FROM_EMAIL from settings
                [recipient_email]
            )
            
            # Attach PDFs for print requests
            if is_print_request:
                for resource in resources:
                    # Read the file content instead of using attach_file
                    if resource.file:
                        file_content = resource.file.read()
                        file_name = resource.file.name.split('/')[-1]  # Extract filename from path
                        email.attach(file_name, file_content, 'application/pdf')
            
            email.send(fail_silently=False)
            
            return JsonResponse({'success': True})
            
        except Exception as e:
            import traceback
            error_details = traceback.format_exc()
            pass  # print(error_details)  # Log the full error for debugging
            return JsonResponse({'success': False, 'error': str(e)})
    
    return JsonResponse({'success': False, 'error': 'Invalid request method'})

@login_required
def pdf_records(request):
    required_permission_id = 450  # Permission ID for "orientation"
    permissions_context = check_permissions(request, required_permission_id)
    if isinstance(permissions_context, HttpResponseRedirect):
        return permissions_context

    user = get_user_for_view(request)

    # If account owner, show only resources/signatures for their main_user
    if hasattr(user, 'is_account_owner') and user.is_account_owner:
        resources = Resource.objects.filter(main_user=user).order_by('-uploaded_at')
    else:
        resources = Resource.objects.filter(user=user).order_by('-uploaded_at')

    signatures = ResourceSignature.objects.filter(resource__in=resources).select_related('resource')

    resource_id = request.GET.get('resource')
    signer_email = request.GET.get('signer_email')
    date_from = request.GET.get('date_from')
    date_to = request.GET.get('date_to')

    if resource_id:
        signatures = signatures.filter(resource_id=resource_id)

    if signer_email:
        signatures = signatures.annotate(
            signer_email_lower=Lower('signer_email')
        ).filter(signer_email_lower__icontains=signer_email.lower())

    if date_from:
        signatures = signatures.filter(signed_at__date__gte=date_from)

    if date_to:
        signatures = signatures.filter(signed_at__date__lte=date_to)

    signatures = signatures.order_by('-signed_at')

    unique_signers = signatures.annotate(
        signer_email_lower=Lower('signer_email')
    ).values('signer_email_lower').distinct().count()

    documents_signed = signatures.values('resource').distinct().count()
    last_signature = signatures.first()
    last_signature_date = last_signature.signed_at if last_signature else None

    context = {
        'signatures': signatures,
        'resources': resources,
        'unique_signers': unique_signers,
        'documents_signed': documents_signed,
        'last_signature_date': last_signature_date,
        **permissions_context
    }

    return render(request, 'tottimeapp/pdf_records.html', context)

@login_required
def abc_quality(request):
    """
    View function for displaying ABC Quality standards and documentation.
    Fetches quality elements and indicators from the database and displays them
    along with any uploaded documentation.
    """
    required_permission_id = 450  # Permission ID for "orientation"
    permissions_context = check_permissions(request, required_permission_id)
    if isinstance(permissions_context, HttpResponseRedirect):
        return permissions_context
        
    # Get the main user for the current user
    main_user = get_user_for_view(request)
    
    # Get all main elements (those without a parent) with prefetched related data
    main_elements = ABCQualityElement.objects.filter(
        parent_element__isnull=True
    ).prefetch_related(
        'indicators', 
        'sections', 
        'sections__indicators'
    ).order_by('display_order')
    
    # Get only ABC Quality resources for this user
    abc_resources = Resource.objects.filter(
        main_user=main_user,
        resource_type='abc_quality'
    ).order_by('-uploaded_at')
    
    # Group resources by indicator for display
    grouped_resources = {}
    for resource in abc_resources:
        # Try to get indicator ID from the abc_indicator field first, then fall back to indicator_id string
        if resource.abc_indicator:
            indicator_id = resource.abc_indicator.indicator_id
        else:
            indicator_id = resource.indicator_id or "Uncategorized"
            
        if indicator_id not in grouped_resources:
            grouped_resources[indicator_id] = []
        grouped_resources[indicator_id].append(resource)
    
    # Add the resources to the context
    context = {
        'main_elements': main_elements,
        'grouped_resources': grouped_resources,
        **permissions_context
    }
    
    return render(request, 'tottimeapp/abc_quality.html', context)

@xframe_options_exempt
def proxy_page(request):
    """
    Proxy view that fetches content from another URL and returns only the main content
    without navigation, headers, and footers. Used for embedding pages in iframes.
    - Appends access_token from the incoming request to the fetched URL if missing.
    - Strips script tags from the extracted content and injects a read-only enforcer script
      that disables forms/inputs/buttons and prevents navigation.
    - Respects main_user context when fetching pages with public access tokens.
    """
    url = request.GET.get('url')
    proxy_token = request.GET.get('access_token') or request.GET.get('token') or ''
    if not url:
        return HttpResponse("No URL provided", status=400)

    try:
        # Build request with appropriate session/auth context
        session = requests.Session()
        
        # If we have a public access token, we need to ensure the proxied request
        # maintains the same main_user context
        headers = {}
        cookies = {}
        
        # Copy cookies from the current request to maintain session
        if request.COOKIES:
            cookies = dict(request.COOKIES)
        
        # If the proxied page doesn't already include an access_token, append the proxy token
        if proxy_token and 'access_token=' not in url:
            url += ('&' if '?' in url else '?') + f"access_token={urllib.parse.quote(proxy_token)}"

        # Fetch target content with session context
        response = session.get(url, timeout=10, cookies=cookies, headers=headers)
        response.raise_for_status()

        content_type = response.headers.get('Content-Type', '')
        if 'text/html' not in content_type:
            return HttpResponse(response.content, content_type=content_type, status=response.status_code)

        soup = BeautifulSoup(response.content, 'html.parser')

        # Collect inline styles and linked CSS (fix relative URLs)
        styles = []
        external_css = []
        head = soup.find('head')
        if head:
            for style in head.find_all('style'):
                styles.append(str(style))
            for link in head.find_all('link', rel='stylesheet'):
                href = link.get('href', '')
                if href:
                    if href.startswith('/') and not href.startswith('//'):
                        base_url = '/'.join(url.split('/')[:3])
                        href = f"{base_url}{href}"
                    elif not href.startswith(('http://', 'https://', '//')):
                        base_url = '/'.join(url.split('/')[:-1])
                        if not base_url.endswith('/'):
                            base_url += '/'
                        href = f"{base_url}{href}"
                    external_css.append(f'<link rel="stylesheet" href="{href}">')

        # Try to find main content using several heuristics
        content_area = None

        content_comments = soup.find_all(string=lambda text: isinstance(text, Comment) and
                                         ('BLOCK CONTENT START' in text or 'CONTENT BLOCK START' in text))
        if content_comments:
            for comment in content_comments:
                sibling = comment.next_element
                content_elements = []
                end_found = False
                while sibling and not end_found:
                    if isinstance(sibling, Comment) and ('BLOCK CONTENT END' in sibling or 'CONTENT BLOCK END' in sibling):
                        end_found = True
                        break
                    content_elements.append(str(sibling))
                    sibling = sibling.next_element
                if end_found:
                    content_html = ''.join(content_elements)
                    content_area = BeautifulSoup(content_html, 'html.parser')
                    break

        if not content_area:
            content_area = soup.select_one('.container.mt-5')
        if not content_area:
            content_area = soup.select_one('#main-content, .main-content')
        if not content_area:
            content_area = soup.select_one('main, article, .content, #content')

        # Build safe CSS strings
        styles_str = '\n'.join(styles)
        external_css_str = '\n'.join(external_css)

        # Read-only enforcer script (disables forms, inputs, buttons, prevents navigation)
        read_only_script = r"""
        <script>
        document.addEventListener('DOMContentLoaded', function(){
            // Disable forms and prevent submission
            document.querySelectorAll('form').forEach(function(f){
                try {
                    f.querySelectorAll('input,textarea,select,button').forEach(function(el){ el.disabled = true; });
                    f.addEventListener('submit', function(e){ e.preventDefault(); }, true);
                    f.removeAttribute('action');
                } catch(e){}
            });

            // Disable standalone buttons
            document.querySelectorAll('button').forEach(function(b){ b.disabled = true; });

            // Make links inert and preserve original href in data-original-href
            document.querySelectorAll('a[href]').forEach(function(a){
                var href = a.getAttribute('href');
                if(!href) return;
                // Keep anchor/hash links inert as well
                a.setAttribute('data-original-href', href);
                a.removeAttribute('href');
                a.style.cursor = 'default';
                a.addEventListener('click', function(e){ e.preventDefault(); });
            });

            // Remove inline event handler attributes
            document.querySelectorAll('*').forEach(function(el){
                ['onclick','onchange','onsubmit','onmouseover','onmousedown','onmouseup','onfocus','onblur'].forEach(function(attr){
                    if(el.hasAttribute && el.hasAttribute(attr)){
                        el.removeAttribute(attr);
                    }
                });
            });
        });
        </script>
        """

        # If content_area found, strip scripts and return cleaned HTML
        if content_area:
            # Remove unwanted nav/header/footer elements
            for nav_elem in content_area.select('nav, header, .navbar, footer, .footer, .site-header, .site-footer'):
                nav_elem.extract()

            # Remove all <script> tags from the extracted content to avoid activating behaviors
            for s in content_area.find_all('script'):
                s.decompose()

            # Also remove inline event attributes server-side where possible
            for el in content_area.find_all(True):
                for attr in list(el.attrs):
                    if attr.lower().startswith('on'):
                        try:
                            del el[attr]
                        except Exception:
                            pass

            response_html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Content Preview</title>

<!-- Bootstrap CSS -->
<link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css" rel="stylesheet">

<!-- Font Awesome -->
<link href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.3.0/css/all.min.css" rel="stylesheet">

{external_css_str}
{styles_str}

<style>
body {{ padding: 0; margin: 0; background-color: #ffffff; }}
.proxy-container {{ padding: 20px; width: 100%; }}
</style>
</head>
<body>
<div class="proxy-container">
{str(content_area)}
</div>

<!-- jQuery (used only for styling/helpers) -->
<script src="https://code.jquery.com/jquery-3.6.0.min.js"></script>
<!-- Bootstrap JS (kept minimal) -->
<script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/js/bootstrap.bundle.min.js"></script>

{read_only_script}
</body>
</html>"""
            return HttpResponse(response_html, content_type='text/html')

        # Fallback: strip navigation from full body and return
        body = soup.find('body')
        if body:
            for nav in body.select('nav, header, .navbar, footer, .site-header, .site-footer'):
                nav.extract()

            # Remove scripts and inline on* attrs from fallback body
            for s in body.find_all('script'):
                s.decompose()
            for el in body.find_all(True):
                for attr in list(el.attrs):
                    if attr.lower().startswith('on'):
                        try:
                            del el[attr]
                        except Exception:
                            pass

            response_html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Page Preview</title>

<!-- Bootstrap CSS -->
<link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css" rel="stylesheet">

<!-- Font Awesome -->
<link href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.3.0/css/all.min.css" rel="stylesheet">

{external_css_str}
{styles_str}

<style>
body {{ padding: 0; margin: 0; background-color: #ffffff; }}
.proxy-container {{ padding: 20px; width: 100%; }}
</style>
</head>
<body>
<div class="proxy-container">
{str(body)}
</div>

<!-- jQuery -->
<script src="https://code.jquery.com/jquery-3.6.0.min.js"></script>
<!-- Bootstrap JS -->
<script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/js/bootstrap.bundle.min.js"></script>

{read_only_script}
</body>
</html>"""
            return HttpResponse(response_html, content_type='text/html')

        # If all else fails, return original content with warning
        return HttpResponse(f"""<!DOCTYPE html>
<html>
<head><title>Content Extraction Failed</title></head>
<body>
<div class="alert alert-warning">
<p>Could not extract main content from the page. Showing original content instead.</p>
</div>
{response.text}
</body>
</html>""", content_type='text/html')

    except requests.RequestException as e:
        logger.error(f"Error fetching URL {url}: {str(e)}")
        return HttpResponse(f"""
<div class="alert alert-danger">
<h4>Error fetching page</h4>
<p>Could not load the requested page. The server may be unavailable or the URL may be incorrect.</p>
<p class="text-muted small">Error details: {str(e)}</p>
</div>
""", content_type='text/html', status=502)
    except Exception as e:
        logger.exception(f"Unexpected error in proxy_page: {str(e)}")
        return HttpResponse(f"""
<div class="alert alert-danger">
<h4>Error processing page</h4>
<p>An error occurred while processing the requested page.</p>
<p class="text-muted small">Error details: {str(e)}</p>
</div>
""", content_type='text/html', status=500)

def abc_quality_public(request, token):
    """
    Public view function for displaying ABC Quality standards and documentation.
    Accepts tokens created as TemporaryAccess and scopes data to the token's user (location).
    """
    # Try to find the temporary access token
    try:
        temp_access = TemporaryAccess.objects.get(token=token, is_active=True)
        if not temp_access.is_valid:
            return render(request, 'tottimeapp/link_expired.html')
        
        # The main_user is derived from the token's user field (the location)
        main_user = temp_access.user
        expires_at = temp_access.expires_at
        
        # Update last_used timestamp
        temp_access.last_used = timezone.now()
        temp_access.save(update_fields=['last_used'])
        
    except TemporaryAccess.DoesNotExist:
        raise Http404("Public link not found or expired")

    # Fetch ABC Quality elements (same for all locations)
    main_elements = ABCQualityElement.objects.filter(
        parent_element__isnull=True
    ).prefetch_related(
        'indicators', 
        'sections', 
        'sections__indicators'
    ).order_by('display_order')

    # Get resources scoped to this specific location (main_user)
    abc_resources = Resource.objects.filter(
        main_user=main_user,
        resource_type='abc_quality'
    ).order_by('-uploaded_at')

    # Group resources by indicator
    grouped_resources = {}
    for resource in abc_resources:
        if resource.abc_indicator:
            indicator_id = resource.abc_indicator.indicator_id
        else:
            indicator_id = resource.indicator_id or "Uncategorized"
        grouped_resources.setdefault(indicator_id, []).append(resource)

    expiry_date = expires_at.strftime("%B %d, %Y at %I:%M %p")
    location_name = main_user.company_name or main_user.get_full_name()

    context = {
        'main_elements': main_elements,
        'grouped_resources': grouped_resources,
        'expiry_date': expiry_date,
        'location_name': location_name,
        'is_public': True,
        'public_token': str(token),
    }

    return render(request, 'tottimeapp/abc_quality_public.html', context)

@login_required
def get_indicator_link(request, indicator_id):
    """
    Return indicator link data for the specified indicator, scoped to current location.
    """
    main_user = get_user_for_view(request)
    
    logger.info(f"Fetching link for indicator {indicator_id}, main_user {main_user.id}")
    
    try:
        indicator = ABCQualityIndicator.objects.get(pk=indicator_id)
    except ABCQualityIndicator.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Indicator not found'}, status=404)

    try:
        link = IndicatorPageLink.objects.get(indicator=indicator, main_user=main_user)
        logger.info(f"Found link: {link.id}, page_template: {link.page_template}")
        link_data = {
            'page_template': link.page_template,
            'title': link.title,
            'updated_at': link.updated_at.strftime('%b %d, %Y %H:%M'),
            'page_url': link.page_template,
            'main_user_id': main_user.id  # Added for debugging
        }
    except IndicatorPageLink.DoesNotExist:
        logger.info(f"No link found for indicator {indicator.id} and main_user {main_user.id}")
        link_data = None

    return JsonResponse({'success': True, 'link': link_data, 'main_user_id': main_user.id})

@login_required
@require_POST
def save_indicator_link(request):
    try:
        main_user = get_user_for_view(request)
        indicator_db_id = request.POST.get('indicator_id')
        page_template = request.POST.get('page_template', '').strip()
        title = request.POST.get('title', '').strip()
        
        logger.info(f"Save request - User: {request.user.id}, Main User: {main_user.id}, Indicator: {indicator_db_id}")
        
        if not indicator_db_id:
            return JsonResponse({'success': False, 'error': 'Missing indicator id'}, status=400)
        
        if not page_template:
            return JsonResponse({'success': False, 'error': 'Page URL is required'}, status=400)
        
        try:
            indicator = ABCQualityIndicator.objects.get(pk=indicator_db_id)
        except ABCQualityIndicator.DoesNotExist:
            return JsonResponse({'success': False, 'error': 'Indicator not found'}, status=404)

        # Debug logging
        logger.info(f"Saving link for indicator {indicator.id}, main_user {main_user.id}, page_template: {page_template}")

        link, created = IndicatorPageLink.objects.update_or_create(
            indicator=indicator,
            main_user=main_user,
            defaults={'page_template': page_template, 'title': title}
        )
        
        logger.info(f"Link {'created' if created else 'updated'}: {link.id}")
        
        # Return more info for debugging
        return JsonResponse({
            'success': True,
            'created': created,
            'link_id': link.id,
            'main_user_id': main_user.id,
            'indicator_id': indicator.id
        })
        
    except Exception as e:
        logger.exception(f"Error saving indicator link: {str(e)}")
        return JsonResponse({
            'success': False,
            'error': f'Server error: {str(e)}'
        }, status=500)

@login_required
@require_POST
def remove_indicator_link(request, indicator_id):
    main_user = get_user_for_view(request)
    
    try:
        indicator = ABCQualityIndicator.objects.get(pk=indicator_id)
    except ABCQualityIndicator.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Indicator not found'}, status=404)
    
    IndicatorPageLink.objects.filter(indicator=indicator, main_user=main_user).delete()
    return JsonResponse({'success': True})

def get_page_preview(request, indicator_id):
    """
    Returns page preview info for the indicator, scoped to the authenticated user's location.
    Works for both logged-in users and public token access.
    """
    # Determine main_user from either logged-in user or public token
    if request.user.is_authenticated:
        main_user = get_user_for_view(request)
    else:
        # Public access: get main_user from token in query params
        token = request.GET.get('access_token')
        if not token:
            return JsonResponse({'success': False, 'message': 'No access token provided'}, status=403)
        
        try:
            temp_access = TemporaryAccess.objects.get(token=token, is_active=True)
            if not temp_access.is_valid:
                return JsonResponse({'success': False, 'message': 'Access token expired'}, status=403)
            main_user = temp_access.user
            
            # Update last_used timestamp
            temp_access.last_used = timezone.now()
            temp_access.save(update_fields=['last_used'])
            
        except (TemporaryAccess.DoesNotExist, ValueError):
            # ValueError handles malformed UUIDs
            return JsonResponse({'success': False, 'message': 'Invalid access token'}, status=403)
    
    try:
        indicator = ABCQualityIndicator.objects.get(pk=indicator_id)
        try:
            # Fetch the page link scoped to the main_user from the token
            page_link = IndicatorPageLink.objects.get(indicator=indicator, main_user=main_user)
            
            return JsonResponse({
                'success': True,
                'title': page_link.title or f"Preview for {indicator.indicator_id}",
                'page_url': page_link.page_template,
                'content': 'Loading content from URL...',
                'main_user_id': main_user.id  # Debug info
            })
        except IndicatorPageLink.DoesNotExist:
            return JsonResponse({
                'success': False,
                'message': f'No page link found for this indicator at {main_user.company_name or "this location"}'
            })
    except ABCQualityIndicator.DoesNotExist:
        return JsonResponse({
            'success': False,
            'message': 'Indicator not found'
        }, status=404)
    
@login_required
def create_public_link(request):
    """
    Creates a public access link for the current user's location.
    The link is permanently tied to the location at the time of creation,
    regardless of future location switches.
    """
    if request.method == 'POST':
        # Get the CURRENT location the user is viewing
        main_user = get_user_for_view(request)
        
        days_valid = int(request.POST.get('days_valid', 7))
        purpose = request.POST.get('purpose', 'ABC Quality Documentation Access')

        # Calculate expiry
        expires_at = timezone.now() + timedelta(days=days_valid)

        # Create temporary access token - this locks to the current main_user
        # Even if the creator switches locations later, this token will always
        # show data for the main_user it was created with
        temp_access = TemporaryAccess.objects.create(
            user=main_user,  # This is the location being shared
            expires_at=expires_at,
            purpose=purpose,
            target_url=f'/abc-quality/public/',
            is_active=True
        )

        # Build the public URL with the token
        public_path = reverse('abc_quality_public', args=[str(temp_access.token)])
        public_url = request.build_absolute_uri(public_path)

        logger.info(f"Public link created by user {request.user.id} for location {main_user.id} ({main_user.company_name})")

        return JsonResponse({
            'success': True,
            'url': public_url,
            'expires_at': expires_at.strftime("%B %d, %Y at %I:%M %p"),
            'location': main_user.company_name or main_user.get_full_name()
        })

    return JsonResponse({'success': False, 'error': 'Invalid request method'}, status=405)

def public_access_redirect(request, token):
    """
    Clean public entrypoint. Look up token, validate, then redirect to target_url
    with access_token query param so middleware/auth backend will log the user in.
    """
    temp_access = get_object_or_404(TemporaryAccess, token=token, is_active=True)
    if not temp_access.is_valid:
        return render(request, 'tottimeapp/link_expired.html')

    # ensure target_url starts with '/'
    target = temp_access.target_url or '/abc-quality/'
    if not target.startswith('/'):
        target = '/' + target

    redirect_url = f"{target}?access_token={token}"
    return redirect(redirect_url)

@login_required
def upload_documentation(request):
    if request.method == 'POST':
        indicator_id = request.POST.get('indicator_id')
        indicator_db_id = request.POST.get('indicator_db_id')
        description = request.POST.get('description', '')
        files = request.FILES.getlist('document_file')
        
        # Find the indicator model - prefer using direct ID if available
        indicator = None
        if indicator_db_id:
            try:
                indicator = ABCQualityIndicator.objects.get(id=indicator_db_id)
                # If we found it by DB ID, make sure we use the correct indicator_id
                indicator_id = indicator.indicator_id
            except (ABCQualityIndicator.DoesNotExist, ValueError):
                pass
                
        # Fallback to string lookup if DB ID didn't work
        if not indicator and indicator_id:
            try:
                indicator = ABCQualityIndicator.objects.get(indicator_id=indicator_id)
            except ABCQualityIndicator.DoesNotExist:
                pass
            
        uploaded_count = 0
        for file in files:
            # Create a title that includes the indicator ID
            title = f"ABC Quality - {indicator_id}"
            
            # Determine the main user for account owners
            main_user = request.user
            if not request.user.is_account_owner and request.user.main_account_owner:
                main_user = request.user.main_account_owner
            
            # Create new resource entry
            resource = Resource(
                user=request.user,
                main_user=main_user,
                title=title,
                description=description,
                file=file,
                resource_type='abc_quality',
                indicator_id=indicator_id,  # Keep for backward compatibility
                abc_indicator=indicator     # Link to the actual indicator model
            )
            resource.save()
            uploaded_count += 1
        
        if uploaded_count > 0:
            messages.success(request, f"Successfully uploaded {uploaded_count} file(s) for indicator {indicator_id}")
        else:
            messages.warning(request, "No files were uploaded")
            
        return redirect('abc_quality')
    
    # If GET request, redirect to ABC Quality page
    return redirect('abc_quality')

@login_required
def compile_all_documents(request):
    """Handle compiling all documents for an element or section into PDF"""
    if request.method == 'POST':
        # Log incoming request details
        logger.info(f"PDF compilation request received. Headers: {request.headers}")
        
        element = request.POST.get('element')
        section = request.POST.get('section', '')
        action = request.POST.get('action')
        email = request.POST.get('email', '')
        email_message = request.POST.get('email_message', '')
        
        try:
            # Get AWS credentials from settings
            aws_access_key = getattr(settings, 'AWS_ACCESS_KEY_ID', None)
            aws_secret_key = getattr(settings, 'AWS_SECRET_ACCESS_KEY', None)
            s3_bucket_name = getattr(settings, 'AWS_STORAGE_BUCKET_NAME', None)
            s3_region = getattr(settings, 'AWS_S3_REGION_NAME', 'us-east-1')
            
            # Initialize S3 client if we have AWS credentials
            s3_client = None
            if aws_access_key and aws_secret_key and s3_bucket_name:
                try:
                    s3_client = boto3.client(
                        's3',
                        aws_access_key_id=aws_access_key,
                        aws_secret_access_key=aws_secret_key,
                        region_name=s3_region,
                        config=Config(signature_version='s3v4')
                    )
                    logger.info(f"S3 client initialized successfully for bucket: {s3_bucket_name}")
                except Exception as e:
                    logger.error(f"Error initializing S3 client: {e}")
                    s3_client = None
            
            # Get the main user for resource lookup
            main_user = get_user_for_view(request)
            
            # Handle the 'all' case for compiling everything
            if element == 'all':
                scope_description = "All Elements and Sections"
                indicators = ABCQualityIndicator.objects.all()
                filename_suffix = "all"
            else:
                scope_description = f"Element {element}"
                filename_suffix = element
                
                if section:
                    scope_description += f", Section: {section}"
                    filename_suffix += f"_{section.replace(' ', '_')}"
                
                if section:
                    indicators = ABCQualityIndicator.objects.filter(
                        element__element_number=element,
                        section__name=section
                    )
                else:
                    indicators = ABCQualityIndicator.objects.filter(
                        element__element_number=element
                    )
            
            # Get all resources for these indicators
            indicator_ids = [indicator.indicator_id for indicator in indicators]
            
            # Log debug information
            logger.debug(f"Found {len(indicator_ids)} indicators: {indicator_ids}")
            
            # First try to find resources linked to the indicator model - filter by main_user
            resources_with_abc_indicator = Resource.objects.filter(
                main_user=main_user,
                abc_indicator__indicator_id__in=indicator_ids,
                resource_type='abc_quality'
            ).order_by('abc_indicator__indicator_id')
            
            # Also get resources that only have the string indicator_id - filter by main_user
            resources_with_string_id = Resource.objects.filter(
                main_user=main_user,
                indicator_id__in=indicator_ids,
                abc_indicator__isnull=True,
                resource_type='abc_quality'
            ).order_by('indicator_id')
            
            # Log debug information
            logger.debug(f"Found {resources_with_abc_indicator.count()} resources with ABC indicator")
            logger.debug(f"Found {resources_with_string_id.count()} resources with string indicator ID")
            
            # Combine the querysets
            from itertools import chain
            resources = list(chain(resources_with_abc_indicator, resources_with_string_id))
            
            # If no resources, return a message
            if not resources:
                error_message = f'No documents found for {scope_description}. Please upload documents for this element/section first.'
                logger.warning(error_message)
                
                if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                    return JsonResponse({'success': False, 'error': error_message})
                else:
                    messages.warning(request, error_message)
                    return redirect('abc_quality')
            
            # Log the number of resources found
            logger.info(f"Found {len(resources)} resources to compile")
            
            # Import required libraries for PDF generation
            from reportlab.lib.pagesizes import letter
            from reportlab.lib import colors
            from reportlab.lib.units import inch
            from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Image, Table, TableStyle, PageBreak
            from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
            from reportlab.lib.enums import TA_CENTER, TA_LEFT
            from io import BytesIO
            import os
            import tempfile
            import fitz  # PyMuPDF
            from PIL import Image as PILImage
            import io
            import requests
            
            # Create a BytesIO buffer for the PDF
            buffer = BytesIO()
            
            # Create the PDF document
            doc = SimpleDocTemplate(
                buffer,
                pagesize=letter,
                title=f"ABC Quality Documentation - {scope_description}",
                author="ABC Quality System",
                subject=f"Documentation for {scope_description}",
                topMargin=0.5*inch,
                bottomMargin=0.5*inch,
                leftMargin=0.5*inch,
                rightMargin=0.5*inch
            )
            
            # Get styles
            styles = getSampleStyleSheet()
            
            # Create custom styles
            header_style = ParagraphStyle(
                'HeaderStyle',
                parent=styles['Heading1'],
                fontSize=16,
                alignment=TA_CENTER,
                spaceAfter=12
            )
            
            subheader_style = ParagraphStyle(
                'SubHeaderStyle',
                parent=styles['Heading2'],
                fontSize=14,
                alignment=TA_CENTER,
                spaceAfter=10
            )
            
            indicator_style = ParagraphStyle(
                'IndicatorStyle',
                parent=styles['Heading3'],
                fontSize=12,
                backColor=colors.lightgrey,
                borderPadding=5,
                spaceAfter=8
            )
            
            file_title_style = ParagraphStyle(
                'FileTitleStyle',
                parent=styles['Normal'],
                fontSize=10,
                fontName='Helvetica-Bold'
            )
            
            normal_style = ParagraphStyle(
                'NormalStyle',
                parent=styles['Normal'],
                fontSize=10
            )
            
            description_style = ParagraphStyle(
                'DescriptionStyle',
                parent=styles['Italic'],
                fontSize=9,
                textColor=colors.darkgrey,
                leftIndent=10
            )
            
            # Start building the document content
            elements = []
            
            # Add title
            elements.append(Paragraph(f"ABC Quality Documentation", header_style))
            elements.append(Paragraph(f"{scope_description}", subheader_style))
            
            # Add date
            from datetime import datetime
            current_date = datetime.now().strftime("%B %d, %Y")
            elements.append(Paragraph(f"Compiled on: {current_date}", normal_style))
            elements.append(Spacer(1, 0.25*inch))
            
            # Track the current indicator to group resources
            current_indicator = None
            
            # Process each resource
            for resource in resources:
                try:
                    # Get the indicator ID from the resource
                    if hasattr(resource, 'abc_indicator') and resource.abc_indicator:
                        indicator_id = resource.abc_indicator.indicator_id
                    else:
                        indicator_id = resource.indicator_id
                    
                    # Check if we need to start a new indicator section
                    if current_indicator != indicator_id:
                        current_indicator = indicator_id
                        
                        # Add some spacing between indicator sections
                        if elements and not isinstance(elements[-1], PageBreak):
                            elements.append(Spacer(1, 0.3*inch))
                        
                        # Add indicator header
                        try:
                            indicator_obj = ABCQualityIndicator.objects.get(indicator_id=current_indicator)
                            indicator_desc = indicator_obj.description
                        except Exception as e:
                            logger.error(f"Error getting indicator description: {e}")
                            indicator_desc = "Unknown Description"
                        
                        elements.append(Paragraph(f"Indicator {current_indicator}: {indicator_desc}", indicator_style))
                    
                    # Get the file details
                    try:
                        if hasattr(resource, 'filename') and callable(resource.filename):
                            file_name = resource.filename()
                        elif hasattr(resource, 'filename') and resource.filename:
                            file_name = resource.filename
                        elif hasattr(resource.file, 'name'):
                            file_name = os.path.basename(resource.file.name)
                        else:
                            file_name = "Untitled Document"
                    except Exception as e:
                        logger.error(f"Error getting filename: {e}")
                        file_name = "Unknown File"
                    
                    # Add file info
                    elements.append(Paragraph(f"File: {file_name}", file_title_style))
                    
                    if hasattr(resource, 'uploaded_at'):
                        upload_date = resource.uploaded_at.strftime('%b %d, %Y')
                        elements.append(Paragraph(f"Uploaded: {upload_date}", normal_style))
                    
                    if hasattr(resource, 'description') and resource.description:
                        elements.append(Paragraph(f"{resource.description}", description_style))
                    
                    elements.append(Spacer(1, 0.1*inch))
                    
                    # Get file content and add preview based on file type
                    if not hasattr(resource, 'file') or not resource.file:
                        elements.append(Paragraph("File is not available", normal_style))
                        continue
                    
                    # Get the file content using S3 pre-signed URL or direct file access
                    file_content = None
                    file_key = None
                    
                    # First try to get the S3 key directly
                    if hasattr(resource.file, 'name'):
                        file_key = resource.file.name
                        # Remove any leading slash
                        if file_key.startswith('/'):
                            file_key = file_key[1:]
                    
                    # If we have S3 client and a key, use presigned URL
                    if s3_client and file_key and s3_bucket_name:
                        try:
                            logger.info(f"Generating presigned URL for: {file_key} from bucket {s3_bucket_name}")
                            
                            # Generate pre-signed URL with one hour expiration
                            url = s3_client.generate_presigned_url(
                                ClientMethod='get_object',
                                Params={'Bucket': s3_bucket_name, 'Key': file_key},
                                ExpiresIn=3600  # URL valid for 1 hour
                            )
                            
                            logger.info(f"Presigned URL generated: {url}")
                            
                            # Download file using requests
                            response = requests.get(url, timeout=30)
                            if response.status_code == 200:
                                file_content = BytesIO(response.content)
                                logger.info(f"File successfully downloaded from S3: {file_key}")
                            else:
                                logger.warning(f"Failed to download S3 file: {response.status_code}")
                        except Exception as s3_err:
                            logger.error(f"Error downloading from S3: {s3_err}")
                    
                    # If S3 download failed or not available, try direct read
                    if not file_content:
                        try:
                            file_content = BytesIO()
                            file_content.write(resource.file.read())
                            file_content.seek(0)
                            resource.file.seek(0)  # Reset file pointer
                            logger.info(f"File read directly from storage: {file_name}")
                        except Exception as file_err:
                            logger.error(f"Error reading file directly: {file_err}")
                            elements.append(Paragraph(f"Could not access file: {str(file_err)}", normal_style))
                            continue
                    
                    # Process file based on type
                    file_name_lower = file_name.lower()
                    
                    # Handle different file types
                    if file_name_lower.endswith(('.jpg', '.jpeg', '.png', '.gif', '.bmp')):
                        # It's an image, add it directly
                        try:
                            img = PILImage.open(file_content)
                            img_width, img_height = img.size
                            
                            # Calculate dimensions to fit in PDF
                            max_width = 6 * inch
                            max_height = 7 * inch
                            
                            width_ratio = max_width / img_width
                            height_ratio = max_height / img_height
                            ratio = min(width_ratio, height_ratio)
                            
                            display_width = img_width * ratio
                            display_height = img_height * ratio
                            
                            # Create a temporary BytesIO for the image
                            img_temp = BytesIO()
                            img.save(img_temp, format=img.format or 'PNG')
                            img_temp.seek(0)
                            
                            # Add the image to the PDF
                            img_obj = Image(img_temp, width=display_width, height=display_height)
                            elements.append(img_obj)
                            
                        except Exception as img_err:
                            logger.error(f"Error processing image {file_name}: {img_err}")
                            elements.append(Paragraph(f"Error loading image: {str(img_err)}", normal_style))
                    
                    elif file_name_lower.endswith('.pdf'):
                        # Handle PDF files - add all pages
                        try:
                            # Use PyMuPDF to open the PDF from memory
                            pdf_document = fitz.open(stream=file_content.getvalue(), filetype="pdf")
                            page_count = pdf_document.page_count
                            
                            elements.append(Paragraph(f"PDF document with {page_count} pages:", normal_style))
                            elements.append(Spacer(1, 0.1*inch))
                            
                            # Process each page (limit to first 10 pages for performance)
                            max_pages = min(page_count, 10)
                            for page_num in range(max_pages):
                                page = pdf_document[page_num]
                                
                                # INCREASED RESOLUTION: Use a higher zoom factor
                                zoom_factor = 2.0
                                
                                # Create a matrix with higher resolution
                                matrix = fitz.Matrix(zoom_factor, zoom_factor)
                                
                                # Get the pixmap with higher resolution and no alpha channel
                                pix = page.get_pixmap(matrix=matrix, alpha=False)
                                
                                # Calculate DPI based on zoom factor (72 is the base DPI)
                                dpi = 72 * zoom_factor
                                logger.info(f"Rendering PDF page at {dpi} DPI")
                                
                                # Create a temp BytesIO for this page
                                # Don't use the 'quality' parameter with tobytes since older versions may not support it
                                img_data = pix.tobytes("png")  # Use PNG instead of JPEG for better quality
                                img_stream = io.BytesIO(img_data)
                                
                                # Calculate dimensions
                                max_width = 6 * inch
                                max_height = 8 * inch
                                
                                width_ratio = max_width / pix.width
                                height_ratio = max_height / pix.height
                                ratio = min(width_ratio, height_ratio)
                                
                                display_width = pix.width * ratio
                                display_height = pix.height * ratio
                                
                                # Add page number
                                elements.append(Paragraph(f"Page {page_num + 1} of {page_count}", normal_style))
                                
                                # Add the image
                                img = Image(img_stream, width=display_width, height=display_height)
                                elements.append(img)
                                elements.append(Spacer(1, 0.2*inch))
                            
                            if page_count > max_pages:
                                elements.append(Paragraph(f"(Showing {max_pages} of {page_count} pages)", normal_style))
                            
                            # Close the PDF
                            pdf_document.close()
                        except Exception as pdf_err:
                            logger.error(f"Error processing PDF {file_name}: {pdf_err}")
                            elements.append(Paragraph(f"Error processing PDF: {str(pdf_err)}", normal_style))
                    
                    else:
                        # Unsupported file type
                        elements.append(Paragraph(f"Preview not available for this file type.", normal_style))
                
                except Exception as e:
                    logger.error(f"Error processing resource: {e}")
                    elements.append(Paragraph(f"Error processing file: {str(e)}", normal_style))
                
                # Add a separator after each file
                elements.append(Spacer(1, 0.3*inch))
                elements.append(PageBreak())
            
            # Build the PDF document
            doc.build(elements)
            
            # Get the PDF data
            buffer.seek(0)
            logger.info(f"PDF compilation complete. Size: {buffer.getbuffer().nbytes} bytes")
            
            if action == 'download':
                # Return the PDF as a download with explicit headers
                try:
                    logger.info(f"Preparing download response for: {scope_description}")
                    
                    from django.http import HttpResponse, FileResponse
                    
                    # Use FileResponse which is better for handling file downloads
                    response = FileResponse(
                        buffer,
                        as_attachment=True,
                        filename=f"abc_quality_{filename_suffix}.pdf",
                        content_type='application/pdf'
                    )
                    
                    # Set additional headers to prevent caching
                    response['Cache-Control'] = 'no-cache, no-store, must-revalidate'
                    response['Pragma'] = 'no-cache'
                    response['Expires'] = '0'
                    
                    logger.info("PDF download response created successfully")
                    return response
                    
                except Exception as download_error:
                    logger.error(f"Error creating download response: {download_error}")
                    messages.error(request, f"Error preparing download: {str(download_error)}")
                    return redirect('abc_quality')
            
            elif action == 'email' and email:
                # Save PDF to a temporary file
                with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as temp_pdf:
                    temp_pdf.write(buffer.getvalue())
                    temp_pdf_path = temp_pdf.name
                
                # Send email with PDF attachment
                try:
                    logger.info(f"Preparing email to {email} with PDF attachment")
                    
                    email_subject = f"ABC Quality Documentation - {scope_description}"
                    email_body = f"Please find attached the compiled documentation for {scope_description}."
                    
                    if email_message:
                        email_body += f"\n\nMessage from sender:\n{email_message}"
                    
                    from django.core.mail import EmailMessage
                    email_obj = EmailMessage(
                        subject=email_subject,
                        body=email_body,
                        from_email=None,  # Use DEFAULT_FROM_EMAIL
                        to=[email],
                    )
                    
                    # Attach the PDF
                    with open(temp_pdf_path, 'rb') as f:
                        email_obj.attach(
                            f'abc_quality_{filename_suffix}.pdf',
                            f.read(),
                            'application/pdf'
                        )
                    
                    # Send the email
                    email_obj.send()
                    logger.info(f"Email with PDF attachment sent to {email}")
                    
                    # Delete the temporary file
                    os.unlink(temp_pdf_path)
                    
                    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                        return JsonResponse({'success': True})
                    else:
                        messages.success(request, f"Documentation for {scope_description} has been emailed to {email}.")
                        return redirect('abc_quality')
                    
                except Exception as e:
                    import traceback
                    error_details = traceback.format_exc()
                    logger.error(f"Failed to send email: {error_details}")
                    
                    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                        return JsonResponse({'success': False, 'error': str(e)})
                    else:
                        messages.error(request, f"Failed to send email: {str(e)}")
                        return redirect('abc_quality')
        
        except Exception as e:
            import traceback
            error_details = traceback.format_exc()
            logger.error(f"Error compiling documents: {error_details}")
            
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({'success': False, 'error': str(e)})
            else:
                messages.error(request, f"Error compiling documents: {str(e)}")
                return redirect('abc_quality')
    
    # If not a POST request or any other issue
    return redirect('abc_quality')

@login_required
def surveys_list(request):
    required_permission_id = 450
    permissions_context = check_permissions(request, required_permission_id)
    if isinstance(permissions_context, HttpResponseRedirect):
        return permissions_context

    main_user = get_user_for_view(request)
    surveys = Survey.objects.filter(main_user=main_user).order_by('-created_at')
    context = {
        'surveys': surveys,
        **permissions_context
    }
    return render(request, 'tottimeapp/surveys.html', context)

@login_required
def create_survey(request):
    required_permission_id = 450
    permissions_context = check_permissions(request, required_permission_id)
    if isinstance(permissions_context, HttpResponseRedirect):
        return permissions_context

    from .forms import SurveyForm
    if request.method == 'POST':
        form = SurveyForm(request.POST)
        if form.is_valid():
            survey = form.save(commit=False)
            survey.main_user = get_user_for_view(request)
            survey.save()
            return redirect('edit_survey', survey_id=survey.id)
    else:
        form = SurveyForm()
    return render(request, 'tottimeapp/create_survey.html', {'form': form, **permissions_context})

@login_required
def edit_survey(request, survey_id):
    required_permission_id = 450
    permissions_context = check_permissions(request, required_permission_id)
    if isinstance(permissions_context, HttpResponseRedirect):
        return permissions_context

    survey = get_object_or_404(Survey, id=survey_id)
    if request.method == 'POST':
        form = SurveyForm(request.POST, instance=survey)
        if form.is_valid():
            form.save()
            messages.success(request, "Survey updated successfully")
            return redirect('surveys_list')
    else:
        form = SurveyForm(instance=survey)
    questions = survey.questions.all().order_by('order')
    context = {
        'form': form,
        'survey': survey,
        'questions': questions,
        **permissions_context
    }
    return render(request, 'tottimeapp/edit_survey.html', context)

@login_required
def add_question(request, survey_id):
    required_permission_id = 450
    permissions_context = check_permissions(request, required_permission_id)
    if isinstance(permissions_context, HttpResponseRedirect):
        return permissions_context

    survey = get_object_or_404(Survey, id=survey_id)
    if request.method == 'POST':
        form = QuestionForm(request.POST)
        if form.is_valid():
            question = form.save(commit=False)
            question.survey = survey
            question.order = survey.questions.count() + 1
            question.save()
            if question.question_type == 'multiple' and 'choices' in request.POST:
                for choice_text in request.POST.getlist('choices'):
                    if choice_text.strip():
                        Choice.objects.create(question=question, text=choice_text.strip())
            messages.success(request, "Question added successfully")
            return redirect('edit_survey', survey_id=survey.id)
    else:
        form = QuestionForm()
    context = {
        'form': form,
        'survey': survey,
        **permissions_context
    }
    return render(request, 'tottimeapp/add_question.html', context)

@login_required
def edit_question(request, question_id):
    required_permission_id = 450
    permissions_context = check_permissions(request, required_permission_id)
    if isinstance(permissions_context, HttpResponseRedirect):
        return permissions_context

    question = get_object_or_404(Question, id=question_id)
    survey = question.survey
    if request.method == 'POST':
        form = QuestionForm(request.POST, instance=question)
        if form.is_valid():
            form.save()
            if question.question_type == 'multiple':
                question.choices.all().delete()
                for choice_text in request.POST.getlist('choices'):
                    if choice_text.strip():
                        Choice.objects.create(question=question, text=choice_text.strip())
            messages.success(request, "Question updated successfully")
            return redirect('edit_survey', survey_id=survey.id)
    else:
        form = QuestionForm(instance=question)
    context = {
        'form': form,
        'question': question,
        'survey': survey,
        **permissions_context
    }
    return render(request, 'tottimeapp/edit_question.html', context)

@login_required
def delete_question(request, question_id):
    required_permission_id = 450
    permissions_context = check_permissions(request, required_permission_id)
    if isinstance(permissions_context, HttpResponseRedirect):
        return permissions_context

    question = get_object_or_404(Question, id=question_id)
    survey_id = question.survey.id
    if request.method == 'POST':
        question.delete()
        messages.success(request, "Question deleted successfully")
    else:
        messages.error(request, "Invalid request method")
    return redirect('edit_survey', survey_id=survey_id)

@login_required
def send_survey(request, survey_id):
    required_permission_id = 450
    permissions_context = check_permissions(request, required_permission_id)
    if isinstance(permissions_context, HttpResponseRedirect):
        return permissions_context

    survey = get_object_or_404(Survey, id=survey_id)
    if request.method == 'POST':
        recipient_email = request.POST.get('recipient_email')
        email_message = request.POST.get('email_message', '')

        if not recipient_email:
            return JsonResponse({'success': False, 'error': 'Recipient email is required.'})

        survey_link = request.build_absolute_uri(reverse('take_survey', kwargs={'survey_id': survey.id}))
        subject = f"Please complete our survey: {survey.title}"

        message = f"""
Hello,

You have been invited to complete the survey: {survey.title}

Survey link: {survey_link}
"""
        if email_message:
            message += f"\nMessage from sender:\n{email_message}\n"

        message += f"\nRegards,\n{request.user.get_full_name() or request.user.username}"

        try:
            send_mail(
                subject,
                message,
                None,  # Use DEFAULT_FROM_EMAIL from settings
                [recipient_email],
                fail_silently=False,
            )
            return JsonResponse({'success': True})
        except Exception as e:
            return JsonResponse({'success': False, 'error': str(e)})

    return JsonResponse({'success': False, 'error': 'Invalid request method'})

def take_survey(request, survey_id):
    survey = get_object_or_404(Survey, id=survey_id, active=True)
    questions = survey.questions.all().order_by('order')
    if request.method == 'POST':
        respondent_type = request.POST.get('respondent_type', 'parent')
        main_user = survey.main_user
        response = Response.objects.create(
            survey=survey,
            main_user=main_user,
            respondent=request.user if request.user.is_authenticated else None,
            respondent_type=respondent_type
        )
        for question in questions:
            answer_key = f'question_{question.id}'
            if question.question_type == 'text':
                text_answer = request.POST.get(answer_key, '')
                if text_answer:
                    Answer.objects.create(
                        response=response,
                        question=question,
                        text_answer=text_answer
                    )
            elif question.question_type == 'rating':
                rating = request.POST.get(answer_key)
                if rating:
                    Answer.objects.create(
                        response=response,
                        question=question,
                        rating_answer=int(rating)
                    )
            elif question.question_type == 'multiple':
                choice_id = request.POST.get(answer_key)
                if choice_id:
                    choice = Choice.objects.get(id=choice_id)
                    Answer.objects.create(
                        response=response,
                        question=question,
                        choice_answer=choice
                    )
            elif question.question_type == 'boolean':
                boolean_answer = request.POST.get(answer_key)
                if boolean_answer:
                    Answer.objects.create(
                        response=response,
                        question=question,
                        boolean_answer=(boolean_answer == 'true')
                    )
        return render(request, 'tottimeapp/survey_thank_you.html')
    context = {
        'survey': survey,
        'questions': questions,
    }
    return render(request, 'tottimeapp/take_survey.html', context)

@login_required
def survey_results(request, survey_id):
    required_permission_id = 450
    permissions_context = check_permissions(request, required_permission_id)
    if isinstance(permissions_context, HttpResponseRedirect):
        return permissions_context

    survey = get_object_or_404(Survey, id=survey_id)
    questions = survey.questions.all().order_by('order')
    responses = survey.responses.all()
    results = {}
    for question in questions:
        if question.question_type == 'text':
            answers = Answer.objects.filter(
                question=question, 
                response__in=responses
            ).values_list('text_answer', flat=True)
            results[question.id] = {
                'question': question,
                'text_answers': answers
            }
        elif question.question_type == 'rating':
            answers = Answer.objects.filter(
                question=question, 
                response__in=responses
            )
            avg_rating = answers.aggregate(avg=Avg('rating_answer'))['avg']
            distribution = {i: answers.filter(rating_answer=i).count() for i in range(1, 6)}
            results[question.id] = {
                'question': question,
                'average': avg_rating,
                'distribution': distribution,
                'count': answers.count()
            }
        elif question.question_type == 'multiple':
            choice_counts = Answer.objects.filter(
                question=question, 
                response__in=responses
            ).values('choice_answer').annotate(count=Count('choice_answer'))
            choices_dict = {}
            for choice in question.choices.all():
                count = 0
                for item in choice_counts:
                    if item['choice_answer'] == choice.id:
                        count = item['count']
                        break
                choices_dict[choice.id] = {
                    'text': choice.text,
                    'count': count
                }
            results[question.id] = {
                'question': question,
                'choices': choices_dict,
                'count': sum(item['count'] for item in choice_counts)
            }
        elif question.question_type == 'boolean':
            answers = Answer.objects.filter(
                question=question, 
                response__in=responses
            )
            yes_count = answers.filter(boolean_answer=True).count()
            no_count = answers.filter(boolean_answer=False).count()
            results[question.id] = {
                'question': question,
                'yes_count': yes_count,
                'no_count': no_count,
                'count': answers.count()
            }
    improvement_plans = survey.improvement_plans.all()
    suggested_goals = []
    for question in survey.questions.all():
        answers = Answer.objects.filter(question=question, response__survey=survey)
        if question.question_type == 'boolean':
            no_count = answers.filter(boolean_answer=False).count()
            total = answers.count()
            if total > 0 and no_count / total > 0.3:
                suggested_goals.append({
                    'description': f"Improve '{question.text}' (high rate of 'No' responses)",
                    'target_date': ''
                })
        elif question.question_type == 'multiple':
            pass
    context = {
        'survey': survey,
        'results': results,
        'response_count': responses.count(),
        'improvement_plans': improvement_plans,
        'suggested_goals': suggested_goals,
        **permissions_context
    }
    return render(request, 'tottimeapp/survey_results.html', context)

@login_required
def create_improvement_plan(request, survey_id):
    required_permission_id = 450
    permissions_context = check_permissions(request, required_permission_id)
    if isinstance(permissions_context, HttpResponseRedirect):
        return permissions_context

    survey = get_object_or_404(Survey, id=survey_id)
    main_user = get_user_for_view(request)
    suggested_goals = []
    for question in survey.questions.all():
        answers = Answer.objects.filter(question=question, response__survey=survey)
        if question.question_type == 'boolean':
            no_count = answers.filter(boolean_answer=False).count()
            total = answers.count()
            if total > 0 and no_count / total > 0.3:
                suggested_goals.append({
                    'description': f"Improve '{question.text}' (high rate of 'No' responses)",
                    'target_date': ''
                })
        elif question.question_type == 'multiple':
            pass
    if request.method == 'POST':
        form = ImprovementPlanForm(request.POST)
        if form.is_valid():
            plan = form.save(commit=False)
            plan.survey = survey
            plan.main_user = main_user
            plan.created_by = request.user
            plan.save()
            goal_descriptions = request.POST.getlist('goal_description', [])
            goal_dates = request.POST.getlist('goal_target_date', [])
            for i in range(len(goal_descriptions)):
                if goal_descriptions[i].strip() and goal_dates[i].strip():
                    ImprovementGoal.objects.create(
                        plan=plan,
                        main_user=main_user,
                        description=goal_descriptions[i],
                        target_date=goal_dates[i],
                    )
            messages.success(request, "Improvement plan created successfully")
            return redirect('survey_results', survey_id=survey.id)
    else:
        form = ImprovementPlanForm()
    context = {
        'form': form,
        'survey': survey,
        'suggested_goals': suggested_goals,
        **permissions_context
    }
    return render(request, 'tottimeapp/create_improvement_plan.html', context)

@login_required
def edit_improvement_plan(request, plan_id):
    required_permission_id = 450
    permissions_context = check_permissions(request, required_permission_id)
    if isinstance(permissions_context, HttpResponseRedirect):
        return permissions_context

    plan = get_object_or_404(ImprovementPlan, id=plan_id)
    survey = plan.survey
    main_user = get_user_for_view(request)
    if request.method == 'POST':
        form = ImprovementPlanForm(request.POST, instance=plan)
        if form.is_valid():
            form.save()
            plan.goals.all().delete()
            goal_descriptions = request.POST.getlist('goal_description', [])
            goal_dates = request.POST.getlist('goal_target_date', [])
            goal_completed = request.POST.getlist('goal_completed', [])
            for i in range(len(goal_descriptions)):
                if goal_descriptions[i].strip() and goal_dates[i].strip():
                    completed = str(i) in goal_completed
                    ImprovementGoal.objects.create(
                        plan=plan,
                        main_user=main_user,
                        description=goal_descriptions[i],
                        target_date=goal_dates[i],
                        completed=completed
                    )
            messages.success(request, "Improvement plan updated successfully")
            return redirect('survey_results', survey_id=survey.id)
    else:
        form = ImprovementPlanForm(instance=plan)
    context = {
        'form': form,
        'plan': plan,
        'survey': survey,
        **permissions_context
    }
    return render(request, 'tottimeapp/edit_improvement_plan.html', context)

@login_required
def delete_survey(request, survey_id):
    required_permission_id = 450
    permissions_context = check_permissions(request, required_permission_id)
    if isinstance(permissions_context, HttpResponseRedirect):
        return permissions_context

    survey = get_object_or_404(Survey, id=survey_id)
    if request.method == 'POST':
        survey.delete()
        messages.success(request, "Survey deleted successfully.")
        return redirect('surveys_list')
    return render(request, 'tottimeapp/confirm_delete_survey.html', {'survey': survey, **permissions_context})

@login_required
def complete_improvement_plan(request, plan_id):
    required_permission_id = 450
    permissions_context = check_permissions(request, required_permission_id)
    if isinstance(permissions_context, HttpResponseRedirect):
        return permissions_context

    plan = get_object_or_404(ImprovementPlan, id=plan_id)
    if request.method == 'POST':
        plan.is_completed = True
        plan.save()
        messages.success(request, "Improvement plan marked as complete.")
    return redirect('survey_results', survey_id=plan.survey.id)

@login_required
def asq(request):
    required_permission_id = 450  # Permission ID for "orientation"
    permissions_context = check_permissions(request, required_permission_id)
    if isinstance(permissions_context, HttpResponseRedirect):
        return permissions_context

    main_user = get_user_for_view(request)

    context = {
        **permissions_context,
        'main_user': main_user,
    }

    return render(request, 'tottimeapp/asq.html', context)

@login_required
def asq_infant(request):
    required_permission_id = 450  # Permission ID for "orientation"
    permissions_context = check_permissions(request, required_permission_id)
    if isinstance(permissions_context, HttpResponseRedirect):
        return permissions_context

    main_user = get_user_for_view(request)

    questions = [
        "Does your baby laugh or smile at you and other family members?",
        "Does your baby look for you when a stranger comes near?",
        "Does your baby like to play near or be with family and friends?",
        "Does your baby like to be picked up and held?",
        "When upset, can your baby calm down within a half hour?",
        "Does your baby stiffen and arch her back when picked up?",
        "Does your baby like to play games such as Peekaboo?",
        "Is your baby's body relaxed?",
        "Does your baby cry, scream, or have tantrums for long periods of time?",
        "Is your baby able to calm himself down (for example, by sucking his hand or pacifier)?",
        "Is your baby interested in things around her, such as people, toys, and foods?",
        "Does it take longer than 30 minutes to feed your baby?",
        "Do you and your baby enjoy mealtimes together?",
        "Does your baby have any eating problems, such as gagging, vomiting, or ______? (Please describe.)",
        "Does your baby have trouble falling asleep at naptime or at night?",
        "Does your baby make babbling sounds? For example, does he put sounds together such as “ba-ba-ba-ba” or “na-na-na-na”?",
        "Does your baby sleep at least 10 hours in a 24-hour period?",
        "Does your baby get constipated or have diarrhea?",
        "Does your baby let you know when she is hungry, hurt, or tired?",
        "When you talk to your baby, does he turn his head, look, or smile?",
        "Does your baby try to hurt other children, adults, or animals (for example, by kicking or biting)?",
        "Does your baby try to show you things? For example, does she hold out a toy and look at you?",
        "Does your baby respond to his name when you call him? For example, does he turn his head and look at you?",
        "When you point at something, does your baby look in the direction you are pointing?",
        "Does your baby make sounds or use gestures to let you know she wants something (for example, by reaching)?",
        "When you copy sounds your baby makes, does your baby repeat the same sounds back to you?",
        "Has anyone shared concerns about your baby’s behaviors? If “sometimes” or “often or always,” please explain.",
    ]

    context = {
        **permissions_context,
        'main_user': main_user,
        'questions': list(enumerate(questions, 1)),
    }

    return render(request, 'tottimeapp/asq_infant.html', context)

@login_required
def curriculum(request):
    required_permission_id = 450  # Permission ID for "orientation"
    permissions_context = check_permissions(request, required_permission_id)
    if isinstance(permissions_context, HttpResponseRedirect):
        return permissions_context

    main_user = get_user_for_view(request)
    classrooms = Classroom.objects.filter(user=main_user)

    context = {
        **permissions_context,
        'main_user': main_user,
        'classrooms': classrooms,
    }

    return render(request, 'tottimeapp/curriculum.html', context)

@login_required
def classroom_themes(request, classroom_id):
    required_permission_id = 450  # Permission ID for "orientation"
    permissions_context = check_permissions(request, required_permission_id)
    if isinstance(permissions_context, HttpResponseRedirect):
        return permissions_context

    main_user = get_user_for_view(request)
    classroom = get_object_or_404(Classroom, id=classroom_id, user=main_user)

    MONTH_CHOICES = [
        (1, 'January'), (2, 'February'), (3, 'March'), (4, 'April'),
        (5, 'May'), (6, 'June'), (7, 'July'), (8, 'August'),
        (9, 'September'), (10, 'October'), (11, 'November'), (12, 'December')
    ]

    # Handle Add Theme form submission
    if request.method == 'POST':
        month = request.POST.get('month')
        title = request.POST.get('title', '').strip()
        description = request.POST.get('description', '').strip()

        if not month or not title:
            messages.error(request, 'Month and Title are required to add a theme.')
            return redirect('classroom_themes', classroom_id=classroom.id)

        try:
            month_int = int(month)
        except (TypeError, ValueError):
            messages.error(request, 'Invalid month selected.')
            return redirect('classroom_themes', classroom_id=classroom.id)

        # Create theme, respecting unique_together on (classroom, month)
        try:
            CurriculumTheme.objects.create(
                main_user=main_user,
                classroom=classroom,
                month=month_int,
                title=title,
                description=description
            )
            messages.success(request, f'Theme "{title}" added for {MONTH_CHOICES[month_int-1][1]}.')
        except IntegrityError:
            messages.error(request, 'A theme for that month already exists for this classroom.')
        except Exception as e:
            messages.error(request, f'Error creating theme: {e}')

        return redirect('classroom_themes', classroom_id=classroom.id)

    # GET: render page
    themes = classroom.themes.filter(main_user=main_user).order_by('month')
    month_theme_list = []
    for value, name in MONTH_CHOICES:
        theme = next((t for t in themes if t.month == value), None)
        month_theme_list.append((value, name, theme))

    context = {
        **permissions_context,
        'main_user': main_user,
        'classroom': classroom,
        'themes': themes,
        'months': MONTH_CHOICES,
        'month_theme_list': month_theme_list,
    }
    return render(request, 'tottimeapp/classroom_themes.html', context)

@login_required
def theme_activities(request, theme_id, view_type='weeks'):
    required_permission_id = 450
    permissions_context = check_permissions(request, required_permission_id)
    if isinstance(permissions_context, HttpResponseRedirect):
        return permissions_context

    main_user = get_user_for_view(request)
    theme = get_object_or_404(CurriculumTheme, id=theme_id, classroom__user=main_user, main_user=main_user)
    activities = theme.activities.filter(main_user=main_user)
    weekdays = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday']

    # Initialize S3 client for presigned URLs
    s3_client = None
    if hasattr(settings, 'AWS_ACCESS_KEY_ID') and hasattr(settings, 'AWS_STORAGE_BUCKET_NAME'):
        try:
            s3_client = boto3.client(
                's3',
                aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
                aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
                region_name=getattr(settings, 'AWS_S3_REGION_NAME', 'us-east-1'),
                config=Config(signature_version='s3v4')
            )
        except Exception as e:
            pass  # print(f"Error initializing S3 client: {e}")

    # Build weeks data
    num_weeks = 5
    weeks = []
    for week_num in range(1, num_weeks + 1):
        week_activities = []
        for day in weekdays:
            activity = activities.filter(week=week_num, day=day).first()
            
            # Generate presigned URL for attachment if it exists
            attachment_url = None
            if activity and activity.attachment and s3_client:
                try:
                    attachment_url = s3_client.generate_presigned_url(
                        'get_object',
                        Params={
                            'Bucket': settings.AWS_STORAGE_BUCKET_NAME,
                            'Key': activity.attachment.name
                        },
                        ExpiresIn=3600
                    )
                except Exception as e:
                    pass  # print(f"Error generating presigned URL: {e}")
            
            week_activities.append({
                'day': day,
                'activity': activity,
                'week_num': week_num,
                'attachment_url': attachment_url
            })
        weeks.append(week_activities)

    context = {
        **permissions_context,
        'main_user': main_user,
        'theme': theme,
        'weeks': weeks,
        'weekdays': weekdays,
    }
    return render(request, 'tottimeapp/theme_activities.html', context)

@login_required
@require_POST
def upload_activity_file(request, activity_id):
    main_user = get_user_for_view(request)
    activity = get_object_or_404(CurriculumActivity, id=activity_id, main_user=main_user)
    
    if request.FILES.get('attachment'):
        attachment = request.FILES['attachment']
        
        # Validate file type
        allowed_extensions = ['.pdf', '.jpg', '.jpeg', '.png', '.doc', '.docx']
        ext = attachment.name.split('.')[-1].lower()
        if f'.{ext}' not in allowed_extensions:
            messages.error(request, 'Invalid file type! Allowed: PDF, JPEG, PNG, DOC, DOCX')
        elif attachment.size > 10 * 1024 * 1024:
            messages.error(request, 'File size too large! Maximum size is 10MB.')
        else:
            activity.attachment = attachment
            activity.save()
            messages.success(request, 'File uploaded successfully!')
    
    return redirect('theme_activities', theme_id=activity.theme.id, view_type='weeks')

@login_required
@require_POST
def add_activity(request, theme_id):
    main_user = get_user_for_view(request)
    theme = get_object_or_404(CurriculumTheme, id=theme_id, main_user=main_user)
    
    title = request.POST.get('title')
    description = request.POST.get('description', '')
    week = request.POST.get('week')
    day = request.POST.get('day')
    attachment = request.FILES.get('attachment')
    
    # Validate file type
    allowed_extensions = ['.pdf', '.jpg', '.jpeg', '.png', '.doc', '.docx']
    if attachment:
        ext = attachment.name.split('.')[-1].lower()
        if f'.{ext}' not in allowed_extensions:
            messages.error(request, 'Invalid file type! Allowed: PDF, JPEG, PNG, DOC, DOCX')
            return redirect('theme_activities', theme_id=theme.id, view_type='weeks')
        if attachment.size > 10 * 1024 * 1024:  # 10MB limit
            messages.error(request, 'File size too large! Maximum size is 10MB.')
            return redirect('theme_activities', theme_id=theme.id, view_type='weeks')
    
    if title and week and day:
        try:
            CurriculumActivity.objects.create(
                main_user=main_user,
                theme=theme,
                title=title,
                description=description,
                week=int(week),
                day=day,
                attachment=attachment
            )
            messages.success(request, f'Activity "{title}" added successfully!')
        except Exception as e:
            messages.error(request, f'Error creating activity: {e}')
    else:
        messages.error(request, 'Missing required fields!')
    
    return redirect('theme_activities', theme_id=theme.id, view_type='weeks')

@login_required
@require_http_methods(["GET"])
def shopping_list(request):
    """
    API endpoint to get missing ingredients for a menu on a specific date.
    Returns JSON with list of ingredients that are needed but not in stock.
    Quantities are scaled based on CACFP requirements and number of children.
    """
    user = get_user_for_view(request)
    date_str = request.GET.get('date')
    meal_type = request.GET.get('meal_type', 'all')
    
    # Get age group counts from request
    age_counts = {
        '1-2': int(request.GET.get('ages_1_2', 0)),
        '3-5': int(request.GET.get('ages_3_5', 0)),
        '6-12': int(request.GET.get('ages_6_12', 0)),
        '13-18': int(request.GET.get('ages_13_18', 0))
    }
    
    total_children = sum(age_counts.values())
    
    if total_children == 0:
        return JsonResponse({
            'message': 'Enter number of children to calculate requirements',
            'missing_ingredients': []
        })
    
    if not date_str:
        return JsonResponse({'error': 'Date parameter is required'}, status=400)
    
    try:
        date_obj = datetime.strptime(date_str, '%Y-%m-%d').date()
    except ValueError:
        return JsonResponse({'error': 'Invalid date format. Use YYYY-MM-DD'}, status=400)
    
    # Get menu for the specified date
    menu_items = WeeklyMenu.objects.filter(user=user, date=date_obj)
    
    if not menu_items.exists():
        return JsonResponse({
            'message': f'No menu found for {date_obj.strftime("%B %d, %Y")}',
            'missing_ingredients': []
        })
    
    # Define meal fields based on meal_type parameter
    if meal_type == 'breakfast':
        meal_fields = ['am_fluid_milk', 'am_fruit_veg', 'am_bread', 'am_additional']
    elif meal_type == 'lunch':
        meal_fields = [
            'lunch_main_dish', 'lunch_fluid_milk', 'lunch_vegetable', 
            'lunch_fruit', 'lunch_grain', 'lunch_meat', 'lunch_additional'
        ]
    elif meal_type == 'snack':
        meal_fields = [
            'ams_fluid_milk', 'ams_fruit_veg', 'ams_bread', 'ams_meat',
            'pm_fluid_milk', 'pm_fruit_veg', 'pm_bread', 'pm_meat'
        ]
    else:
        meal_fields = [
            'am_fluid_milk', 'am_fruit_veg', 'am_bread', 'am_additional',
            'ams_fluid_milk', 'ams_fruit_veg', 'ams_bread', 'ams_meat',
            'lunch_main_dish', 'lunch_fluid_milk', 'lunch_vegetable', 
            'lunch_fruit', 'lunch_grain', 'lunch_meat', 'lunch_additional',
            'pm_fluid_milk', 'pm_fruit_veg', 'pm_bread', 'pm_meat'
        ]
    
    # Collect all recipe names from the menu
    recipe_names = []
    for menu in menu_items:
        for field in meal_fields:
            recipe_name = getattr(menu, field, '').strip()
            if recipe_name:
                recipe_names.append(recipe_name)
    
    if not recipe_names:
        return JsonResponse({
            'message': 'No recipes found in menu',
            'missing_ingredients': []
        })
    
    # Calculate CACFP scaling factor based on age counts
    # This multiplies ingredient quantities by the number of servings needed
    scaling_factor = float(total_children)
    
    # Calculate ingredient needs with scaling
    ingredient_needs = {}  # {ingredient_id: (ingredient_obj, scaled_quantity_needed, unit)}
    
    for recipe_name in recipe_names:
        recipe = Recipe.objects.filter(user=user, name=recipe_name).first()
        
        if recipe:
            ingredients = get_recipe_ingredients(recipe)
            
            for ingredient, quantity in ingredients:
                if ingredient and quantity:
                    # Scale quantity by number of children
                    scaled_qty = float(quantity) * scaling_factor
                    
                    if ingredient.id in ingredient_needs:
                        # Add to existing quantity
                        existing = ingredient_needs[ingredient.id]
                        ingredient_needs[ingredient.id] = (
                            existing[0], 
                            existing[1] + scaled_qty,
                            existing[2]
                        )
                    else:
                        # New ingredient
                        unit = getattr(ingredient, 'unit_type', 'units')
                        ingredient_needs[ingredient.id] = (
                            ingredient, 
                            scaled_qty,
                            unit if unit else 'units'
                        )
    
    if not ingredient_needs:
        return JsonResponse({
            'message': 'No ingredients found in recipes',
            'missing_ingredients': []
        })
    
    # Compare with inventory and find missing items
    missing_ingredients = []
    
    for ingredient_id, (ingredient_obj, needed_qty, unit) in ingredient_needs.items():
        current_qty = float(ingredient_obj.quantity) if ingredient_obj.quantity else 0.0
        
        if current_qty < needed_qty:
            shortage = needed_qty - current_qty
            missing_ingredients.append({
                'id': ingredient_obj.id,
                'name': ingredient_obj.item,
                'needed': round(shortage, 2),
                'current': round(current_qty, 2),
                'unit': unit
            })
    
    # Sort by name for consistent display
    missing_ingredients.sort(key=lambda x: x['name'])
    
    return JsonResponse({
        'missing_ingredients': missing_ingredients,
        'date': date_obj.strftime('%B %d, %Y')
    })

@login_required
def meal_calculator(request):
    required_permission_id = 272
    permissions_context = check_permissions(request, required_permission_id)
    if isinstance(permissions_context, HttpResponseRedirect):
        return permissions_context

    main_user = get_user_for_view(request)

    # prefer cookie first, then query param
    cookie_minimal = request.COOKIES.get('use_minimal_base') == '1'
    param_minimal = request.GET.get('minimal') == '1'
    use_minimal_base = param_minimal or cookie_minimal

    # If we don't yet know the client's viewport, return a tiny sniffing page
    if not (cookie_minimal or param_minimal):
        sniff_html = """<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
        <script>
        (function(){
            var w = window.innerWidth || document.documentElement.clientWidth || screen.width;
            var url = window.location.href;
            if (w < 1000) {
                document.cookie = "use_minimal_base=1; path=/; max-age=" + (60*60*24*365) + ";";
                if (url.indexOf('minimal=1') === -1) {
                    url += (url.indexOf('?') === -1 ? '?' : '&') + 'minimal=1';
                }
                window.location.replace(url);
            } else {
                url = url.replace(/([?&])minimal=1(&|$)/g, '$1').replace(/[?&]$/, '');
                window.location.replace(url);
            }
        })();
        </script>
        <style>html,body{height:100%;margin:0;background:#fff}</style>
        </head><body></body></html>"""
        return HttpResponse(sniff_html)

    # Choose base template
    base_template = 'tottimeapp/base_minimal.html' if use_minimal_base else 'tottimeapp/base.html'
    permissions_context['base_template'] = base_template

    response = render(request, 'tottimeapp/meal_calculator.html', {
        **permissions_context,
        'main_user': main_user,
    })

    # persist preference when query param present
    if param_minimal:
        response.set_cookie('use_minimal_base', '1', max_age=60*60*24*365, httponly=False, path='/')

    return response

@login_required
def todays_menu(request):
    """Display today's menu with all recipes and required ingredients"""
    required_permission_id = 555
    permissions_context = check_permissions(request, required_permission_id)
    if isinstance(permissions_context, HttpResponseRedirect):
        return permissions_context

    main_user = get_user_for_view(request)
    user = main_user
    today = date.today()
    
    # Get today's menu for the user
    try:
        menu = WeeklyMenu.objects.get(user=user, date=today)
    except WeeklyMenu.DoesNotExist:
        menu = None
    
    context = {
        'menu': menu,
        'recipes_data': [],
        'all_ingredients': {},
        'today': today
    }
    
    if menu:
        # Collect all recipe names from menu fields
        recipe_fields = {
            'Breakfast Milk': menu.am_fluid_milk,
            'Breakfast Fruit/Veg': menu.am_fruit_veg,
            'Breakfast Bread': menu.am_bread,
            'Breakfast Additional': menu.am_additional,
            'AM Snack Milk': menu.ams_fluid_milk,
            'AM Snack Fruit/Veg': menu.ams_fruit_veg,
            'AM Snack Bread': menu.ams_bread,
            'AM Snack Meat': menu.ams_meat,
            'Lunch Main Dish': menu.lunch_main_dish,
            'Lunch Milk': menu.lunch_fluid_milk,
            'Lunch Vegetable': menu.lunch_vegetable,
            'Lunch Fruit': menu.lunch_fruit,
            'Lunch Grain': menu.lunch_grain,
            'Lunch Meat': menu.lunch_meat,
            'Lunch Additional': menu.lunch_additional,
            'PM Snack Milk': menu.pm_fluid_milk,
            'PM Snack Fruit/Veg': menu.pm_fruit_veg,
            'PM Snack Bread': menu.pm_bread,
            'PM Snack Meat': menu.pm_meat,
        }
        
        # Group by meal period
        meal_periods = {
            'Breakfast': [],
            'AM Snack': [],
            'Lunch': [],
            'PM Snack': []
        }
        
        # Process each recipe
        for field_name, recipe_name in recipe_fields.items():
            if not recipe_name or recipe_name.strip() == '':
                continue

            normalized_recipe_name = recipe_name.strip()
                
            # Determine meal period
            if 'Breakfast' in field_name:
                period = 'Breakfast'
            elif 'AM Snack' in field_name:
                period = 'AM Snack'
            elif 'Lunch' in field_name:
                period = 'Lunch'
            elif 'PM Snack' in field_name:
                period = 'PM Snack'
            else:
                period = 'Other'
            
            # Clean field label by removing meal period prefix
            clean_label = field_name
            for prefix in ['Breakfast ', 'AM Snack ', 'PM Snack ', 'Lunch ', 'AMS ']:
                if clean_label.startswith(prefix):
                    clean_label = clean_label[len(prefix):]
                    break

            # Try to find the recipe
            try:
                # Use robust matching so menu text still resolves to the underlying recipe record.
                recipe = Recipe.objects.filter(user=user, name__iexact=normalized_recipe_name).first()
                
                if recipe:
                    # Get RecipeIngredient objects for this recipe
                    content_type = ContentType.objects.get_for_model(recipe)
                    ingredients = RecipeIngredient.objects.filter(
                        content_type=content_type,
                        object_id=recipe.id
                    ).select_related('ingredient').filter(ingredient__isnull=False)

                    # Hide trivial self-ingredient rows (e.g., Blueberries recipe with ingredient Blueberries).
                    recipe_name_normalized = (recipe.name or '').strip().casefold()
                    visible_ingredients = []
                    for ri in ingredients:
                        if not ri.ingredient:
                            continue
                        ingredient_name_normalized = (ri.ingredient.item or '').strip().casefold()
                        if ingredient_name_normalized == recipe_name_normalized:
                            continue
                        ri.display_unit = (
                            getattr(ri.ingredient, 'unit_type', None)
                            or getattr(ri.ingredient, 'base_unit', '')
                            or ''
                        )
                        visible_ingredients.append(ri)

                    has_visible_instructions = bool((recipe.instructions or '').strip())
                    has_visible_ingredients = len(visible_ingredients) > 0
                    
                    recipe_data = {
                        'field_label': clean_label,
                        'recipe': recipe,
                        'ingredients': visible_ingredients,
                        'has_visible_instructions': has_visible_instructions,
                        'has_visible_ingredients': has_visible_ingredients,
                    }
                    
                    meal_periods[period].append(recipe_data)
                    
                    # Add to all_ingredients for shopping list
                    for recipe_ingredient in ingredients:
                        if recipe_ingredient.ingredient:
                            item_name = recipe_ingredient.ingredient.item
                            display_unit = (
                                getattr(recipe_ingredient.ingredient, 'unit_type', None)
                                or getattr(recipe_ingredient.ingredient, 'base_unit', '')
                                or ''
                            )
                            if item_name in context['all_ingredients']:
                                context['all_ingredients'][item_name]['quantity'] += float(recipe_ingredient.quantity or 0)
                            else:
                                context['all_ingredients'][item_name] = {
                                    'quantity': float(recipe_ingredient.quantity or 0),
                                    'units': display_unit,
                                    'current_stock': float(recipe_ingredient.ingredient.quantity or 0)
                                }
                else:
                    # Recipe not found, but we have the name
                    recipe_data = {
                        'field_label': clean_label,
                        'recipe_name': normalized_recipe_name,
                        'recipe': None,
                        'ingredients': [],
                        'has_visible_instructions': False,
                        'has_visible_ingredients': False,
                    }
                    meal_periods[period].append(recipe_data)
                    
            except Exception as e:
                logger.error(f"Error processing recipe {recipe_name}: {str(e)}")
                continue
        
        context['meal_periods'] = meal_periods
    
    return render(request, 'tottimeapp/todays_menu.html', {
        **permissions_context,
        **context,
        'main_user': main_user,
    })

@require_http_methods(["GET"])
def breakfast_recipe_detail(request, recipe_id):
    user = get_user_for_view(request)
    r = Recipe.objects.filter(id=recipe_id, user=user, recipe_type='breakfast').first()
    if not r:
        return JsonResponse({'error': 'Not found'}, status=404)
    
    # Get ingredients from RecipeIngredient table
    ingredients = get_recipe_ingredients(r)
    ingredient_data = {}
    for idx, (ing, qty) in enumerate(ingredients, start=1):
        ingredient_data[f'ingredient{idx}_id'] = ing.id if ing else None
        ingredient_data[f'qty{idx}'] = float(qty) if qty else None
    
    return JsonResponse({
        'id': r.id,
        'name': r.name,
        **ingredient_data,
        'addfood': r.addfood, 'rule_id': r.addfood_rule_id if r.addfood_rule else None, 'instructions': r.instructions,
        'image_url': r.image.url if r.image else None,
        'populate_breakfast': r.populate_breakfast,
        'populate_am_snack': r.populate_am_snack,
        'populate_lunch': r.populate_lunch,
        'populate_pm_snack': r.populate_pm_snack,
        'standalone': r.standalone,
        'ignore_inventory': r.ignore_inventory,
    })

@require_http_methods(["POST"])
def update_breakfast_recipe(request, recipe_id):
    user = get_user_for_view(request)
    r = Recipe.objects.filter(id=recipe_id, user=user, recipe_type='breakfast').first()
    if not r:
        return JsonResponse({'success': False, 'error': 'Not found'}, status=404)
    r.name = request.POST.get('recipeName') or request.POST.get('breakfastMealName') or r.name
    r.addfood = request.POST.get('additionalFood') or r.addfood
    # Update addfood_rule if provided
    rule_id = request.POST.get('breakfastRule')
    if rule_id:
        r.addfood_rule_id = rule_id
    r.instructions = request.POST.get('breakfastInstructions') or r.instructions
    if request.FILES.get('image'):
        r.image = request.FILES['image']  # size check happens in model save()
    
    # Update checkbox fields
    r.populate_breakfast = request.POST.get('breakfastPopulateBreakfast') == 'on'
    r.populate_am_snack = request.POST.get('breakfastPopulateAMSnack') == 'on'
    r.populate_lunch = request.POST.get('breakfastPopulateLunch') == 'on'
    r.populate_pm_snack = request.POST.get('breakfastPopulatePMSnack') == 'on'
    r.standalone = request.POST.get('breakfastStandalone') == 'on'
    r.ignore_inventory = request.POST.get('breakfastIgnoreInventory') == 'on'
    
    r.save()
    
    # Update ingredients
    ingredient_ids = [request.POST.get(f'breakfastMainIngredient{i}') for i in range(1, 21)]
    quantities = [request.POST.get(f'breakfastQtyMainIngredient{i}') for i in range(1, 21)]
    save_recipe_ingredients(r, ingredient_ids, quantities)
    
    from django.shortcuts import redirect
    return redirect(request.META.get('HTTP_REFERER', '/'))

@require_http_methods(["GET"])
def am_recipe_detail(request, recipe_id):
    from django.db.models import Q
    user = get_user_for_view(request)
    r = Recipe.objects.filter(Q(recipe_type='am_snack') | Q(recipe_type='am_pm_snack'), id=recipe_id, user=user).first()
    if not r: return JsonResponse({'error': 'Not found'}, status=404)
    
    # Get ingredients from RecipeIngredient table
    ingredients = get_recipe_ingredients(r)
    ingredient_data = {}
    for idx, (ing, qty) in enumerate(ingredients, start=1):
        ingredient_data[f'ingredient{idx}_id'] = ing.id if ing else None
        ingredient_data[f'qty{idx}'] = float(qty) if qty else None
    
    return JsonResponse({
        'id': r.id, 'name': r.name,
        **ingredient_data,
        'fluid': r.fluid, 'fruit': r.fruit, 'veg': r.veg, 'meat': r.meat,
        'rule_id': r.fluid_rule_id if r.fluid_rule else None, 'instructions': r.instructions,
        'image_url': r.image.url if r.image else None,
        'populate_breakfast': r.populate_breakfast,
        'populate_am_snack': r.populate_am_snack,
        'populate_lunch': r.populate_lunch,
        'populate_pm_snack': r.populate_pm_snack,
        'standalone': r.standalone,
        'ignore_inventory': r.ignore_inventory,
    })

@require_http_methods(["POST"])
def update_am_recipe(request, recipe_id):
    from django.db.models import Q
    user = get_user_for_view(request)
    r = Recipe.objects.filter(Q(recipe_type='am_snack') | Q(recipe_type='am_pm_snack'), id=recipe_id, user=user).first()
    if not r: return JsonResponse({'success': False, 'error': 'Not found'}, status=404)
    r.name = request.POST.get('recipeName') or request.POST.get('amRecipeName') or r.name
    r.fluid = request.POST.get('amFluid') or r.fluid
    # Handle fruit/veg as separate fields or combined
    fruit_veg = request.POST.get('amFruitVeg')
    if fruit_veg:
        r.fruit = fruit_veg
        r.veg = fruit_veg
    r.meat = request.POST.get('amMeat') or r.meat
    # Update fluid_rule if provided
    rule_id = request.POST.get('amRule')
    if rule_id:
        r.fluid_rule_id = rule_id
    r.instructions = request.POST.get('amInstructions') or r.instructions
    if request.FILES.get('image'): r.image = request.FILES['image']
    
    # Update checkbox fields
    r.populate_breakfast = request.POST.get('amPopulateBreakfast') == 'on'
    r.populate_am_snack = request.POST.get('amPopulateAMSnack') == 'on'
    r.populate_lunch = request.POST.get('amPopulateLunch') == 'on'
    r.populate_pm_snack = request.POST.get('amPopulatePMSnack') == 'on'
    r.standalone = request.POST.get('amStandalone') == 'on'
    r.ignore_inventory = request.POST.get('amIgnoreInventory') == 'on'
    
    r.save()
    
    # Update ingredients
    ingredient_ids = [request.POST.get(f'amIngredient{i}') for i in range(1, 21)]
    quantities = [request.POST.get(f'amQty{i}') for i in range(1, 21)]
    save_recipe_ingredients(r, ingredient_ids, quantities)
    
    from django.shortcuts import redirect
    return redirect(request.META.get('HTTP_REFERER', '/'))

@require_http_methods(["GET"])
def pm_recipe_detail(request, recipe_id):
    from django.db.models import Q
    user = get_user_for_view(request)
    r = Recipe.objects.filter(Q(recipe_type='pm_snack') | Q(recipe_type='am_pm_snack'), id=recipe_id, user=user).first()
    if not r: return JsonResponse({'error': 'Not found'}, status=404)
    
    # Get ingredients from RecipeIngredient table
    ingredients = get_recipe_ingredients(r)
    ingredient_data = {}
    for idx, (ing, qty) in enumerate(ingredients, start=1):
        ingredient_data[f'ingredient{idx}_id'] = ing.id if ing else None
        ingredient_data[f'qty{idx}'] = float(qty) if qty else None
    
    return JsonResponse({
        'id': r.id, 'name': r.name,
        **ingredient_data,
        'fluid': r.fluid, 'fruit': r.fruit, 'veg': r.veg, 'meat': r.meat,
        'rule_id': r.fluid_rule_id if r.fluid_rule else None, 'instructions': r.instructions,
        'image_url': r.image.url if r.image else None,
        'populate_breakfast': r.populate_breakfast,
        'populate_am_snack': r.populate_am_snack,
        'populate_lunch': r.populate_lunch,
        'populate_pm_snack': r.populate_pm_snack,
        'standalone': r.standalone,
        'ignore_inventory': r.ignore_inventory,
    })

@require_http_methods(["POST"])
def update_pm_recipe(request, recipe_id):
    from django.db.models import Q
    user = get_user_for_view(request)
    r = Recipe.objects.filter(Q(recipe_type='pm_snack') | Q(recipe_type='am_pm_snack'), id=recipe_id, user=user).first()
    if not r: return JsonResponse({'success': False, 'error': 'Not found'}, status=404)
    r.name = request.POST.get('recipeName') or request.POST.get('pmRecipeName') or r.name
    r.fluid = request.POST.get('pmFluid') or r.fluid
    # Handle fruit/veg as separate fields or combined
    fruit_veg = request.POST.get('pmFruitVeg')
    if fruit_veg:
        r.fruit = fruit_veg
        r.veg = fruit_veg
    r.meat = request.POST.get('pmMeat') or r.meat
    # Update fluid_rule if provided
    rule_id = request.POST.get('pmRule')
    if rule_id:
        r.fluid_rule_id = rule_id
    r.instructions = request.POST.get('pmInstructions') or r.instructions
    if request.FILES.get('image'): r.image = request.FILES['image']
    
    # Update checkbox fields
    r.populate_breakfast = request.POST.get('pmPopulateBreakfast') == 'on'
    r.populate_am_snack = request.POST.get('pmPopulateAMSnack') == 'on'
    r.populate_lunch = request.POST.get('pmPopulateLunch') == 'on'
    r.populate_pm_snack = request.POST.get('pmPopulatePMSnack') == 'on'
    r.standalone = request.POST.get('pmStandalone') == 'on'
    r.ignore_inventory = request.POST.get('pmIgnoreInventory') == 'on'
    
    r.save()
    
    # Update ingredients
    ingredient_ids = [request.POST.get(f'pmIngredient{i}') for i in range(1, 21)]
    quantities = [request.POST.get(f'pmQty{i}') for i in range(1, 21)]
    save_recipe_ingredients(r, ingredient_ids, quantities)
    
    from django.shortcuts import redirect
    return redirect(request.META.get('HTTP_REFERER', '/'))

@require_http_methods(["GET"])
def recipe_detail(request, recipe_id):
    user = get_user_for_view(request)
    r = Recipe.objects.filter(id=recipe_id, user=user).first()
    if not r: return JsonResponse({'error': 'Not found'}, status=404)
    
    # Get ingredients from RecipeIngredient table
    ingredients = get_recipe_ingredients(r)
    ingredient_data = {}
    for idx, (ing, qty) in enumerate(ingredients, start=1):
        ingredient_data[f'ingredient{idx}_id'] = ing.id if ing else None
        ingredient_data[f'qty{idx}'] = float(qty) if qty else None
    
    return JsonResponse({
        'id': r.id, 'name': r.name,
        **ingredient_data,
        'recipe_type': r.recipe_type,
        'grain': r.grain,
        'meat_alternate': r.meat_alternate,
        'fruit': r.fruit,
        'veg': r.veg,
        'meat': r.meat,
        'addfood': r.addfood,
        'fluid': r.fluid,
        'grain_rule_id': r.grain_rule_id,
        'addfood_rule_id': r.addfood_rule_id,
        'fluid_rule_id': r.fluid_rule_id,
        'veg_rule_id': r.veg_rule_id,
        'fruit_rule_id': r.fruit_rule_id,
        'meat_rule_id': r.meat_rule_id,
        'instructions': r.instructions,
        'image_url': r.image.url if r.image else None,
        'populate_breakfast': r.populate_breakfast,
        'populate_am_snack': r.populate_am_snack,
        'populate_lunch': r.populate_lunch,
        'populate_pm_snack': r.populate_pm_snack,
        'standalone': r.standalone,
        'ignore_inventory': r.ignore_inventory,
    })

@require_http_methods(["POST"])
def update_recipe(request, recipe_id):
    user = get_user_for_view(request)
    r = Recipe.objects.filter(id=recipe_id, user=user).first()
    if not r: return JsonResponse({'success': False, 'error': 'Not found'}, status=404)
    initial_name = r.name
    initial_recipe_type = r.recipe_type
    r.name = request.POST.get('recipeName') or request.POST.get('mealName') or r.name
    recipe_type, populate_flags = resolve_recipe_type_and_populate_flags(request.POST)
    r.recipe_type = recipe_type

    def post_or_existing(key, current_value):
        if key in request.POST:
            return request.POST.get(key, '').strip()
        return current_value

    r.grain = post_or_existing('grain', r.grain)
    r.meat_alternate = post_or_existing('meatAlternate', r.meat_alternate)
    r.fruit = post_or_existing('fruit', r.fruit)
    r.veg = post_or_existing('veg', r.veg)
    r.meat = post_or_existing('meat', r.meat)
    r.addfood = post_or_existing('addfood', r.addfood)
    r.fluid = post_or_existing('fluid', r.fluid)
    r.instructions = post_or_existing('instructions', r.instructions)

    # Update rule fields; blank selection should clear existing rule.
    for rule_field in ('grain_rule', 'addfood_rule', 'fluid_rule', 'veg_rule', 'fruit_rule', 'meat_rule'):
        if rule_field in request.POST:
            raw_value = (request.POST.get(rule_field) or '').strip()
            setattr(r, f'{rule_field}_id', raw_value or None)

    if request.FILES.get('image'):
        r.image = request.FILES['image']
    # Update checkbox fields
    r.populate_breakfast = populate_flags['populate_breakfast']
    r.populate_am_snack = populate_flags['populate_am_snack']
    r.populate_lunch = populate_flags['populate_lunch']
    r.populate_pm_snack = populate_flags['populate_pm_snack']
    r.standalone = request.POST.get('standalone') == 'on'
    r.ignore_inventory = request.POST.get('ignoreInventory') == 'on'
    r.save()
    
    # Update ingredients: support both unified and legacy category-specific field prefixes.
    ingredient_prefixes = [
        'mainIngredient',
        'breakfastMainIngredient',
        'amIngredient',
        'pmIngredient',
        'fruitMainIngredient',
        'vegMainIngredient',
        'wgMainIngredient',
        'ingredient',
    ]
    qty_prefixes = [
        'qtyMainIngredient',
        'breakfastQtyMainIngredient',
        'amQty',
        'pmQty',
        'fruitQtyMainIngredient',
        'vegQtyMainIngredient',
        'wgQtyMainIngredient',
        'qty',
    ]

    ingredient_ids = []
    quantities = []
    for i in range(1, 21):
        ingredient_value = None
        qty_value = None

        for prefix in ingredient_prefixes:
            candidate = request.POST.get(f'{prefix}{i}')
            if candidate not in (None, ''):
                ingredient_value = candidate
                break

        for prefix in qty_prefixes:
            candidate = request.POST.get(f'{prefix}{i}')
            if candidate not in (None, ''):
                qty_value = candidate
                break

        ingredient_ids.append(ingredient_value)
        quantities.append(qty_value)

    save_recipe_ingredients(r, ingredient_ids, quantities)
    
    from django.shortcuts import redirect
    return redirect(request.META.get('HTTP_REFERER', '/'))

@require_http_methods(["GET"])
def fruit_recipe_detail(request, recipe_id):
    user = get_user_for_view(request)
    r = Recipe.objects.filter(id=recipe_id, user=user, recipe_type='fruit').first()
    if not r: return JsonResponse({'error': 'Not found'}, status=404)
    
    # Get ingredients from RecipeIngredient table
    ingredients = get_recipe_ingredients(r)
    ingredient_data = {}
    for idx, (ing, qty) in enumerate(ingredients, start=1):
        ingredient_data[f'ingredient{idx}_id'] = ing.id if ing else None
        ingredient_data[f'qty{idx}'] = float(qty) if qty else None
    
    return JsonResponse({
        'id': r.id, 'name': r.name,
        **ingredient_data,
        'rule_id': r.fruit_rule_id if r.fruit_rule else None, 'image_url': r.image.url if r.image else None,
        'populate_breakfast': r.populate_breakfast,
        'populate_am_snack': r.populate_am_snack,
        'populate_lunch': r.populate_lunch,
        'populate_pm_snack': r.populate_pm_snack,
        'standalone': r.standalone,
        'ignore_inventory': r.ignore_inventory,
    })

@require_http_methods(["POST"])
def update_fruit_recipe(request, recipe_id):
    user = get_user_for_view(request)
    r = Recipe.objects.filter(id=recipe_id, user=user, recipe_type='fruit').first()
    if not r: return JsonResponse({'success': False, 'error': 'Not found'}, status=404)
    r.name = request.POST.get('recipeName') or request.POST.get('fruitName') or r.name
    # Update fruit_rule if provided
    rule_id = request.POST.get('fruitRule')
    if rule_id:
        r.fruit_rule_id = rule_id
    if request.FILES.get('image'): r.image = request.FILES['image']
    
    # Update checkbox fields
    r.populate_breakfast = request.POST.get('fruitPopulateBreakfast') == 'on'
    r.populate_am_snack = request.POST.get('fruitPopulateAMSnack') == 'on'
    r.populate_lunch = request.POST.get('fruitPopulateLunch') == 'on'
    r.populate_pm_snack = request.POST.get('fruitPopulatePMSnack') == 'on'
    r.standalone = request.POST.get('fruitStandalone') == 'on'
    r.ignore_inventory = request.POST.get('fruitIgnoreInventory') == 'on'
    
    r.save()
    
    # Update ingredients
    ingredient_ids = [request.POST.get(f'fruitMainIngredient{i}') for i in range(1, 21)]
    quantities = [request.POST.get(f'fruitQtyMainIngredient{i}') for i in range(1, 21)]
    save_recipe_ingredients(r, ingredient_ids, quantities)
    
    from django.shortcuts import redirect
    return redirect(request.META.get('HTTP_REFERER', '/'))

@require_http_methods(["GET"])
def veg_recipe_detail(request, recipe_id):
    user = get_user_for_view(request)
    r = Recipe.objects.filter(id=recipe_id, user=user, recipe_type='vegetable').first()
    if not r: return JsonResponse({'error': 'Not found'}, status=404)
    
    # Get ingredients from RecipeIngredient table
    ingredients = get_recipe_ingredients(r)
    ingredient_data = {}
    for idx, (ing, qty) in enumerate(ingredients, start=1):
        ingredient_data[f'ingredient{idx}_id'] = ing.id if ing else None
        ingredient_data[f'qty{idx}'] = float(qty) if qty else None
    
    return JsonResponse({
        'id': r.id, 'name': r.name,
        **ingredient_data,
        'rule_id': r.veg_rule_id if r.veg_rule else None, 'image_url': r.image.url if r.image else None,
        'populate_breakfast': r.populate_breakfast,
        'populate_am_snack': r.populate_am_snack,
        'populate_lunch': r.populate_lunch,
        'populate_pm_snack': r.populate_pm_snack,
        'standalone': r.standalone,
        'ignore_inventory': r.ignore_inventory,
    })

@require_http_methods(["POST"])
def update_veg_recipe(request, recipe_id):
    user = get_user_for_view(request)
    r = Recipe.objects.filter(id=recipe_id, user=user, recipe_type='vegetable').first()
    if not r: return JsonResponse({'success': False, 'error': 'Not found'}, status=404)
    r.name = request.POST.get('recipeName') or request.POST.get('vegName') or r.name
    # Update veg_rule if provided
    rule_id = request.POST.get('vegRule')
    if rule_id:
        r.veg_rule_id = rule_id
    if request.FILES.get('image'): r.image = request.FILES['image']
    
    # Update checkbox fields
    r.populate_breakfast = request.POST.get('vegPopulateBreakfast') == 'on'
    r.populate_am_snack = request.POST.get('vegPopulateAMSnack') == 'on'
    r.populate_lunch = request.POST.get('vegPopulateLunch') == 'on'
    r.populate_pm_snack = request.POST.get('vegPopulatePMSnack') == 'on'
    r.standalone = request.POST.get('vegStandalone') == 'on'
    r.ignore_inventory = request.POST.get('vegIgnoreInventory') == 'on'
    
    r.save()
    
    # Update ingredients
    ingredient_ids = [request.POST.get(f'vegMainIngredient{i}') for i in range(1, 21)]
    quantities = [request.POST.get(f'vegQtyMainIngredient{i}') for i in range(1, 21)]
    save_recipe_ingredients(r, ingredient_ids, quantities)
    
    from django.shortcuts import redirect
    return redirect(request.META.get('HTTP_REFERER', '/'))

@require_http_methods(["GET"])
def wg_recipe_detail(request, recipe_id):
    user = get_user_for_view(request)
    r = Recipe.objects.filter(id=recipe_id, user=user, recipe_type='whole_grain').first()
    if not r: return JsonResponse({'error': 'Not found'}, status=404)
    
    # Get ingredients from RecipeIngredient table
    ingredients = get_recipe_ingredients(r)
    ingredient_data = {}
    for idx, (ing, qty) in enumerate(ingredients, start=1):
        ingredient_data[f'ingredient{idx}_id'] = ing.id if ing else None
        ingredient_data[f'qty{idx}'] = float(qty) if qty else None
    
    return JsonResponse({
        'id': r.id, 'name': r.name,
        **ingredient_data,
        'rule_id': r.grain_rule_id if r.grain_rule else None, 'image_url': r.image.url if r.image else None,
        'populate_breakfast': r.populate_breakfast,
        'populate_am_snack': r.populate_am_snack,
        'populate_lunch': r.populate_lunch,
        'populate_pm_snack': r.populate_pm_snack,
        'standalone': r.standalone,
        'ignore_inventory': r.ignore_inventory,
    })

@login_required
def similarity_groups_list(request):
    user = get_user_for_view(request)
    groups = RecipeSimilarityGroup.objects.filter(user=user).prefetch_related('recipes')
    data = []
    for g in groups:
        data.append({
            'id': g.id,
            'name': g.name,
            'recipes': [{'id': r.id, 'name': r.name} for r in g.recipes.order_by('name')],
        })
    return JsonResponse({'groups': data})


@login_required
@require_http_methods(["POST"])
def similarity_group_create(request):
    user = get_user_for_view(request)
    name = (request.POST.get('name') or '').strip()
    if not name:
        return JsonResponse({'success': False, 'error': 'Name is required.'}, status=400)
    if RecipeSimilarityGroup.objects.filter(user=user, name=name).exists():
        return JsonResponse({'success': False, 'error': 'A group with that name already exists.'}, status=400)
    group = RecipeSimilarityGroup.objects.create(user=user, name=name)
    recipe_ids = request.POST.getlist('recipe_ids')
    valid_ids = list(Recipe.objects.filter(user=user, id__in=recipe_ids).values_list('id', flat=True))
    group.recipes.set(valid_ids)
    return JsonResponse({'success': True, 'id': group.id})


@login_required
@require_http_methods(["POST"])
def similarity_group_update(request, group_id):
    user = get_user_for_view(request)
    group = RecipeSimilarityGroup.objects.filter(id=group_id, user=user).first()
    if not group:
        return JsonResponse({'success': False, 'error': 'Not found.'}, status=404)
    name = (request.POST.get('name') or '').strip()
    if not name:
        return JsonResponse({'success': False, 'error': 'Name is required.'}, status=400)
    if RecipeSimilarityGroup.objects.filter(user=user, name=name).exclude(id=group_id).exists():
        return JsonResponse({'success': False, 'error': 'A group with that name already exists.'}, status=400)
    group.name = name
    group.save()
    recipe_ids = request.POST.getlist('recipe_ids')
    valid_ids = list(Recipe.objects.filter(user=user, id__in=recipe_ids).values_list('id', flat=True))
    group.recipes.set(valid_ids)
    return JsonResponse({'success': True})


@login_required
@require_http_methods(["DELETE"])
def similarity_group_delete(request, group_id):
    user = get_user_for_view(request)
    deleted, _ = RecipeSimilarityGroup.objects.filter(id=group_id, user=user).delete()
    if deleted:
        return JsonResponse({'success': True})
    return JsonResponse({'success': False, 'error': 'Not found.'}, status=404)


@require_http_methods(["POST"])
def update_wg_recipe(request, recipe_id):
    user = get_user_for_view(request)
    r = Recipe.objects.filter(id=recipe_id, user=user, recipe_type='whole_grain').first()
    if not r: return JsonResponse({'success': False, 'error': 'Not found'}, status=404)
    r.name = request.POST.get('recipeName') or request.POST.get('wgName') or r.name
    # Update grain_rule if provided (whole grain uses grain_rule)
    rule_id = request.POST.get('wgRule')
    if rule_id:
        r.grain_rule_id = rule_id
    if request.FILES.get('image'): r.image = request.FILES['image']
    
    # Update checkbox fields
    r.populate_breakfast = request.POST.get('wgPopulateBreakfast') == 'on'
    r.populate_am_snack = request.POST.get('wgPopulateAMSnack') == 'on'
    r.populate_lunch = request.POST.get('wgPopulateLunch') == 'on'
    r.populate_pm_snack = request.POST.get('wgPopulatePMSnack') == 'on'
    r.standalone = request.POST.get('wgStandalone') == 'on'
    r.ignore_inventory = request.POST.get('wgIgnoreInventory') == 'on'
    
    r.save()
    
    # Update ingredients
    ingredient_ids = [request.POST.get(f'wgMainIngredient{i}') for i in range(1, 21)]
    quantities = [request.POST.get(f'wgQtyMainIngredient{i}') for i in range(1, 21)]
    save_recipe_ingredients(r, ingredient_ids, quantities)
    
    from django.shortcuts import redirect
    return redirect(request.META.get('HTTP_REFERER', '/'))
