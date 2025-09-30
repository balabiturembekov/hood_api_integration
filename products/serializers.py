from rest_framework import serializers
from .models import Product, HoodCategory, UploadLog, BulkUpload


class HoodCategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = HoodCategory
        fields = '__all__'


class ProductSerializer(serializers.ModelSerializer):
    hood_category_name = serializers.CharField(source='hood_category.name', read_only=True)
    created_by_username = serializers.SerializerMethodField()
    
    class Meta:
        model = Product
        fields = '__all__'
        read_only_fields = ['created_by', 'created_at', 'updated_at', 'uploaded_at']
    
    def get_created_by_username(self, obj):
        return obj.created_by.username if obj.created_by else 'Неизвестно'
    
    def create(self, validated_data):
        # Автоматически устанавливаем создателя
        validated_data['created_by'] = self.context['request'].user
        return super().create(validated_data)


class ProductListSerializer(serializers.ModelSerializer):
    """Упрощенный сериализатор для списка продуктов"""
    hood_category_name = serializers.CharField(source='hood_category.name', read_only=True)
    created_by_username = serializers.SerializerMethodField()
    
    class Meta:
        model = Product
        fields = [
            'id', 'title', 'price', 'condition', 'is_approved', 
            'is_uploaded_to_hood', 'hood_item_id', 'created_at',
            'hood_category_name', 'created_by_username'
        ]
    
    def get_created_by_username(self, obj):
        return obj.created_by.username if obj.created_by else 'Неизвестно'


class UploadLogSerializer(serializers.ModelSerializer):
    product_title = serializers.CharField(source='product.title', read_only=True)
    
    class Meta:
        model = UploadLog
        fields = '__all__'
        read_only_fields = ['created_at', 'updated_at']


class BulkUploadSerializer(serializers.ModelSerializer):
    created_by_username = serializers.SerializerMethodField()
    progress_percentage = serializers.SerializerMethodField()
    
    class Meta:
        model = BulkUpload
        fields = '__all__'
        read_only_fields = ['created_by', 'created_at', 'started_at', 'completed_at']
    
    def get_created_by_username(self, obj):
        return obj.created_by.username if obj.created_by else 'Неизвестно'
    
    def get_progress_percentage(self, obj):
        return obj.get_progress_percentage()
    
    def create(self, validated_data):
        # Автоматически устанавливаем создателя
        validated_data['created_by'] = self.context['request'].user
        return super().create(validated_data)


class ProductUploadSerializer(serializers.Serializer):
    """Сериализатор для загрузки продукта на Hood.de"""
    product_id = serializers.IntegerField()
    
    def validate_product_id(self, value):
        try:
            product = Product.objects.get(id=value)
            if product.is_uploaded_to_hood:
                raise serializers.ValidationError("Продукт уже загружен на Hood.de")
            return value
        except Product.DoesNotExist:
            raise serializers.ValidationError("Продукт не найден")


class BulkUploadRequestSerializer(serializers.Serializer):
    """Сериализатор для массовой загрузки"""
    product_ids = serializers.ListField(
        child=serializers.IntegerField(),
        min_length=1,
        max_length=100
    )
    name = serializers.CharField(max_length=200)
    description = serializers.CharField(required=False, allow_blank=True)
    
    def validate_product_ids(self, value):
        # Проверяем, что все продукты существуют и не загружены
        products = Product.objects.filter(id__in=value)
        if len(products) != len(value):
            raise serializers.ValidationError("Некоторые продукты не найдены")
        
        uploaded_products = products.filter(is_uploaded_to_hood=True)
        if uploaded_products.exists():
            uploaded_titles = list(uploaded_products.values_list('title', flat=True))
            raise serializers.ValidationError(
                f"Следующие продукты уже загружены: {', '.join(uploaded_titles)}"
            )
        
        return value
