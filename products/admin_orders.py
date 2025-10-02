from django.contrib import admin
from django.utils.html import format_html
from django.urls import reverse
from .models import Order, OrderItem, OrderStatusHistory, OrderSyncLog


class OrderItemInline(admin.TabularInline):
    """Инлайн для товаров в заказе"""
    model = OrderItem
    extra = 0
    readonly_fields = ['total_price', 'created_at']
    fields = ['product', 'hood_item_id', 'item_title', 'item_sku', 'quantity', 'unit_price', 'total_price']


class OrderStatusHistoryInline(admin.TabularInline):
    """Инлайн для истории статусов заказа"""
    model = OrderStatusHistory
    extra = 0
    readonly_fields = ['changed_at', 'changed_by']
    fields = ['old_status', 'new_status', 'change_reason', 'changed_by', 'changed_at']


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    """Админка для заказов"""
    list_display = [
        'hood_order_id', 'order_number', 'status_display', 'buyer_username', 
        'total_amount', 'payment_method', 'order_date', 'synced_at'
    ]
    list_filter = [
        'status', 'payment_method', 'payment_status', 'order_date', 
        'shipping_country', 'synced_at'
    ]
    search_fields = [
        'hood_order_id', 'order_number', 'buyer_username', 'buyer_email', 
        'buyer_name', 'shipping_name'
    ]
    readonly_fields = [
        'hood_order_id', 'created_at', 'updated_at', 'synced_at', 
        'last_status_change', 'items_count'
    ]
    
    fieldsets = (
        ('Основная информация', {
            'fields': (
                'hood_order_id', 'order_number', 'status', 'order_date',
                'last_status_change', 'synced_at'
            )
        }),
        ('Покупатель', {
            'fields': (
                'buyer_username', 'buyer_email', 'buyer_name'
            )
        }),
        ('Адрес доставки', {
            'fields': (
                'shipping_name', 'shipping_company', 'shipping_address1', 
                'shipping_address2', 'shipping_city', 'shipping_state',
                'shipping_postal_code', 'shipping_country', 'shipping_phone'
            ),
            'classes': ('collapse',)
        }),
        ('Финансовая информация', {
            'fields': (
                'subtotal', 'shipping_cost', 'tax_amount', 'total_amount'
            )
        }),
        ('Платеж и доставка', {
            'fields': (
                'payment_method', 'payment_status', 'payment_date',
                'shipping_method', 'tracking_number', 'shipped_date', 'delivered_date'
            ),
            'classes': ('collapse',)
        }),
        ('Примечания', {
            'fields': ('notes', 'internal_notes'),
            'classes': ('collapse',)
        }),
        ('Системная информация', {
            'fields': ('items_count', 'created_at', 'updated_at'),
            'classes': ('collapse',)
        })
    )
    
    inlines = [OrderItemInline, OrderStatusHistoryInline]
    
    def status_display(self, obj):
        """Отображение статуса с цветом"""
        color = obj.get_status_display_color()
        color_map = {
            'primary': '#007bff',
            'success': '#28a745',
            'info': '#17a2b8',
            'warning': '#ffc107',
            'danger': '#dc3545',
            'secondary': '#6c757d',
        }
        
        return format_html(
            '<span style="background-color: {}; color: white; padding: 3px 8px; border-radius: 3px; font-size: 12px;">{}</span>',
            color_map.get(color, '#6c757d'),
            obj.get_status_display()
        )
    status_display.short_description = 'Статус'
    
    def items_count(self, obj):
        """Количество товаров в заказе"""
        return obj.items.count()
    items_count.short_description = 'Товаров'
    
    def get_queryset(self, request):
        return super().get_queryset(request).prefetch_related('items')


@admin.register(OrderItem)
class OrderItemAdmin(admin.ModelAdmin):
    """Админка для товаров в заказах"""
    list_display = [
        'order', 'item_title', 'item_sku', 'quantity', 
        'unit_price', 'total_price', 'product_link'
    ]
    list_filter = ['order__status', 'created_at']
    search_fields = [
        'item_title', 'item_sku', 'item_ean', 'hood_item_id',
        'order__hood_order_id', 'order__buyer_username'
    ]
    readonly_fields = ['total_price', 'created_at', 'updated_at']
    
    def product_link(self, obj):
        """Ссылка на связанный продукт"""
        if obj.product:
            url = reverse('admin:products_product_change', args=[obj.product.id])
            return format_html('<a href="{}">{}</a>', url, obj.product.title)
        return '-'
    product_link.short_description = 'Продукт'


@admin.register(OrderStatusHistory)
class OrderStatusHistoryAdmin(admin.ModelAdmin):
    """Админка для истории статусов заказов"""
    list_display = [
        'order', 'old_status', 'new_status', 'changed_by', 'changed_at'
    ]
    list_filter = ['old_status', 'new_status', 'changed_at', 'changed_by']
    search_fields = [
        'order__hood_order_id', 'order__buyer_username', 'change_reason'
    ]
    readonly_fields = ['changed_at']
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related('order', 'changed_by')


@admin.register(OrderSyncLog)
class OrderSyncLogAdmin(admin.ModelAdmin):
    """Админка для логов синхронизации заказов"""
    list_display = [
        'sync_type', 'status_display', 'total_orders_found', 'orders_created',
        'orders_updated', 'orders_failed', 'success_rate_display', 'started_at'
    ]
    list_filter = ['sync_type', 'status', 'started_at']
    search_fields = ['sync_type', 'error_details']
    readonly_fields = [
        'started_at', 'completed_at', 'success_rate_display', 'duration_display'
    ]
    
    fieldsets = (
        ('Основная информация', {
            'fields': (
                'sync_type', 'status', 'start_date', 'end_date',
                'started_at', 'completed_at', 'duration_display'
            )
        }),
        ('Результаты', {
            'fields': (
                'total_orders_found', 'orders_created', 'orders_updated', 
                'orders_failed', 'success_rate_display'
            )
        }),
        ('Детали', {
            'fields': ('error_details', 'response_data'),
            'classes': ('collapse',)
        })
    )
    
    def status_display(self, obj):
        """Отображение статуса с цветом"""
        colors = {
            'pending': '#ffc107',
            'success': '#28a745',
            'error': '#dc3545',
            'partial': '#fd7e14',
        }
        
        return format_html(
            '<span style="background-color: {}; color: white; padding: 3px 8px; border-radius: 3px; font-size: 12px;">{}</span>',
            colors.get(obj.status, '#6c757d'),
            obj.get_status_display()
        )
    status_display.short_description = 'Статус'
    
    def success_rate_display(self, obj):
        """Отображение процента успешности"""
        rate = obj.get_success_rate()
        if rate >= 90:
            color = '#28a745'
        elif rate >= 70:
            color = '#ffc107'
        else:
            color = '#dc3545'
        
        return format_html(
            '<span style="color: {}; font-weight: bold;">{}%</span>',
            color, rate
        )
    success_rate_display.short_description = 'Успешность'
    
    def duration_display(self, obj):
        """Отображение длительности синхронизации"""
        if obj.completed_at and obj.started_at:
            duration = obj.completed_at - obj.started_at
            return str(duration)
        return '-'
    duration_display.short_description = 'Длительность'
