from django.contrib import admin
from django.utils.html import format_html
from django.urls import reverse
from django.utils.safestring import mark_safe
from .models import Product, HoodCategory, UploadLog, BulkUpload, Order, OrderItem, OrderStatusHistory, OrderSyncLog

# Импортируем админку для заказов
from .admin_orders import *


@admin.register(HoodCategory)
class HoodCategoryAdmin(admin.ModelAdmin):
    """Админка для категорий Hood.de"""
    list_display = ['name', 'hood_id', 'level', 'parent', 'is_active', 'created_at']
    list_filter = ['level', 'is_active', 'created_at']
    search_fields = ['name', 'hood_id', 'path']
    ordering = ['path']
    readonly_fields = ['created_at', 'updated_at']
    
    fieldsets = (
        ('Основная информация', {
            'fields': ('hood_id', 'name', 'path', 'level', 'parent', 'is_active')
        }),
        ('Системная информация', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    """Расширенная админка для продуктов с группировкой полей Hood.de API"""
    
    list_display = ['title', 'manufacturer', 'price', 'condition', 'is_uploaded_to_hood', 'created_at']
    list_filter = ['condition', 'item_mode', 'is_uploaded_to_hood', 'manufacturer', 'hood_category', 'created_at']
    search_fields = ['title', 'description', 'ean', 'mpn', 'manufacturer']
    ordering = ['-created_at']
    readonly_fields = ['created_at', 'updated_at', 'uploaded_at']
    
    # Группировка полей по категориям Hood.de API
    fieldsets = (
        ('📋 Основные поля (Basic Fields)', {
            'fields': (
                'title',
                'description',
                'html_description',
                'item_mode',
                'hood_category',
                'category_id',
                'quantity',
                'condition',
            ),
            'classes': ('wide',)
        }),
        
        ('💰 Ценовые поля (Price Fields)', {
            'fields': (
                'price',
                'price_start',
                'list_price',
                'purchase_price',
                'sales_tax',
            ),
            'classes': ('wide',)
        }),
        
        ('⏰ Временные поля (Time Fields)', {
            'fields': (
                'start_date',
                'start_time',
                'duration_in_days',
                'auto_renew',
            ),
            'classes': ('wide',)
        }),
        
        ('🚚 Поля доставки (Shipping Fields)', {
            'fields': (
                'shipmethods',
                'weight',
            ),
            'classes': ('wide',)
        }),
        
        ('💳 Поля оплаты (Payment Fields)', {
            'fields': (
                'pay_options',
            ),
            'classes': ('wide',)
        }),
        
        ('📦 Продуктовые поля (Product Fields)', {
            'fields': (
                'ean',
                'isbn',
                'mpn',
                'manufacturer',
                'item_number',
                'item_number_unique_flag',
                'unit',
                'packaging_size',
                'packaging_unit',
                'minimum_purchase',
            ),
            'classes': ('wide',)
        }),
        
        ('🔄 Поля вариантов (Variant Fields)', {
            'fields': (
                'product_options',
                'product_properties',
            ),
            'classes': ('wide',)
        }),
        
        ('⭐ Поля особенностей (Feature Fields)', {
            'fields': (
                'category2_id',
                'item_name_sub_title',
                'feature_bold_title',
                'feature_background_color',
                'feature_gallery',
                'feature_category',
                'feature_home_page',
                'feature_home_page_image',
                'feature_xxl_image',
            ),
            'classes': ('wide',)
        }),
        
        ('🏪 Поля магазина (Shop Fields)', {
            'fields': (
                'prod_cat_id',
                'prod_cat_id2',
                'prod_cat_id3',
                'short_desc',
                'if_is_sold_out',
                'is_approved',
                'show_on_start_page',
            ),
            'classes': ('wide',)
        }),
        
        ('📦 Поля доставки (Delivery Fields)', {
            'fields': (
                'delivery_days_on_stock_from',
                'delivery_days_on_stock_to',
                'delivery_days_not_on_stock_from',
                'delivery_days_not_on_stock_to',
            ),
            'classes': ('wide',)
        }),
        
        ('🔒 Специальные поля (Special Fields)', {
            'fields': (
                'fsk',
                'usk',
                'energy_efficiency_class',
                'energy_label_url',
                'product_info_url',
                'deficiency_description',
                'warranty_shortened_flag',
                'no_identifier_flag',
            ),
            'classes': ('wide',)
        }),
        
        ('🖼️ Поля изображений (Image Fields)', {
            'fields': (
                'images',
            ),
            'classes': ('wide',)
        }),
        
        ('🏷️ Дополнительные поля', {
            'fields': (
                'material',
                'color',
                'dimensions',
            ),
            'classes': ('wide',)
        }),
        
        ('📊 Статусы загрузки', {
            'fields': (
                'is_uploaded_to_hood',
                'hood_item_id',
                'uploaded_at',
            ),
            'classes': ('wide',)
        }),
        
        ('🔧 Системные поля', {
            'fields': (
                'custom_specifics',
                'created_by',
                'created_at',
                'updated_at',
            ),
            'classes': ('collapse',)
        }),
    )
    
    # Фильтры для быстрого доступа
    list_filter = [
        'condition',
        'item_mode',
        'is_uploaded_to_hood',
        'manufacturer',
        'hood_category',
        'created_at',
        'sales_tax',
        'duration_in_days',
    ]
    
    # Поиск по полям
    search_fields = [
        'title',
        'description',
        'ean',
        'isbn',
        'mpn',
        'manufacturer',
        'item_number',
        'material',
        'color',
    ]
    
    # Действия для массовых операций
    actions = ['upload_to_hood', 'mark_as_uploaded', 'generate_html_descriptions']
    
    def upload_to_hood(self, request, queryset):
        """Действие для загрузки выбранных товаров на Hood.de"""
        from .services import HoodAPIService
        
        hood_service = HoodAPIService()
        uploaded_count = 0
        error_count = 0
        
        for product in queryset:
            try:
                hood_data = product.get_hood_data()
                result = hood_service.upload_item(hood_data)
                
                if result.get('success'):
                    product.is_uploaded_to_hood = True
                    product.hood_item_id = result.get('item_id', '')
                    product.uploaded_at = timezone.now()
                    product.save()
                    uploaded_count += 1
                else:
                    error_count += 1
                    
            except Exception as e:
                error_count += 1
                continue
        
        self.message_user(
            request,
            f'Загружено: {uploaded_count}, Ошибок: {error_count}'
        )
    
    upload_to_hood.short_description = "Загрузить выбранные товары на Hood.de"
    
    def mark_as_uploaded(self, request, queryset):
        """Отметить товары как загруженные"""
        updated = queryset.update(is_uploaded_to_hood=True)
        self.message_user(request, f'Отмечено как загруженные: {updated} товаров')
    
    mark_as_uploaded.short_description = "Отметить как загруженные"
    
    def generate_html_descriptions(self, request, queryset):
        """Сгенерировать HTML описания для выбранных товаров"""
        from .utils import generate_html_description
        
        generated_count = 0
        for product in queryset:
            try:
                html_desc = generate_html_description(product)
                product.html_description = html_desc
                product.save()
                generated_count += 1
            except Exception as e:
                continue
        
        self.message_user(request, f'Сгенерировано HTML описаний: {generated_count}')
    
    generate_html_descriptions.short_description = "Сгенерировать HTML описания"
    
    # Методы для отображения дополнительной информации
    def get_hood_data_preview(self, obj):
        """Предварительный просмотр данных для Hood.de"""
        hood_data = obj.get_hood_data()
        preview = []
        for key, value in list(hood_data.items())[:10]:  # Показываем первые 10 полей
            if value:
                preview.append(f"{key}: {value}")
        return format_html('<br>'.join(preview))
    
    get_hood_data_preview.short_description = "Данные для Hood.de (первые 10 полей)"
    
    def get_upload_status(self, obj):
        """Статус загрузки с цветовой индикацией"""
        if obj.is_uploaded_to_hood:
            return format_html(
                '<span style="color: green;">✅ Загружен</span><br>'
                f'<small>ID: {obj.hood_item_id}</small><br>'
                f'<small>Дата: {obj.uploaded_at}</small>'
            )
        else:
            return format_html('<span style="color: red;">❌ Не загружен</span>')
    
    get_upload_status.short_description = "Статус загрузки"
    
    # Добавляем дополнительные поля в list_display
    list_display = [
        'title',
        'manufacturer',
        'price',
        'condition',
        'get_upload_status',
        'created_at'
    ]
    
    # Настройки для больших форм
    save_on_top = True
    save_as = True
    
    # Автозаполнение полей
    def save_model(self, request, obj, form, change):
        if not change:  # Если создается новый объект
            obj.created_by = request.user
        super().save_model(request, obj, form, change)


@admin.register(UploadLog)
class UploadLogAdmin(admin.ModelAdmin):
    """Админка для логов загрузки"""
    list_display = ['product', 'status', 'hood_item_id', 'created_at']
    list_filter = ['status', 'created_at']
    search_fields = ['product__title', 'hood_item_id', 'error_message']
    ordering = ['-created_at']
    readonly_fields = ['created_at', 'updated_at']
    
    fieldsets = (
        ('Основная информация', {
            'fields': ('product', 'status', 'hood_item_id')
        }),
        ('Данные ответа', {
            'fields': ('response_data', 'error_message'),
            'classes': ('wide',)
        }),
        ('Системная информация', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )


@admin.register(BulkUpload)
class BulkUploadAdmin(admin.ModelAdmin):
    """Админка для массовых загрузок"""
    list_display = ['name', 'status', 'total_products', 'uploaded_products', 'failed_products', 'created_at']
    list_filter = ['status', 'created_at']
    search_fields = ['name']
    ordering = ['-created_at']
    readonly_fields = ['created_at', 'updated_at']
    
    fieldsets = (
        ('Основная информация', {
            'fields': ('name', 'status', 'created_by')
        }),
        ('Статистика', {
            'fields': ('total_products', 'uploaded_products', 'failed_products')
        }),
        ('Системная информация', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
