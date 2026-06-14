"""
Tests for the orders app: stock and balance correctness.

These tests pin down the intended behavior of the core money/stock flows:
  - withdrawing batteries (creating an Order) decrements stock exactly once,
  - the customer's owed balance reflects order total + scrap (supplement),
  - payments reduce what is owed,
  - editing an order cleanly restocks and re-balances,
  - and a handful of small bugs (crashing __str__, broken search) stay fixed.

Run with:  .venv/Scripts/python.exe manage.py test apps.orders
"""
import uuid
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from apps.orders.models import Order, OrderItem, BalanceNote, LedgerEntry
from apps.products.models import Brand, Product

User = get_user_model()


class OrdersBaseTestCase(TestCase):
    def setUp(self):
        # A staff member who operates the app.
        self.staff = User.objects.create_user(
            username="staff", password="pw", is_staff=True
        )
        # A customer (one of the stores is modeled as a customer too).
        self.customer = User.objects.create(first_name="متجر رقم واحد")
        self.brand = Brand.objects.create(name="Bosch")
        self.product = Product.objects.create(
            name="battery-100", brand=self.brand, price=Decimal("100.00"), stock=10
        )
        self.client = APIClient()
        self.client.force_authenticate(self.staff)

    def _order_payload(self, quantity=3, supplement="50"):
        return {
            "user": self.customer.id,
            "supplement": supplement,
            "order_items": [{"product": self.product.id, "quantity": quantity}],
        }

    def _balance(self):
        self.customer.userbalance.refresh_from_db()
        return self.customer.userbalance


class OrderCreationTests(OrdersBaseTestCase):
    def test_creation_decrements_stock_exactly_once(self):
        resp = self.client.post("/api/orders/", self._order_payload(quantity=3), format="json")
        self.assertEqual(resp.status_code, 201, resp.content)

        self.product.refresh_from_db()
        self.assertEqual(self.product.stock, 7)  # 10 - 3, not 10 - 6

    def test_creation_sets_owed_balance_to_total_plus_scrap(self):
        resp = self.client.post(
            "/api/orders/", self._order_payload(quantity=3, supplement="50"), format="json"
        )
        self.assertEqual(resp.status_code, 201, resp.content)

        balance = self._balance()
        # 3 * 100 = 300 goods + 50 scrap = 350 owed
        self.assertEqual(balance.orders_total, Decimal("350.00"))
        self.assertEqual(balance.amount_to_pay(), Decimal("350.00"))

    def test_insufficient_stock_returns_400_and_changes_nothing(self):
        resp = self.client.post(
            "/api/orders/", self._order_payload(quantity=999), format="json"
        )
        self.assertEqual(resp.status_code, 400, resp.content)

        self.product.refresh_from_db()
        self.assertEqual(self.product.stock, 10)  # untouched
        self.assertEqual(Order.objects.count(), 0)
        self.assertEqual(self._balance().orders_total, Decimal("0"))


class OrderItemModelTests(OrdersBaseTestCase):
    def test_resaving_item_does_not_re_decrement_stock(self):
        self.client.post("/api/orders/", self._order_payload(quantity=3), format="json")
        self.product.refresh_from_db()
        stock_after_create = self.product.stock

        item = OrderItem.objects.first()
        item.save()  # a second save must NOT touch stock again

        self.product.refresh_from_db()
        self.assertEqual(self.product.stock, stock_after_create)

    def test_item_total_and_fixed_price_are_computed(self):
        self.client.post("/api/orders/", self._order_payload(quantity=4), format="json")
        item = OrderItem.objects.first()
        self.assertEqual(item.total, Decimal("400.00"))
        self.assertEqual(item.fixed_price, Decimal("100.00"))


class PaymentTests(OrdersBaseTestCase):
    def test_payment_reduces_amount_owed_and_records_note(self):
        self.client.post(
            "/api/orders/", self._order_payload(quantity=3, supplement="50"), format="json"
        )
        balance = self._balance()  # owes 350

        resp = self.client.post(
            f"/api/user-balance/{balance.id}/deposit/",
            {"amount": "100", "balance_type": "paid_amount", "note": "دفعة أولى"},
            format="json",
        )
        self.assertEqual(resp.status_code, 200, resp.content)

        balance = self._balance()
        self.assertEqual(balance.paid_amount, Decimal("100.00"))
        self.assertEqual(balance.amount_to_pay(), Decimal("250.00"))
        self.assertEqual(BalanceNote.objects.filter(user=self.customer).count(), 1)

    def test_balance_note_str_does_not_crash(self):
        note = BalanceNote.objects.create(
            user=self.customer, note="ملاحظة", amount=Decimal("100.00")
        )
        # __str__ used to reference a non-existent attribute and raise.
        self.assertIn("100", str(note))


class OrderEditTests(OrdersBaseTestCase):
    def test_edit_restocks_and_rebalances(self):
        create = self.client.post(
            "/api/orders/", self._order_payload(quantity=3, supplement="0"), format="json"
        )
        order_id = create.json()["id"]
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock, 7)
        self.assertEqual(self._balance().orders_total, Decimal("300.00"))

        # Change the same order to 5 units instead of 3.
        edit_payload = {
            "user": self.customer.id,
            "supplement": "0",
            "order_items": [{"product": self.product.id, "quantity": 5}],
        }
        resp = self.client.put(
            f"/api/orders/{order_id}/", edit_payload, format="json"
        )
        self.assertEqual(resp.status_code, 200, resp.content)

        self.product.refresh_from_db()
        self.assertEqual(self.product.stock, 5)  # back to 10, then -5
        self.assertEqual(self._balance().orders_total, Decimal("500.00"))


class OrderApiRobustnessTests(OrdersBaseTestCase):
    def test_search_query_does_not_crash(self):
        resp = self.client.get("/api/orders/?search=anything")
        self.assertEqual(resp.status_code, 200, resp.content)

    def test_analytics_returns_expected_totals(self):
        self.client.post(
            "/api/orders/", self._order_payload(quantity=3, supplement="50"), format="json"
        )
        resp = self.client.get("/api/orders-analytics/")
        self.assertEqual(resp.status_code, 200, resp.content)

        today = resp.json()["today"]
        self.assertEqual(Decimal(str(today["products_total"])), Decimal("300"))
        self.assertEqual(Decimal(str(today["supplements_total"])), Decimal("50"))
        self.assertEqual(Decimal(str(today["amount_to_pay_total"])), Decimal("350"))
        self.assertEqual(today["products_count"], 3)


class LedgerTests(OrdersBaseTestCase):
    def test_order_writes_a_ledger_entry(self):
        self.client.post(
            "/api/orders/", self._order_payload(quantity=3, supplement="50"), format="json"
        )
        entry = LedgerEntry.objects.get(user=self.customer, kind=LedgerEntry.Kind.ORDER)
        self.assertEqual(entry.field, "orders_total")
        self.assertEqual(entry.amount, Decimal("350.00"))

    def test_recompute_from_ledger_matches_cached_balance(self):
        self.client.post(
            "/api/orders/", self._order_payload(quantity=3, supplement="50"), format="json"
        )
        balance = self._balance()
        self.client.post(
            f"/api/user-balance/{balance.id}/deposit/",
            {"amount": "120", "balance_type": "paid_amount"},
            format="json",
        )
        balance = self._balance()

        rebuilt = balance.recompute_from_ledger()
        self.assertEqual(rebuilt["orders_total"], balance.orders_total)
        self.assertEqual(rebuilt["paid_amount"], balance.paid_amount)


class IdempotencyTests(OrdersBaseTestCase):
    def test_replayed_order_uuid_charges_once(self):
        payload = self._order_payload(quantity=3, supplement="50")
        payload["client_uuid"] = str(uuid.uuid4())

        first = self.client.post("/api/orders/", payload, format="json")
        self.assertEqual(first.status_code, 201, first.content)

        # Same request again (as an offline replay would send).
        second = self.client.post("/api/orders/", payload, format="json")
        self.assertIn(second.status_code, (200, 201), second.content)

        self.assertEqual(Order.objects.count(), 1)
        self.assertEqual(first.json()["id"], second.json()["id"])
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock, 7)  # decremented once, not twice
        self.assertEqual(self._balance().orders_total, Decimal("350.00"))

    def test_replayed_payment_uuid_applies_once(self):
        self.client.post(
            "/api/orders/", self._order_payload(quantity=3, supplement="50"), format="json"
        )
        balance = self._balance()
        key = str(uuid.uuid4())
        body = {"amount": "100", "balance_type": "paid_amount", "client_uuid": key}

        first = self.client.post(f"/api/user-balance/{balance.id}/deposit/", body, format="json")
        self.assertEqual(first.status_code, 200, first.content)
        second = self.client.post(f"/api/user-balance/{balance.id}/deposit/", body, format="json")
        self.assertEqual(second.status_code, 200, second.content)

        balance = self._balance()
        self.assertEqual(balance.paid_amount, Decimal("100.00"))  # applied once
        self.assertEqual(
            LedgerEntry.objects.filter(user=self.customer, kind=LedgerEntry.Kind.PAYMENT).count(),
            1,
        )
