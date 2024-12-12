from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from django.contrib.auth.decorators import login_required  # Import login_required
from django.views.generic import RedirectView
from tottimeapp import views

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', login_required(views.index), name='index'),  
    path('index.html', login_required(views.index), name='index'),  
    path('index_director.html', login_required(views.index_director), name='index_director'),  
    path('index_teacher.html', login_required(views.index_teacher), name='index_teacher'),  
    path('index_cook.html', login_required(views.index_cook), name='index_cook'),  
    path('index_parent.html', login_required(views.index_parent), name='index_parent'),  
    path('index_free_user.html', login_required(views.index_free_user), name='index_free_user'),  
    path('login/', views.user_login, name='login'),  # Unprotected view
    path('signup/', views.user_signup, name='signup'),  # Unprotected view
    path('logout/', login_required(views.logout_view), name='logout'),  
    path('inventory/', login_required(views.inventory_list), name='inventory_list'),  
    path('app/', include('tottimeapp.urls')),  
    path('recipes/', login_required(views.recipes), name='recipes'),  
    path('rosters/', login_required(views.rosters), name='rosters'),  
    path('weekly-menu/', login_required(views.menu), name='menu'),  
    path('menu_rules/', login_required(views.menu_rules), name='menu_rules'),
    path('add_rule/', login_required(views.add_rule), name='add_rule'),
    path('milk_count/', login_required(views.milk_count), name='milk_count'),  
    path('inventory/add/', login_required(views.add_item), name='add_item'),  
    path('edit_quantity/<int:item_id>/', login_required(views.edit_quantity), name='edit_quantity'),  
    path('remove_item/<int:item_id>/', login_required(views.remove_item), name='remove_item'),  
    path('api/out-of-stock-items/', login_required(views.get_out_of_stock_items), name='out_of_stock_items'),     
    path('api/order-soon-items/', login_required(views.order_soon_items_view), name='order_soon_items'),  
    path('fetch-ingredients/', login_required(views.fetch_ingredients), name='fetch_ingredients'),  
    path('create-recipe/', login_required(views.create_recipe), name='create_recipe'),  
    path('create-fruit-recipe/', login_required(views.create_fruit_recipe), name='create_fruit_recipe'),
    path('create-veg-recipe/', login_required(views.create_veg_recipe), name='create_veg_recipe'),
    path('create-wg-recipe/', login_required(views.create_wg_recipe), name='create_wg_recipe'),
    path('fetch-recipes/', login_required(views.fetch_recipes), name='fetch_recipes'), 
    path('fetch-fruit-recipes/', login_required(views.fetch_fruit_recipes), name='fetch_fruit_recipes'),  
    path('fetch-veg-recipes/', login_required(views.fetch_veg_recipes), name='fetch_veg_recipes'),  
    path('fetch-wg-recipes/', login_required(views.fetch_wg_recipes), name='fetch_wg_recipes'),  
    path('fetch-rules/', login_required(views.fetch_rules), name='fetch_rules'),
    path('save-menu/', login_required(views.save_menu), name='save-menu'),  
    path('get-recipe/<int:recipe_id>/', login_required(views.get_recipe), name='get_recipe'),  
    path('delete-recipe/<int:recipe_id>/', login_required(views.delete_recipe), name='delete_recipe'),  
    path('classroom_options/', login_required(views.classroom_options), name='classroom_options'),  
    path('401/', login_required(views.error401), name='error401'),  
    path('404/', login_required(views.error404), name='error404'),  
    path('500/', login_required(views.error500), name='error500'),  
    path('create-breakfast-recipe/', login_required(views.create_breakfast_recipe), name='create_breakfast_recipe'), 
    path('fetch-breakfast-recipes/', login_required(views.fetch_breakfast_recipes), name='fetch_breakfast_recipes'),  
    path('delete-breakfast-recipe/<int:recipe_id>/', login_required(views.delete_breakfast_recipe), name='delete_breakfast_recipe'),  
    path('create-am-recipe/', login_required(views.create_am_recipe), name='create_am_recipe'),  
    path('fetch-am-recipes/', login_required(views.fetch_am_recipes), name='fetch_am_recipes'),  
    path('delete-am-recipe/<int:recipe_id>/', login_required(views.delete_am_recipe), name='delete_am_recipe'),  
    path('create-pm-recipe/', login_required(views.create_pm_recipe), name='create_pm_recipe'),  
    path('fetch-pm-recipes/', login_required(views.fetch_pm_recipes), name='fetch_pm_recipes'),  
    path('delete-pm-recipe/<int:recipe_id>/', login_required(views.delete_pm_recipe), name='delete_pm_recipe'),  
    path('order-list/', login_required(views.order_list), name='order_list'), 
    path('api/shopping-list', login_required(views.shopping_list_api), name='shopping_list_api'), 
    path('update-orders/', login_required(views.update_orders), name='update_orders'), 
    path('delete-shopping-items/', login_required(views.delete_shopping_items), name='delete_shopping_items'),
    path('sign-in/', login_required(views.sign_in), name='sign_in'),
    path('process_code/', login_required(views.process_code), name='process_code'),
    path('daily-attendance/', login_required(views.daily_attendance), name='daily_attendance'),
    path('add_student/', login_required(views.add_student), name='add_student'),
    path('add_classroom/', login_required(views.add_classroom), name='add_classroom'),
    path('delete_classrooms/', login_required(views.delete_classrooms), name='delete_classrooms'),
    path('update_milk_count/', login_required(views.update_milk_count), name='update_milk_count'),
    path('milk-count/', login_required(views.milk_count_view), name='milk_count'),
    path('meal_count/', login_required(views.meal_count), name='meal_count'),
    path('generate_breakfast_menu/', login_required(views.generate_breakfast_menu), name='generate_breakfast_menu'),
    path('generate_pm_menu/', login_required(views.generate_pm_menu), name='generate_pm_menu'),
    path('generate_am_menu/', login_required(views.generate_am_menu), name='generate_am_menu'),
    path('generate_vegetable_menu/', login_required(views.generate_vegetable_menu), name='generate_vegetable_menu'),
    path('generate_fruit_menu/', login_required(views.generate_fruit_menu), name='generate_fruit_menu'),
    path('generate_menu/', login_required(views.generate_menu), name='generate_menu'),
    path('api/fruits/', login_required(views.get_fruits), name='get_fruits'),
    path('account_settings/', login_required(views.account_settings), name='account_settings'),
    path('api/save_menu/', login_required(views.save_menu), name='save_menu'),
    path('api/check_menu/', login_required(views.check_menu), name='check_menu'),
    path('past-menus/', login_required(views.past_menus), name='past_menus'),
    path('permissions/', login_required(views.permissions), name='permissions'),
    path('send-invitation/', login_required(views.send_invitation), name='send_invitation'),
    path('accept-invitation/<str:token>/', views.accept_invitation, name='accept_invitation'),
    path('invalid-invitation/', views.invalid_invitation, name='invalid_invitation'), 
    path('no_access/', login_required(views.no_access), name='no_access'),
    path('save_permissions/', login_required(views.save_permissions), name='save_permissions'),
    path('inbox/', login_required(views.inbox), name='message_inbox'), 
    path('conversation/<int:user_id>/', login_required(views.conversation), name='conversation'),
    path('start_conversation/<int:user_id>/', login_required(views.start_conversation), name='start_conversation'),
    path('payment/<int:subuser_id>/', login_required(views.payment_view), name='payment_detail'),
    path('payments/', login_required(views.payment_view), name='payment'),
    path('create-payment/', login_required(views.create_payment), name='create_payment'),
    path('create-payment-intent/', views.create_payment_intent, name='create_payment_intent'),
    path('update-payment-status/', views.update_payment_status, name='update_payment_status'),
    path('record-payment/', views.record_payment, name='record_payment'),
    path('stripe/', login_required(views.stripe_login), name='stripe'),
    path("stripe/connect/", views.stripe_connect, name="stripe_connect"),
    path("stripe/callback/", views.stripe_callback, name="stripe_callback"),
    path('clock_in/', login_required(views.clock_in), name='clock_in'),
    path('process_teacher_code/', login_required(views.clock_in), name='process_teacher_code'),
    path('time-sheet/', login_required(views.time_sheet), name='time_sheet'),
    path('employee-detail/', login_required(views.employee_detail), name='employee_detail'),
    path('edit_time/', login_required(views.edit_time), name='edit_time'),
    path('delete-time/', login_required(views.delete_time), name='delete_time'),
    path('upload-profile-picture/', login_required(views.upload_profile_picture), name='upload_profile_picture'),


] + static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)


# Serve media files in development if DEBUG is True
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)