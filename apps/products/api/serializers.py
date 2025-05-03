from rest_framework import serializers

from apps.products.models import Product, Brand


class ProductSerializer(serializers.ModelSerializer):
    class Meta:
        model = Product
        fields = '__all__'
        read_only_fields = ('id', 'created_at', 'updated_at')

    def validate(self, attrs):
        name = attrs.get('name')
        brand = attrs.get('brand')

        if name:
            attrs['name'] = name.lower()

        # Only check for duplicates on create or when name/brand is updated
        if name:
            print('attrs', attrs)
            queryset = Product.objects.filter(
                name=attrs['name'],
                brand=brand,
                deleted=False
            )
            print(queryset)

            # Exclude current instance on update
            if self.instance:
                queryset = queryset.exclude(pk=self.instance.pk)

            if queryset.exists():
                raise serializers.ValidationError({
                    'name': 'هذا المنتج موجود بالفعل'
                })

        return attrs


class BrandSerializer(serializers.ModelSerializer):
    class Meta:
        model = Brand
        fields = '__all__'
