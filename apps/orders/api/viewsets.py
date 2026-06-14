from datetime import datetime, time, timedelta

from django.db import transaction
from django.db.models import F, Sum
from django.utils import timezone
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


class OrderViewSet(viewsets.ModelViewSet):
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
    filterset_fields = ["order_items__product", "user"]

    def update(self, request, *args, **kwargs):
        """Replace an order: reverse the old one, then create the new one.

        The reversal (restock + un-charge the balance) happens BEFORE creating
        the replacement, and the whole thing is one transaction — so a failure
        (e.g. not enough stock for the new quantities) rolls everything back and
        leaves the original order intact.
        """
        instance = self.get_object()

        # Editing only makes sense while the recorded prices still match the
        # current product prices; otherwise the reversal math would drift.
        if not all(item.fixed_price == item.product.price for item in instance.order_items.all()):
            return Response(
                {"error": "لا يمكن تعديل هذا الطلب لأن أسعار المنتجات تغيرت"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            with transaction.atomic():
                # 1) Reverse the existing order's effects.
                instance.user.userbalance.deposit(
                    -instance.amount_to_pay(), "orders_total",
                    kind=LedgerEntry.Kind.ORDER_REVERSAL, note=f"تعديل الطلب #{instance.id}",
                )
                for item in instance.order_items.all():
                    Product.objects.filter(pk=item.product_id).update(
                        stock=F("stock") + item.quantity
                    )
                instance.delete()

                # 2) Create the replacement (stock/balance applied by the serializer).
                serializer = self.get_serializer(data=request.data)
                serializer.is_valid(raise_exception=True)
                serializer.save()
        except serializers.ValidationError:
            raise
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

        return Response(serializer.data, status=status.HTTP_200_OK)




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
                    BalanceNote.objects.create(user=user_balance.user, amount=amount, note=note or "")
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

class OrderAnalyticsView(APIView):
    """
    API view to return analytics for orders.
    Returns analytics for today, this month, and this year periods.
    Analytics include sum of products purchased, sum of supplements, sum of amount to pay,
    and count of users created within each period.
    """

    def get(self, request, *args, **kwargs):
        # Use the active timezone so the day/month/year boundaries line up with
        # the local calendar. Building these as timezone-aware datetimes keeps
        # the date-range filtering correct under USE_TZ=True.
        now = timezone.localtime(timezone.now())
        today = now.date()
        tz = timezone.get_current_timezone()

        def aware(dt):
            return timezone.make_aware(dt, tz)

        # Today period
        today_start = aware(datetime.combine(today, time.min))
        today_end = aware(datetime.combine(today, time.max))

        # This month period
        month_start = aware(datetime(today.year, today.month, 1, 0, 0, 0))
        if today.month == 12:
            next_month = aware(datetime(today.year + 1, 1, 1, 0, 0, 0))
        else:
            next_month = aware(datetime(today.year, today.month + 1, 1, 0, 0, 0))
        month_end = next_month - timedelta(seconds=1)

        # This year period
        year_start = aware(datetime(today.year, 1, 1, 0, 0, 0))
        year_end = aware(datetime(today.year, 12, 31, 23, 59, 59))

        # Get user model
        from django.contrib.auth import get_user_model
        User = get_user_model()

        # Calculate analytics for each period
        response_data = {
            "today": self._calculate_analytics(today_start, today_end, User),
            "this_month": self._calculate_analytics(month_start, month_end, User),
            "this_year": self._calculate_analytics(year_start, year_end, User)
        }

        return Response(response_data, status=status.HTTP_200_OK)

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

        # Calculate the total amount to pay (total + supplement)
        sum_amount_to_pay = sum_products + sum_supplements

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
            "amount_to_pay_total": sum_amount_to_pay,
            "users_created": users_created,
        }