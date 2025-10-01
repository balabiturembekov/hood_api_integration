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
    """Расширенная модель для продуктов с всеми полями Hood.de API"""
    
    # === ОСНОВНЫЕ ПОЛЯ (BASIC FIELDS) ===
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
    title = models.CharField(max_length=200, default="", verbose_name="Название товара")
    description = models.TextField(default="", verbose_name="Описание товара")
    html_description = models.TextField(blank=True, verbose_name="HTML описание")
    
    # Hood.de поля
    item_mode = models.CharField(max_length=20, choices=ITEM_MODE_CHOICES, default='shopProduct', verbose_name="Режим товара")
    hood_category = models.ForeignKey(HoodCategory, on_delete=models.SET_NULL, null=True, blank=True, verbose_name="Категория Hood.de")
    category_id = models.CharField(max_length=20, blank=True, default="", verbose_name="ID категории")
    quantity = models.IntegerField(default=1, verbose_name="Количество")
    condition = models.CharField(max_length=20, choices=CONDITION_CHOICES, default='new', verbose_name="Состояние товара")
    
    # === ЦЕНОВЫЕ ПОЛЯ (PRICE FIELDS) ===
    price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True, verbose_name="Цена")
    price_start = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True, verbose_name="Стартовая цена аукциона")
    list_price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True, verbose_name="Рекомендованная цена (UVP)")
    purchase_price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True, verbose_name="Закупочная цена")
    sales_tax = models.IntegerField(default=19, verbose_name="Налог с продаж (%)")
    
    # === ВРЕМЕННЫЕ ПОЛЯ (TIME FIELDS) ===
    start_date = models.DateField(null=True, blank=True, verbose_name="Дата начала (dd.mm.yyyy)")
    start_time = models.TimeField(null=True, blank=True, verbose_name="Время начала (HH:MM)")
    
    DURATION_CHOICES = [
        (3, '3 дня'),
        (5, '5 дней'),
        (7, '7 дней'),
        (10, '10 дней'),
        (14, '14 дней'),
    ]
    duration_in_days = models.IntegerField(choices=DURATION_CHOICES, default=7, verbose_name="Продолжительность в днях")
    
    AUTO_RENEW_CHOICES = [
        ('yes', 'Да'),
        ('no', 'Нет'),
        ('1', '1'),
        ('0', '0'),
    ]
    auto_renew = models.CharField(max_length=3, choices=AUTO_RENEW_CHOICES, default='no', verbose_name="Автопродление")
    
    # === ПОЛЯ ДОСТАВКИ (SHIPPING FIELDS) ===
    SHIPMETHODS_CHOICES = [
        ('seeDesc_nat', 'Описание - национальная'),
        ('seeDesc_eu', 'Описание - ЕС'),
        ('seeDesc_at', 'Описание - Австрия'),
        ('seeDesc_ch', 'Описание - Швейцария'),
        ('seeDesc_int', 'Описание - международная'),
        ('postletter_nat', 'Почтовое письмо - национальная'),
        ('postletter_eu', 'Почтовое письмо - ЕС'),
        ('postletter_at', 'Почтовое письмо - Австрия'),
        ('postletter_ch', 'Почтовое письмо - Швейцария'),
        ('postletter_int', 'Почтовое письмо - международная'),
        ('DHLsmallPacket_nat', 'DHL малый пакет - национальная'),
        ('DHLsmallPacket_eu', 'DHL малый пакет - ЕС'),
        ('DHLsmallPacket_at', 'DHL малый пакет - Австрия'),
        ('DHLsmallPacket_ch', 'DHL малый пакет - Швейцария'),
        ('DHLsmallPacket_int', 'DHL малый пакет - международная'),
        ('DHLPacket_nat', 'DHL пакет - национальная'),
        ('DHLPacket_eu', 'DHL пакет - ЕС'),
        ('DHLPacket_at', 'DHL пакет - Австрия'),
        ('DHLPacket_ch', 'DHL пакет - Швейцария'),
        ('DHLPacket_int', 'DHL пакет - международная'),
        ('GLS_nat', 'GLS - национальная'),
        ('GLS_eu', 'GLS - ЕС'),
        ('GLS_at', 'GLS - Австрия'),
        ('GLS_ch', 'GLS - Швейцария'),
        ('GLS_int', 'GLS - международная'),
        ('UPS_nat', 'UPS - национальная'),
        ('UPS_eu', 'UPS - ЕС'),
        ('UPS_at', 'UPS - Австрия'),
        ('UPS_ch', 'UPS - Швейцария'),
        ('UPS_int', 'UPS - международная'),
        ('DPD_nat', 'DPD - национальная'),
        ('DPD_eu', 'DPD - ЕС'),
        ('DPD_at', 'DPD - Австрия'),
        ('DPD_ch', 'DPD - Швейцария'),
        ('DPD_int', 'DPD - международная'),
        ('Hermes_nat', 'Hermes - национальная'),
        ('Hermes_eu', 'Hermes - ЕС'),
        ('Hermes_at', 'Hermes - Австрия'),
        ('Hermes_ch', 'Hermes - Швейцария'),
        ('Hermes_int', 'Hermes - международная'),
        ('FedEx_nat', 'FedEx - национальная'),
        ('FedEx_eu', 'FedEx - ЕС'),
        ('FedEx_at', 'FedEx - Австрия'),
        ('FedEx_ch', 'FedEx - Швейцария'),
        ('FedEx_int', 'FedEx - международная'),
        ('TNT_nat', 'TNT - национальная'),
        ('TNT_eu', 'TNT - ЕС'),
        ('TNT_at', 'TNT - Австрия'),
        ('TNT_ch', 'TNT - Швейцария'),
        ('TNT_int', 'TNT - международная'),
        ('pickup_nat', 'Самовывоз - национальная'),
        ('pickup_eu', 'Самовывоз - ЕС'),
        ('pickup_at', 'Самовывоз - Австрия'),
        ('pickup_ch', 'Самовывоз - Швейцария'),
        ('pickup_int', 'Самовывоз - международная'),
    ]
    shipmethods = models.CharField(max_length=500, default='DHLPacket_nat,DHLPacket_eu', verbose_name="Методы доставки")
    weight = models.DecimalField(max_digits=8, decimal_places=3, null=True, blank=True, verbose_name="Вес в кг")
    
    # === ПОЛЯ ОПЛАТЫ (PAYMENT FIELDS) ===
    PAY_OPTIONS_CHOICES = [
        ('wireTransfer', 'Банковский перевод'),
        ('invoice', 'Счет'),
        ('cashOnDelivery', 'Наложенный платеж'),
        ('cash', 'Наличные'),
        ('payPal', 'PayPal'),
        ('sofort', 'Sofort'),
        ('amazon', 'Amazon Pay'),
        ('klarna', 'Klarna'),
    ]
    pay_options = models.CharField(max_length=500, default='wireTransfer,payPal,cashOnDelivery', verbose_name="Варианты оплаты")
    
    # === ПРОДУКТОВЫЕ ПОЛЯ (PRODUCT FIELDS) ===
    ean = models.CharField(max_length=20, blank=True, default="", verbose_name="EAN код")
    isbn = models.CharField(max_length=20, blank=True, default="", verbose_name="ISBN")
    mpn = models.CharField(max_length=100, blank=True, default="", verbose_name="MPN (номер производителя)")
    manufacturer = models.CharField(max_length=100, default='JV Möbel', verbose_name="Производитель")
    item_number = models.CharField(max_length=100, blank=True, default="", verbose_name="Номер товара клиента")
    item_number_unique_flag = models.BooleanField(default=True, verbose_name="Флаг уникальности номера товара")
    
    UNIT_CHOICES = [
        ('g', 'Грамм'),
        ('kg', 'Килограмм'),
        ('ml', 'Миллилитр'),
        ('l', 'Литр'),
        ('m', 'Метр'),
        ('qm', 'Квадратный метр'),
        ('cbm', 'Кубический метр'),
        ('Stk', 'Штука'),
    ]
    unit = models.CharField(max_length=10, choices=UNIT_CHOICES, default='Stk', verbose_name="Единица измерения")
    packaging_size = models.CharField(max_length=100, blank=True, default="", verbose_name="Размер упаковки")
    
    PACKAGING_UNIT_CHOICES = [
        ('g', 'Грамм'),
        ('kg', 'Килограмм'),
        ('ml', 'Миллилитр'),
        ('l', 'Литр'),
        ('m', 'Метр'),
        ('qm', 'Квадратный метр'),
        ('cbm', 'Кубический метр'),
        ('Stk', 'Штука'),
    ]
    packaging_unit = models.CharField(max_length=10, choices=PACKAGING_UNIT_CHOICES, blank=True, default="", verbose_name="Единица упаковки")
    minimum_purchase = models.IntegerField(null=True, blank=True, verbose_name="Минимальное количество покупки")
    
    # === ПОЛЯ ВАРИАНТОВ (VARIANT FIELDS) ===
    product_options = models.JSONField(default=dict, blank=True, verbose_name="Варианты продукта")
    product_properties = models.JSONField(default=dict, blank=True, verbose_name="Свойства продукта")
    
    # === ПОЛЯ ОСОБЕННОСТЕЙ (FEATURE FIELDS) ===
    category2_id = models.CharField(max_length=20, blank=True, default="", verbose_name="Вторая категория")
    item_name_sub_title = models.CharField(max_length=200, blank=True, default="", verbose_name="Подзаголовок товара")
    
    FEATURE_CHOICES = [
        ('yes', 'Да'),
        ('no', 'Нет'),
        ('1', '1'),
        ('0', '0'),
    ]
    feature_bold_title = models.CharField(max_length=3, choices=FEATURE_CHOICES, default='no', verbose_name="Жирный заголовок")
    feature_background_color = models.CharField(max_length=3, choices=FEATURE_CHOICES, default='no', verbose_name="Цветной фон")
    feature_gallery = models.CharField(max_length=3, choices=FEATURE_CHOICES, default='no', verbose_name="Галерея изображений")
    feature_category = models.CharField(max_length=3, choices=FEATURE_CHOICES, default='no', verbose_name="Выделение в категории")
    feature_home_page = models.CharField(max_length=3, choices=FEATURE_CHOICES, default='no', verbose_name="На главной странице")
    feature_home_page_image = models.CharField(max_length=3, choices=FEATURE_CHOICES, default='no', verbose_name="Изображение на главной")
    feature_xxl_image = models.CharField(max_length=3, choices=FEATURE_CHOICES, default='no', verbose_name="XXL изображение")
    
    # === ПОЛЯ МАГАЗИНА (SHOP FIELDS) ===
    prod_cat_id = models.CharField(max_length=20, blank=True, default="", verbose_name="ID категории магазина")
    prod_cat_id2 = models.CharField(max_length=20, blank=True, default="", verbose_name="Дополнительная категория магазина")
    prod_cat_id3 = models.CharField(max_length=20, blank=True, default="", verbose_name="Третья категория магазина")
    short_desc = models.TextField(blank=True, default="", verbose_name="Краткое описание")
    
    IF_IS_SOLD_OUT_CHOICES = [
        ('endLess', 'Бесконечно'),
        ('hide', 'Скрыть'),
    ]
    if_is_sold_out = models.CharField(max_length=10, choices=IF_IS_SOLD_OUT_CHOICES, default='hide', verbose_name="Поведение при отсутствии")
    
    IS_APPROVED_CHOICES = [
        ('yes', 'Да'),
        ('no', 'Нет'),
        ('1', '1'),
        ('0', '0'),
    ]
    is_approved = models.CharField(max_length=3, choices=IS_APPROVED_CHOICES, default='yes', verbose_name="Статус одобрения")
    
    SHOW_ON_START_PAGE_CHOICES = [
        ('0', '0'),
        ('1', '1'),
        ('2', '2'),
    ]
    show_on_start_page = models.CharField(max_length=1, choices=SHOW_ON_START_PAGE_CHOICES, default='0', verbose_name="Показ на главной странице")
    
    # === ПОЛЯ ДОСТАВКИ (DELIVERY FIELDS) ===
    delivery_days_on_stock_from = models.IntegerField(null=True, blank=True, verbose_name="Дни доставки (в наличии ОТ)")
    delivery_days_on_stock_to = models.IntegerField(null=True, blank=True, verbose_name="Дни доставки (в наличии ДО)")
    delivery_days_not_on_stock_from = models.IntegerField(null=True, blank=True, verbose_name="Дни доставки (под заказ ОТ)")
    delivery_days_not_on_stock_to = models.IntegerField(null=True, blank=True, verbose_name="Дни доставки (под заказ ДО)")
    
    # === СПЕЦИАЛЬНЫЕ ПОЛЯ (SPECIAL FIELDS) ===
    FSK_CHOICES = [
        ('0', '0'),
        ('6', '6'),
        ('12', '12'),
        ('16', '16'),
        ('18', '18'),
        ('unknown', 'Неизвестно'),
    ]
    fsk = models.CharField(max_length=10, choices=FSK_CHOICES, blank=True, default="", verbose_name="Возрастные ограничения")
    
    USK_CHOICES = [
        ('0', '0'),
        ('6', '6'),
        ('12', '12'),
        ('16', '16'),
        ('18', '18'),
        ('unknown', 'Неизвестно'),
    ]
    usk = models.CharField(max_length=10, choices=USK_CHOICES, blank=True, default="", verbose_name="Возрастные ограничения USK")
    
    ENERGY_EFFICIENCY_CHOICES = [
        ('A+++', 'A+++'),
        ('A++', 'A++'),
        ('A+', 'A+'),
        ('A', 'A'),
        ('B', 'B'),
        ('C', 'C'),
        ('D', 'D'),
        ('E', 'E'),
        ('F', 'F'),
        ('G', 'G'),
    ]
    energy_efficiency_class = models.CharField(max_length=5, choices=ENERGY_EFFICIENCY_CHOICES, blank=True, default="", verbose_name="Класс энергоэффективности")
    energy_label_url = models.URLField(blank=True, default="", verbose_name="Ссылка на энергетическую этикетку")
    product_info_url = models.URLField(blank=True, default="", verbose_name="Ссылка на технический паспорт")
    deficiency_description = models.TextField(blank=True, default="", verbose_name="Описание дефектов")
    
    WARRANTY_CHOICES = [
        ('yes', 'Да'),
        ('no', 'Нет'),
        ('1', '1'),
        ('0', '0'),
    ]
    warranty_shortened_flag = models.CharField(max_length=3, choices=WARRANTY_CHOICES, default='no', verbose_name="Сокращенная гарантия")
    
    NO_IDENTIFIER_CHOICES = [
        ('1', '1'),
        ('0', '0'),
    ]
    no_identifier_flag = models.CharField(max_length=1, choices=NO_IDENTIFIER_CHOICES, default='0', verbose_name="Флаг отсутствия идентификатора")
    
    # === ПОЛЯ ИЗОБРАЖЕНИЙ (IMAGE FIELDS) ===
    images = models.JSONField(default=list, blank=True, verbose_name="Список изображений")
    
    # === ДОПОЛНИТЕЛЬНЫЕ ПОЛЯ ===
    material = models.CharField(max_length=100, blank=True, default="", verbose_name="Материал")
    color = models.CharField(max_length=50, blank=True, default="", verbose_name="Цвет")
    dimensions = models.CharField(max_length=200, blank=True, default="", verbose_name="Размеры")
    
    # === СТАТУСЫ И МЕТАДАННЫЕ ===
    is_uploaded_to_hood = models.BooleanField(default=False, verbose_name="Загружен на Hood.de")
    hood_item_id = models.CharField(max_length=50, blank=True, null=True, verbose_name="ID товара на Hood.de")
    uploaded_at = models.DateTimeField(null=True, blank=True, verbose_name="Дата загрузки")
    
    # === ПОЛЯ ДЛЯ СОВМЕСТИМОСТИ ===
    custom_specifics = models.JSONField(default=dict, blank=True, verbose_name="Пользовательские характеристики")
    
    # === СИСТЕМНЫЕ ПОЛЯ ===
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, verbose_name="Создано пользователем")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Создано")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Обновлено")

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
        
        # Получаем описание и проверяем его длину
        description = self.html_description or self.description or ''
        
        # Hood.de требует описания минимум 100 символов
        if len(description) < 100:
            # Расширяем описание, добавляя информацию о товаре
            extended_description = f"{description}\n\n"
            extended_description += f"Детали товара:\n"
            extended_description += f"- Название: {self.title}\n"
            if self.manufacturer:
                extended_description += f"- Производитель: {self.manufacturer}\n"
            if self.ean:
                extended_description += f"- EAN: {self.ean}\n"
            if self.mpn:
                extended_description += f"- MPN: {self.mpn}\n"
            extended_description += f"- Состояние: {self.get_condition_display()}\n"
            if self.weight:
                extended_description += f"- Вес: {self.weight} кг\n"
            extended_description += f"- Цена: {self.price} €\n"
            extended_description += f"\nЭтот товар предлагается в отличном состоянии и готов к использованию."
            description = extended_description
            
        return {
            'itemMode': self.item_mode,
            'categoryID': category_id,
            'itemName': self.title,
            'quantity': self.quantity,
            'condition': self.condition,
            'description': description,
            'price': float(self.price) if self.price else None,
            'priceStart': float(self.price_start) if self.price_start else None,
            'listPrice': float(self.list_price) if self.list_price else None,
            'purchasePrice': float(self.purchase_price) if self.purchase_price else None,
            'salesTax': self.sales_tax,
            'startDate': self.start_date.strftime('%d.%m.%Y') if self.start_date else None,
            'startTime': self.start_time.strftime('%H:%M') if self.start_time else None,
            'durationInDays': self.duration_in_days,
            'autoRenew': self.auto_renew,
            'shipmethods': self.shipmethods,
            'weight': float(self.weight) if self.weight else None,
            'payOptions': self.pay_options,
            'ean': self.ean,
            'isbn': self.isbn,
            'mpn': self.mpn,
            'manufacturer': self.manufacturer,
            'itemNumber': self.item_number,
            'itemNumberUniqueFlag': self.item_number_unique_flag,
            'unit': self.unit,
            'packagingSize': self.packaging_size,
            'packagingUnit': self.packaging_unit,
            'minimumPurchase': self.minimum_purchase,
            'productOptions': self.product_options,
            'productProperties': self.product_properties,
            'category2ID': self.category2_id,
            'itemNameSubTitle': self.item_name_sub_title,
            'featureBoldTitle': self.feature_bold_title,
            'featureBackGroundColor': self.feature_background_color,
            'featureGallery': self.feature_gallery,
            'featureCategory': self.feature_category,
            'featureHomePage': self.feature_home_page,
            'featureHomePageImage': self.feature_home_page_image,
            'featureXXLImage': self.feature_xxl_image,
            'prodCatID': self.prod_cat_id,
            'prodCatID2': self.prod_cat_id2,
            'prodCatID3': self.prod_cat_id3,
            'shortDesc': self.short_desc,
            'ifIsSoldOut': self.if_is_sold_out,
            'isApproved': self.is_approved,
            'showOnStartPage': self.show_on_start_page,
            'deliveryDaysOnStockFrom': self.delivery_days_on_stock_from,
            'deliveryDaysOnStockTo': self.delivery_days_on_stock_to,
            'deliveryDaysNotOnStockFrom': self.delivery_days_not_on_stock_from,
            'deliveryDaysNotOnStockTo': self.delivery_days_not_on_stock_to,
            'fsk': self.fsk,
            'usk': self.usk,
            'energyEfficiencyClass': self.energy_efficiency_class,
            'energyLabelUrl': self.energy_label_url,
            'productInfoUrl': self.product_info_url,
            'deficiencyDescription': self.deficiency_description,
            'warrantyShortenedFlag': self.warranty_shortened_flag,
            'noIdentifierFlag': self.no_identifier_flag,
            'images': self.images if isinstance(self.images, list) else [],
        }


class ImportLog(models.Model):
    """Модель для логирования импорта продуктов"""
    STATUS_CHOICES = [
        ('pending', 'В процессе'),
        ('success', 'Успешно'),
        ('error', 'Ошибка'),
        ('partial', 'Частично успешно'),
    ]
    
    file_name = models.CharField(max_length=255, verbose_name="Имя файла")
    total_rows = models.IntegerField(default=0, verbose_name="Всего строк")
    success_count = models.IntegerField(default=0, verbose_name="Успешно импортировано")
    error_count = models.IntegerField(default=0, verbose_name="Ошибок")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending', verbose_name="Статус")
    error_details = models.TextField(blank=True, verbose_name="Детали ошибок")
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, verbose_name="Создано пользователем")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Создано")
    completed_at = models.DateTimeField(null=True, blank=True, verbose_name="Завершено")
    
    class Meta:
        verbose_name = "Лог импорта"
        verbose_name_plural = "Логи импорта"
        ordering = ['-created_at']
    
    def __str__(self):
        return f"Импорт {self.file_name} - {self.get_status_display()}"
    
    def get_success_rate(self):
        """Получить процент успешности импорта"""
        if self.total_rows == 0:
            return 0
        return round((self.success_count / self.total_rows) * 100, 2)


class UploadLog(models.Model):
    """Модель для логов загрузки товаров на Hood.de"""
    
    STATUS_CHOICES = [
        ('pending', 'Ожидает'),
        ('success', 'Успешно'),
        ('error', 'Ошибка'),
        ('cancelled', 'Отменено'),
    ]
    
    product = models.ForeignKey(Product, on_delete=models.CASCADE, verbose_name="Продукт")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending', verbose_name="Статус")
    hood_item_id = models.CharField(max_length=50, blank=True, null=True, verbose_name="ID товара на Hood.de")
    response_data = models.JSONField(default=dict, blank=True, verbose_name="Данные ответа")
    error_message = models.TextField(blank=True, verbose_name="Сообщение об ошибке")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Создано")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Обновлено")

    class Meta:
        verbose_name = "Лог загрузки"
        verbose_name_plural = "Логи загрузки"
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.product.title} - {self.status}"


class BulkUpload(models.Model):
    """Модель для массовых загрузок"""
    
    STATUS_CHOICES = [
        ('pending', 'Ожидает'),
        ('processing', 'Обрабатывается'),
        ('completed', 'Завершено'),
        ('error', 'Ошибка'),
    ]
    
    name = models.CharField(max_length=200, verbose_name="Название")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending', verbose_name="Статус")
    total_products = models.IntegerField(default=0, verbose_name="Всего товаров")
    uploaded_products = models.IntegerField(default=0, verbose_name="Загружено товаров")
    failed_products = models.IntegerField(default=0, verbose_name="Неудачных загрузок")
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, verbose_name="Создано пользователем")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Создано")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Обновлено")

    class Meta:
        verbose_name = "Массовая загрузка"
        verbose_name_plural = "Массовые загрузки"
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.name} - {self.status}"
