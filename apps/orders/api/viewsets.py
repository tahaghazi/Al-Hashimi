from datetime import datetime, time, timedelta

from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import F, Sum
from django.db.models.functions import TruncDay, TruncHour, TruncMonth
from django.utils import timezone
import django_filters
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import filters, serializers, viewsets
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.generics import get_object_or_404
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.orders.api.serializers import OrderSerializer, UserBalanceSerializer, UserBalanceDepositSerializer, \
    UserBalanceNoteSerializer
from apps.orders.models import Order, UserBalance, OrderItem, BalanceNote, LedgerEntry
from apps.products.models import Product
from apps.users.audit import AuditMixin, log_action
from apps.users.models import AuditLog


class OrderFilter(django_filters.FilterSet):
    # Inclusive date-range filter on the order date (e.g. the all-bills page).
    start = django_filters.DateFilter(field_name="created_at", lookup_expr="date__gte")
    end = django_filters.DateFilter(field_name="created_at", lookup_expr="date__lte")

    class Meta:
        model = Order
        fields = ["user", "order_items__product", "start", "end"]


class OrderViewSet(AuditMixin, viewsets.ModelViewSet):
    audit_entity = "Order"
    # select_related/prefetch_related collapse what used to be an N+1 storm:
    # the serializer touches user, balance, items, products and brands per order.
    queryset = (
        Order.objects
        .select_related("user", "user__userbalance")
        .prefetch_related("order_items__product__brand")
    )
    serializer_class = OrderSerializer
    filter_backends = [filters.SearchFilter, filters.OrderingFilter, DjangoFilterBackend, ]
    # Order has no name/description; search by the customer's name instead.
    search_fields = ["user__first_name"]
    filterset_class = OrderFilter

    def update(self, request, *args, **kwargs):
        """Edit an order IN PLACE (id stays stable), keeping a full revision
        history. Editing is allowed indefinitely; every edit snapshots the
        previous state into an OrderRevision so nothing is ever lost."""
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        try:
            self._apply_edit(request, instance, serializer.validated_data,
                             reason=request.data.get("reason", ""))
        except serializers.ValidationError:
            raise
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

        instance.refresh_from_db()
        data = self.get_serializer(instance).data
        log_action(request, AuditLog.Action.UPDATE, entity="Order", object_id=instance.id,
                   object_repr=f"Order #{instance.id}",
                   after={"amount_to_pay": str(data.get("amount_to_pay"))})
        return Response(data, status=status.HTTP_200_OK)

    def _apply_edit(self, request, instance, validated_data, reason=""):
        """Snapshot a revision, reverse the order's current effects, then apply
        the new items/scrap/discount — all atomic."""
        from apps.orders.models import OrderRevision, order_snapshot
        actor = request.user if getattr(request.user, "is_authenticated", False) else None
        with transaction.atomic():
            OrderRevision.objects.create(
                order=instance, snapshot=order_snapshot(instance), editor=actor,
                editor_username=getattr(actor, "username", "") or "", reason=reason[:200],
            )
            # reverse old effects
            instance.user.userbalance.deposit(
                -instance.amount_to_pay(), "orders_total",
                kind=LedgerEntry.Kind.ORDER_REVERSAL, note=f"تعديل الطلب #{instance.id}",
            )
            for item in instance.order_items.all():
                Product.objects.filter(pk=item.product_id).update(stock=F("stock") + item.quantity)
            instance.order_items.all().delete()

            # apply new items
            items_data = validated_data.get("order_items", [])
            if "supplement" in validated_data:
                instance.supplement = validated_data["supplement"]
            if "discount" in validated_data:
                instance.discount = validated_data["discount"]
            if "discount_note" in validated_data:
                instance.discount_note = validated_data["discount_note"]
            new_items = []
            for item_data in items_data:
                product = item_data["product"]
                qty = item_data["quantity"]
                locked = Product.objects.select_for_update().get(pk=product.pk)
                if qty > locked.stock:
                    raise serializers.ValidationError(
                        {"order_items": f"المخزون غير كافٍ للمنتج {locked}. المتاح: {locked.stock}"})
                locked.stock -= qty
                locked.save(update_fields=["stock"])
                new_items.append(OrderItem.objects.create(**item_data))
            instance.order_items.set(new_items)
            instance.recalculate_total()
            if instance.amount_to_pay() <= 0:
                raise serializers.ValidationError(
                    {"discount": "المبلغ النهائي للفاتورة يجب أن يكون أكبر من صفر"})
            instance.user.userbalance.deposit(
                instance.amount_to_pay(), "orders_total", kind=LedgerEntry.Kind.ORDER, order=instance)
            instance.save()

    @action(detail=True, methods=["get"])
    def revisions(self, request, pk=None):
        from apps.orders.api.serializers import OrderRevisionSerializer
        order = self.get_object()
        return Response(OrderRevisionSerializer(order.revisions.all(), many=True).data)

    @action(detail=True, methods=["post"], url_path="rollback/(?P<rev_id>[0-9]+)")
    def rollback(self, request, pk=None, rev_id=None):
        from apps.orders.models import OrderRevision
        order = self.get_object()
        rev = get_object_or_404(OrderRevision, pk=rev_id, order=order)
        snap = rev.snapshot
        # Re-apply the snapshot's items/scrap/discount as a fresh edit.
        data = {
            "user": order.user_id,
            "supplement": snap.get("supplement", 0),
            "discount": snap.get("discount", 0),
            "discount_note": snap.get("discount_note", ""),
            "order_items": [{"product": it["product"], "quantity": it["quantity"]}
                            for it in snap.get("items", [])],
        }
        serializer = self.get_serializer(order, data=data, partial=True)
        serializer.is_valid(raise_exception=True)
        try:
            self._apply_edit(request, order, serializer.validated_data,
                             reason=f"استرجاع نسخة #{rev_id}")
        except serializers.ValidationError:
            raise
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        order.refresh_from_db()
        return Response(self.get_serializer(order).data, status=status.HTTP_200_OK)




class UserBalanceViewSet(viewsets.ModelViewSet):
    serializer_class = UserBalanceSerializer
    filter_backends = [DjangoFilterBackend, filters.SearchFilter]
    filterset_fields = ['user__id']
    def get_queryset(self):
        # Users can only see their own balance
        return UserBalance.objects.all()

    @action(detail=True, methods=['post'], serializer_class=UserBalanceDepositSerializer)
    def deposit(self, request, pk=None):
        user_balance = get_object_or_404(UserBalance, pk=pk)
        serializer = self.get_serializer(data=request.data)

        if serializer.is_valid():
            amount = serializer.validated_data['amount']
            balance_type = serializer.validated_data['balance_type']
            note = serializer.validated_data.get('note')
            source = serializer.validated_data.get('source', '')
            client_uuid = serializer.validated_data.get('client_uuid')

            # Idempotency: a replayed offline payment (same client_uuid) must be
            # applied at most once — acknowledge it without re-charging.
            if client_uuid and LedgerEntry.objects.filter(client_uuid=client_uuid).exists():
                return Response({
                    'status': 'success',
                    'message': 'already processed',
                    'balance': UserBalanceSerializer(user_balance).data,
                })

            try:
                with transaction.atomic():
                    user_balance.deposit(
                        amount, balance_type,
                        kind=LedgerEntry.Kind.PAYMENT, note=note or "", client_uuid=client_uuid,
                    )
                    user_balance.refresh_from_db()
                    BalanceNote.objects.create(user=user_balance.user, amount=amount, note=note or "", source=source)
                log_action(request, AuditLog.Action.PAYMENT, entity="Payment",
                           object_id=user_balance.user_id,
                           object_repr=f"{amount} ({source or '-'}) -> {user_balance.user}",
                           after={"amount": str(amount), "source": source, "balance": balance_type})
                return Response({
                    'status': 'success',
                    'message': f'{amount} deposited to {balance_type} successfully',
                    'balance': UserBalanceSerializer(user_balance).data
                })
            except Exception as e:
                return Response({
                    'status': 'error',
                    'message': str(e)
                }, status=status.HTTP_400_BAD_REQUEST)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class UserBalanceNoteViewSet(viewsets.ModelViewSet):
    serializer_class = UserBalanceNoteSerializer
    filter_backends = [DjangoFilterBackend, filters.SearchFilter]
    filterset_fields = ['user__id']

    def get_queryset(self):
        # Users can only see their own balance
        return BalanceNote.objects.all()

MONTHS_AR = ["يناير", "فبراير", "مارس", "أبريل", "مايو", "يونيو",
             "يوليو", "أغسطس", "سبتمبر", "أكتوبر", "نوفمبر", "ديسمبر"]


class OrderAnalyticsView(APIView):
    """
    Order analytics.

    - No params: legacy response { today, this_month, this_year } used by the
      home dashboard.
    - ?period=day|week|month|year  OR  ?start=YYYY-MM-DD&end=YYYY-MM-DD :
      returns { period, start, end, totals, series } where `series` is a
      time-bucketed breakdown for charting.
    """

    def get(self, request, *args, **kwargs):
        now = timezone.localtime(timezone.now())
        self.tz = timezone.get_current_timezone()
        today = now.date()
        User = get_user_model()

        period = request.GET.get("period")
        start_param = request.GET.get("start")
        end_param = request.GET.get("end")

        # ---- legacy mode (home dashboard) ----
        if not period and not start_param:
            ts, te = self._day_bounds(today, today)
            ms, me = self._day_bounds(today.replace(day=1), today)
            ys, ye = self._day_bounds(today.replace(month=1, day=1), today)
            return Response({
                "today": self._calculate_analytics(ts, te, User),
                "this_month": self._calculate_analytics(ms, me, User),
                "this_year": self._calculate_analytics(ys, ye, User),
            })

        # ---- filtered range mode ----
        try:
            start_dt, end_dt, gran = self._resolve_range(period, start_param, end_param, today)
        except ValueError as exc:
            return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        return Response({
            "period": period or "custom",
            "start": start_dt.date().isoformat(),
            "end": end_dt.date().isoformat(),
            "granularity": gran,
            "totals": self._calculate_analytics(start_dt, end_dt, User),
            "series": self._series(start_dt, end_dt, gran),
        })

    # ---------------- helpers ----------------
    def _aware(self, dt):
        return timezone.make_aware(dt, self.tz)

    def _day_bounds(self, start_date, end_date):
        return (self._aware(datetime.combine(start_date, time.min)),
                self._aware(datetime.combine(end_date, time.max)))

    def _resolve_range(self, period, start_param, end_param, today):
        if period == "day":
            return (*self._day_bounds(today, today), "hour")
        if period == "week":
            return (*self._day_bounds(today - timedelta(days=6), today), "day")
        if period == "month":
            return (*self._day_bounds(today.replace(day=1), today), "day")
        if period == "year":
            return (*self._day_bounds(today.replace(month=1, day=1), today), "month")

        # custom range
        if not (start_param and end_param):
            raise ValueError("custom range requires start and end (YYYY-MM-DD)")
        try:
            s = datetime.strptime(start_param, "%Y-%m-%d").date()
            e = datetime.strptime(end_param, "%Y-%m-%d").date()
        except ValueError:
            raise ValueError("invalid date format, expected YYYY-MM-DD")
        if e < s:
            s, e = e, s
        span = (e - s).days
        gran = "day" if span <= 92 else "month"
        return (*self._day_bounds(s, e), gran)

    def _series(self, start_dt, end_dt, gran):
        trunc = {"hour": TruncHour, "day": TruncDay, "month": TruncMonth}[gran]
        keyfmt = {"hour": "%Y-%m-%d %H", "day": "%Y-%m-%d", "month": "%Y-%m"}[gran]

        orders = (Order.objects
                  .filter(created_at__gte=start_dt, created_at__lte=end_dt)
                  .annotate(b=trunc("created_at", tzinfo=self.tz))
                  .values("b").annotate(pt=Sum("total"), st=Sum("supplement"), dc=Sum("discount")))
        omap = {timezone.localtime(o["b"]).strftime(keyfmt): o for o in orders}

        items = (OrderItem.objects
                 .filter(order__created_at__gte=start_dt, order__created_at__lte=end_dt)
                 .annotate(b=trunc("order__created_at", tzinfo=self.tz))
                 .values("b").annotate(qc=Sum("quantity")))
        imap = {timezone.localtime(i["b"]).strftime(keyfmt): (i["qc"] or 0) for i in items}

        out = []
        for key, label in self._buckets(start_dt, end_dt, gran):
            o = omap.get(key)
            pt = (o["pt"] if o else 0) or 0
            st = (o["st"] if o else 0) or 0
            dc = (o["dc"] if o else 0) or 0
            out.append({
                "label": label,
                "products_total": pt,
                "supplements_total": st,
                "discounts_total": dc,
                "amount_to_pay_total": pt + st - dc,
                "products_count": imap.get(key, 0),
            })
        return out

    def _buckets(self, start_dt, end_dt, gran):
        buckets = []
        if gran == "hour":
            cur = start_dt
            while cur <= end_dt:
                buckets.append((cur.strftime("%Y-%m-%d %H"), cur.strftime("%H:00")))
                cur += timedelta(hours=1)
        elif gran == "day":
            cur = start_dt
            while cur.date() <= end_dt.date():
                buckets.append((cur.strftime("%Y-%m-%d"), cur.strftime("%d/%m")))
                cur += timedelta(days=1)
        else:  # month
            y, m = start_dt.year, start_dt.month
            while (y, m) <= (end_dt.year, end_dt.month):
                buckets.append((f"{y:04d}-{m:02d}", MONTHS_AR[m - 1]))
                m += 1
                if m > 12:
                    m = 1
                    y += 1
        return buckets

    def _calculate_analytics(self, start_datetime, end_datetime, User):
        """
        Helper method to calculate analytics for a given period
        """
        # Query orders for the period
        period_orders = Order.objects.filter(
            created_at__gte=start_datetime,
            created_at__lte=end_datetime
        )

        # Get the sum of all order totals for the period (excluding supplements)
        sum_products = period_orders.aggregate(sum=Sum('total'))['sum'] or 0

        # Get the sum of all supplements
        sum_supplements = period_orders.aggregate(sum=Sum('supplement'))['sum'] or 0

        # Sum of discounts granted
        sum_discounts = period_orders.aggregate(sum=Sum('discount'))['sum'] or 0

        # Final amount to pay (total + supplement - discount)
        sum_amount_to_pay = sum_products + sum_supplements - sum_discounts

        # Get count of products purchased in the period
        order_items = OrderItem.objects.filter(
            order__in=period_orders
        )
        products_count = order_items.aggregate(sum=Sum('quantity'))['sum'] or 0

        # Get count of users created in the period
        users_created = User.objects.filter(
            date_joined__gte=start_datetime,
            date_joined__lte=end_datetime,
            deleted=False,
            is_staff=False,
        ).count()

        # Keep money as Decimal end to end; DRF renders it as a JSON number
        # (COERCE_DECIMAL_TO_STRING=False) without reintroducing float error.
        return {
            "products_count": products_count,
            "products_total": sum_products,
            "supplements_total": sum_supplements,
            "discounts_total": sum_discounts,
            "amount_to_pay_total": sum_amount_to_pay,
            "users_created": users_created,
        }