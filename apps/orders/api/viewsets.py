from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import filters, viewsets, status
from rest_framework.decorators import action
from rest_framework.generics import get_object_or_404
from rest_framework.response import Response

from apps.orders.api.serializers import OrderSerializer, UserBalanceSerializer, UserBalanceDepositSerializer
from apps.orders.models import Order, UserBalance


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
