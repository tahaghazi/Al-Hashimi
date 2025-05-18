from datetime import datetime, time, timedelta

from django.db import transaction
from django.db.models import Sum
from django.utils import timezone
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import filters, viewsets
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.generics import get_object_or_404
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.orders.api.serializers import OrderSerializer, UserBalanceSerializer, UserBalanceDepositSerializer, \
    UserBalanceNoteSerializer
from apps.orders.models import Order, UserBalance, OrderItem, BalanceNote


class OrderViewSet(viewsets.ModelViewSet):
    queryset = Order.objects.all()
    serializer_class = OrderSerializer
    filter_backends = [filters.SearchFilter, filters.OrderingFilter, DjangoFilterBackend, ]
    search_fields = ['name', 'description']
    filterset_fields = ["order_items__product", "user"]

    def update(self, request, *args, **kwargs):
        instance = self.get_object()
        if not instance.user.userbalance.orders_total >= instance.amount_to_pay():
            return Response({"error": "You can't edit this order"}, status=status.HTTP_400_BAD_REQUEST)

        try:

            with transaction.atomic():
                response = self.create(request, *args, **kwargs)
                instance.user.userbalance.deposit(-instance.amount_to_pay(), "orders_total")
                for item in instance.order_items.all():
                    item.product.stock += item.quantity
                    item.product.save()

                instance.delete()
                return response
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)




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
            print(serializer.validated_data)
            amount = serializer.validated_data['amount']
            balance_type = serializer.validated_data['balance_type']
            note = serializer.validated_data.get('note')

            try:
                user_balance.deposit(amount, balance_type)
                user_balance.refresh_from_db()
                BalanceNote.objects.create(user=user_balance.user, amount=amount, note=note)
                print(user_balance.amount_to_pay())
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
        # Get current date
        now = timezone.now()
        today = now.date()

        # Define periods
        # Today period
        today_start = datetime.combine(today, time.min)
        today_end = datetime.combine(today, time.max)

        # This month period
        month_start = datetime(today.year, today.month, 1, 0, 0, 0)
        if today.month == 12:
            next_month = datetime(today.year + 1, 1, 1, 0, 0, 0)
        else:
            next_month = datetime(today.year, today.month + 1, 1, 0, 0, 0)
        month_end = next_month - timedelta(seconds=1)

        # This year period
        year_start = datetime(today.year, 1, 1, 0, 0, 0)
        year_end = datetime(today.year, 12, 31, 23, 59, 59)

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

        # Create the response data for this period
        return {
            "products_count": products_count,
            "products_total": float(sum_products),
            "supplements_total": float(sum_supplements),
            "amount_to_pay_total": float(sum_amount_to_pay),
            "users_created": users_created,
        }