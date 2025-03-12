from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import filters, viewsets

from apps.orders.api.serializers import OrderSerializer
from apps.orders.models import Order


class OrderViewSet(viewsets.ModelViewSet):
    queryset = Order.objects.all()
    serializer_class = OrderSerializer
    filter_backends = [filters.SearchFilter, filters.OrderingFilter, DjangoFilterBackend, ]
    search_fields = ['name', 'description']
    filterset_fields = ["order_items__product"]
