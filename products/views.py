from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.shortcuts import get_object_or_404
from django.db import transaction, models
from django.utils import timezone
from django.core.paginator import Paginator
from django.http import JsonResponse
import logging

from .models import Product, HoodCategory, UploadLog, BulkUpload, Order, OrderItem, OrderSyncLog
from .serializers import (
    ProductSerializer, ProductListSerializer, HoodCategorySerializer,
    UploadLogSerializer, BulkUploadSerializer, ProductUploadSerializer,
    BulkUploadRequestSerializer, OrderSerializer, OrderListSerializer,
    OrderSyncLogSerializer, OrderSyncRequestSerializer
)
from .services import HoodAPIService

logger = logging.getLogger(__name__)


class ProductViewSet(viewsets.ModelViewSet):
    """ViewSet для управления продуктами"""
    queryset = Product.objects.all()
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        return Product.objects.select_related('hood_category', 'created_by').order_by('-created_at')
    
    def get_serializer_class(self):
        if self.action == 'list':
            return ProductListSerializer
        return ProductSerializer
    
    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)
    
    @action(detail=True, methods=['post'])
    def upload_to_hood(self, request, pk=None):
        """Загрузка продукта на Hood.de"""
        product = self.get_object()
        
        if product.is_uploaded_to_hood:
            return Response(
                {'error': 'Продукт уже загружен на Hood.de'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Получаем данные для загрузки
        hood_data = product.get_hood_data()
        
        # Создаем лог загрузки
        upload_log = UploadLog.objects.create(
            product=product,
            status='pending'
        )
        
        try:
            # Загружаем на Hood.de
            hood_service = HoodAPIService()
            result = hood_service.upload_item(hood_data)
            
            # Обновляем лог
            upload_log.response_data = result
            upload_log.status = 'success' if result.get('success') else 'error'
            upload_log.hood_item_id = result.get('item_id', '')
            upload_log.error_message = result.get('error', '')
            upload_log.save()
            
            # Обновляем продукт
            if result.get('success'):
                product.is_uploaded_to_hood = True
                product.hood_item_id = result.get('item_id', '')
                product.uploaded_at = timezone.now()
                product.save()
                
                return Response({
                    'success': True,
                    'message': 'Продукт успешно загружен на Hood.de',
                    'hood_item_id': result.get('item_id'),
                    'upload_log_id': upload_log.id
                })
            else:
                return Response({
                    'success': False,
                    'error': result.get('error', 'Неизвестная ошибка'),
                    'upload_log_id': upload_log.id
                }, status=status.HTTP_400_BAD_REQUEST)
                
        except Exception as e:
            logger.error(f"Error uploading product {product.id}: {str(e)}")
            upload_log.status = 'error'
            upload_log.error_message = str(e)
            upload_log.save()
            
            return Response({
                'success': False,
                'error': f'Ошибка загрузки: {str(e)}',
                'upload_log_id': upload_log.id
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    @action(detail=False, methods=['post'])
    def bulk_upload(self, request):
        """Массовая загрузка продуктов"""
        serializer = BulkUploadRequestSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        
        product_ids = serializer.validated_data['product_ids']
        name = serializer.validated_data['name']
        description = serializer.validated_data.get('description', '')
        
        # Создаем запись о массовой загрузке
        bulk_upload = BulkUpload.objects.create(
            name=name,
            description=description,
            total_products=len(product_ids),
            created_by=request.user
        )
        
        # Получаем продукты
        products = Product.objects.filter(id__in=product_ids)
        
        # Запускаем загрузку в фоне (в реальном проекте лучше использовать Celery)
        hood_service = HoodAPIService()
        uploaded_count = 0
        failed_count = 0
        
        bulk_upload.status = 'processing'
        bulk_upload.started_at = timezone.now()
        bulk_upload.save()
        
        for product in products:
            try:
                hood_data = product.get_hood_data()
                result = hood_service.upload_item(hood_data)
                
                # Создаем лог
                upload_log = UploadLog.objects.create(
                    product=product,
                    status='success' if result.get('success') else 'error',
                    hood_item_id=result.get('item_id', ''),
                    response_data=result,
                    error_message=result.get('error', '')
                )
                
                if result.get('success'):
                    product.is_uploaded_to_hood = True
                    product.hood_item_id = result.get('item_id', '')
                    product.uploaded_at = timezone.now()
                    product.save()
                    uploaded_count += 1
                else:
                    failed_count += 1
                    
            except Exception as e:
                logger.error(f"Error uploading product {product.id}: {str(e)}")
                UploadLog.objects.create(
                    product=product,
                    status='error',
                    error_message=str(e)
                )
                failed_count += 1
        
        # Обновляем статистику
        bulk_upload.uploaded_products = uploaded_count
        bulk_upload.failed_products = failed_count
        bulk_upload.status = 'completed'
        bulk_upload.completed_at = timezone.now()
        bulk_upload.save()
        
        return Response({
            'success': True,
            'message': f'Массовая загрузка завершена. Загружено: {uploaded_count}, Ошибок: {failed_count}',
            'bulk_upload_id': bulk_upload.id,
            'uploaded_count': uploaded_count,
            'failed_count': failed_count
        })
    
    @action(detail=False, methods=['get'])
    def stats(self, request):
        """Статистика продуктов"""
        total_products = Product.objects.count()
        uploaded_products = Product.objects.filter(is_uploaded_to_hood=True).count()
        active_products = Product.objects.filter(is_approved='yes').count()
        
        return Response({
            'total_products': total_products,
            'uploaded_products': uploaded_products,
            'active_products': active_products,
            'upload_percentage': (uploaded_products / total_products * 100) if total_products > 0 else 0
        })


class HoodCategoryViewSet(viewsets.ReadOnlyModelViewSet):
    """ViewSet для категорий Hood.de"""
    queryset = HoodCategory.objects.filter(is_active=True)
    serializer_class = HoodCategorySerializer
    permission_classes = [IsAuthenticated]
    
    @action(detail=False, methods=['post'])
    def sync_categories(self, request):
        """Синхронизация категорий с Hood.de"""
        hood_service = HoodAPIService()
        
        # Сначала пробуем получить категории через API
        result = hood_service.get_categories()
        
        # Если API не работает, используем fallback
        if not result.get('success'):
            result = hood_service.get_categories_fallback()
        
        if not result.get('success'):
            return Response({
                'success': False,
                'error': result.get('error', 'Ошибка получения категорий')
            }, status=status.HTTP_400_BAD_REQUEST)
        
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
                # Обновляем существующую категорию
                category.name = cat_data.get('name', '')
                category.path = cat_data.get('path', '')
                category.level = int(cat_data.get('level', 0))
                category.save()
                updated_count += 1
        
        source_text = "из API Hood.de" if source == 'api' else "из локального файла"
        total_categories = HoodCategory.objects.count()
        return Response({
            'success': True,
            'message': f'Синхронизация завершена {source_text}. Создано: {created_count}, Обновлено: {updated_count}. Всего категорий в базе: {total_categories}',
            'created_count': created_count,
            'updated_count': updated_count,
            'total_categories': total_categories,
            'source': source
        })


class UploadLogViewSet(viewsets.ReadOnlyModelViewSet):
    """ViewSet для логов загрузки"""
    queryset = UploadLog.objects.select_related('product').order_by('-created_at')
    serializer_class = UploadLogSerializer
    permission_classes = [IsAuthenticated]


class BulkUploadViewSet(viewsets.ReadOnlyModelViewSet):
    """ViewSet для массовых загрузок"""
    queryset = BulkUpload.objects.select_related('created_by').order_by('-created_at')
    serializer_class = BulkUploadSerializer
    permission_classes = [IsAuthenticated]


class OrderViewSet(viewsets.ReadOnlyModelViewSet):
    """ViewSet для заказов"""
    queryset = Order.objects.prefetch_related('items', 'status_history').order_by('-order_date')
    permission_classes = [IsAuthenticated]
    
    def get_serializer_class(self):
        if self.action == 'list':
            return OrderListSerializer
        return OrderSerializer
    
    def get_queryset(self):
        queryset = Order.objects.prefetch_related('items', 'status_history').order_by('-order_date')
        
        # Фильтрация по статусу
        status = self.request.query_params.get('status')
        if status:
            queryset = queryset.filter(status=status)
        
        # Фильтрация по покупателю
        buyer = self.request.query_params.get('buyer')
        if buyer:
            queryset = queryset.filter(buyer_username__icontains=buyer)
        
        # Фильтрация по дате
        date_from = self.request.query_params.get('date_from')
        date_to = self.request.query_params.get('date_to')
        if date_from:
            queryset = queryset.filter(order_date__gte=date_from)
        if date_to:
            queryset = queryset.filter(order_date__lte=date_to)
        
        return queryset
    
    @action(detail=False, methods=['post'])
    def sync_orders(self, request):
        """Синхронизация заказов с Hood.de"""
        serializer = OrderSyncRequestSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        
        data = serializer.validated_data
        sync_type = data['sync_type']
        
        # Создаем лог синхронизации
        sync_log = OrderSyncLog.objects.create(
            sync_type=sync_type,
            start_date=data.get('start_date'),
            end_date=data.get('end_date'),
            status='pending'
        )
        
        try:
            hood_service = HoodAPIService()
            
            # Выбираем метод синхронизации
            if sync_type == 'recent':
                days = data.get('days', 7)
                result = hood_service.get_recent_orders(days=days)
            elif sync_type == 'date_range':
                result = hood_service.get_orders_by_date_range(
                    start_date=data['start_date'].strftime('%d.%m.%Y'),
                    end_date=data['end_date'].strftime('%d.%m.%Y')
                )
            elif sync_type == 'by_status':
                result = hood_service.get_orders_by_status_change(
                    start_date=data['start_date'].strftime('%d.%m.%Y'),
                    end_date=data['end_date'].strftime('%d.%m.%Y')
                )
            elif sync_type == 'by_id':
                result = hood_service.get_order_by_id(data['order_id'])
            else:
                raise ValueError(f"Неподдерживаемый тип синхронизации: {sync_type}")
            
            if not result.get('success'):
                sync_log.status = 'error'
                sync_log.error_details = result.get('error', 'Неизвестная ошибка')
                sync_log.completed_at = timezone.now()
                sync_log.save()
                
                return Response({
                    'success': False,
                    'error': result.get('error', 'Ошибка синхронизации'),
                    'sync_log_id': sync_log.id
                }, status=status.HTTP_400_BAD_REQUEST)
            
            # Обрабатываем полученные заказы
            orders_data = result.get('orders', [])
            sync_log.total_orders_found = len(orders_data)
            
            created_count = 0
            updated_count = 0
            failed_count = 0
            
            for order_data in orders_data:
                try:
                    # Извлекаем данные заказа
                    hood_order_id = order_data.get('orderID', '')
                    if not hood_order_id:
                        failed_count += 1
                        continue
                    
                    # Проверяем, существует ли заказ
                    order, created = Order.objects.get_or_create(
                        hood_order_id=hood_order_id,
                        defaults=self._extract_order_fields(order_data)
                    )
                    
                    if created:
                        created_count += 1
                        # Создаем товары заказа
                        self._create_order_items(order, order_data.get('items', []))
                    else:
                        # Обновляем существующий заказ
                        for field, value in self._extract_order_fields(order_data).items():
                            setattr(order, field, value)
                        order.synced_at = timezone.now()
                        order.save()
                        updated_count += 1
                        
                        # Обновляем товары заказа
                        self._update_order_items(order, order_data.get('items', []))
                    
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
            
            return Response({
                'success': True,
                'message': f'Синхронизация завершена. Создано: {created_count}, Обновлено: {updated_count}, Ошибок: {failed_count}',
                'sync_log_id': sync_log.id,
                'created_count': created_count,
                'updated_count': updated_count,
                'failed_count': failed_count
            })
            
        except Exception as e:
            logger.error(f"Ошибка синхронизации заказов: {str(e)}")
            sync_log.status = 'error'
            sync_log.error_details = str(e)
            sync_log.completed_at = timezone.now()
            sync_log.save()
            
            return Response({
                'success': False,
                'error': f'Ошибка синхронизации: {str(e)}',
                'sync_log_id': sync_log.id
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    def _extract_order_fields(self, order_data):
        """Извлекает поля заказа из данных Hood.de API"""
        from datetime import datetime
        
        # Парсим дату заказа
        order_date_str = order_data.get('orderDate', '')
        order_date = None
        if order_date_str:
            try:
                order_date = datetime.strptime(order_date_str, '%d.%m.%Y %H:%M:%S')
            except ValueError:
                try:
                    order_date = datetime.strptime(order_date_str, '%d.%m.%Y')
                except ValueError:
                    order_date = timezone.now()
        else:
            order_date = timezone.now()
        
        return {
            'order_number': order_data.get('orderNumber', ''),
            'status': self._map_hood_status(order_data.get('status', '')),
            'buyer_username': order_data.get('buyerUsername', ''),
            'buyer_email': order_data.get('buyerEmail', ''),
            'buyer_name': order_data.get('buyerName', ''),
            'shipping_name': order_data.get('shippingName', ''),
            'shipping_company': order_data.get('shippingCompany', ''),
            'shipping_address1': order_data.get('shippingAddress1', ''),
            'shipping_address2': order_data.get('shippingAddress2', ''),
            'shipping_city': order_data.get('shippingCity', ''),
            'shipping_state': order_data.get('shippingState', ''),
            'shipping_postal_code': order_data.get('shippingPostalCode', ''),
            'shipping_country': order_data.get('shippingCountry', ''),
            'shipping_phone': order_data.get('shippingPhone', ''),
            'subtotal': float(order_data.get('subtotal', 0)),
            'shipping_cost': float(order_data.get('shippingCost', 0)),
            'tax_amount': float(order_data.get('taxAmount', 0)),
            'total_amount': float(order_data.get('totalAmount', 0)),
            'payment_method': order_data.get('paymentMethod', ''),
            'payment_status': order_data.get('paymentStatus', ''),
            'shipping_method': order_data.get('shippingMethod', ''),
            'tracking_number': order_data.get('trackingNumber', ''),
            'notes': order_data.get('notes', ''),
            'order_date': order_date,
            'synced_at': timezone.now(),
        }
    
    def _map_hood_status(self, hood_status):
        """Маппинг статусов Hood.de в наши статусы"""
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
    
    def _create_order_items(self, order, items_data):
        """Создает товары заказа"""
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
                item_title=item_data.get('itemTitle', ''),
                item_sku=item_data.get('itemSKU', ''),
                item_ean=item_data.get('itemEAN', ''),
                quantity=int(item_data.get('quantity', 1)),
                unit_price=float(item_data.get('unitPrice', 0)),
                variant_details=item_data.get('variantDetails', {})
            )
    
    def _update_order_items(self, order, items_data):
        """Обновляет товары заказа"""
        # Удаляем старые товары
        order.items.all().delete()
        # Создаем новые
        self._create_order_items(order, items_data)
    
    @action(detail=False, methods=['get'])
    def stats(self, request):
        """Статистика заказов"""
        total_orders = Order.objects.count()
        
        # Статистика по статусам
        status_stats = {}
        for status_code, status_name in Order.STATUS_CHOICES:
            count = Order.objects.filter(status=status_code).count()
            status_stats[status_code] = {
                'name': status_name,
                'count': count,
                'percentage': (count / total_orders * 100) if total_orders > 0 else 0
            }
        
        # Статистика по периодам
        from datetime import datetime, timedelta
        now = timezone.now()
        today_orders = Order.objects.filter(order_date__date=now.date()).count()
        week_orders = Order.objects.filter(order_date__gte=now - timedelta(days=7)).count()
        month_orders = Order.objects.filter(order_date__gte=now - timedelta(days=30)).count()
        
        # Общая сумма заказов
        total_amount = Order.objects.aggregate(
            total=models.Sum('total_amount')
        )['total'] or 0
        
        return Response({
            'total_orders': total_orders,
            'status_stats': status_stats,
            'period_stats': {
                'today': today_orders,
                'week': week_orders,
                'month': month_orders
            },
            'total_amount': float(total_amount)
        })


class OrderSyncLogViewSet(viewsets.ReadOnlyModelViewSet):
    """ViewSet для логов синхронизации заказов"""
    queryset = OrderSyncLog.objects.order_by('-started_at')
    serializer_class = OrderSyncLogSerializer
    permission_classes = [IsAuthenticated]