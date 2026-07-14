from decimal import Decimal

from django.db import migrations


def backfill(apps, schema_editor):
    """Reconstruct each invoice's frozen 'previous balance due' by replaying the
    ledger in order: for every invoice (ORDER) entry, the customer's outstanding
    balance just before it is the snapshot we store on that order.
    """
    Order = apps.get_model("orders", "Order")
    LedgerEntry = apps.get_model("orders", "LedgerEntry")
    CustomUser = apps.get_model("users", "CustomUser")

    for user in CustomUser.objects.all():
        orders_total = Decimal("0")
        paid_amount = Decimal("0")
        for e in LedgerEntry.objects.filter(user=user).order_by("id"):
            due_before = orders_total - paid_amount
            if e.field == "orders_total":
                if e.kind == "order" and e.order_id:
                    # Last write wins (handles edited invoices re-issued later).
                    Order.objects.filter(pk=e.order_id).update(prev_balance_due=due_before)
                orders_total += e.amount
            elif e.field == "paid_amount":
                paid_amount += e.amount


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):
    dependencies = [
        ("orders", "0015_order_prev_balance_due"),
    ]
    operations = [
        migrations.RunPython(backfill, noop),
    ]
