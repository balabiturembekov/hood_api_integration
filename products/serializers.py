from rest_framework import serializers
from .models import Product, HoodCategory, UploadLog, BulkUpload, Order, OrderItem, OrderStatusHistory, OrderSyncLog


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


class OrderItemSerializer(serializers.ModelSerializer):
    """Сериализатор для товаров в заказе"""
    product_title = serializers.CharField(source='product.title', read_only=True)
    
    class Meta:
        model = OrderItem
        fields = '__all__'
        read_only_fields = ['created_at', 'updated_at', 'total_price']


class OrderStatusHistorySerializer(serializers.ModelSerializer):
    """Сериализатор для истории статусов заказа"""
    changed_by_username = serializers.CharField(source='changed_by.username', read_only=True)
    
    class Meta:
        model = OrderStatusHistory
        fields = '__all__'
        read_only_fields = ['changed_at']


class OrderSerializer(serializers.ModelSerializer):
    """Сериализатор для заказов"""
    items = OrderItemSerializer(many=True, read_only=True)
    status_history = OrderStatusHistorySerializer(many=True, read_only=True)
    status_display_color = serializers.SerializerMethodField()
    items_count = serializers.SerializerMethodField()
    
    class Meta:
        model = Order
        fields = '__all__'
        read_only_fields = ['created_at', 'updated_at', 'synced_at']
    
    def get_status_display_color(self, obj):
        return obj.get_status_display_color()
    
    def get_items_count(self, obj):
        return obj.items.count()


class OrderListSerializer(serializers.ModelSerializer):
    """Упрощенный сериализатор для списка заказов"""
    status_display_color = serializers.SerializerMethodField()
    items_count = serializers.SerializerMethodField()
    
    class Meta:
        model = Order
        fields = [
            'id', 'hood_order_id', 'order_number', 'status', 'buyer_username',
            'buyer_name', 'total_amount', 'payment_method', 'order_date',
            'status_display_color', 'items_count', 'created_at'
        ]
    
    def get_status_display_color(self, obj):
        return obj.get_status_display_color()
    
    def get_items_count(self, obj):
        return obj.items.count()


class OrderSyncLogSerializer(serializers.ModelSerializer):
    """Сериализатор для логов синхронизации заказов"""
    success_rate = serializers.SerializerMethodField()
    duration = serializers.SerializerMethodField()
    
    class Meta:
        model = OrderSyncLog
        fields = '__all__'
        read_only_fields = ['started_at', 'completed_at']
    
    def get_success_rate(self, obj):
        return obj.get_success_rate()
    
    def get_duration(self, obj):
        if obj.completed_at and obj.started_at:
            duration = obj.completed_at - obj.started_at
            return str(duration)
        return None


class OrderSyncRequestSerializer(serializers.Serializer):
    """Сериализатор для запроса синхронизации заказов"""
    sync_type = serializers.ChoiceField(choices=[
        ('recent', 'Последние заказы'),
        ('date_range', 'За период'),
        ('by_status', 'По изменению статуса'),
        ('by_id', 'По ID заказа'),
    ])
    start_date = serializers.DateField(required=False)
    end_date = serializers.DateField(required=False)
    order_id = serializers.CharField(required=False, max_length=50)
    days = serializers.IntegerField(required=False, min_value=1, max_value=365, default=7)
    
    def validate(self, data):
        sync_type = data.get('sync_type')
        
        if sync_type == 'date_range':
            if not data.get('start_date') or not data.get('end_date'):
                raise serializers.ValidationError(
                    "Для синхронизации за период требуются start_date и end_date"
                )
            if data['start_date'] > data['end_date']:
                raise serializers.ValidationError(
                    "Начальная дата не может быть больше конечной"
                )
        
        elif sync_type == 'by_status':
            if not data.get('start_date') or not data.get('end_date'):
                raise serializers.ValidationError(
                    "Для синхронизации по статусу требуются start_date и end_date"
                )
        
        elif sync_type == 'by_id':
            if not data.get('order_id'):
                raise serializers.ValidationError(
                    "Для синхронизации по ID требуется order_id"
                )
        
        return data
