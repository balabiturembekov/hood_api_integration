from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone
import json


class HoodCategory(models.Model):
    """Модель для категорий Hood.de"""
    hood_id = models.CharField(max_length=20, unique=True, verbose_name="Hood ID")
    name = models.CharField(max_length=200, verbose_name="Название")
    path = models.CharField(max_length=500, verbose_name="Путь")
    level = models.IntegerField(default=0, verbose_name="Уровень")
    parent = models.ForeignKey('self', on_delete=models.CASCADE, null=True, blank=True, verbose_name="Родительская категория")
    is_active = models.BooleanField(default=True, verbose_name="Активна")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Создана")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Обновлена")

    class Meta:
        verbose_name = "Категория Hood.de"
        verbose_name_plural = "Категории Hood.de"
        ordering = ['path']

    def __str__(self):
        return f"{self.name} ({self.hood_id})"


class Product(models.Model):
    """Модель для продуктов"""
    
    CONDITION_CHOICES = [
        ('new', 'Новый'),
        ('likeNew', 'Как новый'),
        ('veryGood', 'Очень хорошее'),
        ('acceptable', 'Удовлетворительное'),
        ('refurbished', 'Восстановленный'),
        ('defect', 'С дефектом'),
        ('usedGood', 'Б/у хорошее'),
    ]
    
    ITEM_MODE_CHOICES = [
        ('classic', 'Классический аукцион'),
        ('buyItNow', 'Купить сейчас'),
        ('shopProduct', 'Товар магазина'),
    ]

    # Основные поля
    title = models.CharField(max_length=200, verbose_name="Название")
    description = models.TextField(verbose_name="Описание")
    html_description = models.TextField(blank=True, verbose_name="HTML описание")
    
    # Цены
    price = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="Цена")
    price_start = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True, verbose_name="Стартовая цена")
    list_price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True, verbose_name="Рекомендованная цена")
    
    # Количество и состояние
    quantity = models.IntegerField(default=1, verbose_name="Количество")
    condition = models.CharField(max_length=20, choices=CONDITION_CHOICES, default='new', verbose_name="Состояние")
    item_mode = models.CharField(max_length=20, choices=ITEM_MODE_CHOICES, default='shopProduct', verbose_name="Режим товара")
    
    # Идентификаторы
    ean = models.CharField(max_length=20, blank=True, verbose_name="EAN")
    mpn = models.CharField(max_length=100, blank=True, verbose_name="MPN")
    manufacturer = models.CharField(max_length=100, blank=True, verbose_name="Производитель")
    item_number = models.CharField(max_length=100, blank=True, verbose_name="Номер товара")
    
    # Физические характеристики
    weight = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True, verbose_name="Вес (кг)")
    dimensions = models.CharField(max_length=200, blank=True, verbose_name="Размеры")
    material = models.CharField(max_length=200, blank=True, verbose_name="Материал")
    color = models.CharField(max_length=100, blank=True, verbose_name="Цвет")
    
    # Категории
    hood_category = models.ForeignKey(HoodCategory, on_delete=models.SET_NULL, null=True, blank=True, verbose_name="Категория Hood.de")
    category_id = models.CharField(max_length=20, blank=True, verbose_name="ID категории")
    
    # Изображения
    images = models.JSONField(default=list, verbose_name="Изображения")
    gallery_url = models.URLField(blank=True, verbose_name="URL галереи")
    picture_url = models.URLField(blank=True, verbose_name="URL изображения")
    
    # Дополнительные поля
    custom_specifics = models.JSONField(default=dict, verbose_name="Дополнительные характеристики")
    product_properties = models.JSONField(default=dict, verbose_name="Свойства продукта")
    
    # Статус и даты
    is_active = models.BooleanField(default=True, verbose_name="Активен")
    is_uploaded_to_hood = models.BooleanField(default=False, verbose_name="Загружен на Hood.de")
    hood_item_id = models.CharField(max_length=50, blank=True, verbose_name="ID товара на Hood.de")
    
    # Пользователь и даты
    created_by = models.ForeignKey(User, on_delete=models.CASCADE, verbose_name="Создан пользователем")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Создан")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Обновлен")
    uploaded_at = models.DateTimeField(null=True, blank=True, verbose_name="Загружен на Hood.de")

    class Meta:
        verbose_name = "Продукт"
        verbose_name_plural = "Продукты"
        ordering = ['-created_at']

    def __str__(self):
        return self.title

    def get_hood_data(self):
        """Получить данные для загрузки на Hood.de"""
        # Приоритет: hood_category.hood_id > category_id
        category_id = ''
        if self.hood_category and self.hood_category.hood_id:
            category_id = self.hood_category.hood_id
        elif self.category_id:
            category_id = self.category_id
            
        return {
            'itemMode': self.item_mode,
            'categoryID': category_id,
            'itemName': self.title,
            'quantity': self.quantity,
            'condition': self.condition,
            'description': self.html_description or self.description,
            'price': float(self.price),
            'priceStart': float(self.price_start) if self.price_start else None,
            'ean': self.ean,
            'manufacturer': self.manufacturer,
            'weight': float(self.weight) if self.weight else None,
            'images': self.images,
            'productProperties': self.product_properties,
        }


class UploadLog(models.Model):
    """Модель для логов загрузки на Hood.de"""
    
    STATUS_CHOICES = [
        ('pending', 'Ожидает'),
        ('success', 'Успешно'),
        ('error', 'Ошибка'),
        ('duplicate', 'Дубликат'),
    ]

    product = models.ForeignKey(Product, on_delete=models.CASCADE, verbose_name="Продукт")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending', verbose_name="Статус")
    hood_item_id = models.CharField(max_length=50, blank=True, verbose_name="ID товара на Hood.de")
    response_data = models.JSONField(default=dict, verbose_name="Данные ответа")
    error_message = models.TextField(blank=True, verbose_name="Сообщение об ошибке")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Создан")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Обновлен")

    class Meta:
        verbose_name = "Лог загрузки"
        verbose_name_plural = "Логи загрузки"
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.product.title} - {self.get_status_display()}"


class BulkUpload(models.Model):
    """Модель для массовых загрузок"""
    
    STATUS_CHOICES = [
        ('pending', 'Ожидает'),
        ('processing', 'Обрабатывается'),
        ('completed', 'Завершена'),
        ('failed', 'Неудачна'),
    ]

    name = models.CharField(max_length=200, verbose_name="Название")
    description = models.TextField(blank=True, verbose_name="Описание")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending', verbose_name="Статус")
    
    # Статистика
    total_products = models.IntegerField(default=0, verbose_name="Всего продуктов")
    uploaded_products = models.IntegerField(default=0, verbose_name="Загружено продуктов")
    failed_products = models.IntegerField(default=0, verbose_name="Неудачных загрузок")
    
    # Пользователь и даты
    created_by = models.ForeignKey(User, on_delete=models.CASCADE, verbose_name="Создан пользователем")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Создан")
    started_at = models.DateTimeField(null=True, blank=True, verbose_name="Начата")
    completed_at = models.DateTimeField(null=True, blank=True, verbose_name="Завершена")

    class Meta:
        verbose_name = "Массовая загрузка"
        verbose_name_plural = "Массовые загрузки"
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.name} - {self.get_status_display()}"

    def get_progress_percentage(self):
        """Получить процент выполнения"""
        if self.total_products == 0:
            return 0
        return (self.uploaded_products + self.failed_products) / self.total_products * 100