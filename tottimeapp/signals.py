from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from .models import OrderList, Inventory, Payment, SubUser
from django.db.models import Sum
from django.db import transaction
import logging

logger = logging.getLogger(__name__)

@receiver(post_save, sender=OrderList)
@receiver(post_delete, sender=OrderList)
def update_inventory_on_order_change(sender, instance, **kwargs):
    try:
        user_id = instance.user.id
        item = instance.item

        with transaction.atomic():
            # Recalculate the total quantity
            total_order_quantity = OrderList.objects.filter(user=user_id, item=item).aggregate(Sum('quantity'))['quantity__sum'] or 0
            inventory_item, created = Inventory.objects.get_or_create(user=user_id, item=item)

            # Update total_quantity
            inventory_item.total_quantity = inventory_item.quantity + total_order_quantity
            inventory_item.save()

    except Exception as e:
        logger.error(f"Error updating inventory on order change: {e}")

@receiver(post_save, sender=Inventory)
@receiver(post_delete, sender=Inventory)
def update_total_quantity_on_inventory_change(sender, instance, **kwargs):
    try:
        user = instance.user
        item = instance.item

        with transaction.atomic():
            # Calculate the new total quantity
            total_order_quantity = OrderList.objects.filter(user=user, item=item).aggregate(Sum('quantity'))['quantity__sum'] or 0
            inventory_items = Inventory.objects.filter(user=user, item=item)

            total_quantity = sum(inv.quantity for inv in inventory_items) + total_order_quantity

            # Update total_quantity for all inventory items
            for inv_item in inventory_items:
                if inv_item.total_quantity != total_quantity:  # Only update if necessary
                    inv_item.total_quantity = total_quantity
                    inv_item.save()

    except Exception as e:
        logger.error(f"Error updating total quantity on inventory change: {e}")

# Signal to update SubUser balance when a Payment is saved
@receiver(post_save, sender=Payment)
def update_subuser_balance_on_save(sender, instance, **kwargs):
    subuser = instance.subuser
    # Calculate the total balance of all payments linked to this SubUser
    total_balance = subuser.payments.aggregate(total=Sum('balance'))['total'] or 0
    subuser.balance = total_balance
    subuser.save()

# Signal to update SubUser balance when a Payment is deleted
@receiver(post_delete, sender=Payment)
def update_subuser_balance_on_delete(sender, instance, **kwargs):
    subuser = instance.subuser
    # Calculate the total balance of all payments linked to this SubUser
    total_balance = subuser.payments.aggregate(total=Sum('balance'))['total'] or 0
    subuser.balance = total_balance
    subuser.save()

@receiver(post_save, sender=Payment)
def create_recurring_payments(sender, instance, created, **kwargs):
    if created:  # Only process if the payment is newly created
        # Disconnect the signal temporarily to prevent recursion
        post_save.disconnect(create_recurring_payments, sender=Payment)
        
        try:
            instance.create_recurring_payments()  # Call the method to create recurring payments
        finally:
            # Reconnect the signal after processing
            post_save.connect(create_recurring_payments, sender=Payment)