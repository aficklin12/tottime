from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.models import Group
from django.contrib.auth import authenticate, login, logout, get_user_model
from django.db.models import Q, Subquery, IntegerField, Count, F, Sum, Max, Min, ExpressionWrapper, DurationField, Exists, OuterRef
from django.db.models.functions import Concat, Lower
from django.http import HttpResponseForbidden, HttpResponseBadRequest, JsonResponse, HttpResponseNotAllowed, HttpResponseRedirect
import urllib.parse, stripe, requests, random, logging, json, pytz, os, uuid
from square.client import Client
from django.conf import settings
from django.core.paginator import Paginator
stripe.api_key = settings.STRIPE_SECRET_KEY
from django.utils.timezone import now
from decimal import Decimal
from django.db import transaction, models
from django.contrib import messages
from django.contrib.sites.shortcuts import get_current_site
from .forms import SignupForm, ForgotUsernameForm, LoginForm, RuleForm, MessageForm, InvitationForm
from .models import Classroom, ABCQualityElement, ABCQualityIndicator, ResourceSignature, Resource, StandardCategory, ClassroomScoreSheet, StandardCriteria, ScoreItem, OrientationItem, StaffOrientation, OrientationProgress, EnrollmentTemplate, EnrollmentPolicy, EnrollmentSubmission, CompanyAccountOwner, Announcement, UserMessagingPermission, DiaperChangeRecord, IncidentReport, MainUser, SubUser, RolePermission, Student, Inventory, Recipe,MessagingPermission, BreakfastRecipe, Classroom, ClassroomAssignment, AMRecipe, PMRecipe, OrderList, Student, AttendanceRecord, Message, Conversation, Payment, WeeklyTuition, TeacherAttendanceRecord, TuitionPlan, PaymentRecord, MilkCount, WeeklyMenu, Rule, MainUser, FruitRecipe, VegRecipe, WgRecipe, RolePermission, SubUser, Invitation
from django.contrib.auth.decorators import login_required
from django.views.decorators.csrf import csrf_protect, csrf_exempt
from django.views.decorators.http import require_POST
from PIL import Image
from io import BytesIO
from pytz import utc
from datetime import datetime, timedelta, date, time
from collections import defaultdict
from django.utils import timezone
from calendar import monthrange
from django.core.mail import send_mail
from django.urls import reverse
from django.core.exceptions import ValidationError
import bleach
ALLOWED_TAGS = [
    'p', 'b', 'strong', 'i', 'em', 'u', 'ul', 'ol', 'li', 'br', 'span'
]
ALLOWED_ATTRIBUTES = {
    'a': ['href', 'rel', 'target'], 
    'span': ['style']
}
ALLOWED_STYLES = ['font-weight', 'font-style', 'text-decoration']

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
        'total_unread_count': 0,
    }

    try:
        sub_user = SubUser.objects.get(user=request.user)
        group_id = sub_user.group_id.id
        main_user_id = sub_user.main_user.id

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

    except SubUser.DoesNotExist:
        # If user is not a SubUser, assume it's a main user and allow access to all links
        allow_access = True
        for key in permissions_context:
            permissions_context[key] = True

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

@login_required
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
    print(f"DEBUG: main_user.id={main_user.id}, username={main_user.username}")
    print(f"DEBUG: company_locations found: {[loc.id for loc in company_locations]}")

    # Get all active templates for all company locations
    if company_locations.exists():
        templates = EnrollmentTemplate.objects.filter(
            company__in=company_locations.values_list('company', flat=True),
            location__in=company_locations,
            is_active=True
        ).select_related('company', 'location')
        print(f"DEBUG: Found {templates.count()} templates for main_user.id={main_user.id}")
        for t in templates:
            print(f"DEBUG: Template id={t.id}, name={t.template_name}, location_id={t.location_id}, company_id={t.company_id}, is_active={t.is_active}")
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
        print("DEBUG: No company_location found, templates queryset is empty.")

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

    return render(request, 'tottimeapp/enrollment.html', context)

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
                    
                    print(f"Email notification sent successfully to {admin_email}")
                    
                else:
                    print(f"No email address found for notification. Main user: {main_user_for_notification}")
                    
            except Exception as email_error:
                print(f"Email notification failed: {email_error}")
                # Don't fail the submission if email fails
            
            messages.success(request, 'Enrollment form submitted successfully! We will contact you soon.')
            return redirect('public_enrollment_success')
            
        except Exception as e:
            print(f"Enrollment submission error: {e}")
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
    
    # Get the company account owner for the current user
    try:
        company_account_owner = CompanyAccountOwner.objects.select_related('company', 'main_account_owner').get(
            main_account_owner=request.user
        )
        facility_name = company_account_owner.location_name or "Not Set"
        sponsor_name = company_account_owner.company.name
    except CompanyAccountOwner.DoesNotExist:
        facility_name = "Not Set"
        sponsor_name = "Not Set"
    
    # Add facility and sponsor to the context
    permissions_context.update({
        'facility_name': facility_name,
        'sponsor_name': sponsor_name,
    })
    
    # If access is allowed, proceed with rendering the menu
    return render(request, 'tottimeapp/weekly-menu.html', permissions_context)

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
    
    # ADD THIS: Get order items for shopping list and ordered items tabs
    order_items = OrderList.objects.filter(user=user)

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
        'order_items': order_items,  # ADD THIS LINE
        **permissions_context,  # Include permission flags dynamically
    })

@login_required
def infant_menu(request):
    # Check permissions for the specific page
    required_permission_id = 272  # Permission ID for accessing infant menu view
    permissions_context = check_permissions(request, required_permission_id)
    # If check_permissions returns a redirect, return it immediately
    if isinstance(permissions_context, HttpResponseRedirect):
        return permissions_context
    
    # Get the user (MainUser) for filtering
    user = get_user_for_view(request)
    
    # Get all inventory items with category 'Infants' for dropdowns, filtered by user
    inventory_items = Inventory.objects.filter(category='Infants', user=user)
    permissions_context['inventory_items'] = inventory_items
    
    # If access is allowed, render the infant menu page
    return render(request, 'tottimeapp/infant_menu.html', permissions_context)

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
    def add_recipe_ingredients(recipe_model, recipe_name):
        if not recipe_name:
            return
        
        try:
            recipe = recipe_model.objects.get(user=user, name=recipe_name)
            for i in range(1, 6):  # Check ingredient1 through ingredient5
                ingredient = getattr(recipe, f'ingredient{i}', None)
                qty = getattr(recipe, f'qty{i}', None)
                if ingredient and qty:
                    if ingredient.id not in ingredient_requirements:
                        ingredient_requirements[ingredient.id] = {
                            'ingredient': ingredient,
                            'total_required': 0
                        }
                    ingredient_requirements[ingredient.id]['total_required'] += qty
        except recipe_model.DoesNotExist:
            pass
    
    # Helper function for single ingredient recipes
    def add_single_ingredient_recipe(recipe_model, recipe_name):
        if not recipe_name:
            return
        
        try:
            recipe = recipe_model.objects.get(user=user, name=recipe_name)
            if recipe.ingredient1 and recipe.qty1:
                if recipe.ingredient1.id not in ingredient_requirements:
                    ingredient_requirements[recipe.ingredient1.id] = {
                        'ingredient': recipe.ingredient1,
                        'total_required': 0
                    }
                ingredient_requirements[recipe.ingredient1.id]['total_required'] += recipe.qty1
        except recipe_model.DoesNotExist:
            pass
    
    # Process each menu entry in the latest week
    for menu in latest_menus:
        # Define menu fields and their associated recipe models
        menu_fields = [
            # AM Snack fields
            ('am_fluid_milk', AMRecipe),
            ('am_fruit_veg', AMRecipe),
            ('am_bread', AMRecipe),
            ('am_additional', AMRecipe),
            
            # AMS fields
            ('ams_fluid_milk', BreakfastRecipe),
            ('ams_fruit_veg', BreakfastRecipe),
            ('ams_bread', BreakfastRecipe),
            ('ams_meat', BreakfastRecipe),
            
            # Lunch fields
            ('lunch_main_dish', Recipe),
            ('lunch_fluid_milk', Recipe),
            ('lunch_additional', Recipe),
            ('lunch_meat', Recipe),
            
            # PM Snack fields
            ('pm_fluid_milk', PMRecipe),
            ('pm_fruit_veg', PMRecipe),
            ('pm_bread', PMRecipe),
            ('pm_meat', PMRecipe),
        ]
        
        # Special fields with specific recipe types
        lunch_vegetable = getattr(menu, 'lunch_vegetable', None)
        lunch_fruit = getattr(menu, 'lunch_fruit', None)
        lunch_grain = getattr(menu, 'lunch_grain', None)
        
        # Process regular menu fields
        for field_name, recipe_model in menu_fields:
            recipe_name = getattr(menu, field_name, None)
            add_recipe_ingredients(recipe_model, recipe_name)
        
        # Process special lunch fields
        if lunch_vegetable:
            add_single_ingredient_recipe(VegRecipe, lunch_vegetable)
        
        if lunch_fruit:
            add_single_ingredient_recipe(FruitRecipe, lunch_fruit)
        
        if lunch_grain:
            add_single_ingredient_recipe(WgRecipe, lunch_grain)
    
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
                'required_qty': total_required,
                'shortage': total_required - float(ingredient.total_quantity)  # Use total_quantity
            })
    
    # Sort by name
    order_soon_items.sort(key=lambda x: x['name'])
    
    return JsonResponse(order_soon_items, safe=False)

@login_required
def order_soon_items_api(request):
    try:
        user = get_user_for_view(request)
        print(f"User: {user}")
        
        # Get items where current quantity is at or below resupply threshold
        order_soon_items = Inventory.objects.filter(
            user=user,
            quantity__lte=F('resupply')
        ).values('item', 'quantity', 'resupply', 'units')
        
        print(f"Raw queryset: {list(order_soon_items)}")
        
        items_data = []
        for item in order_soon_items:
            item_dict = {
                'name': item['item'],
                'current_quantity': float(item['quantity']) if item['quantity'] is not None else 0,
                'resupply_threshold': float(item['resupply']) if item['resupply'] is not None else 0,
                'units': item['units'] or ''
            }
            items_data.append(item_dict)
            print(f"Item dict: {item_dict}")
        
        print(f"Final items_data: {items_data}")
        return JsonResponse(items_data, safe=False)
        
    except Exception as e:
        print(f"Error in order_soon_items_api: {str(e)}")
        import traceback
        traceback.print_exc()
        return JsonResponse({'error': str(e)}, status=500)

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
            # Parse JSON data from the request body
            raw_body = request.body.decode('utf-8')
           
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
                    print(f"Found existing menu for {day_key}: {existing_menu.id}")
                else:
                    print(f"No existing menu found for {day_key}")

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
  

                except Exception as day_error:
                    import traceback
                    traceback.print_exc()
                    return JsonResponse({
                        'status': 'fail', 
                        'error': f'Error saving {day_key}: {str(day_error)}'
                    }, status=500)

            print("Successfully saved all menu data")
            return JsonResponse({'status': 'success'}, status=200)

        except json.JSONDecodeError as e:
            print(f"JSON decode error: {str(e)}")
            return JsonResponse({'status': 'fail', 'error': 'Invalid JSON'}, status=400)

        except Exception as e:
            print(f"Unexpected error in save_menu: {str(e)}")
            print(f"Error type: {type(e).__name__}")
            import traceback
            traceback.print_exc()
            return JsonResponse({'status': 'fail', 'error': f'Unexpected error: {str(e)}'}, status=500)

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
        user = get_user_for_view(request)
        shopping_list_items = OrderList.objects.filter(user=user)
        serialized_items = [{'id': item.id, 'name': item.item, 'quantity': item.quantity, 'ordered': item.ordered} for item in shopping_list_items]
        return JsonResponse(serialized_items, safe=False)
    else:
        return HttpResponseNotAllowed(['GET'])

def update_orders(request):
    if request.method == 'POST':
        item_ids = request.POST.getlist('items')
        try:
            user = get_user_for_view(request)
            for item_id in item_ids:
                order_item = get_object_or_404(OrderList, id=item_id, user=user)
                order_item.ordered = True
                order_item.save()
                
                # Add ordered item to inventory automatically
                inventory_item, created = Inventory.objects.get_or_create(
                    user=user,
                    item=order_item.item,
                    defaults={
                        'quantity': order_item.quantity,
                        'category': order_item.category or 'Other',
                        'units': 'units',
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
def update_shopping_item_status(request):
    if request.method == 'POST':
        import json
        data = json.loads(request.body)
        item_id = data.get('item_id')
        ordered = data.get('ordered')
        
        try:
            user = get_user_for_view(request)
            order_item = get_object_or_404(OrderList, id=item_id, user=user)
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
            user = get_user_for_view(request)
            order_item = get_object_or_404(OrderList, id=item_id, user=user)
            order_item.delete()
            return JsonResponse({'success': True, 'message': 'Item deleted successfully'})
        except Exception as e:
            return JsonResponse({'success': False, 'error': str(e)}, status=500)
    else:
        return HttpResponseNotAllowed(['DELETE'])

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
    # Check permissions for the specific page
    required_permission_id = 274  # Permission ID for daily_attendance view
    permissions_context = check_permissions(request, required_permission_id)
    # If check_permissions returns a redirect, return it immediately
    if isinstance(permissions_context, HttpResponseRedirect):
        return permissions_context
    # Fetch attendance data
    today = date.today()
    user = get_user_for_view(request)
    students = Student.objects.all()
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
        'active_tab': 'students', 
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

    groups = Group.objects.exclude(id=8).exclude(name__in=["Owner", "Parent", "Free User"]).order_by('name')

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

@login_required
@csrf_exempt
def switch_account(request):

    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            account_owner_id = data.get('account_owner_id')
            
            # Verify user has permission to switch
            if not request.user.can_switch:
                return JsonResponse({'success': False, 'error': 'Permission denied'})
            
            # Verify the account owner exists and is in the same company
            if request.user.company:
                # Check if the account owner ID exists in the CompanyAccountOwner table for this company
                account_owner = get_object_or_404(
                    CompanyAccountOwner, 
                    main_account_owner_id=account_owner_id,
                    company=request.user.company
                )
                
                # Get the MainUser object for the selected account owner
                new_main_account_owner = get_object_or_404(MainUser, id=account_owner_id)
                
                # Update the user's main_account_owner_id
                request.user.main_account_owner_id = account_owner_id
                request.user.save()
                
                # Check if this user is also a SubUser and update accordingly
                try:
                    subuser = SubUser.objects.get(user=request.user)
                    if subuser.can_switch:
                        subuser.main_user = new_main_account_owner
                        subuser.save()
                        print(f"Updated SubUser {subuser.id} main_user to {new_main_account_owner.id}")
                except SubUser.DoesNotExist:
                    # User is not a SubUser, which is fine
                    pass
                
                return JsonResponse({'success': True})
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
            print(f"Error creating orientation: {str(e)}")
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
    """Handle sending signature request emails for multiple resources"""
    if request.method == 'POST':
        resource_ids = request.POST.get('resource_ids', '').split(',')
        recipient_email = request.POST.get('recipient_email')
        email_message = request.POST.get('email_message', '')
        
        if not resource_ids or not recipient_email:
            return JsonResponse({'success': False, 'error': 'Missing required parameters'})
        
        try:
            # Get the resources
            resources = Resource.objects.filter(pk__in=resource_ids)
            
            # Check if we found all requested resources
            if len(resources) != len(resource_ids):
                return JsonResponse({'success': False, 'error': 'Some resources could not be found'})
            
            # Build the email message
            subject = f"Signature Request: {len(resources)} Document(s)"
            
            # Get the first resource for the main URL
            first_resource = resources.first()
            
            # Build the signature URL with all resource IDs as query parameters
            current_site = get_current_site(request)
            
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
            
            # Send the email with simplified parameters
            from django.core.mail import send_mail
            
            send_mail(
                subject,
                message,
                None,  # Use DEFAULT_FROM_EMAIL from settings
                [recipient_email],
                fail_silently=False,
            )
            
            return JsonResponse({'success': True})
            
        except Exception as e:
            import traceback
            error_details = traceback.format_exc()
            print(error_details)  # Log the full error for debugging
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
            resources = Resource.objects.filter(indicator_id__in=indicator_ids).order_by('indicator_id')
            
            # If no resources, return a message
            if not resources.exists():
                if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                    return JsonResponse({'success': False, 'error': f'No documents found for {scope_description}.'})
                else:
                    messages.warning(request, f"No documents found for {scope_description}.")
                    return redirect('abc_quality')
            
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
                # Check if we need to start a new indicator section
                if current_indicator != resource.indicator_id:
                    current_indicator = resource.indicator_id
                    
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
                    if hasattr(resource.file, 'name'):
                        file_name = os.path.basename(resource.file.name)
                    else:
                        file_name = resource.title or "Untitled Document"
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
                try:
                    # Use file's content instead of path
                    file_content = BytesIO(resource.file.read())
                    resource.file.seek(0)  # Reset the file pointer for later use
                    
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
                                pix = page.get_pixmap(matrix=fitz.Matrix(0.5, 0.5))
                                
                                # Create a temp BytesIO for this page
                                img_data = pix.tobytes("png")
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
                    logger.error(f"Error processing file {file_name}: {e}")
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
                    
                    from django.http import HttpResponse
                    
                    # Create an HttpResponse instead of FileResponse for more control
                    response = HttpResponse(buffer.getvalue(), content_type='application/pdf')
                    
                    # Set explicit Content-Disposition header
                    response['Content-Disposition'] = f'attachment; filename="abc_quality_{filename_suffix}.pdf"'
                    
                    # Set additional headers to prevent caching
                    response['Content-Length'] = buffer.getbuffer().nbytes
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