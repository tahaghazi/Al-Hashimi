from rest_framework import filters, viewsets, status
from rest_framework.response import Response

from apps.products.api.serializers import ProductSerializer, BrandSerializer
from apps.products.models import Product, Brand
from apps.users.audit import AuditMixin, log_action
from apps.users.models import AuditLog


class ProductViewSet(AuditMixin, viewsets.ModelViewSet):
    queryset = Product.objects.filter(deleted=False)
    serializer_class = ProductSerializer
    filter_backends = [filters.SearchFilter, filters.OrderingFilter, ]
    search_fields = ['name', 'description', 'sku']
    audit_entity = "Battery"

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        log_action(request, AuditLog.Action.DELETE, entity="Battery",
                   object_id=instance.pk, object_repr=str(instance))
        instance.deleted = True
        instance.save()
        return Response(status=status.HTTP_204_NO_CONTENT)


class BrandViewSet(AuditMixin, viewsets.ModelViewSet):
    queryset = Brand.objects.all()
    serializer_class = BrandSerializer
    audit_entity = "Brand"
