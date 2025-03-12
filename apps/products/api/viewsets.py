from rest_framework import filters, viewsets

from apps.products.api.serializers import ProductSerializer, BrandSerializer
from apps.products.models import Product, Brand


class ProductViewSet(viewsets.ModelViewSet):
    queryset = Product.objects.all()
    serializer_class = ProductSerializer
    filter_backends = [filters.SearchFilter, filters.OrderingFilter, ]
    search_fields = ['name', 'description']


class BrandViewSet(viewsets.ModelViewSet):
    queryset = Brand.objects.all()
    serializer_class = BrandSerializer
