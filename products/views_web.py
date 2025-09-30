from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse
from django.core.paginator import Paginator
from django.db.models import Q
from .models import Product, HoodCategory, UploadLog, BulkUpload
from .services import HoodAPIService
import json


def public_home(request):
    """Публичная главная страница (доступна без логина)"""
    return render(request, 'products/public_home.html', {
        'title': 'Hood.de Integration Service',
        'description': 'Сервис интеграции с Hood.de для управления товарами'
    })


@login_required
def dashboard(request):
    """Главная страница дашборда"""
    # Статистика
    total_products = Product.objects.count()
    uploaded_products = Product.objects.filter(is_uploaded_to_hood=True).count()
    active_products = Product.objects.filter(is_approved='yes').count()
    total_categories = HoodCategory.objects.count()
    
    # Последние продукты
    recent_products = Product.objects.select_related('hood_category', 'created_by').order_by('-created_at')[:10]
    
    # Последние загрузки
    recent_uploads = UploadLog.objects.select_related('product').order_by('-created_at')[:5]
    
    # Проверка соединения с Hood.de API
    hood_service = HoodAPIService()
    api_connection = hood_service.check_api_connection()
    
    context = {
        'total_products': total_products,
        'uploaded_products': uploaded_products,
        'active_products': active_products,
        'total_categories': total_categories,
        'upload_percentage': (uploaded_products / total_products * 100) if total_products > 0 else 0,
        'recent_products': recent_products,
        'recent_uploads': recent_uploads,
        'api_connection': api_connection,
    }
    
    return render(request, 'products/dashboard.html', context)


@login_required
def products_list(request):
    """Список продуктов"""
    search_query = request.GET.get('search', '')
    category_filter = request.GET.get('category', '')
    status_filter = request.GET.get('status', '')
    
    products = Product.objects.select_related('hood_category', 'created_by').order_by('-created_at')
    
    # Фильтрация
    if search_query:
        products = products.filter(
            Q(title__icontains=search_query) |
            Q(ean__icontains=search_query) |
            Q(manufacturer__icontains=search_query)
        )
    
    if category_filter:
        products = products.filter(hood_category__id=category_filter)
    
    if status_filter == 'uploaded':
        products = products.filter(is_uploaded_to_hood=True)
    elif status_filter == 'not_uploaded':
        products = products.filter(is_uploaded_to_hood=False)
    
    # Пагинация
    paginator = Paginator(products, 20)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    # Категории для фильтра
    categories = HoodCategory.objects.filter(is_active=True).order_by('name')
    
    # Добавляем дополнительные поля для каждого продукта
    for product in page_obj.object_list:
        product.created_by_username = product.created_by.username if product.created_by else 'Неизвестно'
        product.hood_category_name = product.hood_category.name if product.hood_category else None
    
    context = {
        'page_obj': page_obj,
        'categories': categories,
        'search_query': search_query,
        'category_filter': category_filter,
        'status_filter': status_filter,
    }
    
    return render(request, 'products/products_list.html', context)


@login_required
def product_detail(request, pk):
    """Детальная страница продукта"""
    product = Product.objects.select_related('hood_category', 'created_by').get(pk=pk)
    
    # Логи загрузки
    upload_logs = UploadLog.objects.filter(product=product).order_by('-created_at')
    
    # Добавляем дополнительные поля для шаблона
    product.created_by_username = product.created_by.username if product.created_by else 'Неизвестно'
    
    context = {
        'product': product,
        'upload_logs': upload_logs,
    }
    
    return render(request, 'products/product_detail.html', context)


@login_required
def upload_product(request, pk):
    """Загрузка продукта на Hood.de"""
    if request.method == 'POST':
        try:
            product = Product.objects.get(pk=pk)
            
            if product.is_uploaded_to_hood:
                messages.error(request, 'Продукт уже загружен на Hood.de')
                return redirect('product_detail', pk=pk)
            
            # Получаем данные для загрузки
            hood_data = product.get_hood_data()
            
            # Загружаем на Hood.de
            hood_service = HoodAPIService()
            result = hood_service.upload_item(hood_data)
            
            if result.get('success'):
                # Обновляем продукт
                product.is_uploaded_to_hood = True
                product.hood_item_id = result.get('item_id', '')
                product.save()
                
                # Проверяем, существует ли товар уже
                if result.get('already_exists'):
                    messages.warning(request, f'Товар уже существует на Hood.de! ID: {result.get("item_id")}')
                else:
                    messages.success(request, f'Продукт успешно загружен на Hood.de! ID: {result.get("item_id")}')
            else:
                messages.error(request, f'Ошибка загрузки: {result.get("error", "Неизвестная ошибка")}')
            
        except Product.DoesNotExist:
            messages.error(request, 'Продукт не найден')
        except Exception as e:
            messages.error(request, f'Ошибка: {str(e)}')
    
    return redirect('product_detail', pk=pk)


@login_required
def delete_product(request, pk):
    """Удаление товара с Hood.de"""
    try:
        product = Product.objects.get(pk=pk)
        
        if not product.is_uploaded_to_hood or not product.hood_item_id:
            messages.error(request, 'Товар не загружен на Hood.de или не имеет ID')
            return redirect('product_detail', pk=pk)
        
        if request.method == 'POST':
            try:
                hood_service = HoodAPIService()
                result = hood_service.delete_item(product.hood_item_id)
                
                if result.get('success'):
                    # Обновляем товар в базе данных
                    product.is_uploaded_to_hood = False
                    product.hood_item_id = None
                    product.save()
                    
                    messages.success(request, f'Товар "{product.title}" успешно удален с Hood.de')
                else:
                    error = result.get('error', 'Неизвестная ошибка')
                    messages.error(request, f'Ошибка удаления: {error}')
                    
            except Exception as e:
                messages.error(request, f'Ошибка при удалении: {str(e)}')
            
            return redirect('product_detail', pk=pk)
        
        # GET запрос - показываем страницу подтверждения
        return render(request, 'products/delete_confirm.html', {
            'product': product
        })
        
    except Product.DoesNotExist:
        messages.error(request, 'Продукт не найден')
        return redirect('products_list')


@login_required
def bulk_upload(request):
    """Массовая загрузка продуктов"""
    if request.method == 'POST':
        product_ids = request.POST.getlist('product_ids')
        name = request.POST.get('name', '')
        
        if not product_ids or not name:
            messages.error(request, 'Необходимо выбрать продукты и указать название')
            return redirect('products_list')
        
        try:
            # Создаем запись о массовой загрузке
            bulk_upload = BulkUpload.objects.create(
                name=name,
                total_products=len(product_ids),
                created_by=request.user
            )
            
            # Получаем продукты
            products = Product.objects.filter(id__in=product_ids)
            
            # Запускаем загрузку
            hood_service = HoodAPIService()
            uploaded_count = 0
            failed_count = 0
            
            bulk_upload.status = 'processing'
            bulk_upload.save()
            
            for product in products:
                try:
                    hood_data = product.get_hood_data()
                    result = hood_service.upload_item(hood_data)
                    
                    if result.get('success'):
                        product.is_uploaded_to_hood = True
                        product.hood_item_id = result.get('item_id', '')
                        product.save()
                        uploaded_count += 1
                    else:
                        failed_count += 1
                        
                except Exception as e:
                    failed_count += 1
            
            # Обновляем статистику
            bulk_upload.uploaded_products = uploaded_count
            bulk_upload.failed_products = failed_count
            bulk_upload.status = 'completed'
            bulk_upload.save()
            
            messages.success(request, f'Массовая загрузка завершена! Загружено: {uploaded_count}, Ошибок: {failed_count}')
            
        except Exception as e:
            messages.error(request, f'Ошибка массовой загрузки: {str(e)}')
    
    return redirect('products_list')


@login_required
def sync_categories(request):
    """Синхронизация категорий с Hood.de"""
    if request.method == 'POST':
        try:
            hood_service = HoodAPIService()
            
            # Сначала пробуем получить категории через API
            result = hood_service.get_categories()
            
            # Если API не работает, используем fallback
            if not result.get('success'):
                messages.warning(request, f'API недоступен: {result.get("error")}. Используем локальные категории.')
                result = hood_service.get_categories_fallback()
            
            if result.get('success'):
                categories_data = result.get('categories', [])
                created_count = 0
                updated_count = 0
                source = result.get('source', 'api')
                
                for cat_data in categories_data:
                    hood_id = cat_data.get('id', '')
                    if not hood_id:
                        continue
                        
                    category, created = HoodCategory.objects.get_or_create(
                        hood_id=hood_id,
                        defaults={
                            'name': cat_data.get('name', ''),
                            'path': cat_data.get('path', ''),
                            'level': int(cat_data.get('level', 0))
                        }
                    )
                    
                    if created:
                        created_count += 1
                    else:
                        category.name = cat_data.get('name', '')
                        category.path = cat_data.get('path', '')
                        category.level = int(cat_data.get('level', 0))
                        category.save()
                        updated_count += 1
                
                source_text = "из API Hood.de" if source == 'api' else "из локального файла"
                total_categories = HoodCategory.objects.count()
                messages.success(request, f'Синхронизация завершена {source_text}! Создано: {created_count}, Обновлено: {updated_count}. Всего категорий в базе: {total_categories}')
            else:
                messages.error(request, f'Ошибка синхронизации: {result.get("error")}')
                
        except Exception as e:
            messages.error(request, f'Ошибка: {str(e)}')
    
    return redirect('dashboard')


@login_required
def api_test(request):
    """Тестирование API Hood.de"""
    if request.method == 'POST':
        try:
            hood_service = HoodAPIService()
            
            # Тестируем получение категорий
            result = hood_service.get_categories()
            
            if result.get('success'):
                categories_count = len(result.get('categories', []))
                messages.success(request, f'API работает! Получено категорий: {categories_count}')
            else:
                messages.error(request, f'Ошибка API: {result.get("error")}')
                
        except Exception as e:
            messages.error(request, f'Ошибка: {str(e)}')
    
    return redirect('dashboard')


@login_required
def check_api_connection(request):
    """AJAX endpoint для проверки соединения с API"""
    if request.method == 'GET':
        try:
            hood_service = HoodAPIService()
            result = hood_service.check_api_connection()
            return JsonResponse(result)
        except Exception as e:
            return JsonResponse({
                'success': False,
                'status': 'error',
                'message': f'Ошибка проверки соединения: {str(e)}'
            })
    
    return JsonResponse({'success': False, 'message': 'Метод не поддерживается'})


@login_required
def hood_items_list(request):
    """Список товаров с Hood.de (itemList)"""
    # Параметры фильтрации
    item_status = request.GET.get('status', 'running')
    page = int(request.GET.get('page', 1))
    page_size = int(request.GET.get('page_size', 20))
    start_date = request.GET.get('start_date', '')
    end_date = request.GET.get('end_date', '')
    
    # Валидация статуса
    valid_statuses = ['running', 'sold', 'unsuccessful']
    if item_status not in valid_statuses:
        item_status = 'running'
    
    # Подготовка параметров для API
    date_range = None
    if start_date and end_date:
        date_range = {
            'startDate': start_date,
            'endDate': end_date
        }
    
    try:
        hood_service = HoodAPIService()
        
        # Получаем товары с пагинацией
        result = hood_service.get_items_paginated(
            item_status=item_status,
            page=page,
            page_size=page_size,
            date_range=date_range
        )
        
        if result.get('success'):
            items = result.get('items', [])
            pagination = result.get('pagination', {})
            
            # Добавляем дополнительную информацию для шаблона
            for item in items:
                item['status_display'] = get_status_display(item_status)
                item['status_class'] = get_status_class(item_status)
        else:
            items = []
            pagination = {}
            error_message = result.get("error", "Неизвестная ошибка")
            error_type = result.get("error_type", "unknown")
            
            # Более информативные сообщения об ошибках
            if error_type == 'html_response':
                messages.error(request, f'API вернул HTML вместо XML. Проверьте настройки подключения.')
            elif error_type == 'global_error':
                messages.error(request, f'Ошибка API: {error_message}')
            elif error_type == 'missing_response':
                messages.error(request, f'Некорректный ответ API: {error_message}')
            elif error_type == 'xml_parse_error':
                messages.error(request, f'Ошибка парсинга XML: {error_message}')
            else:
                messages.error(request, f'Ошибка получения товаров: {error_message}')
            
    except Exception as e:
        items = []
        pagination = {}
        messages.error(request, f'Ошибка: {str(e)}')
    
    context = {
        'items': items,
        'pagination': pagination,
        'current_status': item_status,
        'statuses': [
            {'value': 'running', 'label': 'Активные товары'},
            {'value': 'sold', 'label': 'Проданные товары'},
            {'value': 'unsuccessful', 'label': 'Непроданные товары'},
        ],
        'start_date': start_date,
        'end_date': end_date,
    }
    
    return render(request, 'products/hood_items_list.html', context)


@login_required
def hood_item_status(request, item_id):
    """Детальная информация о товаре с Hood.de (itemStatus)"""
    detail_level = request.GET.get('detail_level', 'image,description')
    
    # Парсим уровни детализации
    detail_levels = []
    if detail_level:
        detail_levels = [level.strip() for level in detail_level.split(',')]
    
    try:
        hood_service = HoodAPIService()
        
        # Получаем детальную информацию о товаре
        result = hood_service.get_item_status_by_id(item_id, detail_levels)
        
        if result.get('success'):
            items = result.get('items', [])
            item = items[0] if items else None
            
            if item:
                # Добавляем дополнительную информацию для шаблона
                item['has_images'] = bool(item.get('images'))
                item['has_description'] = bool(item.get('description'))
                item['has_properties'] = bool(item.get('productProperties'))
                
                # Форматируем цены
                if item.get('price'):
                    try:
                        item['price_formatted'] = f"{float(item['price']):.2f} €"
                    except (ValueError, TypeError):
                        item['price_formatted'] = item['price']
                
                # Форматируем даты
                if item.get('startDate'):
                    item['start_date_formatted'] = format_date(item['startDate'])
                if item.get('endDate'):
                    item['end_date_formatted'] = format_date(item['endDate'])
            else:
                messages.error(request, 'Товар не найден в ответе API')
                return redirect('hood_items_list')
        else:
            error_message = result.get("error", "Неизвестная ошибка")
            error_type = result.get("error_type", "unknown")
            
            # Более информативные сообщения об ошибках
            if error_type == 'html_response':
                messages.error(request, f'API вернул HTML вместо XML. Проверьте настройки подключения.')
            elif error_type == 'global_error':
                messages.error(request, f'Ошибка API: {error_message}')
            elif error_type == 'missing_response':
                messages.error(request, f'Некорректный ответ API: {error_message}')
            elif error_type == 'xml_parse_error':
                messages.error(request, f'Ошибка парсинга XML: {error_message}')
            else:
                messages.error(request, f'Ошибка получения информации о товаре: {error_message}')
            return redirect('hood_items_list')
            
    except Exception as e:
        messages.error(request, f'Ошибка: {str(e)}')
        return redirect('hood_items_list')
    
    context = {
        'item': item,
        'detail_levels': detail_levels,
        'available_detail_levels': [
            {'value': 'image', 'label': 'Изображения'},
            {'value': 'description', 'label': 'Описание'},
        ],
    }
    
    return render(request, 'products/hood_item_status.html', context)


@login_required
def hood_items_analysis(request):
    """Анализ товаров с Hood.de"""
    analysis_type = request.GET.get('type', 'summary')
    item_status = request.GET.get('status', 'running')
    days = int(request.GET.get('days', 7))
    
    try:
        hood_service = HoodAPIService()
        
        if analysis_type == 'summary':
            # Сводка по товарам
            result = hood_service.get_items_summary(item_status)
            analysis_data = result.get('summary', {}) if result.get('success') else {}
            
        elif analysis_type == 'recent':
            # Товары за последние N дней
            result = hood_service.get_recent_items(days, item_status)
            analysis_data = {
                'items': result.get('items', []),
                'total_records': result.get('total_records', 0),
                'days': days
            } if result.get('success') else {}
            
        elif analysis_type == 'detailed':
            # Детальный анализ (требует ID товаров)
            item_ids = request.GET.getlist('item_ids')
            if item_ids:
                result = hood_service.get_items_detailed_status(item_ids)
                analysis_data = result.get('detailed_status', {}) if result.get('success') else {}
            else:
                analysis_data = {}
                messages.warning(request, 'Для детального анализа необходимо выбрать товары')
                
        else:
            analysis_data = {}
            
    except Exception as e:
        analysis_data = {}
        messages.error(request, f'Ошибка анализа: {str(e)}')
    
    context = {
        'analysis_type': analysis_type,
        'analysis_data': analysis_data,
        'current_status': item_status,
        'days': days,
        'analysis_types': [
            {'value': 'summary', 'label': 'Сводка'},
            {'value': 'recent', 'label': 'За последние дни'},
            {'value': 'detailed', 'label': 'Детальный анализ'},
        ],
        'statuses': [
            {'value': 'running', 'label': 'Активные товары'},
            {'value': 'sold', 'label': 'Проданные товары'},
            {'value': 'unsuccessful', 'label': 'Непроданные товары'},
        ],
    }
    
    return render(request, 'products/hood_items_analysis.html', context)


@login_required
def hood_items_compare(request):
    """Сравнение товаров с Hood.de"""
    if request.method == 'POST':
        item_ids = request.POST.getlist('item_ids')
        
        if len(item_ids) < 2:
            messages.error(request, 'Для сравнения необходимо выбрать минимум 2 товара')
            return redirect('hood_items_list')
        
        try:
            hood_service = HoodAPIService()
            result = hood_service.compare_items_status(item_ids)
            
            if result.get('success'):
                comparison_data = result.get('comparison', {})
            else:
                messages.error(request, f'Ошибка сравнения: {result.get("error")}')
                return redirect('hood_items_list')
                
        except Exception as e:
            messages.error(request, f'Ошибка: {str(e)}')
            return redirect('hood_items_list')
        
        context = {
            'comparison_data': comparison_data,
            'item_ids': item_ids,
        }
        
        return render(request, 'products/hood_items_compare.html', context)
    
    # GET запрос - показываем форму выбора товаров
    return redirect('hood_items_list')


def get_status_display(status):
    """Получение отображаемого названия статуса"""
    status_map = {
        'running': 'Активные',
        'sold': 'Проданные',
        'unsuccessful': 'Непроданные'
    }
    return status_map.get(status, status)


def get_status_class(status):
    """Получение CSS класса для статуса"""
    status_map = {
        'running': 'success',
        'sold': 'info',
        'unsuccessful': 'warning'
    }
    return status_map.get(status, 'secondary')


def format_date(date_str):
    """Форматирование даты для отображения"""
    try:
        from datetime import datetime
        # Предполагаем формат даты от Hood.de
        if isinstance(date_str, str) and len(date_str) > 10:
            # Убираем лишние символы и парсим
            clean_date = date_str.replace('{ts \'', '').replace('\'}', '')
            dt = datetime.strptime(clean_date, '%Y-%m-%d %H:%M:%S')
            return dt.strftime('%d.%m.%Y %H:%M')
        return date_str
    except:
        return date_str
