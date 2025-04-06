from rest_framework import filters, viewsets, status
from rest_framework.response import Response

from apps.products.api.serializers import ProductSerializer, BrandSerializer
from apps.products.models import Product, Brand


class ProductViewSet(viewsets.ModelViewSet):
    queryset = Product.objects.filter(deleted=False)
    serializer_class = ProductSerializer
    filter_backends = [filters.SearchFilter, filters.OrderingFilter, ]
    search_fields = ['name', 'description']

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        instance.deleted = True
        instance.save()
        return Response(status=status.HTTP_204_NO_CONTENT)


class BrandViewSet(viewsets.ModelViewSet):
    queryset = Brand.objects.all()
    serializer_class = BrandSerializer
