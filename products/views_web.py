from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse
from django.core.paginator import Paginator
from django.db.models import Q
from .services import HoodAPIService
from .models import Product, HoodCategory, UploadLog, BulkUpload, ImportLog, Order, OrderItem, OrderSyncLog
import json
import logging
import csv
import io
from django.utils import timezone
from django.db import transaction

logger = logging.getLogger(__name__)


def public_home(request):
    """Публичная главная страница (доступна без логина)"""
    return render(request, 'products/public_home.html', {
        'title': 'Hood.de Integration Service',
        'description': 'Сервис интеграции с Hood.de для управления товарами'
    })


@login_required
def dashboard(request):
    """Главная страница дашборда"""
    from django.db.models import Sum
    
    # Статистика продуктов
    total_products = Product.objects.count()
    uploaded_products = Product.objects.filter(is_uploaded_to_hood=True).count()
    active_products = Product.objects.filter(is_approved='yes').count()
    total_categories = HoodCategory.objects.count()
    
    # Статистика заказов
    total_orders = Order.objects.count()
    new_orders = Order.objects.filter(status='new').count()
    today = timezone.now().date()
    today_orders = Order.objects.filter(order_date__date=today).count()
    total_revenue = Order.objects.aggregate(total=Sum('total_amount'))['total'] or 0
    
    # Последние продукты
    recent_products = Product.objects.select_related('hood_category', 'created_by').order_by('-created_at')[:10]
    
    # Последние загрузки
    recent_uploads = UploadLog.objects.select_related('product').order_by('-created_at')[:5]
    
    # Последние заказы
    recent_orders = Order.objects.order_by('-order_date')[:5]
    
    # Проверка соединения с Hood.de API
    hood_service = HoodAPIService()
    api_connection = hood_service.check_api_connection()
    
    context = {
        'total_products': total_products,
        'uploaded_products': uploaded_products,
        'active_products': active_products,
        'total_categories': total_categories,
        'total_orders': total_orders,
        'new_orders': new_orders,
        'today_orders': today_orders,
        'total_revenue': total_revenue,
        'upload_percentage': (uploaded_products / total_products * 100) if total_products > 0 else 0,
        'recent_products': recent_products,
        'recent_uploads': recent_uploads,
        'recent_orders': recent_orders,
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
            
            # Создаем лог загрузки
            upload_log = UploadLog.objects.create(
                product=product,
                status='pending'
            )
            
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
                
                # Обновляем лог как успешный
                upload_log.status = 'success'
                upload_log.hood_item_id = result.get('item_id', '')
                upload_log.response_data = result
                upload_log.save()
                
                # Проверяем, существует ли товар уже
                if result.get('already_exists'):
                    messages.warning(request, f'Товар уже существует на Hood.de! ID: {result.get("item_id")}')
                else:
                    messages.success(request, f'Продукт успешно загружен на Hood.de! ID: {result.get("item_id")}')
            else:
                # Обновляем лог как ошибочный
                upload_log.status = 'error'
                upload_log.error_message = result.get('error', 'Неизвестная ошибка')
                upload_log.response_data = result
                upload_log.save()
                
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
                # Создаем лог для каждого товара
                upload_log = UploadLog.objects.create(
                    product=product,
                    status='pending'
                )
                
                try:
                    hood_data = product.get_hood_data()
                    result = hood_service.upload_item(hood_data)
                    
                    if result.get('success'):
                        product.is_uploaded_to_hood = True
                        product.hood_item_id = result.get('item_id', '')
                        product.save()
                        uploaded_count += 1
                        
                        # Обновляем лог как успешный
                        upload_log.status = 'success'
                        upload_log.hood_item_id = result.get('item_id', '')
                        upload_log.response_data = result
                        upload_log.save()
                        
                        logger.info(f"Продукт {product.id} ({product.title}) успешно загружен")
                    else:
                        failed_count += 1
                        error_msg = result.get('error', 'Неизвестная ошибка')
                        
                        # Обновляем лог как ошибочный
                        upload_log.status = 'error'
                        upload_log.error_message = error_msg
                        upload_log.response_data = result
                        upload_log.save()
                        
                        logger.error(f"Ошибка загрузки продукта {product.id} ({product.title}): {error_msg}")
                        
                except Exception as e:
                    failed_count += 1
                    
                    # Обновляем лог как ошибочный
                    upload_log.status = 'error'
                    upload_log.error_message = str(e)
                    upload_log.save()
                    
                    logger.error(f"Исключение при загрузке продукта {product.id} ({product.title}): {str(e)}")
            
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


@login_required
def get_all_product_ids(request):
    """Получить все ID товаров для массовой загрузки"""
    try:
        # Получаем все ID товаров, которые еще не загружены на Hood.de
        product_ids = Product.objects.filter(is_uploaded_to_hood=False).values_list('id', flat=True)
        return JsonResponse({
            'success': True,
            'product_ids': list(product_ids),
            'count': len(product_ids)
        })
    except Exception as e:
        logger.error(f"Ошибка получения списка товаров: {str(e)}")
        return JsonResponse({'success': False, 'error': str(e)})
    
    return JsonResponse({'success': False, 'message': 'Метод не поддерживается'})


@login_required
def bulk_delete(request):
    """Массовое удаление продуктов"""
    if request.method == 'POST':
        try:
            import json as json_lib
            data = json_lib.loads(request.body)
            product_ids = data.get('product_ids', [])
            
            if not product_ids:
                return JsonResponse({'success': False, 'error': 'Не указаны ID продуктов'})
            
            # Получаем продукты для удаления
            products_to_delete = Product.objects.filter(id__in=product_ids)
            hood_deleted_count = 0
            errors = []
            
            for product in products_to_delete:
                try:
                    # Если товар загружен на Hood.de, удаляем его оттуда
                    if product.is_uploaded_to_hood and product.hood_item_id:
                        hood_service = HoodAPIService()
                        hood_result = hood_service.delete_item(product.hood_item_id)
                        
                        if hood_result.get('success'):
                            hood_deleted_count += 1
                            # Обновляем статус в локальной БД - помечаем как не загруженный
                            product.is_uploaded_to_hood = False
                            product.hood_item_id = ''
                            product.save()
                            logger.info(f"Товар {product.id} ({product.title}) удален с Hood.de")
                        else:
                            error_msg = hood_result.get('error', 'Неизвестная ошибка')
                            errors.append(f"Товар {product.id}: {error_msg}")
                            logger.error(f"Ошибка удаления товара {product.id} с Hood.de: {error_msg}")
                    else:
                        # Товар не загружен на Hood.de
                        errors.append(f"Товар {product.id}: не загружен на Hood.de")
                    
                except Exception as e:
                    error_msg = str(e)
                    errors.append(f"Товар {product.id}: {error_msg}")
                    logger.error(f"Ошибка удаления товара {product.id}: {error_msg}")
            
            logger.info(f"Массово удалено с Hood.de {hood_deleted_count} продуктов пользователем {request.user.username}")
            
            # Формируем сообщение
            message = f'Успешно удалено с Hood.de {hood_deleted_count} продуктов'
            if errors:
                message += f'. Ошибки: {len(errors)} товаров'
            
            return JsonResponse({
                'success': True,
                'deleted_count': hood_deleted_count,  # Для совместимости с фронтендом
                'hood_deleted_count': hood_deleted_count,
                'errors': errors,
                'message': message
            })
            
        except Exception as e:
            logger.error(f"Ошибка массового удаления: {str(e)}")
            return JsonResponse({'success': False, 'error': str(e)})
    
    return JsonResponse({'success': False, 'error': 'Метод не поддерживается'})


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
                if item.get('dateFrom'):
                    item['start_date_formatted'] = format_date(item['dateFrom'])
                if item.get('dateTo'):
                    item['end_date_formatted'] = format_date(item['dateTo'])
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
    
    else:
        # GET запрос - показываем форму для выбора товаров для сравнения
        try:
            hood_service = HoodAPIService()
            
            # Получаем список товаров для выбора
            result = hood_service.get_item_list('running', 1, 50)
            
            if result.get('success'):
                items = result.get('items', [])
            else:
                items = []
                messages.warning(request, f'Не удалось загрузить список товаров: {result.get("error", "Неизвестная ошибка")}')
            
            context = {
                'items': items,
                'page_title': 'Сравнение товаров Hood.de',
            }
            
            return render(request, 'products/hood_items_compare_form.html', context)
            
        except Exception as e:
            messages.error(request, f'Ошибка загрузки товаров: {str(e)}')
            return redirect('hood_items_list')


@login_required
def import_products(request):
    """Импорт продуктов из CSV файла"""
    if request.method == 'GET':
        # GET запрос - показываем форму импорта
        return render(request, 'products/import_products.html', {
            'title': 'Импорт продуктов из CSV'
        })
    
    if request.method == 'POST':
        try:
            csv_file = request.FILES.get('csv_file')
            if not csv_file:
                return JsonResponse({'success': False, 'error': 'Файл не выбран'})
            
            if not csv_file.name.endswith('.csv'):
                return JsonResponse({'success': False, 'error': 'Файл должен быть в формате CSV'})
            
            # Создаем лог импорта
            import_log = ImportLog.objects.create(
                file_name=csv_file.name,
                created_by=request.user,
                status='pending'
            )
            
            # Читаем CSV файл
            try:
                # Декодируем файл как UTF-8
                file_content = csv_file.read().decode('utf-8')
                csv_reader = csv.DictReader(io.StringIO(file_content))
                
                # Получаем заголовки
                headers = csv_reader.fieldnames
                logger.info(f"Заголовки CSV: {headers}")
                
                # Маппинг полей CSV на поля модели
                field_mapping = {
                    'title': ['title', 'name', 'название', 'товар'],
                    'description': ['description', 'описание', 'desc'],
                    'price': ['price', 'цена', 'cost'],
                    'quantity': ['quantity', 'количество', 'qty'],
                    'condition': ['condition', 'состояние', 'состояние_товара'],
                    'manufacturer': ['manufacturer', 'производитель', 'brand'],
                    'ean': ['ean', 'EAN', 'штрихкод'],
                    'mpn': ['mpn', 'MPN', 'артикул'],
                    'weight': ['weight', 'вес', 'масса'],
                    'category': ['category', 'категория', 'cat'],
                    'images': ['images', 'изображения', 'фото'],
                }
                
                success_count = 0
                error_count = 0
                errors = []
                
                # Обрабатываем каждую строку
                for row_num, row in enumerate(csv_reader, start=2):  # Начинаем с 2, так как 1 - заголовки
                    try:
                        # Создаем продукт
                        product_data = {}
                        
                        # Маппим поля
                        for field_name, csv_headers in field_mapping.items():
                            for csv_header in csv_headers:
                                if csv_header in row and row[csv_header]:
                                    product_data[field_name] = row[csv_header].strip()
                                    break
                        
                        # Валидация обязательных полей
                        if not product_data.get('title'):
                            errors.append(f"Строка {row_num}: Отсутствует название товара")
                            error_count += 1
                            continue
                        
                        if not product_data.get('price'):
                            errors.append(f"Строка {row_num}: Отсутствует цена")
                            error_count += 1
                            continue
                        
                        # Обработка цены
                        try:
                            price_str = product_data.get('price', '0').replace(',', '.').replace('€', '').replace('$', '').strip()
                            product_data['price'] = float(price_str)
                        except ValueError:
                            errors.append(f"Строка {row_num}: Неверный формат цены: {product_data.get('price')}")
                            error_count += 1
                            continue
                        
                        # Обработка количества
                        if product_data.get('quantity'):
                            try:
                                product_data['quantity'] = int(product_data['quantity'])
                            except ValueError:
                                product_data['quantity'] = 1
                        else:
                            product_data['quantity'] = 1
                        
                        # Обработка веса
                        if product_data.get('weight'):
                            try:
                                weight_str = product_data['weight'].replace(',', '.').replace('kg', '').replace('кг', '').strip()
                                product_data['weight'] = float(weight_str)
                            except ValueError:
                                product_data['weight'] = None
                        
                        # Обработка состояния
                        condition_map = {
                            'новый': 'new',
                            'как новый': 'likeNew',
                            'очень хорошее': 'veryGood',
                            'удовлетворительное': 'acceptable',
                            'восстановленный': 'refurbished',
                            'с дефектом': 'defect',
                            'б/у хорошее': 'usedGood',
                        }
                        if product_data.get('condition'):
                            condition_lower = product_data['condition'].lower()
                            product_data['condition'] = condition_map.get(condition_lower, 'new')
                        else:
                            product_data['condition'] = 'new'
                        
                        # Обработка изображений
                        if product_data.get('images'):
                            # Разделяем изображения по запятой или точке с запятой
                            images_str = product_data['images']
                            images_list = [img.strip() for img in images_str.replace(';', ',').split(',') if img.strip()]
                            product_data['images'] = images_list
                        
                        # Создаем продукт
                        product = Product.objects.create(
                            title=product_data['title'],
                            description=product_data.get('description', ''),
                            price=product_data['price'],
                            quantity=product_data['quantity'],
                            condition=product_data['condition'],
                            manufacturer=product_data.get('manufacturer', ''),
                            ean=product_data.get('ean', ''),
                            mpn=product_data.get('mpn', ''),
                            weight=product_data.get('weight'),
                            images=product_data.get('images', []),
                            created_by=request.user
                        )
                        
                        success_count += 1
                        logger.info(f"Импортирован продукт: {product.title}")
                        
                    except Exception as e:
                        error_msg = f"Строка {row_num}: {str(e)}"
                        errors.append(error_msg)
                        error_count += 1
                        logger.error(f"Ошибка импорта строки {row_num}: {str(e)}")
                
                # Обновляем лог импорта
                import_log.total_rows = success_count + error_count
                import_log.success_count = success_count
                import_log.error_count = error_count
                import_log.error_details = '\n'.join(errors[:50])  # Ограничиваем количество ошибок
                import_log.completed_at = timezone.now()
                
                if error_count == 0:
                    import_log.status = 'success'
                elif success_count == 0:
                    import_log.status = 'error'
                else:
                    import_log.status = 'partial'
                
                import_log.save()
                
                logger.info(f"Импорт завершен: {success_count} успешно, {error_count} ошибок")
                
                return JsonResponse({
                    'success': True,
                    'message': f'Импорт завершен: {success_count} товаров импортировано, {error_count} ошибок',
                    'success_count': success_count,
                    'error_count': error_count,
                    'total_rows': import_log.total_rows,
                    'errors': errors[:10]  # Показываем только первые 10 ошибок
                })
                
            except UnicodeDecodeError:
                return JsonResponse({'success': False, 'error': 'Ошибка кодировки файла. Убедитесь, что файл сохранен в UTF-8'})
            except Exception as e:
                logger.error(f"Ошибка чтения CSV файла: {str(e)}")
                return JsonResponse({'success': False, 'error': f'Ошибка чтения файла: {str(e)}'})
                
        except Exception as e:
            logger.error(f"Ошибка импорта: {str(e)}")
            return JsonResponse({'success': False, 'error': str(e)})
    
    return JsonResponse({'success': False, 'error': 'Метод не поддерживается'})


@login_required
def auto_assign_subcategories(request):
    """Автоматическое назначение подкатегорий товарам"""
    if request.method == 'POST':
        try:
            hood_service = HoodAPIService()
            result = hood_service.auto_assign_subcategories()
            
            if result.get('success'):
                assigned_count = result.get('assigned_count', 0)
                total_processed = result.get('total_processed', 0)
                errors = result.get('errors', [])
                
                if assigned_count > 0:
                    messages.success(request, f'Успешно назначено подкатегорий: {assigned_count} из {total_processed} товаров')
                else:
                    messages.info(request, 'Все товары уже имеют назначенные категории')
                
                if errors:
                    for error in errors[:5]:  # Показываем только первые 5 ошибок
                        messages.warning(request, error)
            else:
                messages.error(request, f'Ошибка назначения подкатегорий: {result.get("error")}')
                
        except Exception as e:
            messages.error(request, f'Ошибка: {str(e)}')
    
    return redirect('products_list')


@login_required
def sync_full_categories(request):
    """Синхронизация полной иерархии категорий с Hood.de"""
    if request.method == 'POST':
        try:
            hood_service = HoodAPIService()
            
            # Получаем полную иерархию категорий
            result = hood_service.get_full_category_hierarchy()
            
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
                
                source_text = "из полной иерархии API Hood.de" if source == 'api_full_hierarchy' else "из локального файла"
                total_categories = HoodCategory.objects.count()
                messages.success(request, f'Синхронизация полной иерархии завершена {source_text}! Создано: {created_count}, Обновлено: {updated_count}. Всего категорий в базе: {total_categories}')
            else:
                messages.error(request, f'Ошибка синхронизации: {result.get("error")}')
                
        except Exception as e:
            messages.error(request, f'Ошибка: {str(e)}')
    
    return redirect('dashboard')


@login_required
def import_logs(request):
    """Список логов импорта"""
    logs = ImportLog.objects.all().order_by('-created_at')
    paginator = Paginator(logs, 20)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    return render(request, 'products/import_logs.html', {
        'page_obj': page_obj,
        'title': 'Логи импорта'
    })


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


# ==================== ЗАКАЗЫ ====================

@login_required
def orders_list(request):
    """Список заказов"""
    orders = Order.objects.prefetch_related('items').order_by('-order_date')
    
    # Фильтрация
    status_filter = request.GET.get('status')
    if status_filter:
        orders = orders.filter(status=status_filter)
    
    buyer_filter = request.GET.get('buyer')
    if buyer_filter:
        orders = orders.filter(buyer_username__icontains=buyer_filter)
    
    search = request.GET.get('search')
    if search:
        orders = orders.filter(
            Q(hood_order_id__icontains=search) |
            Q(order_number__icontains=search) |
            Q(buyer_username__icontains=search) |
            Q(buyer_name__icontains=search)
        )
    
    # Пагинация
    paginator = Paginator(orders, 20)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    # Статистика для фильтров
    status_stats = {}
    for status_code, status_name in Order.STATUS_CHOICES:
        count = Order.objects.filter(status=status_code).count()
        status_stats[status_code] = {'name': status_name, 'count': count}
    
    context = {
        'page_obj': page_obj,
        'status_stats': status_stats,
        'current_status': status_filter,
        'current_buyer': buyer_filter,
        'current_search': search,
        'total_orders': Order.objects.count(),
    }
    
    return render(request, 'products/orders_list.html', context)


@login_required
def order_detail(request, pk):
    """Детали заказа"""
    try:
        order = Order.objects.prefetch_related('items__product', 'status_history__changed_by').get(pk=pk)
    except Order.DoesNotExist:
        messages.error(request, 'Заказ не найден')
        return redirect('orders_list')
    
    context = {
        'order': order,
        'items': order.items.all(),
        'status_history': order.status_history.all()[:10],  # Последние 10 изменений
    }
    
    return render(request, 'products/order_detail.html', context)


@login_required
def sync_orders(request):
    """Синхронизация заказов с Hood.de"""
    if request.method == 'POST':
        sync_type = request.POST.get('sync_type', 'recent')
        days = int(request.POST.get('days', 7))
        start_date = request.POST.get('start_date')
        end_date = request.POST.get('end_date')
        order_id = request.POST.get('order_id')
        
        # Создаем лог синхронизации
        sync_log = OrderSyncLog.objects.create(
            sync_type=sync_type,
            start_date=start_date if start_date else None,
            end_date=end_date if end_date else None,
            status='pending'
        )
        
        try:
            hood_service = HoodAPIService()
            
            # Выбираем метод синхронизации
            if sync_type == 'recent':
                result = hood_service.get_recent_orders(days=days)
            elif sync_type == 'date_range' and start_date and end_date:
                result = hood_service.get_orders_by_date_range(
                    start_date=start_date,
                    end_date=end_date
                )
            elif sync_type == 'by_id' and order_id:
                result = hood_service.get_order_by_id(order_id)
            else:
                raise ValueError("Неправильные параметры синхронизации")
            
            if not result.get('success'):
                sync_log.status = 'error'
                sync_log.error_details = result.get('error', 'Неизвестная ошибка')
                sync_log.completed_at = timezone.now()
                sync_log.save()
                
                messages.error(request, f"Ошибка синхронизации: {result.get('error')}")
                return redirect('sync_orders')
            
            # Обрабатываем полученные заказы
            orders_data = result.get('orders', [])
            sync_log.total_orders_found = len(orders_data)
            
            created_count = 0
            updated_count = 0
            failed_count = 0
            
            for order_data in orders_data:
                try:
                    hood_order_id = order_data.get('orderID', '')
                    if not hood_order_id:
                        failed_count += 1
                        continue
                    
                    # Извлекаем данные заказа
                    order_fields = _extract_order_fields_web(order_data)
                    
                    # Проверяем, существует ли заказ
                    order, created = Order.objects.get_or_create(
                        hood_order_id=hood_order_id,
                        defaults=order_fields
                    )
                    
                    if created:
                        created_count += 1
                        # Создаем товары заказа
                        _create_order_items_web(order, order_data.get('items', []))
                    else:
                        # Обновляем существующий заказ
                        for field, value in order_fields.items():
                            setattr(order, field, value)
                        order.synced_at = timezone.now()
                        order.save()
                        updated_count += 1
                        
                        # Обновляем товары заказа
                        order.items.all().delete()
                        _create_order_items_web(order, order_data.get('items', []))
                
                except Exception as e:
                    logger.error(f"Ошибка обработки заказа {hood_order_id}: {str(e)}")
                    failed_count += 1
            
            # Обновляем лог синхронизации
            sync_log.orders_created = created_count
            sync_log.orders_updated = updated_count
            sync_log.orders_failed = failed_count
            sync_log.status = 'success' if failed_count == 0 else 'partial'
            sync_log.response_data = result
            sync_log.completed_at = timezone.now()
            sync_log.save()
            
            messages.success(
                request, 
                f'Синхронизация завершена! Создано: {created_count}, Обновлено: {updated_count}, Ошибок: {failed_count}'
            )
            
        except Exception as e:
            logger.error(f"Ошибка синхронизации заказов: {str(e)}")
            sync_log.status = 'error'
            sync_log.error_details = str(e)
            sync_log.completed_at = timezone.now()
            sync_log.save()
            
            messages.error(request, f'Ошибка синхронизации: {str(e)}')
        
        return redirect('sync_orders')
    
    # GET запрос - показываем форму синхронизации
    recent_sync_logs = OrderSyncLog.objects.order_by('-started_at')[:10]
    
    context = {
        'recent_sync_logs': recent_sync_logs,
    }
    
    return render(request, 'products/sync_orders.html', context)


@login_required
def orders_stats(request):
    """Статистика заказов"""
    from django.db.models import Sum, Count
    from datetime import datetime, timedelta
    
    total_orders = Order.objects.count()
    total_amount = Order.objects.aggregate(total=Sum('total_amount'))['total'] or 0
    
    # Статистика по статусам
    status_stats = []
    for status_code, status_name in Order.STATUS_CHOICES:
        count = Order.objects.filter(status=status_code).count()
        percentage = (count / total_orders * 100) if total_orders > 0 else 0
        status_stats.append({
            'code': status_code,
            'name': status_name,
            'count': count,
            'percentage': round(percentage, 1)
        })
    
    # Статистика по периодам
    now = timezone.now()
    today_orders = Order.objects.filter(order_date__date=now.date()).count()
    week_orders = Order.objects.filter(order_date__gte=now - timedelta(days=7)).count()
    month_orders = Order.objects.filter(order_date__gte=now - timedelta(days=30)).count()
    
    # Топ покупатели
    top_buyers = Order.objects.values('buyer_username', 'buyer_name').annotate(
        orders_count=Count('id'),
        total_spent=Sum('total_amount')
    ).order_by('-total_spent')[:10]
    
    # Статистика по способам оплаты
    payment_stats = Order.objects.values('payment_method').annotate(
        count=Count('id')
    ).order_by('-count')
    
    # Средний чек
    average_order_value = (total_amount / total_orders) if total_orders > 0 else 0
    
    context = {
        'total_orders': total_orders,
        'total_amount': total_amount,
        'average_order_value': average_order_value,
        'status_stats': status_stats,
        'period_stats': {
            'today': today_orders,
            'week': week_orders,
            'month': month_orders
        },
        'top_buyers': top_buyers,
        'payment_stats': payment_stats,
    }
    
    return render(request, 'products/orders_stats.html', context)


def _extract_order_fields_web(order_data):
    """Извлекает поля заказа из данных Hood.de API для веб-интерфейса"""
    from datetime import datetime
    
    # Парсим дату заказа (новый формат с {ts '...'})
    order_date_str = order_data.get('date', order_data.get('orderDate', ''))
    order_date = timezone.now()
    
    if order_date_str:
        try:
            # Убираем {ts ' и '} из даты
            clean_date = order_date_str.replace('{ts \'', '').replace('\'}', '')
            naive_date = datetime.strptime(clean_date, '%Y-%m-%d %H:%M:%S')
            # Делаем дату timezone-aware
            order_date = timezone.make_aware(naive_date)
        except ValueError:
            try:
                naive_date = datetime.strptime(clean_date, '%Y-%m-%d')
                order_date = timezone.make_aware(naive_date)
            except ValueError:
                order_date = timezone.now()
    
    # Определяем статус заказа на основе статусов покупателя и продавца
    buyer_status = order_data.get('orderStatusActionBuyer', '').lower()
    seller_status = order_data.get('orderStatusActionSeller', '').lower()
    shipping_status = order_data.get('shippingStatusCode', '').lower()
    
    # Маппинг статусов
    if buyer_status == 'payed' and seller_status == 'payed':
        status = 'paid'
    elif buyer_status == 'payed':
        status = 'paid'
    elif 'cancel' in buyer_status or 'cancel' in seller_status:
        status = 'cancelled'
    elif 'refund' in buyer_status:
        status = 'refunded'
    elif 'shipped' in shipping_status:
        status = 'shipped'
    elif 'received' in shipping_status:
        status = 'delivered'
    else:
        status = 'new'
    
    return {
        'order_number': order_data.get('orderNumber', ''),
        'status': status,
        'buyer_username': order_data.get('buyerAccountName', order_data.get('accountName', '')),
        'buyer_email': order_data.get('buyerEmail', ''),
        'buyer_name': f"{order_data.get('buyerFirstName', '')} {order_data.get('buyerLastName', '')}".strip(),
        'shipping_name': f"{order_data.get('shippingFirstName', '')} {order_data.get('shippingLastName', '')}".strip(),
        'shipping_company': order_data.get('shippingCompany', ''),
        'shipping_address1': order_data.get('shippingAddress', ''),
        'shipping_address2': '',
        'shipping_city': order_data.get('shippingCity', ''),
        'shipping_state': '',
        'shipping_postal_code': order_data.get('shippingZip', ''),
        'shipping_country': order_data.get('shippingCountry', ''),
        'shipping_phone': order_data.get('shippingPhone', ''),
        'subtotal': float(order_data.get('price', 0)),
        'shipping_cost': float(order_data.get('shipCost', 0)),
        'tax_amount': float(order_data.get('taxTotalValue', 0)),
        'total_amount': float(order_data.get('price', 0)) + float(order_data.get('shipCost', 0)),
        'payment_method': _map_payment_method_web(order_data.get('paymentTypeCode', '')),
        'payment_status': order_data.get('paymentStatus', ''),
        'shipping_method': order_data.get('shipMethod', ''),
        'tracking_number': '',
        'notes': order_data.get('comments', ''),
        'order_date': order_date,
        'synced_at': timezone.now(),
    }


def _map_payment_method_web(payment_code):
    """Маппинг кодов способов оплаты для веб-интерфейса"""
    mapping = {
        'wireTransfer': 'wireTransfer',
        'payPal': 'payPal', 
        'hoodPay': 'hoodPay',
        'cash': 'cash',
        'invoice': 'invoice',
        'cashOnDelivery': 'cashOnDelivery',
        'sofort': 'sofort',
        'amazon': 'amazon',
        'klarna': 'klarna',
    }
    return mapping.get(payment_code, payment_code)


def _map_hood_status_web(hood_status):
    """Маппинг статусов Hood.de в наши статусы для веб-интерфейса"""
    status_mapping = {
        'new': 'new',
        'paid': 'paid',
        'shipped': 'shipped',
        'delivered': 'delivered',
        'cancelled': 'cancelled',
        'returned': 'returned',
        'refunded': 'refunded',
    }
    return status_mapping.get(hood_status.lower(), 'new')


def _create_order_items_web(order, items_data):
    """Создает товары заказа для веб-интерфейса"""
    for item_data in items_data:
        # Пытаемся найти продукт по hood_item_id
        product = None
        hood_item_id = item_data.get('itemID', '')
        if hood_item_id:
            try:
                product = Product.objects.get(hood_item_id=hood_item_id)
            except Product.DoesNotExist:
                pass
        
        OrderItem.objects.create(
            order=order,
            product=product,
            hood_item_id=hood_item_id,
            item_title=item_data.get('prodName', ''),
            item_sku=item_data.get('itemNumber', ''),
            item_ean=item_data.get('ean', ''),
            quantity=int(item_data.get('quantity', 1)),
            unit_price=float(item_data.get('price', 0)),
            variant_details={}
        )
