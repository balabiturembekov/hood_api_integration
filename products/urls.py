from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import ProductViewSet, HoodCategoryViewSet, UploadLogViewSet, BulkUploadViewSet
from . import views_web

router = DefaultRouter()
router.register(r'products', ProductViewSet)
router.register(r'categories', HoodCategoryViewSet)
router.register(r'upload-logs', UploadLogViewSet)
router.register(r'bulk-uploads', BulkUploadViewSet)

urlpatterns = [
    # API маршруты
    path('api/', include(router.urls)),
    
    # Веб-интерфейс маршруты
    path('', views_web.public_home, name='public_home'),
    path('dashboard/', views_web.dashboard, name='dashboard'),
    path('products/', views_web.products_list, name='products_list'),
    path('products/<int:pk>/', views_web.product_detail, name='product_detail'),
    path('products/<int:pk>/upload/', views_web.upload_product, name='upload_product'),
    path('products/<int:pk>/delete/', views_web.delete_product, name='delete_product'),
    path('bulk-upload/', views_web.bulk_upload, name='bulk_upload'),
    path('bulk-delete/', views_web.bulk_delete, name='bulk_delete'),
    path('import-products/', views_web.import_products, name='import_products'),
    path('import-logs/', views_web.import_logs, name='import_logs'),
    path('sync-categories/', views_web.sync_categories, name='sync_categories'),
    path('api-test/', views_web.api_test, name='api_test'),
    path('check-api-connection/', views_web.check_api_connection, name='check_api_connection'),
    path('get-all-product-ids/', views_web.get_all_product_ids, name='get_all_product_ids'),
    
    # Hood.de API функции
    path('hood-items/', views_web.hood_items_list, name='hood_items_list'),
    path('hood-items/<str:item_id>/', views_web.hood_item_status, name='hood_item_status'),
    path('hood-items-analysis/', views_web.hood_items_analysis, name='hood_items_analysis'),
    path('hood-items-compare/', views_web.hood_items_compare, name='hood_items_compare'),
]
