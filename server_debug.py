#!/usr/bin/env python3
"""
Диагностический скрипт для сервера - проверка ответа Hood API
"""

import os
import sys
import django
from django.conf import settings

# Добавляем путь к проекту
sys.path.append('/home/server/hood_api_integration')

# Настройка Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'hood_integration_service.settings')
django.setup()

from products.services import HoodAPIService
from products.models import Product
import xml.etree.ElementTree as ET

def debug_api_response():
    """Диагностика ответа API на сервере"""
    print("🔍 ДИАГНОСТИКА HOOD API ОТВЕТА НА СЕРВЕРЕ")
    print("=" * 60)
    
    # Получаем первый товар из базы данных
    try:
        product = Product.objects.first()
        if not product:
            print("❌ Нет товаров в базе данных")
            return
        
        print(f"📦 Тестируем товар: {product.title}")
        print(f"🆔 ID товара: {product.id}")
        
        # Получаем данные для загрузки
        hood_data = product.get_hood_data()
        print(f"📋 Данные для загрузки: {len(hood_data)} полей")
        
        # Создаем сервис
        hood_service = HoodAPIService()
        
        # Создаем XML запрос
        xml_request = hood_service._build_xml_request('itemInsert', [hood_data])
        print(f"📤 XML запрос (первые 500 символов):")
        print(xml_request[:500] + "..." if len(xml_request) > 500 else xml_request)
        print()
        
        # Отправляем запрос
        print("🚀 Отправляем запрос к API...")
        response = hood_service.session.post(
            hood_service.api_url,
            data=xml_request,
            headers={'Content-Type': 'text/xml; charset=UTF-8'},
            timeout=30
        )
        
        print(f"📥 Статус ответа: {response.status_code}")
        print(f"📥 Заголовки ответа: {dict(response.headers)}")
        print()
        
        # Анализируем ответ
        print("🔍 АНАЛИЗ ОТВЕТА:")
        print("=" * 30)
        
        response_text = response.text
        print(f"📄 Длина ответа: {len(response_text)} символов")
        print(f"📄 Полный ответ:")
        print(response_text)
        print()
        
        # Парсим XML
        try:
            root = ET.fromstring(response_text)
            print(f"✅ XML успешно распарсен")
            print(f"🏷️ Корневой элемент: {root.tag}")
            print(f"🏷️ Атрибуты корневого элемента: {root.attrib}")
            print()
            
            # Ищем response
            response_container = None
            if root.tag == 'response':
                response_container = root
                print("✅ Найден корневой элемент 'response'")
            else:
                response_container = root.find('.//response')
                if response_container is not None:
                    print("✅ Найден элемент 'response' внутри корневого")
                else:
                    print("❌ Элемент 'response' не найден")
            
            if response_container is not None:
                print(f"🏷️ Атрибуты response: {response_container.attrib}")
                
                # Ищем items
                items_container = response_container.find('items')
                if items_container is not None:
                    print("✅ Найден элемент 'items'")
                    item_container = items_container.find('item')
                    if item_container is not None:
                        print("✅ Найден элемент 'item' внутри 'items'")
                    else:
                        print("❌ Элемент 'item' не найден внутри 'items'")
                else:
                    print("❌ Элемент 'items' не найден")
                    # Ищем item напрямую
                    item_container = response_container.find('item')
                    if item_container is not None:
                        print("✅ Найден элемент 'item' напрямую в response")
                    else:
                        print("❌ Элемент 'item' не найден нигде")
                
                # Выводим все дочерние элементы response
                print(f"📋 Все дочерние элементы response:")
                for child in response_container:
                    print(f"  - {child.tag}: {child.text[:100] if child.text else 'None'}")
            
            # Ищем глобальные ошибки
            global_error = root.find('.//globalError')
            if global_error is not None:
                print(f"❌ Глобальная ошибка: {global_error.text}")
            
            # Ищем другие возможные элементы
            possible_elements = ['error', 'message', 'status', 'itemID', 'referenceID']
            for elem_name in possible_elements:
                elem = root.find(f'.//{elem_name}')
                if elem is not None:
                    print(f"🔍 Найден элемент '{elem_name}': {elem.text}")
            
        except ET.ParseError as e:
            print(f"❌ Ошибка парсинга XML: {e}")
            print(f"📄 Ответ не является валидным XML")
        
        # Тестируем функцию upload_item
        print("\n🧪 ТЕСТ ФУНКЦИИ upload_item:")
        print("=" * 40)
        result = hood_service.upload_item(hood_data)
        print(f"📊 Результат:")
        print(f"  ✅ Успех: {result.get('success', False)}")
        print(f"  🆔 Item ID: {result.get('item_id', 'Не найден')}")
        print(f"  📝 Статус: {result.get('status', 'Не найден')}")
        print(f"  💰 Стоимость: {result.get('cost', 'Не найдена')}")
        print(f"  ❌ Ошибка: {result.get('error', 'Нет ошибок')}")
        
    except Exception as e:
        print(f"❌ Ошибка: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    debug_api_response()
