from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.models import User
from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from .forms import SignupForm, LoginForm, RuleForm
from .models import Inventory, Recipe, BreakfastRecipe, Classroom, AMRecipe, PMRecipe, OrderList, Student, AttendanceRecord
from .models import MilkCount, WeeklyMenu, Location, Rule, FruitRecipe, VegRecipe, WgRecipe
from django.contrib.auth.decorators import login_required
from django.http import HttpResponseBadRequest, JsonResponse, HttpResponseNotAllowed, HttpResponse
import random, logging, json
from django.views.decorators.csrf import csrf_protect
import pytz
from django.contrib.auth.forms import UserCreationForm
from django.db import models
from pytz import utc
from datetime import datetime, timedelta, date, time
from collections import defaultdict
from django.utils import timezone
from django.apps import apps
from django.db.models import F, Sum, Subquery, OuterRef, Max, Min
from django.views.decorators.csrf import csrf_exempt
from calendar import monthrange
from django.core.mail import send_mail
from django.urls import reverse
from django.conf import settings
import uuid
logger = logging.getLogger(__name__)

def login_view(request):
    return render(request, 'login.html')

@login_required(login_url='/login/')
def index(request):
    order_items = OrderList.objects.filter(user=request.user)
    return render(request, 'index.html', {'order_items': order_items})

def recipes(request):
    return render(request, 'recipes.html')

def menu(request):
    return render(request, 'weekly-menu.html')

def account_settings(request):
    return render(request, 'account_settings.html')

def menu_rules(request):
    form = RuleForm()
    rules = Rule.objects.all()  # Query all rules from the database
    return render(request, 'menu_rules.html', {'form': form, 'rules': rules})

@login_required
def add_rule(request):
    if request.method == 'POST':
        form = RuleForm(request.POST)
        if form.is_valid():
            # Assign the current user to the rule before saving
            rule = form.save(commit=False)
            rule.user = request.user
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
            return redirect('index.html')  # Replace with the name of the view to redirect after signup
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
            if user:
                login(request, user)    
                return redirect('index')
    else:
        form = LoginForm()
    return render(request, 'login.html', {'form': form})
    
def logout_view(request):
    logout(request)
    # Redirect to the homepage or any other desired page
    return redirect('index')

@login_required
def inventory_list(request):
    # Retrieve inventory data
    inventory_items = Inventory.objects.filter(user_id=request.user.id)

    # Get unique categories for filtering options
    categories = Inventory.objects.filter(user_id=request.user.id).values_list('category', flat=True).distinct()

    # Filter by category if selected
    category_filter = request.GET.get('category')
    if category_filter:
        inventory_items = inventory_items.filter(category=category_filter)

    # Retrieve rules from the Rule model
    rules = Rule.objects.all()

    return render(request, 'inventory_list.html', {
        'inventory_items': inventory_items,
        'categories': categories,
        'rules': rules
    })

@login_required
def add_item(request):
    if request.method == 'POST':
        item = request.POST.get('item')
        category = request.POST.get('category')
        quantity = request.POST.get('quantity')
        resupply = request.POST.get('resupply')
        units = request.POST.get('units')  # Now this will directly capture the user's input


        rule_id = request.POST.get('rule')  # Get the rule value from the form
        if rule_id:
            rule = get_object_or_404(Rule, id=rule_id)
        else:
            rule = None

        Inventory.objects.create(
            user_id=request.user.id,
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
    out_of_stock_items = Inventory.objects.filter(user=request.user,quantity=0)
    data = [{'name': item.item} for item in out_of_stock_items]
    return JsonResponse(data, safe=False)

def order_soon_items_view(request):
    # Fetch items from the Inventory model where the quantity is less than the resupply threshold
    order_soon_items = Inventory.objects.filter(user=request.user, quantity__lt=F('resupply'), quantity__gt=0)

    # Convert queryset to a list of dictionaries containing item names
    order_soon_items_data = [{'name': item.item} for item in order_soon_items]

    # Return the items as a JSON response
    return JsonResponse(order_soon_items_data, safe=False)

def fetch_ingredients(request):
    user_id = request.user.id  # Assuming you're using some form of user authentication
    ingredients = Inventory.objects.filter(user_id=user_id).values('id', 'item')
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

        # Get the authenticated user
        user = request.user

        # Get the rule object if rule_id is provided
        rule = Rule.objects.get(id=rule_id) if rule_id else None

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
        for ingredient_id, quantity in zip(main_ingredient_ids, quantities):
            if ingredient_id and quantity:
                ingredient = Inventory.objects.get(id=ingredient_id)
                setattr(recipe, f'ingredient{main_ingredient_ids.index(ingredient_id) + 1}', ingredient)
                setattr(recipe, f'qty{main_ingredient_ids.index(ingredient_id) + 1}', quantity)
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

        # Get the authenticated user
        user = request.user

        # Get the rule object if rule_id is provided
        rule = Rule.objects.get(id=rule_id) if rule_id else None

        # Create fruit recipe instance
        fruit_recipe = FruitRecipe.objects.create(
            user=user,
            name=recipe_name,
            rule=rule
        )

        # Save the ingredient and its quantity to the fruit recipe
        if ingredient_id and quantity:
            ingredient = Inventory.objects.get(id=ingredient_id)
            fruit_recipe.ingredient1 = ingredient
            fruit_recipe.qty1 = quantity
        fruit_recipe.save()

        return JsonResponse({'success': True})
    else:
        return JsonResponse({'error': 'Method not allowed'}, status=405)

@login_required
def create_veg_recipe(request):
    if request.method == 'POST':
        recipe_name = request.POST.get('vegName')
        ingredient_id = request.POST.get('vegMainIngredient1')
        quantity = request.POST.get('vegQtyMainIngredient1')
        rule_id = request.POST.get('vegRule')

        if not recipe_name:
            return JsonResponse({'error': 'Recipe name is required'}, status=400)
        if not ingredient_id:
            return JsonResponse({'error': 'Main ingredient is required'}, status=400)
        if not quantity:
            return JsonResponse({'error': 'Quantity is required'}, status=400)
        if not rule_id:
            return JsonResponse({'error': 'Rule is required'}, status=400)

        user = request.user
        rule = Rule.objects.get(id=rule_id) if rule_id else None

        veg_recipe = VegRecipe.objects.create(
            user=user,
            name=recipe_name,
            rule=rule
        )

        if ingredient_id and quantity:
            ingredient = Inventory.objects.get(id=ingredient_id)
            veg_recipe.ingredient1 = ingredient
            veg_recipe.qty1 = quantity
        veg_recipe.save()

        return JsonResponse({'success': True})
    else:
        return JsonResponse({'error': 'Method not allowed'}, status=405)

@login_required
def create_wg_recipe(request):
    if request.method == 'POST':
        recipe_name = request.POST.get('wgName')
        ingredient_id = request.POST.get('wgMainIngredient1')
        quantity = request.POST.get('wgQtyMainIngredient1')
        rule_id = request.POST.get('wgRule')

        if not recipe_name:
            return JsonResponse({'error': 'Recipe name is required'}, status=400)
        if not ingredient_id:
            return JsonResponse({'error': 'Main ingredient is required'}, status=400)
        if not quantity:
            return JsonResponse({'error': 'Quantity is required'}, status=400)
        if not rule_id:
            return JsonResponse({'error': 'Rule is required'}, status=400)

        user = request.user
        rule = Rule.objects.get(id=rule_id) if rule_id else None

        wg_recipe = WgRecipe.objects.create(
            user=user,
            name=recipe_name,
            rule=rule
        )

        if ingredient_id and quantity:
            ingredient = Inventory.objects.get(id=ingredient_id)
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

        # Get the authenticated user
        user = request.user

        rule = Rule.objects.get(id=rule_id) if rule_id else None
        # Create breakfast recipe instance
        breakfast_recipe = BreakfastRecipe.objects.create(user=user, name=recipe_name, instructions=instructions, addfood=additional_food, rule=rule)

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

        # Get the authenticated user
        user = request.user

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
        # Get the authenticated user
        user = request.user
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
    # Retrieve all recipes from the database
    recipes = Recipe.objects.filter(user=request.user).values('id', 'name')  
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
    veg_recipes = VegRecipe.objects.filter(user=request.user).values('id', 'name')
    return JsonResponse({'recipes': list(veg_recipes)})

@login_required
def fetch_wg_recipes(request):
    wg_recipes = WgRecipe.objects.filter(user=request.user).values('id', 'name')
    return JsonResponse({'recipes': list(wg_recipes)})

def fetch_fruit_recipes(request):
    fruit_recipes = FruitRecipe.objects.filter(user=request.user).values('id', 'name')
    return JsonResponse({'recipes': list(fruit_recipes)})

def fetch_breakfast_recipes(request):
    # Fetch breakfast recipes for the current user from the database
    breakfast_recipes = BreakfastRecipe.objects.filter(user=request.user).values('id', 'name')
    return JsonResponse({'recipes': list(breakfast_recipes)})

def fetch_am_recipes(request):
    # Retrieve all AM recipes for the authenticated user from the database
    am_recipes = AMRecipe.objects.filter(user=request.user).values('id', 'name')  
    return JsonResponse({'am_recipes': list(am_recipes)})

def fetch_pm_recipes(request):
    # Retrieve all AM recipes for the authenticated user from the database
    am_recipes = PMRecipe.objects.filter(user=request.user).values('id', 'name')  
    return JsonResponse({'pm_recipes': list(am_recipes)})

def get_filtered_recipes(user, model, recent_days=14):
    """Filter recipes not used in the last `recent_days` days."""
    all_recipes = list(model.objects.filter(user=user))
    cutoff_date = timezone.now() - timedelta(days=recent_days)
    recent_recipes = model.objects.filter(user=user, last_used__gte=cutoff_date)
    return [recipe for recipe in all_recipes if recipe not in recent_recipes]

def check_ingredients_availability(recipe, user):
    """Check if all ingredients in a recipe are available in sufficient quantities."""
    for i in range(1, 6):
        ingredient_id = getattr(recipe, f"ingredient{i}_id")
        qty = getattr(recipe, f"qty{i}")
        if ingredient_id and qty:
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

            # Check if any of the dates have existing menu entries
            exists = WeeklyMenu.objects.filter(date__in=dates_to_check, user=request.user).exists()

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

            # Loop through each day to save menu data
            for day_key, day_abbr in days_of_week.items():
                day_data = data.get(day_key, {})

                # Create or update the WeeklyMenu for each day
                WeeklyMenu.objects.update_or_create(
                    user=request.user,
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
            OrderList.objects.create(user=request.user, item=item, quantity=quantity, category=category)
            return redirect('order_list')
        else:
            return HttpResponseBadRequest('Invalid form submission')
    else:
        order_items = OrderList.objects.filter(user=request.user)
        return render(request, 'index.html', {'order_items': order_items})



@login_required
def shopping_list_api(request):
    if request.method == 'GET':
        shopping_list_items = OrderList.objects.filter(user=request.user)
        serialized_items = [{'name': item.item} for item in shopping_list_items]
        return JsonResponse(serialized_items, safe=False)
    else:
        return HttpResponseNotAllowed(['GET'])

def update_orders(request):
    if request.method == 'POST':
        item_ids = request.POST.getlist('items')
        try:
            for item_id in item_ids:
                order_item = get_object_or_404(OrderList, id=item_id, user=request.user)
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
    if request.method == 'POST':
        code = request.POST['code']
        student = Student.objects.get(code=code)
        user = request.user  # Get the current user

        record, created = AttendanceRecord.objects.get_or_create(student=student, sign_out_time=None)
        record.sign_in_time = timezone.now()
        record.user = user  # Assign the current user to the attendance record
        record.save()

        return redirect('home')
    
    return render(request, 'sign_in.html')

@login_required
def process_code(request):
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            code = data.get('code')
            user_id = data.get('user_id')  # Retrieve user_id from the request
            if code and user_id:
                timestamp = timezone.now()

                # Retrieve student from the database using the code
                student = Student.objects.get(code=code)

                # Retrieve user from the database using the user_id
                user = User.objects.get(id=user_id)

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
                return JsonResponse({'success': False, 'message': 'Code and user ID are required.'})
        except Student.DoesNotExist:
            return JsonResponse({'success': False, 'message': 'Invalid code. Please try again.'})
        except User.DoesNotExist:
            return JsonResponse({'success': False, 'message': 'Invalid user ID. Please try again.'})
        except Exception as e:
            return JsonResponse({'success': False, 'message': str(e)})

    return JsonResponse({'success': False, 'message': 'Invalid request method'})

@login_required
def daily_attendance(request):
    # Get today's date
    today = date.today()

    # Retrieve attendance records for today
    attendance_records = AttendanceRecord.objects.filter(sign_in_time__date=today)

    return render(request, 'daily_attendance.html', {'attendance_records': attendance_records})

@login_required
def rosters(request):
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

        # Get the current user (assuming the user is logged in)
        user = request.user

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

def classroom_options(request):
    classrooms = Classroom.objects.filter(user=request.user)
    for classroom in classrooms:
        classroom.students = Student.objects.filter(classroom=classroom)
    return render(request, 'classroom_options.html', {'classrooms': classrooms})

@login_required 
def add_classroom(request):
    if request.method == 'POST':
        classroom_name = request.POST.get('className')
        user = request.user  # Get the current user

        if classroom_name:
            new_classroom = Classroom(name=classroom_name, user=user)  # Assign the user to the classroom
            new_classroom.save()
            return JsonResponse({'success': True})
    
    return JsonResponse({'success': False})

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
    
def milk_count(request):
    current_date = datetime.now()
    current_year = current_date.year
    current_month = current_date.month
    
    # Get the selected month and year from the request.GET dictionary
    selected_month = int(request.GET.get('month', current_month))
    selected_year = int(request.GET.get('year', current_year))
    
    # Prepare data for rendering in template
    # Add your milk count related logic here
    
    # Prepare a list of months and years for the template
    months = [
        {'month': i, 'name': datetime.strptime(str(i), "%m").strftime("%B")}
        for i in range(1, 13)
    ]
    years = list(range(2020, 2031))
    
    context = {
        # Add your milk count related context data here
        'months': months,
        'years': years,
        'selected_month': selected_month,
        'selected_year': selected_year,
        # Add other context variables as needed
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

        # Create a new MilkCount entry for the current update
        milk_count = MilkCount.objects.create(
            inventory_item=inventory_item,
            timestamp=now,
            current_qty=inventory_item.quantity,  # Set the current quantity
            received_qty=int(extra_milk_quantity) if extra_milk_quantity else 0,  # Set received quantity
            user=request.user  # Assuming you have user authentication
        )

        return JsonResponse({'success': True})
    else:
        return JsonResponse({'success': False, 'error': 'Invalid request'})

def milk_count_view(request):
    # Get distinct months and years from the MilkCount entries
    months = MilkCount.objects.dates('timestamp', 'month')
    years = MilkCount.objects.dates('timestamp', 'year')

    # Retrieve selected month and year from the request GET parameters
    selected_month = request.GET.get('month')
    selected_year = request.GET.get('year')

    # If both month and year are provided, filter MilkCount objects based on them
    if selected_month and selected_year:
        # Get the current timezone
        tz = timezone.get_current_timezone()

        # Convert selected month and year to datetime object with the current timezone
        start_date = datetime(int(selected_year), int(selected_month), 1, tzinfo=tz)
        end_date = start_date.replace(day=1, month=start_date.month % 12 + 1)

        # Filter MilkCount objects for the selected month and year
        milk_counts = MilkCount.objects.filter(timestamp__gte=start_date, timestamp__lt=end_date)

        # Get the first entry for each unique inventory_item_id within the selected month
        first_entries = milk_counts.values('inventory_item').annotate(
            min_timestamp=Min('timestamp')
        ).values_list('min_timestamp', flat=True)

        # Calculate the sum of current_qty for the first entries
        beginning_inventory_count = MilkCount.objects.filter(timestamp__in=first_entries).aggregate(
            beginning_inventory_qty=Sum('current_qty')
        )['beginning_inventory_qty'] or 0

        # Get the last entry for each unique inventory_item_id within the selected month
        last_entries = milk_counts.values('inventory_item').annotate(
            max_timestamp=Max('timestamp')
        ).values_list('max_timestamp', flat=True)

        # Calculate the sum of current_qty for the last entries
        end_of_month_inventory = MilkCount.objects.filter(timestamp__in=last_entries).aggregate(
            end_of_month_qty=Sum('current_qty')
        )['end_of_month_qty'] or 0

        # Calculate the total received quantity (received_qty)
        total_received_qty = milk_counts.aggregate(total_qty=Sum('received_qty'))['total_qty'] or 0

        # Calculate the total available quantity
        total_available_qty = beginning_inventory_count + total_received_qty

        # Calculate the total used during the month
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
            'selected_year': selected_year
        }
    else:
        # If month or year is not provided, return an empty context
        context = {
            'months': months,
            'years': years
        }

    return render(request, 'milk_count.html', context)

def meal_count(request):

     # Get distinct months and years from the MilkCount entries
    months = MilkCount.objects.dates('timestamp', 'month', order='DESC')
    years = MilkCount.objects.dates('timestamp', 'year', order='DESC')
    
    # Retrieve selected month and year from the request GET parameters
    selected_month = request.GET.get('month')
    selected_year = request.GET.get('year')

    # If both month and year are provided, filter AttendanceRecord objects based on them
    if selected_month and selected_year:
        # Get the current timezone
        tz = timezone.get_current_timezone()

        # Convert selected month and year to datetime object with the current timezone
        start_date = datetime(int(selected_year), int(selected_month), 1, tzinfo=tz)
        end_date = start_date.replace(day=1, month=start_date.month % 12 + 1)

        # Filter AttendanceRecord objects for the selected month and year
        attendance_records = AttendanceRecord.objects.filter(sign_in_time__gte=start_date, sign_in_time__lt=end_date)
    else:
        attendance_records = AttendanceRecord.objects.all()

    # Initialize counts for each time slot
    am_count = 0
    lunch_count = 0
    pm_count = 0

    # Define time ranges in EST (hour, minute, hour, minute)
    am_range = (4, 0, 9, 0)  # 4:00 AM - 9:00 AM EST
    lunch_range = (10, 30, 12, 30)  # 10:30 AM - 12:30 PM EST
    pm_range = (13, 0, 17, 0)  # 1:00 PM - 5:00 PM EST

    # Get timezone object for US Eastern Time
    eastern = pytz.timezone('US/Eastern')

    # Helper function to check if any part of the attendance record overlaps with a given time range
    def overlaps(time_range, sign_in_time, sign_out_time):
        start_hour, start_minute, end_hour, end_minute = time_range
        start_time = timezone.make_aware(timezone.datetime(2000, 1, 1, start_hour, start_minute), eastern).time()
        end_time = timezone.make_aware(timezone.datetime(2000, 1, 1, end_hour, end_minute), eastern).time()
        return (sign_in_time.time() < end_time and sign_out_time.time() > start_time)

    # Iterate through attendance records
    for record in attendance_records:
        # Convert sign-in and sign-out times to EST
        sign_in_time_est = record.sign_in_time.astimezone(eastern)
        sign_out_time_est = record.sign_out_time.astimezone(eastern) if record.sign_out_time else sign_in_time_est

        # Check if any part of the attendance record overlaps with the AM, lunch, and PM time ranges
        if overlaps(am_range, sign_in_time_est, sign_out_time_est):
            am_count += 1
           
        if overlaps(lunch_range, sign_in_time_est, sign_out_time_est):
            lunch_count += 1
            
        if overlaps(pm_range, sign_in_time_est, sign_out_time_est):
            pm_count += 1
            

    # Render your HTML template with counts as context
    return render(request, 'meal_count.html', {'am_count': am_count, 'lunch_count': lunch_count, 'pm_count': pm_count, 'months':months, 'years': years, 'selected_month':selected_month, 'selected_year': selected_year})


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



def generate_menu(request):
    user = request.user
    recipes = get_filtered_recipes(user, Recipe)
    menu_data = select_meals_for_days(recipes, user)
    return JsonResponse(menu_data)

def generate_snack_menu(request, model, fluid_key, fruit_key, bread_key, meat_key):
    user = request.user
    snack_data = {}
    days_of_week = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]
    recipes = list(model.objects.filter(user=user))

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

    return JsonResponse(snack_data)

def generate_am_menu(request):
    return generate_snack_menu(request, AMRecipe, 'choose1', 'fruit2', 'bread2', 'meat1')

def generate_pm_menu(request):
    return generate_snack_menu(request, PMRecipe, 'choose2', 'fruit4', 'bread3', 'meat3')

def generate_breakfast_menu(request):
    user = request.user
    breakfast_data = {}
    days_of_week = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]
    recipes = list(BreakfastRecipe.objects.filter(user=user))

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

    return JsonResponse(breakfast_data)

def generate_fruit_menu(request):
    fruit_menu_data = {}
    days_of_week = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]
    
    # Retrieve available fruits for the entire week
    all_fruits = list(
        Inventory.objects.filter(
            user=request.user,
            category="Fruits",
            total_quantity__gt=0
        ).values_list('item', flat=True)
    )
    
    # Retrieve available fruits with quantity > 0
    fruits_with_quantity = list(
        Inventory.objects.filter(
            user=request.user,
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

def generate_vegetable_menu(request):
    user = request.user
    vegetable_menu_data = {}
    days_of_week = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]

    # Retrieve available vegetables based on total_quantity
    all_vegetables = list(Inventory.objects.filter(
        user=user,
        category="Vegetables",
        total_quantity__gt=0
    ).values_list('item', flat=True))

    # Retrieve vegetables with quantity > 0
    vegetables_with_quantity = list(Inventory.objects.filter(
        user=user,
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


def past_menus(request):
    # Fetch all unique Monday dates from the WeeklyMenu model, ordered by date in descending order
    monday_dates = WeeklyMenu.objects.filter(day_of_week='Mon').values_list('date', flat=True).distinct().order_by('-date')

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

            # Fetch WeeklyMenu entries within the selected range, sorted by date
            selected_menu_data = WeeklyMenu.objects.filter(date__range=[start_date, end_date]).order_by('date')

        # Handle form submission to save menu changes
        # Assuming each menu entry has a unique identifier
        if 'save_changes' in request.POST:
            for i, menu in enumerate(selected_menu_data):
                
                # Retrieve input values from the form for the current menu entry
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
                
                # Save the updated menu entry
                menu.save()

            # Redirect to the same page to refresh the data
            return redirect('past_menus')  # Make sure this name matches your URL pattern

    # Pass the date ranges, selected menu data, and selected range to the template
    context = {
        'date_ranges': date_ranges,
        'selected_menu_data': selected_menu_data,
        'selected_range': selected_range  # Add this line
    }

    return render(request, 'past-menus.html', context)