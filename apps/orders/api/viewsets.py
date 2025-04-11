from datetime import datetime, time

from django.db.models import Sum
from django.utils import timezone
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import filters, viewsets
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.generics import get_object_or_404
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.orders.api.serializers import OrderSerializer, UserBalanceSerializer, UserBalanceDepositSerializer
from apps.orders.models import Order, UserBalance, OrderItem


class OrderViewSet(viewsets.ModelViewSet):
    queryset = Order.objects.all()
    serializer_class = OrderSerializer
    filter_backends = [filters.SearchFilter, filters.OrderingFilter, DjangoFilterBackend, ]
    search_fields = ['name', 'description']
    filterset_fields = ["order_items__product"]


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

            try:
                user_balance.deposit(amount, balance_type)
                user_balance.refresh_from_db()
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


class TodayOrderAnalyticsView(APIView):
    """
    API view to return analytics for today's orders only.
    Returns sum of products purchased, sum of supplements, and sum of amount to pay.
    """

    def get(self, request, *args, **kwargs):
        # Use today's date
        today = timezone.now().date()

        # Define the start and end of today
        start_datetime = datetime.combine(today, time.min)
        end_datetime = datetime.combine(today, time.max)

        # Query orders for today only
        today_orders = Order.objects.filter(
            created_at__gte=start_datetime,
            created_at__lte=end_datetime
        )

        # Get the sum of all order totals for today (excluding supplements)
        sum_products = today_orders.aggregate(sum=Sum('total'))['sum'] or 0

        # Get the sum of all supplements
        sum_supplements = today_orders.aggregate(sum=Sum('supplement'))['sum'] or 0

        # Calculate the total amount to pay (total + supplement)
        sum_amount_to_pay = sum_products + sum_supplements

        # Get count of products purchased today
        order_items = OrderItem.objects.filter(
            order__in=today_orders
        )
        products_count = order_items.aggregate(sum=Sum('quantity'))['sum'] or 0

        # Create the response data
        response_data = {
            "products_count": products_count,
            "products_total": float(sum_products),
            "supplements_total": float(sum_supplements),
            "amount_to_pay_total": float(sum_amount_to_pay),
        }

        return Response(response_data, status=status.HTTP_200_OK)
