from datetime import datetime, time

from django.db.models import Sum
from django.utils import timezone
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import filters, viewsets
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.orders.api.serializers import OrderSerializer, UserBalanceSerializer
from apps.orders.models import Order, UserBalance, OrderItem


class OrderViewSet(viewsets.ModelViewSet):
    queryset = Order.objects.all()
    serializer_class = OrderSerializer
    filter_backends = [filters.SearchFilter, filters.OrderingFilter, DjangoFilterBackend, ]
    search_fields = ['name', 'description']
    filterset_fields = ["order_items__product", "user"]


class UserBalanceViewSet(viewsets.ModelViewSet):
    serializer_class = UserBalanceSerializer
    filter_backends = [DjangoFilterBackend, filters.SearchFilter]
    filterset_fields = ['user__id']
    def get_queryset(self):
        # Users can only see their own balance
        return UserBalance.objects.all()



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
