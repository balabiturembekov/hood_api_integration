from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.shortcuts import get_object_or_404
from django.db import transaction
from django.utils import timezone
from django.core.paginator import Paginator
from django.http import JsonResponse
import logging

from .models import Product, HoodCategory, UploadLog, BulkUpload
from .serializers import (
    ProductSerializer, ProductListSerializer, HoodCategorySerializer,
    UploadLogSerializer, BulkUploadSerializer, ProductUploadSerializer,
    BulkUploadRequestSerializer
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