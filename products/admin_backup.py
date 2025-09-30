from django.contrib import admin
from django.utils.html import format_html
from django.urls import reverse
from django.utils.safestring import mark_safe
from .models import Product, HoodCategory, UploadLog, BulkUpload


@admin.register(HoodCategory)
class HoodCategoryAdmin(admin.ModelAdmin):
    list_display = ['name', 'hood_id', 'path', 'level', 'is_active', 'created_at']
    list_filter = ['level', 'is_active', 'created_at']
    search_fields = ['name', 'hood_id', 'path']
    readonly_fields = ['created_at', 'updated_at']
    ordering = ['path']


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = [
        'title', 'price', 'condition', 'is_active', 
        'is_uploaded_to_hood', 'hood_item_id', 'created_at'
    ]
    list_filter = [
        'condition', 'item_mode', 'is_active', 
        'is_uploaded_to_hood', 'created_at', 'hood_category'
    ]
    search_fields = ['title', 'ean', 'manufacturer', 'item_number']
    readonly_fields = ['created_at', 'updated_at', 'uploaded_at']
    
    fieldsets = (
        ('Основная информация', {
            'fields': ('title', 'description', 'html_description', 'created_by')
        }),
        ('Цены', {
            'fields': ('price', 'price_start', 'list_price')
        }),
        ('Количество и состояние', {
            'fields': ('quantity', 'condition', 'item_mode')
        }),
        ('Идентификаторы', {
            'fields': ('ean', 'mpn', 'manufacturer', 'item_number')
        }),
        ('Физические характеристики', {
            'fields': ('weight', 'dimensions', 'material', 'color')
        }),
        ('Категории', {
            'fields': ('hood_category', 'category_id')
        }),
        ('Изображения', {
            'fields': ('images', 'gallery_url', 'picture_url')
        }),
        ('Дополнительные данные', {
            'fields': ('custom_specifics', 'product_properties'),
            'classes': ('collapse',)
        }),
        ('Статус', {
            'fields': ('is_active', 'is_uploaded_to_hood', 'hood_item_id')
        }),
        ('Даты', {
            'fields': ('created_at', 'updated_at', 'uploaded_at'),
            'classes': ('collapse',)
        }),
    )
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related('hood_category', 'created_by')
    
    def save_model(self, request, obj, form, change):
        if not change:  # Если это новый объект
            obj.created_by = request.user
        super().save_model(request, obj, form, change)


@admin.register(UploadLog)
class UploadLogAdmin(admin.ModelAdmin):
    list_display = [
        'product', 'status', 'hood_item_id', 'created_at'
    ]
    list_filter = ['status', 'created_at']
    search_fields = ['product__title', 'hood_item_id', 'error_message']
    readonly_fields = ['created_at', 'updated_at']
    
    fieldsets = (
        ('Основная информация', {
            'fields': ('product', 'status', 'hood_item_id')
        }),
        ('Ответ API', {
            'fields': ('response_data', 'error_message'),
            'classes': ('collapse',)
        }),
        ('Даты', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related('product')


@admin.register(BulkUpload)
class BulkUploadAdmin(admin.ModelAdmin):
    list_display = [
        'name', 'status', 'total_products', 'uploaded_products', 
        'failed_products', 'progress_percentage', 'created_at'
    ]
    list_filter = ['status', 'created_at']
    search_fields = ['name', 'description']
    readonly_fields = [
        'created_at', 'started_at', 'completed_at', 
        'total_products', 'uploaded_products', 'failed_products'
    ]
    
    fieldsets = (
        ('Основная информация', {
            'fields': ('name', 'description', 'status', 'created_by')
        }),
        ('Статистика', {
            'fields': ('total_products', 'uploaded_products', 'failed_products')
        }),
        ('Даты', {
            'fields': ('created_at', 'started_at', 'completed_at'),
            'classes': ('collapse',)
        }),
    )
    
    def progress_percentage(self, obj):
        """Отображение процента выполнения"""
        percentage = obj.get_progress_percentage()
        color = 'green' if percentage == 100 else 'orange' if percentage > 0 else 'red'
        return format_html(
            '<span style="color: {};">{:.1f}%</span>',
            color, percentage
        )
    progress_percentage.short_description = 'Прогресс'
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related('created_by')


# Настройка админ-сайта
admin.site.site_header = "Hood.de Integration Service"
admin.site.site_title = "Hood Integration"
admin.site.index_title = "Управление интеграцией с Hood.de"