import hashlib
import requests
import xml.etree.ElementTree as ET
from django.conf import settings
from typing import Dict, Any, Optional, List
import logging
import re
import html
import ssl

logger = logging.getLogger(__name__)


class HoodAPIService:
    """Сервис для работы с Hood.de API"""
    
    def __init__(self):
        self.api_url = 'https://www.hood.de/api.htm'
        self.api_user = settings.HOOD_API_USERNAME
        self.api_password = settings.HOOD_API_PASSWORD
        self.account_name = settings.HOOD_ACCOUNT_NAME
        self.account_pass = settings.HOOD_ACCOUNT_PASS
        
        # Настройка TLS для соответствия требованиям Hood.de API
        self.session = requests.Session()
        self.session.verify = True  # Включаем проверку SSL сертификатов
        
        # Настройка TLS 1.2+ (минимальное требование Hood.de API)
        self.session.mount('https://', requests.adapters.HTTPAdapter())
        
        # Таймаут для запросов
        self.timeout = 30
    
    def _hash_password(self, password: str) -> str:
        """Хеширование пароля MD5"""
        return hashlib.md5(password.encode('utf-8')).hexdigest()
    
    def _clean_xml_response(self, xml_text: str) -> str:
        """Очистка XML ответа от некорректных символов"""
        if not xml_text:
            return ""
        
        # Удаляем BOM и другие невидимые символы
        xml_text = xml_text.strip()
        
        # Заменяем некорректные символы
        xml_text = re.sub(r'[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]', '', xml_text)
        
        # Исправляем некорректные XML символы
        xml_text = xml_text.replace('&', '&amp;')
        xml_text = xml_text.replace('<', '&lt;')
        xml_text = xml_text.replace('>', '&gt;')
        xml_text = xml_text.replace('"', '&quot;')
        xml_text = xml_text.replace("'", '&apos;')
        
        # Восстанавливаем корректные XML теги
        xml_text = xml_text.replace('&lt;', '<')
        xml_text = xml_text.replace('&gt;', '>')
        xml_text = xml_text.replace('&quot;', '"')
        xml_text = xml_text.replace('&apos;', "'")
        
        # Исправляем двойные амперсанды
        xml_text = xml_text.replace('&amp;amp;', '&amp;')
        
        return xml_text
    
    def _parse_xml_safely(self, xml_text: str) -> Optional[ET.Element]:
        """Безопасный парсинг XML с обработкой ошибок"""
        try:
            # Очищаем XML
            cleaned_xml = self._clean_xml_response(xml_text)
            
            # Пробуем парсить
            root = ET.fromstring(cleaned_xml)
            return root
            
        except ET.ParseError as e:
            logger.error(f"XML Parse Error: {str(e)}")
            logger.error(f"XML Content (first 500 chars): {xml_text[:500]}")
            
            # Пробуем альтернативные методы парсинга
            try:
                # Удаляем проблемные символы более агрессивно
                cleaned_xml = re.sub(r'[^\x20-\x7E\n\r\t]', '', xml_text)
                root = ET.fromstring(cleaned_xml)
                return root
            except ET.ParseError:
                logger.error("Failed to parse XML even after cleaning")
                return None
    
    def _build_xml_request(self, function: str, items: List[Dict[str, Any]] = None, **kwargs) -> str:
        """Построение XML запроса согласно документации Hood.de API v2.0.1"""
        xml_parts = [
            '<?xml version="1.0" encoding="UTF-8"?>',
            f'<api type="public" version="2.0" user="{self.api_user}" password="{self._hash_password(self.api_password)}">',
            f'<function>{function}</function>',
            f'<accountName>{self.account_name}</accountName>',
            f'<accountPass>{self._hash_password(self.account_pass)}</accountPass>'
        ]
        
        # Добавляем дополнительные параметры функции
        for key, value in kwargs.items():
            if value is not None:
                xml_parts.append(f'<{key}>{value}</{key}>')
        
        # Функции, которые требуют элементы items
        item_functions = ['itemInsert', 'itemUpdate', 'itemValidate', 'itemDetail']
        
        if function in item_functions and items:
            xml_parts.append('<items>')
            
            for item in items:
                xml_parts.append('<item>')
                
                # Для itemDetail нужен только itemID
                if function == 'itemDetail':
                    xml_parts.append(f'<itemID>{item.get("itemID", "")}</itemID>')
                else:
                    # Основные поля для других функций
                    # itemMode: shopProduct, classic, buyItNow
                    item_mode = item.get("itemMode", "shopProduct")
                    if item_mode not in ["shopProduct", "classic", "buyItNow"]:
                        item_mode = "shopProduct"  # По умолчанию для магазинов
                    xml_parts.append(f'<itemMode>{item_mode}</itemMode>')
                
                xml_parts.append(f'<categoryID>{item.get("categoryID", "")}</categoryID>')
                xml_parts.append(f'<itemName><![CDATA[{item.get("itemName", "")}]]></itemName>')
                xml_parts.append(f'<quantity>{item.get("quantity", 1)}</quantity>')
                
                # condition: new, likeNew, veryGood, acceptable, usedGood, refurbished, defect
                condition = item.get("condition", "new")
                if condition not in ["new", "likeNew", "veryGood", "acceptable", "usedGood", "refurbished", "defect"]:
                    condition = "new"  # По умолчанию новый
                xml_parts.append(f'<condition>{condition}</condition>')
                
                xml_parts.append(f'<description><![CDATA[{item.get("description", "")}]]></description>')
                
                # Цены
                if item.get("price"):
                    xml_parts.append(f'<price>{item["price"]}</price>')
                if item.get("priceStart"):
                    xml_parts.append(f'<priceStart>{item["priceStart"]}</priceStart>')
                
                # Идентификаторы
                if item.get("ean"):
                    xml_parts.append(f'<ean>{item["ean"]}</ean>')
                if item.get("manufacturer"):
                    xml_parts.append(f'<manufacturer>{item["manufacturer"]}</manufacturer>')
                if item.get("weight"):
                    xml_parts.append(f'<weight>{item["weight"]}</weight>')
                
                # Изображения (рекомендуется) - поддержка URL и Base64
                if item.get("images"):
                    xml_parts.append('<images>')
                    
                    for image_data in item["images"]:
                        # Если это строка URL
                        if isinstance(image_data, str):
                            xml_parts.append(f'<imageURL>{image_data}</imageURL>')
                        
                        # Если это словарь с детальной информацией
                        elif isinstance(image_data, dict):
                            # Base64 изображение (простая структура)
                            if image_data.get("base64"):
                                xml_parts.append(f'<imageBase64>{image_data["base64"]}</imageBase64>')
                            
                            # URL изображения с деталями варианта
                            elif image_data.get("url"):
                                xml_parts.append('<image>')
                                xml_parts.append(f'<imageURL>{image_data["url"]}</imageURL>')
                                
                                # Детали варианта (если есть)
                                if image_data.get("optionDetails"):
                                    xml_parts.append('<optionDetails>')
                                    for detail in image_data["optionDetails"]:
                                        xml_parts.append('<nameValueList>')
                                        xml_parts.append(f'<name><![CDATA[{detail.get("name", "")}]]></name>')
                                        xml_parts.append(f'<value><![CDATA[{detail.get("value", "")}]]></value>')
                                        xml_parts.append('</nameValueList>')
                                    xml_parts.append('</optionDetails>')
                                
                                xml_parts.append('</image>')
                    
                    xml_parts.append('</images>')
                
                # Варианты продукта (для магазинов Gold/Platinum)
                if item.get("productOptions"):
                    xml_parts.append('<productOptions>')
                    
                    for option in item["productOptions"]:
                        xml_parts.append('<productOption>')
                        
                        # Основные поля варианта
                        if option.get("optionPrice"):
                            xml_parts.append(f'<optionPrice>{option["optionPrice"]}</optionPrice>')
                        if option.get("optionQuantity"):
                            xml_parts.append(f'<optionQuantity>{option["optionQuantity"]}</optionQuantity>')
                        if option.get("optionItemNumber"):
                            xml_parts.append(f'<optionItemNumber>{option["optionItemNumber"]}</optionItemNumber>')
                        if option.get("mpn"):
                            xml_parts.append(f'<mpn>{option["mpn"]}</mpn>')
                        if option.get("ean"):
                            xml_parts.append(f'<ean>{option["ean"]}</ean>')
                        if option.get("PackagingSize"):
                            xml_parts.append(f'<PackagingSize>{option["PackagingSize"]}</PackagingSize>')
                        
                        # Детали варианта (обязательно)
                        if option.get("optionDetails"):
                            xml_parts.append('<optionDetails>')
                            for detail in option["optionDetails"]:
                                xml_parts.append('<nameValueList>')
                                xml_parts.append(f'<name><![CDATA[{detail.get("name", "")}]]></name>')
                                xml_parts.append(f'<value><![CDATA[{detail.get("value", "")}]]></value>')
                                xml_parts.append('</nameValueList>')
                            xml_parts.append('</optionDetails>')
                        
                        xml_parts.append('</productOption>')
                    
                    xml_parts.append('</productOptions>')
                
                # Свойства продукта (до 15 свойств, максимум 30 символов каждое)
                if item.get("productProperties"):
                    xml_parts.append('<productProperties>')
                    
                    # Валидируем и ограничиваем свойства
                    validated_properties = self._validate_product_properties(item["productProperties"])
                    
                    for prop_name, prop_value in validated_properties.items():
                        xml_parts.append('<nameValueList>')
                        xml_parts.append(f'<name><![CDATA[{prop_name}]]></name>')
                        xml_parts.append(f'<value><![CDATA[{prop_value}]]></value>')
                        xml_parts.append('</nameValueList>')
                    
                    xml_parts.append('</productProperties>')
                
                # Платежи (обязательно для classic и buyItNow, игнорируется для shopProduct)
                if item_mode in ["classic", "buyItNow"]:
                    xml_parts.append('<payOptions>')
                    
                    # Получаем опции оплаты из данных товара или используем по умолчанию
                    pay_options = item.get("payOptions", ["wireTransfer", "paypal"])
                    
                    # Проверяем правильность значений
                    valid_options = ["wireTransfer", "invoice", "cashOnDelivery", "cash", "paypal", "sofort", "amazon", "klarna"]
                    for option in pay_options:
                        if option in valid_options:
                            xml_parts.append(f'<option>{option}</option>')
                    
                    # Если нет валидных опций, используем по умолчанию
                    if not any(opt in valid_options for opt in pay_options):
                        xml_parts.append('<option>wireTransfer</option>')
                        xml_parts.append('<option>paypal</option>')
                    
                    xml_parts.append('</payOptions>')
                
                # Доставка (обязательно) - используем данные из товара или значения по умолчанию
                xml_parts.append('<shipmethods>')
                
                # Получаем способы доставки из данных товара
                ship_methods = item.get("shipMethods", {})
                
                # Если не указаны способы доставки, используем по умолчанию
                if not ship_methods:
                    ship_methods = {
                        "seeDesc_nat": 5.0,  # См. описание - национальная доставка
                        "DHLPacket_nat": 8.0  # DHL Packet - национальная доставка
                    }
                
                # Добавляем способы доставки
                for method_name, cost in ship_methods.items():
                    xml_parts.append(f'<shipmethod name="{method_name}">')
                    xml_parts.append(f'<value>{cost}</value>')
                    xml_parts.append('</shipmethod>')
                
                xml_parts.append('</shipmethods>')
                
                # Обязательные временные поля
                from datetime import datetime, timedelta
                start_date = datetime.now() + timedelta(hours=1)  # Начинаем через час
                xml_parts.append(f'<startDate>{start_date.strftime("%d.%m.%Y")}</startDate>')
                xml_parts.append(f'<startTime>{start_date.strftime("%H:%M")}</startTime>')
                xml_parts.append(f'<durationInDays>{item.get("durationInDays", 7)}</durationInDays>')
                xml_parts.append(f'<autoRenew>{item.get("autoRenew", "no")}</autoRenew>')
                
                # Флаг предотвращения дублирования товаров
                if item.get("itemNumberUniqueFlag"):
                    xml_parts.append(f'<itemNumberUniqueFlag>{item["itemNumberUniqueFlag"]}</itemNumberUniqueFlag>')
                
                # Энергетические метки и технические паспорта (для электронных товаров)
                if item.get("energyLabelUrl"):
                    xml_parts.append(f'<energyLabelUrl>{item["energyLabelUrl"]}</energyLabelUrl>')
                if item.get("productInfoUrl"):
                    xml_parts.append(f'<productInfoUrl>{item["productInfoUrl"]}</productInfoUrl>')
                
                xml_parts.append('</item>')
            
            xml_parts.append('</items>')
        
        xml_parts.append('</api>')
        return '\n'.join(xml_parts)
    
    def upload_item(self, item_data: Dict[str, Any]) -> Dict[str, Any]:
        """Загрузка одного товара (только один товар на запрос согласно документации)"""
        try:
            # Согласно документации: только один товар на запрос для itemInsert
            xml_request = self._build_xml_request('itemInsert', [item_data])
            
            response = self.session.post(
                self.api_url,
                data=xml_request.encode('utf-8'),
                headers={'Content-Type': 'text/xml; charset=UTF-8'},
                timeout=30
            )
            
            logger.info(f"Hood API Response Status: {response.status_code}")
            logger.info(f"Hood API Response Content: {response.text[:500]}...")
            logger.info(f"Hood API Full Response: {response.text}")
            
            # Парсинг ответа
            root = self._parse_xml_safely(response.text)
            
            if root is not None:
                # Проверяем на глобальные ошибки
                global_error = root.find('.//globalError')
                if global_error is not None:
                    return {
                        'success': False,
                        'error': global_error.text,
                        'raw_response': response.text
                    }
                
                # Обрабатываем ответ согласно документации
                # Проверяем, является ли корневой элемент response
                if root.tag == 'response':
                    response_container = root
                else:
                    response_container = root.find('.//response')
                
                if response_container is not None:
                    # Согласно диагностике, API возвращает item напрямую в response
                    # Сначала ищем item напрямую в response (основной случай)
                    item_container = response_container.find('item')
                    if item_container is not None:
                        logger.info("Найден элемент 'item' напрямую в response")
                    else:
                        # Если не найден, ищем внутри items (для обратной совместимости)
                        items_container = response_container.find('items')
                        if items_container is not None:
                            item_container = items_container.find('item')
                            logger.info("Найден элемент 'item' внутри контейнера 'items'")
                        else:
                            logger.info("Элемент 'item' не найден ни в response, ни в items")
                    
                    logger.info(f"item_container найден: {item_container is not None}")
                    
                    if item_container is not None:
                        # Извлекаем данные из ответа согласно документации
                        reference_id = item_container.find('referenceID')
                        status = item_container.find('status')
                        item_id = item_container.find('itemID')
                        cost = item_container.find('cost')
                        costs = item_container.find('costs')  # Также проверяем costs
                        message = item_container.find('message')
                        
                        # Определяем успешность на основе статуса
                        # Успех: success, not approved (товар уже существует), или любой статус кроме failed/error
                        status_text = status.text if status is not None else ''
                        is_success = status_text in ['success', 'not approved'] or (status_text and status_text not in ['failed', 'error'])
                        
                        # Логируем детали ответа
                        logger.info(f"Upload Status: {status.text if status is not None else 'unknown'}")
                        logger.info(f"Item ID: {item_id.text if item_id is not None else 'None'}")
                        logger.info(f"Reference ID: {reference_id.text if reference_id is not None else 'None'}")
                        logger.info(f"Cost: {cost.text if cost is not None else 'None'}")
                        logger.info(f"Message: {message.text if message is not None else 'None'}")
                        logger.info(f"Success: {is_success}")
                        
                        result = {
                            'success': is_success,
                            'raw_response': response.text
                        }
                        
                        if reference_id is not None:
                            result['referenceID'] = reference_id.text
                            result['reference_id'] = reference_id.text  # Для обратной совместимости
                        if status is not None:
                            result['status'] = status.text
                        if item_id is not None:
                            result['itemID'] = item_id.text
                            result['item_id'] = item_id.text  # Для обратной совместимости
                        if cost is not None:
                            result['cost'] = cost.text
                            result['costs'] = cost.text  # Для обратной совместимости
                        
                        # Также проверяем элемент costs
                        if costs is not None:
                            result['cost'] = costs.text
                            result['costs'] = costs.text  # Для обратной совместимости
                        if message is not None:
                            result['message'] = message.text
                        
                        # Проверяем элемент error для дополнительной информации
                        error_element = item_container.find("error")
                        if error_element is not None:
                            result["error"] = error_element.text
                            result["error_message"] = error_element.text
                        
                        # Если товар уже существует (not approved), это тоже успех
                        if status_text == "not approved":
                            result["already_exists"] = True
                            result["message"] = "Товар уже существует на Hood.de"
                        
                        return result
                    else:
                        logger.error("item_container не найден в ответе API")
                        logger.error(f"response_container содержимое: {ET.tostring(response_container, encoding='unicode')}")
                        return {
                            'success': False,
                            'error': 'Не удалось найти элемент item в ответе API',
                            'raw_response': response.text
                        }
                else:
                    return {
                        'success': False,
                        'error': 'Не удалось найти элемент response в ответе API',
                        'raw_response': response.text
                    }
            else:
                result = {
                    'success': False,
                    'error': 'Не удалось распарсить XML ответ от API',
                    'raw_response': response.text
                }
            
                return {
                    "success": False,
                    "error": "Не удалось распарсить XML ответ от API",
                    "raw_response": response.text
                }
        except Exception as e:
            logger.error(f"Hood API Unexpected Error: {str(e)}")
            return {
                'success': False,
                'error': f'Неожиданная ошибка: {str(e)}',
                'raw_response': ''
            }
    
    def upload_multiple_items(self, items_data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Загрузка нескольких товаров (по одному на запрос согласно документации)"""
        results = []
        
        logger.info(f"Начинаем загрузку {len(items_data)} товаров (по одному на запрос)")
        
        for i, item_data in enumerate(items_data):
            logger.info(f"Загружаем товар {i+1}/{len(items_data)}: {item_data.get('itemName', 'Unknown')}")
            
            # Согласно документации: только один товар на запрос для itemInsert
            result = self.upload_item(item_data)
            result['item_index'] = i
            results.append(result)
            
            # Добавляем небольшую задержку между запросами для оптимизации нагрузки
            if i < len(items_data) - 1:
                import time
                time.sleep(1)  # 1 секунда между запросами
        
        return results
    
    def get_categories(self) -> Dict[str, Any]:
        """Получение списка категорий"""
        try:
            # Создаем XML запрос для categoriesBrowse с categoryID=0
            xml_request = f'''<?xml version="1.0" encoding="UTF-8"?>
<api type="public" version="2.0" user="{self.api_user}" password="{self._hash_password(self.api_password)}">
\t<function>categoriesBrowse</function>
\t<categoryID>0</categoryID>
</api>'''
            
            response = self.session.post(
                self.api_url,
                data=xml_request,
                headers={'Content-Type': 'text/xml; charset=UTF-8'},
                timeout=30
            )
            
            logger.info(f"Categories API Response Status: {response.status_code}")
            logger.info(f"Categories API Response Content: {response.text[:500]}...")
            
            root = self._parse_xml_safely(response.text)
            
            if root is not None:
                categories = []
                
                for category in root.findall('.//category'):
                    cat_data = {
                        'id': category.find('categoryID').text if category.find('categoryID') is not None else '',
                        'name': category.find('categoryName').text if category.find('categoryName') is not None else '',
                        'path': category.find('categoryName').text if category.find('categoryName') is not None else '',
                        'level': '0',  # Уровень будет определяться по parentID
                        'parentID': category.find('parentID').text if category.find('parentID') is not None else '0',
                        'childCount': category.find('childCount').text if category.find('childCount') is not None else '0',
                        'insertProduct': category.find('insertProduct').text if category.find('insertProduct') is not None else '0',
                    }
                    categories.append(cat_data)
                
                return {
                    'success': True,
                    'categories': categories,
                    'raw_response': response.text
                }
            else:
                return {
                    'success': False,
                    'error': 'Не удалось распарсить XML ответ от API категорий',
                    'raw_response': response.text
                }
                
        except requests.RequestException as e:
            logger.error(f"Categories API Request Error: {str(e)}")
            return {
                'success': False,
                'error': f'Ошибка запроса: {str(e)}',
                'raw_response': ''
            }
        except Exception as e:
            logger.error(f"Categories API Unexpected Error: {str(e)}")
            return {
                'success': False,
                'error': f'Неожиданная ошибка: {str(e)}',
                'raw_response': ''
            }
    
    def get_categories_by_parent(self, parent_id: str) -> Dict[str, Any]:
        """Получение подкатегорий для родительской категории"""
        try:
            # Создаем XML запрос для categoriesBrowse с конкретным categoryID
            xml_request = f'''<?xml version="1.0" encoding="UTF-8"?>
<api type="public" version="2.0" user="{self.api_user}" password="{self._hash_password(self.api_password)}">
\t<function>categoriesBrowse</function>
\t<categoryID>{parent_id}</categoryID>
</api>'''
            
            response = self.session.post(
                self.api_url,
                data=xml_request,
                headers={'Content-Type': 'text/xml; charset=UTF-8'},
                timeout=30
            )
            
            logger.info(f"Categories by parent API Response Status: {response.status_code}")
            logger.info(f"Categories by parent API Response Content: {response.text[:500]}...")
            
            root = self._parse_xml_safely(response.text)
            
            if root is not None:
                categories = []
                
                for category in root.findall('.//category'):
                    cat_data = {
                        'id': category.find('categoryID').text if category.find('categoryID') is not None else '',
                        'name': category.find('categoryName').text if category.find('categoryName') is not None else '',
                        'path': category.find('categoryName').text if category.find('categoryName') is not None else '',
                        'level': '1',  # Подкатегория
                        'parentID': category.find('parentID').text if category.find('parentID') is not None else parent_id,
                        'childCount': category.find('childCount').text if category.find('childCount') is not None else '0',
                        'insertProduct': category.find('insertProduct').text if category.find('insertProduct') is not None else '0',
                    }
                    categories.append(cat_data)
                
                return {
                    'success': True,
                    'categories': categories,
                    'raw_response': response.text
                }
            else:
                return {
                    'success': False,
                    'error': 'Не удалось распарсить XML ответ от API категорий',
                    'raw_response': response.text
                }
                
        except requests.RequestException as e:
            logger.error(f"Categories by parent API Request Error: {str(e)}")
            return {
                'success': False,
                'error': f'Ошибка запроса: {str(e)}',
                'raw_response': ''
            }
        except Exception as e:
            logger.error(f"Categories by parent API Unexpected Error: {str(e)}")
            return {
                'success': False,
                'error': f'Неожиданная ошибка: {str(e)}',
                'raw_response': ''
            }
    
    def get_categories_fallback(self) -> Dict[str, Any]:
        """Получение категорий из локального файла (fallback)"""
        try:
            import json
            import os
            
            # Путь к файлу с категориями
            categories_file = '/Users/balabiturembek/Desktop/matplot/hood_categories_manual.json'
            
            if os.path.exists(categories_file):
                with open(categories_file, 'r', encoding='utf-8') as f:
                    categories_data = json.load(f)
                
                # Преобразуем в формат API
                categories = []
                for i, cat in enumerate(categories_data):
                    # Генерируем ID на основе индекса, если его нет
                    cat_id = cat.get('id', str(10000 + i))  # Используем индексы начиная с 10000
                    categories.append({
                        'id': str(cat_id),
                        'name': cat.get('name', ''),
                        'path': cat.get('url', cat.get('path', '')),
                        'level': str(cat.get('level', 0))
                    })
                
                return {
                    'success': True,
                    'categories': categories,
                    'source': 'fallback_file',
                    'raw_response': 'Loaded from local file'
                }
            else:
                return {
                    'success': False,
                    'error': 'Файл с категориями не найден',
                    'raw_response': ''
                }
                
        except Exception as e:
            logger.error(f"Fallback categories error: {str(e)}")
            return {
                'success': False,
                'error': f'Ошибка загрузки fallback категорий: {str(e)}',
                'raw_response': ''
            }
    
    def check_api_connection(self) -> Dict[str, Any]:
        """Проверка соединения с Hood.de API"""
        try:
            # Создаем простой тестовый запрос для проверки соединения
            xml_request = f'''<?xml version="1.0" encoding="UTF-8"?>
<api type="public" version="2.0" user="{self.api_user}" password="{self._hash_password(self.api_password)}">
\t<function>categoriesBrowse</function>
\t<categoryID>0</categoryID>
</api>'''
            
            response = self.session.post(
                self.api_url,
                data=xml_request,
                headers={'Content-Type': 'text/xml; charset=UTF-8'},
                timeout=10  # Короткий таймаут для быстрой проверки
            )
            
            # Проверяем статус ответа
            if response.status_code == 200:
                response_text = response.text.strip()
                
                # Проверяем, что ответ не является HTML страницей
                if response_text.startswith('<!DOCTYPE html>') or response_text.startswith('<html'):
                    return {
                        'success': False,
                        'status': 'html_response',
                        'message': 'API вернул HTML страницу вместо XML. Проверьте URL и учетные данные.',
                        'response_time': response.elapsed.total_seconds(),
                        'response_preview': response_text[:200] + '...' if len(response_text) > 200 else response_text
                    }
                
                # Пробуем парсить ответ как XML
                root = self._parse_xml_safely(response_text)
                
                if root is not None:
                    # Проверяем наличие категорий в ответе
                    categories = root.findall('.//category')
                    if categories:
                        return {
                            'success': True,
                            'status': 'connected',
                            'message': 'Соединение с Hood.de API установлено',
                            'response_time': response.elapsed.total_seconds(),
                            'categories_count': len(categories)
                        }
                    else:
                        # Проверяем наличие ошибок
                        error = root.find('.//error')
                        if error is not None and error.text == 'globalError':
                            info = root.find('.//info')
                            return {
                                'success': False,
                                'status': 'api_error',
                                'message': f'API ошибка: {info.text if info is not None else "Unknown error"}',
                                'response_time': response.elapsed.total_seconds(),
                                'response_preview': response_text[:200] + '...' if len(response_text) > 200 else response_text
                            }
                        else:
                            return {
                                'success': False,
                                'status': 'invalid_response',
                                'message': 'API вернул некорректный XML ответ',
                                'response_time': response.elapsed.total_seconds(),
                                'response_preview': response_text[:200] + '...' if len(response_text) > 200 else response_text
                            }
                else:
                    return {
                        'success': False,
                        'status': 'parse_error',
                        'message': 'Не удалось распарсить XML ответ от API',
                        'response_time': response.elapsed.total_seconds(),
                        'response_preview': response_text[:200] + '...' if len(response_text) > 200 else response_text
                    }
            else:
                return {
                    'success': False,
                    'status': 'http_error',
                    'message': f'HTTP ошибка: {response.status_code}',
                    'response_time': response.elapsed.total_seconds()
                }
                
        except requests.exceptions.Timeout:
            return {
                'success': False,
                'status': 'timeout',
                'message': 'Таймаут соединения с API',
                'response_time': None
            }
        except requests.exceptions.ConnectionError as e:
            error_msg = 'Ошибка соединения с API'
            if 'SSL' in str(e) or 'TLS' in str(e):
                error_msg += '. Возможно проблема с TLS версией (требуется TLS 1.2+)'
            return {
                'success': False,
                'status': 'connection_error',
                'message': error_msg,
                'response_time': None,
                'ssl_error': str(e)
            }
        except ssl.SSLError as e:
            return {
                'success': False,
                'status': 'ssl_error',
                'message': f'SSL ошибка: {str(e)}. Требуется TLS 1.2+',
                'response_time': None,
                'ssl_error': str(e)
            }
        except requests.exceptions.RequestException as e:
            return {
                'success': False,
                'status': 'request_error',
                'message': f'Ошибка запроса: {str(e)}',
                'response_time': None
            }
        except Exception as e:
            logger.error(f"API connection check error: {str(e)}")
            return {
                'success': False,
                'status': 'unknown_error',
                'message': f'Неожиданная ошибка: {str(e)}',
                'response_time': None
            }
    
    def item_validate(self, item_data: Dict[str, Any]) -> Dict[str, Any]:
        """Валидация товара перед загрузкой (показывает стоимость добавления)"""
        try:
            xml_request = self._build_xml_request('itemValidate', [item_data])
            
            response = self.session.post(
                self.api_url,
                data=xml_request,
                headers={'Content-Type': 'text/xml; charset=UTF-8'},
                timeout=30
            )
            
            root = self._parse_xml_safely(response.text)
            
            if root is not None:
                # Проверяем на глобальные ошибки
                global_error = root.find('.//globalError')
                if global_error is not None:
                    return {
                        'success': False,
                        'error': global_error.text,
                        'raw_response': response.text
                    }
                
                # Обрабатываем ответ согласно документации
                # Проверяем, является ли корневой элемент response
                if root.tag == 'response':
                    response_container = root
                else:
                    response_container = root.find('.//response')
                
                if response_container is not None:
                    # Ищем элемент items в response, затем item внутри items
                    items_container = response_container.find('items')
                    if items_container is not None:
                        item_container = items_container.find('item')
                    else:
                        item_container = response_container.find('item')
                    
                    if item_container is not None:
                        # Извлекаем данные из ответа согласно документации
                        reference_id = item_container.find('referenceID')
                        status = item_container.find('status')
                        item_id = item_container.find('itemID')
                        cost = item_container.find('cost')
                        costs = item_container.find('costs')  # Также проверяем costs
                        message = item_container.find('message')
                        
                        result = {
                            'success': status.text == 'success' if status is not None else False,
                            'raw_response': response.text
                        }
                        
                        if reference_id is not None:
                            result['referenceID'] = reference_id.text
                        if status is not None:
                            result['status'] = status.text
                        if item_id is not None:
                            result['itemID'] = item_id.text
                        if cost is not None:
                            result['cost'] = cost.text
                            result['costs'] = cost.text  # Для обратной совместимости
                        
                        # Также проверяем элемент costs
                        if costs is not None:
                            result['cost'] = costs.text
                            result['costs'] = costs.text  # Для обратной совместимости
                        if message is not None:
                            result['message'] = message.text
                        
                        return result
                
                # Ищем информацию о стоимости (старый формат для обратной совместимости)
                costs_element = root.find('.//costs')
                costs = costs_element.text if costs_element is not None else None
                
                return {
                    'success': True,
                    'costs': costs,
                    'raw_response': response.text
                }
            
            return {
                'success': False,
                'error': 'Не удалось распарсить ответ валидации',
                'raw_response': response.text
            }
            
        except Exception as e:
            logger.error(f"Item validation error: {str(e)}")
            return {
                'success': False,
                'error': f'Ошибка валидации: {str(e)}',
                'raw_response': ''
            }
    
    def item_update(self, item_id: str, item_data: Dict[str, Any]) -> Dict[str, Any]:
        """Обновление существующего товара (до 5 товаров одновременно)"""
        try:
            # Добавляем ID товара в данные
            item_data['itemID'] = item_id
            xml_request = self._build_xml_request('itemUpdate', [item_data])
            
            response = self.session.post(
                self.api_url,
                data=xml_request,
                headers={'Content-Type': 'text/xml; charset=UTF-8'},
                timeout=30
            )
            
            root = self._parse_xml_safely(response.text)
            
            if root is not None:
                # Проверяем на глобальные ошибки
                global_error = root.find('.//globalError')
                if global_error is not None:
                    return {
                        'success': False,
                        'error': global_error.text,
                        'raw_response': response.text
                    }
                
                # Обрабатываем ответ согласно документации
                response_container = root.find('.//response')
                if response_container is not None:
                    # Проверяем наличие контейнера items
                    items_container = response_container.find('.//items')
                    if items_container is not None:
                        # Обрабатываем все товары в контейнере items
                        items = items_container.findall('.//item')
                        results = []
                        
                        for item in items:
                            item_id_elem = item.find('itemID')
                            status = item.find('status')
                            message = item.find('message')
                            
                            item_result = {
                                'success': status.text == 'success' if status is not None else False,
                                'raw_response': response.text
                            }
                            
                            if item_id_elem is not None:
                                item_result['itemID'] = item_id_elem.text
                            if status is not None:
                                item_result['status'] = status.text
                            if message is not None:
                                item_result['message'] = message.text
                            
                            results.append(item_result)
                        
                        # Возвращаем результат для первого товара (для обратной совместимости)
                        if results:
                            return results[0]
                    
                    # Обрабатываем одиночный товар (старый формат)
                    item_container = response_container.find('.//item')
                    if item_container is not None:
                        item_id_elem = item_container.find('itemID')
                        status = item_container.find('status')
                        message = item_container.find('message')
                        
                        result = {
                            'success': status.text == 'success' if status is not None else False,
                            'raw_response': response.text
                        }
                        
                        if item_id_elem is not None:
                            result['itemID'] = item_id_elem.text
                        if status is not None:
                            result['status'] = status.text
                        if message is not None:
                            result['message'] = message.text
                        
                        return result
            
            return {
                'success': False,
                'error': 'Не удалось распарсить ответ обновления',
                'raw_response': response.text
            }
            
        except Exception as e:
            logger.error(f"Item update error: {str(e)}")
            return {
                'success': False,
                'error': f'Ошибка обновления: {str(e)}',
                'raw_response': ''
            }
    
    def item_delete(self, item_id: str) -> Dict[str, Any]:
        """Удаление товара"""
        try:
            xml_request = self._build_xml_request('itemDelete', itemID=item_id)
            
            response = self.session.post(
                self.api_url,
                data=xml_request,
                headers={'Content-Type': 'text/xml; charset=UTF-8'},
                timeout=30
            )
            
            root = self._parse_xml_safely(response.text)
            
            if root is not None:
                # Проверяем на глобальные ошибки
                global_error = root.find('.//globalError')
                if global_error is not None:
                    return {
                        'success': False,
                        'error': global_error.text,
                        'raw_response': response.text
                    }
                
                # Обрабатываем ответ согласно документации
                response_container = root.find('.//response')
                if response_container is not None:
                    # Проверяем наличие контейнера items
                    items_container = response_container.find('.//items')
                    if items_container is not None:
                        # Обрабатываем все товары в контейнере items
                        items = items_container.findall('.//item')
                        results = []
                        
                        for item in items:
                            item_id_elem = item.find('itemID')
                            status = item.find('status')
                            item_error = item.find('itemError')
                            
                            item_result = {
                                'success': status.text == 'success' if status is not None else False,
                                'raw_response': response.text
                            }
                            
                            if item_id_elem is not None:
                                item_result['itemID'] = item_id_elem.text
                            if status is not None:
                                item_result['status'] = status.text
                            if item_error is not None:
                                item_result['itemError'] = item_error.text
                                item_result['message'] = item_error.text  # Для обратной совместимости
                            
                            results.append(item_result)
                        
                        # Возвращаем результат для первого товара (для обратной совместимости)
                        if results:
                            return results[0]
                    
                    # Обрабатываем одиночный товар (старый формат)
                    item_container = response_container.find('.//item')
                    if item_container is not None:
                        item_id_elem = item_container.find('itemID')
                        status = item_container.find('status')
                        item_error = item_container.find('itemError')
                        
                        result = {
                            'success': status.text == 'success' if status is not None else False,
                            'raw_response': response.text
                        }
                        
                        if item_id_elem is not None:
                            result['itemID'] = item_id_elem.text
                        if status is not None:
                            result['status'] = status.text
                        if item_error is not None:
                            result['itemError'] = item_error.text
                            result['message'] = item_error.text  # Для обратной совместимости
                        
                        return result
            
            return {
                'success': False,
                'error': 'Не удалось распарсить ответ удаления',
                'raw_response': response.text
            }
            
        except Exception as e:
            logger.error(f"Item delete error: {str(e)}")
            return {
                'success': False,
                'error': f'Ошибка удаления: {str(e)}',
                'raw_response': ''
            }
    
    
    def delete_item(self, item_id: str) -> Dict[str, Any]:
        """Удаление одного товара согласно документации Hood.de API"""
        try:
            # Создаем XML запрос для удаления одного товара согласно документации
            xml_request = f"""<?xml version="1.0" encoding="UTF-8"?>
<api type="public" version="2.0" user="{self.api_user}" password="{self._hash_password(self.api_password)}">
	<function>itemDelete</function>
	<accountName>{self.account_name}</accountName>
	<accountPass>{self._hash_password(self.account_pass)}</accountPass>
	<items>
		<item>
			<itemID>{item_id}</itemID>
		</item>
	</items>
</api>"""
            
            response = self.session.post(
                self.api_url,
                data=xml_request,
                headers={'Content-Type': 'text/xml; charset=UTF-8'},
                timeout=30
            )
            
            logger.info(f"Delete API Response Status: {response.status_code}")
            logger.info(f"Delete API Response Content: {response.text[:500]}...")
            
            # Парсинг ответа
            root = self._parse_xml_safely(response.text)
            
            if root is not None:
                # Проверяем на глобальные ошибки
                global_error = root.find('.//globalError')
                if global_error is not None:
                    return {
                        'success': False,
                        'error': global_error.text,
                        'raw_response': response.text
                    }
                
                # Проверяем на info ошибки
                info_error = root.find('.//info')
                if info_error is not None and 'error' in info_error.text.lower():
                    return {
                        'success': False,
                        'error': info_error.text,
                        'raw_response': response.text
                    }
                
                # Обрабатываем ответ согласно документации
                # Проверяем, является ли корневой элемент response
                if root.tag == 'response':
                    response_container = root
                else:
                    response_container = root.find('.//response')
                
                if response_container is not None:
                    # Ищем элемент items в response, затем item внутри items
                    items_container = response_container.find('items')
                    if items_container is not None:
                        item_container = items_container.find('item')
                    else:
                        item_container = response_container.find('item')
                    
                    if item_container is not None:
                        # Извлекаем данные из ответа
                        item_id_elem = item_container.find('itemID')
                        status = item_container.find('status')
                        item_error = item_container.find('itemError')
                        
                        # Определяем успешность на основе статуса
                        is_success = status.text == 'success' if status is not None else False
                        
                        # Логируем детали ответа
                        logger.info(f"Delete Status: {status.text if status is not None else 'unknown'}")
                        logger.info(f"Item ID: {item_id_elem.text if item_id_elem is not None else 'None'}")
                        logger.info(f"Item Error: {item_error.text if item_error is not None else 'None'}")
                        logger.info(f"Success: {is_success}")
                        
                        result = {
                            'success': is_success,
                            'raw_response': response.text
                        }
                        
                        if item_id_elem is not None:
                            result['itemID'] = item_id_elem.text
                        if status is not None:
                            result['status'] = status.text
                        if item_error is not None:
                            result['itemError'] = item_error.text
                        
                        return result
                    else:
                        result = {
                            'success': False,
                            'error': 'Не удалось найти элемент item в ответе API',
                            'raw_response': response.text
                        }
                else:
                    result = {
                        'success': False,
                        'error': 'Не удалось найти элемент response в ответе API',
                        'raw_response': response.text
                    }
            else:
                result = {
                    'success': False,
                    'error': 'Не удалось распарсить XML ответ от API',
                    'raw_response': response.text
                }
            
            return result
            
        except requests.RequestException as e:
            logger.error(f"Delete API Request Error: {str(e)}")
            return {
                'success': False,
                'error': f'Ошибка запроса: {str(e)}',
                'raw_response': ''
            }
        except Exception as e:
            logger.error(f"Delete API Unexpected Error: {str(e)}")
            return {
                'success': False,
                'error': f'Неожиданная ошибка: {str(e)}',
                'raw_response': ''
            }

    def item_detail(self, item_id: str) -> Dict[str, Any]:
        """Получение детальной информации о товаре через itemStatus"""
        try:
            # Используем itemStatus вместо itemDetail для совместимости
            result = self.get_item_status_by_id(item_id, ['image', 'description'])
            
            if result.get('success'):
                items = result.get('items', [])
                if items:
                    return {
                        'success': True,
                        'item_data': items[0],
                        'all_items': items,
                        'raw_response': result.get('raw_response', '')
                    }
                else:
                    return {
                        'success': False,
                        'error': 'Товар не найден в ответе itemStatus',
                        'raw_response': result.get('raw_response', '')
                    }
            else:
                return {
                    'success': False,
                    'error': result.get('error', 'Ошибка получения статуса товара'),
                    'raw_response': result.get('raw_response', '')
                }
                
        except Exception as e:
            logger.error(f"Item detail error: {str(e)}")
            return {
                'success': False,
                'error': f'Ошибка получения деталей: {str(e)}',
                'raw_response': ''
            }
    
    def _extract_item_data(self, item_element) -> Dict[str, Any]:
        """Извлекает все данные товара из XML элемента"""
        item_data = {}
        
        # Основные поля товара
        basic_fields = [
            'itemID', 'itemName', 'quantity', 'condition', 'description', 
            'price', 'manufacturer', 'weight', 'itemMode', 'categoryID',
            'startDate', 'startTime', 'durationInDays', 'autoRenew',
            'energyLabelUrl', 'productInfoUrl', 'itemNumberUniqueFlag'
        ]
        
        for field in basic_fields:
            element = item_element.find(field)
            if element is not None and element.text:
                item_data[field] = element.text
        
        # Обработка изображений
        images_element = item_element.find('images')
        if images_element is not None:
            images = []
            for image_url in images_element.findall('imageURL'):
                if image_url.text:
                    images.append(image_url.text)
            
            for image_base64 in images_element.findall('imageBase64'):
                if image_base64.text:
                    images.append({
                        'type': 'base64',
                        'data': image_base64.text
                    })
            
            for image in images_element.findall('image'):
                image_data = {}
                image_url_elem = image.find('imageURL')
                if image_url_elem is not None and image_url_elem.text:
                    image_data['url'] = image_url_elem.text
                
                image_base64_elem = image.find('imageBase64')
                if image_base64_elem is not None and image_base64_elem.text:
                    image_data['base64'] = image_base64_elem.text
                
                option_details = image.find('optionDetails')
                if option_details is not None:
                    image_data['optionDetails'] = self._extract_option_details(option_details)
                
                if image_data:
                    images.append(image_data)
            
            if images:
                item_data['images'] = images
        
        # Обработка способов доставки
        shipmethods_element = item_element.find('shipmethods')
        if shipmethods_element is not None:
            shipmethods = []
            for shipmethod in shipmethods_element.findall('shipmethod'):
                name = shipmethod.get('name')
                value_elem = shipmethod.find('value')
                if name and value_elem is not None and value_elem.text:
                    shipmethods.append({
                        'name': name,
                        'value': value_elem.text
                    })
            if shipmethods:
                item_data['shipMethods'] = shipmethods
        
        # Обработка способов оплаты
        payoptions_element = item_element.find('payOptions')
        if payoptions_element is not None:
            payoptions = []
            for option in payoptions_element.findall('option'):
                if option.text:
                    payoptions.append(option.text)
            if payoptions:
                item_data['payOptions'] = payoptions
        
        # Обработка свойств товара
        productproperties_element = item_element.find('productProperties')
        if productproperties_element is not None:
            properties = {}
            for namevaluelist in productproperties_element.findall('nameValueList'):
                name_elem = namevaluelist.find('name')
                value_elem = namevaluelist.find('value')
                if name_elem is not None and value_elem is not None:
                    name = name_elem.text
                    value = value_elem.text
                    if name and value:
                        properties[name] = value
            if properties:
                item_data['productProperties'] = properties
        
        # Обработка вариантов товара
        productoptions_element = item_element.find('productOptions')
        if productoptions_element is not None:
            product_options = []
            for productoption in productoptions_element.findall('productOption'):
                option_data = {}
                
                # Основные поля варианта
                option_fields = [
                    'optionPrice', 'optionQuantity', 'optionItemNumber', 
                    'mpn', 'ean', 'PackagingSize'
                ]
                
                for field in option_fields:
                    element = productoption.find(field)
                    if element is not None and element.text:
                        option_data[field] = element.text
                
                # Обработка деталей варианта
                optiondetails = productoption.find('optionDetails')
                if optiondetails is not None:
                    option_data['optionDetails'] = self._extract_option_details(optiondetails)
                
                if option_data:
                    product_options.append(option_data)
            
            if product_options:
                item_data['productOptions'] = product_options
        
        return item_data
    
    def _extract_option_details(self, optiondetails_element) -> Dict[str, str]:
        """Извлекает детали варианта из XML элемента"""
        details = {}
        for namevaluelist in optiondetails_element.findall('nameValueList'):
            name_elem = namevaluelist.find('name')
            value_elem = namevaluelist.find('value')
            if name_elem is not None and value_elem is not None:
                name = name_elem.text
                value = value_elem.text
                if name and value:
                    details[name] = value
        return details
    
    def get_item_summary(self, item_id: str) -> Dict[str, Any]:
        """Получает краткую сводку о товаре"""
        detail_result = self.item_detail(item_id)
        
        if not detail_result.get('success'):
            return detail_result
        
        item_data = detail_result.get('item_data', {})
        
        summary = {
            'itemID': item_data.get('itemID'),
            'itemName': item_data.get('itemName'),
            'price': item_data.get('price'),
            'quantity': item_data.get('quantity'),
            'condition': item_data.get('condition'),
            'manufacturer': item_data.get('manufacturer'),
            'categoryID': item_data.get('categoryID'),
            'itemMode': item_data.get('itemMode'),
            'has_images': bool(item_data.get('images')),
            'image_count': len(item_data.get('images', [])),
            'has_product_properties': bool(item_data.get('productProperties')),
            'properties_count': len(item_data.get('productProperties', {})),
            'has_product_options': bool(item_data.get('productOptions')),
            'options_count': len(item_data.get('productOptions', [])),
            'has_ship_methods': bool(item_data.get('shipMethods')),
            'ship_methods_count': len(item_data.get('shipMethods', [])),
            'has_pay_options': bool(item_data.get('payOptions')),
            'pay_options_count': len(item_data.get('payOptions', [])),
            'has_energy_efficiency': bool(item_data.get('energyLabelUrl') or item_data.get('productInfoUrl')),
            'energy_class': item_data.get('productProperties', {}).get('energyEfficiencyClass'),
            'is_unique': bool(item_data.get('itemNumberUniqueFlag'))
        }
        
        return {
            'success': True,
            'summary': summary,
            'raw_response': detail_result.get('raw_response')
        }
    
    def get_item_images(self, item_id: str) -> Dict[str, Any]:
        """Получает только изображения товара"""
        detail_result = self.item_detail(item_id)
        
        if not detail_result.get('success'):
            return detail_result
        
        item_data = detail_result.get('item_data', {})
        images = item_data.get('images', [])
        
        return {
            'success': True,
            'images': images,
            'image_count': len(images),
            'raw_response': detail_result.get('raw_response')
        }
    
    def get_item_properties(self, item_id: str) -> Dict[str, Any]:
        """Получает только свойства товара"""
        detail_result = self.item_detail(item_id)
        
        if not detail_result.get('success'):
            return detail_result
        
        item_data = detail_result.get('item_data', {})
        properties = item_data.get('productProperties', {})
        
        return {
            'success': True,
            'properties': properties,
            'properties_count': len(properties),
            'raw_response': detail_result.get('raw_response')
        }
    
    def get_item_options(self, item_id: str) -> Dict[str, Any]:
        """Получает только варианты товара"""
        detail_result = self.item_detail(item_id)
        
        if not detail_result.get('success'):
            return detail_result
        
        item_data = detail_result.get('item_data', {})
        options = item_data.get('productOptions', [])
        
        return {
            'success': True,
            'options': options,
            'options_count': len(options),
            'raw_response': detail_result.get('raw_response')
        }
    
    def compare_items(self, item_id1: str, item_id2: str) -> Dict[str, Any]:
        """Сравнивает два товара"""
        detail1 = self.item_detail(item_id1)
        detail2 = self.item_detail(item_id2)
        
        if not detail1.get('success') or not detail2.get('success'):
            return {
                'success': False,
                'error': 'Не удалось получить данные одного или обоих товаров'
            }
        
        data1 = detail1.get('item_data', {})
        data2 = detail2.get('item_data', {})
        
        comparison = {
            'item1': {
                'itemID': data1.get('itemID'),
                'itemName': data1.get('itemName'),
                'price': data1.get('price'),
                'quantity': data1.get('quantity')
            },
            'item2': {
                'itemID': data2.get('itemID'),
                'itemName': data2.get('itemName'),
                'price': data2.get('price'),
                'quantity': data2.get('quantity')
            },
            'differences': [],
            'similarities': []
        }
        
        # Сравниваем основные поля
        basic_fields = ['itemName', 'price', 'quantity', 'condition', 'manufacturer']
        for field in basic_fields:
            value1 = data1.get(field)
            value2 = data2.get(field)
            
            if value1 == value2:
                comparison['similarities'].append({
                    'field': field,
                    'value': value1
                })
            else:
                comparison['differences'].append({
                    'field': field,
                    'value1': value1,
                    'value2': value2
                })
        
        return {
            'success': True,
            'comparison': comparison
        }
    
    def get_shop_categories(self) -> Dict[str, Any]:
        """Получение категорий магазина"""
        try:
            xml_request = self._build_xml_request('shopCategories')
            
            response = self.session.post(
                self.api_url,
                data=xml_request,
                headers={'Content-Type': 'text/xml; charset=UTF-8'},
                timeout=30
            )
            
            root = self._parse_xml_safely(response.text)
            
            if root is not None:
                categories = []
                for category in root.findall('.//category'):
                    cat_data = {
                        'id': category.find('categoryID').text if category.find('categoryID') is not None else '',
                        'name': category.find('categoryName').text if category.find('categoryName') is not None else '',
                        'parent_id': category.find('parentID').text if category.find('parentID') is not None else '',
                        'child_count': category.find('childCount').text if category.find('childCount') is not None else '0',
                        'insert_product': category.find('insertProduct').text if category.find('insertProduct') is not None else '0',
                    }
                    categories.append(cat_data)
                
                return {
                    'success': True,
                    'categories': categories,
                    'raw_response': response.text
                }
            
            return {
                'success': False,
                'error': 'Не удалось распарсить ответ категорий магазина',
                'raw_response': response.text
            }
            
        except Exception as e:
            logger.error(f"Shop categories error: {str(e)}")
            return {
                'success': False,
                'error': f'Ошибка получения категорий магазина: {str(e)}',
                'raw_response': ''
            }
    
    def get_shop_categories_detailed(self) -> Dict[str, Any]:
        """Получение детальных категорий магазина с поддержкой собственных категорий"""
        try:
            xml_request = f'''<?xml version="1.0" encoding="UTF-8"?>
<api type="public" version="2.0" user="{self.api_user}" password="{self._hash_password(self.api_password)}">
\t<function>shopCategories</function>
\t<accountName>{self.account_name}</accountName>
\t<accountPass>{self._hash_password(self.account_pass)}</accountPass>
</api>'''
            
            response = self.session.post(
                self.api_url,
                data=xml_request,
                headers={'Content-Type': 'text/xml; charset=UTF-8'},
                timeout=30
            )
            
            root = self._parse_xml_safely(response.text)
            
            if root is not None:
                categories = []
                for category in root.findall('.//category'):
                    cat_data = {
                        'id': category.find('id').text if category.find('id') is not None else '',
                        'name': category.find('name').text if category.find('name') is not None else '',
                        'path': category.find('path').text if category.find('path') is not None else '',
                        'level': category.find('level').text if category.find('level') is not None else '0',
                        'is_custom': category.find('isCustom').text if category.find('isCustom') is not None else '0',
                        'parent_id': category.find('parentID').text if category.find('parentID') is not None else '',
                    }
                    categories.append(cat_data)
                
                return {
                    'success': True,
                    'categories': categories,
                    'raw_response': response.text
                }
            
            return {
                'success': False,
                'error': 'Не удалось распарсить ответ категорий магазина',
                'raw_response': response.text
            }
            
        except Exception as e:
            logger.error(f"Shop categories detailed error: {str(e)}")
            return {
                'success': False,
                'error': f'Ошибка получения детальных категорий магазина: {str(e)}',
                'raw_response': ''
            }
    
    def create_product_variant(self, 
                             option_price: float,
                             option_quantity: int,
                             option_details: List[Dict[str, str]],
                             option_item_number: str = None,
                             mpn: str = None,
                             ean: str = None,
                             packaging_size: int = 1) -> Dict[str, Any]:
        """Создает вариант продукта для Gold/Platinum магазинов"""
        return {
            'optionPrice': option_price,
            'optionQuantity': option_quantity,
            'optionItemNumber': option_item_number,
            'mpn': mpn,
            'ean': ean,
            'PackagingSize': packaging_size,
            'optionDetails': option_details
        }
    
    def create_gold_variants(self, 
                           base_price: float,
                           colors: List[str],
                           sizes: List[str],
                           quantities: List[int] = None) -> List[Dict[str, Any]]:
        """Создает варианты для Gold магазина (2 типа: цвет и размер)"""
        variants = []
        
        if quantities is None:
            quantities = [1] * len(colors) * len(sizes)
        
        quantity_index = 0
        for color in colors:
            for size in sizes:
                variant = self.create_product_variant(
                    option_price=base_price,
                    option_quantity=quantities[quantity_index] if quantity_index < len(quantities) else 1,
                    option_details=[
                        {'name': 'colour', 'value': color},
                        {'name': 'size', 'value': size}
                    ],
                    option_item_number=f"ITEM-{color.upper()}-{size.upper()}"
                )
                variants.append(variant)
                quantity_index += 1
        
        return variants
    
    def create_platinum_variants(self,
                                base_price: float,
                                colors: List[str],
                                sizes: List[str],
                                materials: List[str],
                                designs: List[str],
                                styles: List[str],
                                quantities: List[int] = None) -> List[Dict[str, Any]]:
        """Создает варианты для Platinum магазина (5 типов: цвет, размер, материал, дизайн, стиль)"""
        variants = []
        
        if quantities is None:
            quantities = [1] * len(colors) * len(sizes) * len(materials) * len(designs) * len(styles)
        
        quantity_index = 0
        for color in colors:
            for size in sizes:
                for material in materials:
                    for design in designs:
                        for style in styles:
                            variant = self.create_product_variant(
                                option_price=base_price,
                                option_quantity=quantities[quantity_index] if quantity_index < len(quantities) else 1,
                                option_details=[
                                    {'name': 'colour', 'value': color},
                                    {'name': 'size', 'value': size},
                                    {'name': 'material', 'value': material},
                                    {'name': 'design', 'value': design},
                                    {'name': 'style', 'value': style}
                                ],
                                option_item_number=f"ITEM-{color.upper()}-{size.upper()}-{material.upper()}-{design.upper()}-{style.upper()}"
                            )
                            variants.append(variant)
                            quantity_index += 1
        
        return variants
    
    def validate_shop_package(self, product_options: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Валидирует варианты товара согласно пакету магазина"""
        if not product_options:
            return {
                'valid': True,
                'package': 'Silver',
                'variant_count': 0,
                'max_variants': 0
            }
        
        # Определяем количество типов вариантов
        variant_types = set()
        for option in product_options:
            if 'optionDetails' in option:
                for detail in option['optionDetails']:
                    variant_types.add(detail['name'])
        
        variant_type_count = len(variant_types)
        variant_count = len(product_options)
        
        # Определяем пакет магазина
        if variant_type_count <= 1:
            package = 'Silver'
            max_variants = 0
        elif variant_type_count <= 2:
            package = 'Gold'
            max_variants = 2
        elif variant_type_count <= 5:
            package = 'Platinum'
            max_variants = 5
        else:
            package = 'Unknown'
            max_variants = 0
        
        # Проверяем соответствие
        valid = variant_type_count <= max_variants if max_variants > 0 else True
        
        return {
            'valid': valid,
            'package': package,
            'variant_count': variant_count,
            'variant_type_count': variant_type_count,
            'max_variants': max_variants,
            'variant_types': list(variant_types)
        }
    
    def _validate_product_properties(self, properties: Dict[str, str]) -> Dict[str, str]:
        """Валидирует и ограничивает свойства продукта согласно документации"""
        validated_properties = {}
        
        # Ограничиваем количество свойств до 15
        properties_items = list(properties.items())[:15]
        
        for prop_name, prop_value in properties_items:
            # Ограничиваем длину имени и значения до 30 символов
            validated_name = str(prop_name)[:30] if prop_name else ""
            validated_value = str(prop_value)[:30] if prop_value else ""
            
            # Пропускаем пустые свойства
            if validated_name and validated_value:
                validated_properties[validated_name] = validated_value
        
        return validated_properties
    
    def validate_age_restriction(self, category_id: str, properties: Dict[str, str]) -> Dict[str, Any]:
        """Валидирует ограничения по возрасту для определенных категорий"""
        # Категории, требующие ограничения по возрасту
        age_restricted_categories = {
            'film_dvd_bluray': ['Film & DVD > Blu-ray and DVD'],
            'games_consoles_games': ['Games & consoles > Games'],
            'books_magazines_mens': ['Books > Magazines > Men\'s Magazines']
        }
        
        # Возможные значения ограничений по возрасту
        valid_age_values = ['0', '6', '12', '16', '18', 'unknown']
        
        # Проверяем, нужны ли ограничения по возрасту для данной категории
        requires_age_restriction = False
        category_name = ""
        
        # Здесь можно добавить логику проверки category_id
        # Пока что возвращаем общую информацию
        
        # Проверяем наличие ограничения по возрасту в свойствах
        age_restriction = properties.get('age restriction', '').lower()
        
        result = {
            'requires_age_restriction': requires_age_restriction,
            'category_name': category_name,
            'has_age_restriction': bool(age_restriction),
            'age_restriction_value': age_restriction,
            'is_valid_age_value': age_restriction in valid_age_values,
            'valid_age_values': valid_age_values,
            'recommendations': []
        }
        
        if requires_age_restriction and not age_restriction:
            result['recommendations'].append(
                f"Категория '{category_name}' требует указания ограничения по возрасту"
            )
        
        if age_restriction and age_restriction not in valid_age_values:
            result['recommendations'].append(
                f"Недопустимое значение ограничения по возрасту: '{age_restriction}'. "
                f"Допустимые значения: {', '.join(valid_age_values)}"
            )
        
        return result
    
    def get_property_naming_recommendations(self, properties: Dict[str, str]) -> Dict[str, Any]:
        """Предоставляет рекомендации по именованию свойств продукта"""
        recommendations = {
            'general_recommendations': [],
            'specific_recommendations': {},
            'improved_properties': {}
        }
        
        # Общие рекомендации
        recommendations['general_recommendations'] = [
            "Используйте общие названия свойств (например, 'colour' вместо 'item colour')",
            "Максимум 30 символов для названия и значения",
            "Максимум 15 свойств на товар",
            "Избегайте дублирования свойств из вариантов товара"
        ]
        
        # Специфические рекомендации для каждого свойства
        for prop_name, prop_value in properties.items():
            prop_lower = prop_name.lower()
            specific_recommendations = []
            improved_name = prop_name
            
            # Рекомендации по именованию
            if 'color' in prop_lower or 'colour' in prop_lower:
                if prop_lower != 'colour':
                    improved_name = 'colour'
                    specific_recommendations.append("Используйте 'colour' вместо 'color'")
            elif 'size' in prop_lower:
                if prop_lower != 'size':
                    improved_name = 'size'
                    specific_recommendations.append("Используйте 'size' вместо других вариантов")
            elif 'material' in prop_lower:
                if prop_lower != 'material':
                    improved_name = 'material'
                    specific_recommendations.append("Используйте 'material' вместо других вариантов")
            elif 'brand' in prop_lower:
                if prop_lower != 'brand':
                    improved_name = 'brand'
                    specific_recommendations.append("Используйте 'brand' вместо других вариантов")
            elif 'model' in prop_lower:
                if prop_lower != 'model':
                    improved_name = 'model'
                    specific_recommendations.append("Используйте 'model' вместо других вариантов")
            
            # Проверка длины
            if len(prop_name) > 30:
                specific_recommendations.append(f"Название слишком длинное ({len(prop_name)} символов), максимум 30")
                improved_name = prop_name[:30]
            
            if len(prop_value) > 30:
                specific_recommendations.append(f"Значение слишком длинное ({len(prop_value)} символов), максимум 30")
            
            if specific_recommendations:
                recommendations['specific_recommendations'][prop_name] = specific_recommendations
                recommendations['improved_properties'][prop_name] = improved_name
        
        return recommendations
    
    def validate_energy_efficiency(self, category_id: str, properties: Dict[str, str]) -> Dict[str, Any]:
        """Валидирует требования энергетической эффективности согласно EU директивы 518/2014"""
        # Категории, требующие энергетических меток
        energy_efficiency_categories = {
            'televisions': ['Televisions'],
            'lamps_lights': ['Lamps and lights'],
            'ovens_hobs': ['Ovens & hobs'],
            'fridges_freezers': ['Fridges and freezers'],
            'washing_machines': ['Washing machines'],
            'dishwashers': ['Dishwashers'],
            'washer_dryers': ['Washer-dryers'],
            'air_conditioning': ['Air conditioning and ventilation'],
            'room_heaters': ['Room heaters'],
            'water_heaters': ['Water heaters'],
            'vacuum_cleaners': ['Vacuum cleaners'],
            'extractor_hoods': ['Extractor hoods']
        }
        
        # Возможные значения энергетических классов
        valid_energy_classes = ['A+++', 'A++', 'A+', 'A', 'B', 'C', 'D', 'E', 'F', 'G']
        
        # Проверяем, нужны ли энергетические метки для данной категории
        requires_energy_efficiency = False
        category_name = ""
        
        # Здесь можно добавить логику проверки category_id
        # Пока что возвращаем общую информацию
        
        # Проверяем наличие энергетического класса в свойствах
        energy_class = properties.get('energyEfficiencyClass', '').strip()
        
        result = {
            'requires_energy_efficiency': requires_energy_efficiency,
            'category_name': category_name,
            'has_energy_class': bool(energy_class),
            'energy_class': energy_class,
            'is_valid_energy_class': energy_class in valid_energy_classes,
            'valid_energy_classes': valid_energy_classes,
            'requires_energy_label': False,
            'requires_product_datasheet': False,
            'recommendations': []
        }
        
        # Определяем требования для разных категорий
        if requires_energy_efficiency:
            if category_name in ['Televisions', 'Ovens & hobs', 'Fridges and freezers', 
                               'Washing machines', 'Dishwashers', 'Washer-dryers', 
                               'Air conditioning and ventilation', 'Vacuum cleaners', 
                               'Extractor hoods']:
                result['requires_energy_label'] = True
                result['requires_product_datasheet'] = True
            elif category_name in ['Room heaters', 'Water heaters']:
                result['requires_energy_label'] = True
                result['requires_product_datasheet'] = True
            elif category_name in ['Lamps and lights']:
                result['requires_energy_label'] = True
                result['requires_product_datasheet'] = False
        
        if requires_energy_efficiency and not energy_class:
            result['recommendations'].append(
                f"Категория '{category_name}' требует указания энергетического класса"
            )
        
        if energy_class and energy_class not in valid_energy_classes:
            result['recommendations'].append(
                f"Недопустимый энергетический класс: '{energy_class}'. "
                f"Допустимые значения: {', '.join(valid_energy_classes)}"
            )
        
        return result
    
    def validate_energy_urls(self, item_data: Dict[str, Any]) -> Dict[str, Any]:
        """Валидирует URL энергетических меток и технических паспортов"""
        energy_label_url = item_data.get('energyLabelUrl', '')
        product_info_url = item_data.get('productInfoUrl', '')
        
        result = {
            'has_energy_label_url': bool(energy_label_url),
            'has_product_info_url': bool(product_info_url),
            'energy_label_url': energy_label_url,
            'product_info_url': product_info_url,
            'energy_label_valid': False,
            'product_info_valid': False,
            'recommendations': []
        }
        
        # Проверяем формат URL энергетической метки
        if energy_label_url:
            if energy_label_url.lower().endswith(('.pdf', '.jpg', '.jpeg', '.png')):
                result['energy_label_valid'] = True
            else:
                result['recommendations'].append(
                    "URL энергетической метки должен указывать на PDF или JPG файл"
                )
        
        # Проверяем формат URL технического паспорта
        if product_info_url:
            if product_info_url.lower().endswith('.pdf'):
                result['product_info_valid'] = True
            else:
                result['recommendations'].append(
                    "URL технического паспорта должен указывать на PDF файл"
                )
        
        return result
    
    def get_energy_efficiency_recommendations(self, category_id: str, properties: Dict[str, str]) -> Dict[str, Any]:
        """Предоставляет рекомендации по энергетической эффективности"""
        recommendations = {
            'general_recommendations': [],
            'category_specific': [],
            'url_recommendations': [],
            'compliance_status': 'unknown'
        }
        
        # Общие рекомендации
        recommendations['general_recommendations'] = [
            "Энергетические метки обязательны для электронных товаров с 01.01.2015",
            "Используйте энергетический класс от A+++ до G",
            "Предоставляйте URL энергетических меток (PDF или JPG)",
            "Предоставляйте URL технических паспортов (только PDF)",
            "Для ламп и светильников нужны только метки",
            "Для обогревателей и водонагревателей метки нужны для всех товаров"
        ]
        
        # Категорийные рекомендации
        energy_categories = {
            'televisions': 'Телевизоры требуют энергетические метки и технические паспорта',
            'lamps_lights': 'Лампы и светильники требуют только энергетические метки',
            'ovens_hobs': 'Печи и варочные панели требуют энергетические метки и технические паспорта',
            'fridges_freezers': 'Холодильники и морозильники требуют энергетические метки и технические паспорта',
            'washing_machines': 'Стиральные машины требуют энергетические метки и технические паспорта',
            'dishwashers': 'Посудомоечные машины требуют энергетические метки и технические паспорта',
            'washer_dryers': 'Стирально-сушильные машины требуют энергетические метки и технические паспорта',
            'air_conditioning': 'Кондиционеры требуют энергетические метки и технические паспорта',
            'room_heaters': 'Обогреватели требуют энергетические метки и технические паспорта (все товары)',
            'water_heaters': 'Водонагреватели требуют энергетические метки и технические паспорта (все товары)',
            'vacuum_cleaners': 'Пылесосы требуют энергетические метки и технические паспорта',
            'extractor_hoods': 'Вытяжки требуют энергетические метки и технические паспорта'
        }
        
        # Здесь можно добавить логику определения категории по category_id
        # Пока что предоставляем общие рекомендации
        
        # Рекомендации по URL
        recommendations['url_recommendations'] = [
            "energyLabelUrl: URL энергетической метки (PDF или JPG)",
            "productInfoUrl: URL технического паспорта (только PDF)",
            "Убедитесь, что файлы доступны по указанным URL",
            "Используйте HTTPS для безопасности"
        ]
        
        return recommendations
    
    def update_multiple_items(self, items_data: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Обновление нескольких товаров одновременно (до 5 товаров)"""
        if len(items_data) > 5:
            return {
                'success': False,
                'error': 'Максимум 5 товаров можно обновить одновременно',
                'raw_response': ''
            }
        
        try:
            # Добавляем itemID для каждого товара
            for item in items_data:
                if 'itemID' not in item:
                    return {
                        'success': False,
                        'error': 'itemID обязателен для обновления товара',
                        'raw_response': ''
                    }
            
            xml_request = self._build_xml_request('itemUpdate', items_data)
            
            response = self.session.post(
                self.api_url,
                data=xml_request,
                headers={'Content-Type': 'text/xml; charset=UTF-8'},
                timeout=30
            )
            
            root = self._parse_xml_safely(response.text)
            
            if root is not None:
                # Проверяем на глобальные ошибки
                global_error = root.find('.//globalError')
                if global_error is not None:
                    return {
                        'success': False,
                        'error': global_error.text,
                        'raw_response': response.text
                    }
                
                # Обрабатываем ответ согласно документации
                response_container = root.find('.//response')
                if response_container is not None:
                    items_container = response_container.find('.//items')
                    if items_container is not None:
                        items = items_container.findall('.//item')
                        results = []
                        
                        for item in items:
                            item_id_elem = item.find('itemID')
                            status = item.find('status')
                            message = item.find('message')
                            
                            item_result = {
                                'success': status.text == 'success' if status is not None else False,
                                'raw_response': response.text
                            }
                            
                            if item_id_elem is not None:
                                item_result['itemID'] = item_id_elem.text
                            if status is not None:
                                item_result['status'] = status.text
                            if message is not None:
                                item_result['message'] = message.text
                            
                            results.append(item_result)
                        
                        return {
                            'success': all(r['success'] for r in results),
                            'results': results,
                            'raw_response': response.text
                        }
            
            return {
                'success': False,
                'error': 'Не удалось распарсить ответ массового обновления',
                'raw_response': response.text
            }
            
        except Exception as e:
            logger.error(f"Multiple items update error: {str(e)}")
            return {
                'success': False,
                'error': f'Ошибка массового обновления: {str(e)}',
                'raw_response': ''
            }
    
    def delete_multiple_items(self, item_ids: List[str]) -> Dict[str, Any]:
        """Удаление нескольких товаров одновременно"""
        try:
            # Создаем данные для удаления
            items_data = [{'itemID': item_id} for item_id in item_ids]
            xml_request = self._build_xml_request('itemDelete', items_data)
            
            response = self.session.post(
                self.api_url,
                data=xml_request,
                headers={'Content-Type': 'text/xml; charset=UTF-8'},
                timeout=30
            )
            
            root = self._parse_xml_safely(response.text)
            
            if root is not None:
                # Проверяем на глобальные ошибки
                global_error = root.find('.//globalError')
                if global_error is not None:
                    return {
                        'success': False,
                        'error': global_error.text,
                        'raw_response': response.text
                    }
                
                # Обрабатываем ответ согласно документации
                response_container = root.find('.//response')
                if response_container is not None:
                    items_container = response_container.find('.//items')
                    if items_container is not None:
                        items = items_container.findall('.//item')
                        results = []
                        
                        for item in items:
                            item_id_elem = item.find('itemID')
                            status = item.find('status')
                            item_error = item.find('itemError')
                            
                            item_result = {
                                'success': status.text == 'success' if status is not None else False,
                                'raw_response': response.text
                            }
                            
                            if item_id_elem is not None:
                                item_result['itemID'] = item_id_elem.text
                            if status is not None:
                                item_result['status'] = status.text
                            if item_error is not None:
                                item_result['itemError'] = item_error.text
                                item_result['message'] = item_error.text
                            
                            results.append(item_result)
                        
                        return {
                            'success': all(r['success'] for r in results),
                            'results': results,
                            'raw_response': response.text
                        }
            
            return {
                'success': False,
                'error': 'Не удалось распарсить ответ массового удаления',
                'raw_response': response.text
            }
            
        except Exception as e:
            logger.error(f"Multiple items delete error: {str(e)}")
            return {
                'success': False,
                'error': f'Ошибка массового удаления: {str(e)}',
                'raw_response': ''
            }
    
    def create_unique_item(self, item_data: Dict[str, Any], enable_unique_flag: bool = True) -> Dict[str, Any]:
        """Создает товар с флагом предотвращения дублирования"""
        if enable_unique_flag:
            item_data['itemNumberUniqueFlag'] = 1
        
        return item_data
    
    def check_item_uniqueness(self, item_number: str) -> Dict[str, Any]:
        """Проверяет уникальность номера товара"""
        # Здесь можно добавить логику проверки существования товара
        # Пока что возвращаем общую информацию
        return {
            'item_number': item_number,
            'is_unique': True,  # Предполагаем, что товар уникален
            'message': 'Проверка уникальности не реализована'
        }
    
    def parse_api_response(self, response_text: str) -> Dict[str, Any]:
        """Парсит ответ API согласно документации"""
        try:
            root = self._parse_xml_safely(response_text)
            
            if root is None:
                return {
                    'success': False,
                    'error': 'Не удалось распарсить XML ответ',
                    'raw_response': response_text
                }
            
            # Проверяем на глобальные ошибки
            global_error = root.find('.//globalError')
            if global_error is not None:
                return {
                    'success': False,
                    'error': global_error.text,
                    'raw_response': response_text
                }
            
            # Обрабатываем ответ согласно документации
            response_container = root.find('.//response')
            if response_container is not None:
                item_container = response_container.find('.//item')
                if item_container is not None:
                    # Извлекаем данные из ответа согласно документации
                    reference_id = item_container.find('referenceID')
                    status = item_container.find('status')
                    item_id = item_container.find('itemID')
                    cost = item_container.find('cost')
                    message = item_container.find('message')
                    
                    result = {
                        'success': status.text == 'success' if status is not None else False,
                        'raw_response': response_text
                    }
                    
                    if reference_id is not None:
                        result['referenceID'] = reference_id.text
                    if status is not None:
                        result['status'] = status.text
                    if item_id is not None:
                        result['itemID'] = item_id.text
                    if cost is not None:
                        result['cost'] = cost.text
                    if message is not None:
                        result['message'] = message.text
                    
                    return result
            
            return {
                'success': False,
                'error': 'Не удалось найти контейнер response в ответе',
                'raw_response': response_text
            }
            
        except Exception as e:
            return {
                'success': False,
                'error': f'Ошибка парсинга ответа: {str(e)}',
                'raw_response': response_text
            }
    
    def create_item_insert_template(self, item_data: Dict[str, Any]) -> str:
        """Создает XML шаблон для itemInsert согласно документации"""
        xml_parts = [
            '<?xml version="1.0" encoding="UTF-8"?>',
            f'<api type="public" version="2.0" user="{self.api_user}" password="{self._hash_password(self.api_password)}">',
            '<function>itemInsert</function>',
            f'<accountName>{self.account_name}</accountName>',
            f'<accountPass>{self._hash_password(self.account_pass)}</accountPass>',
            '<items>',
            '<item>'
        ]
        
        # Основные обязательные поля
        # itemMode: shopProduct, classic, buyItNow
        item_mode = item_data.get("itemMode", "shopProduct")
        if item_mode not in ["shopProduct", "classic", "buyItNow"]:
            item_mode = "shopProduct"  # По умолчанию для магазинов
        xml_parts.append(f'<itemMode>{item_mode}</itemMode>')
        
        xml_parts.append(f'<categoryID>{item_data.get("categoryID", "")}</categoryID>')
        xml_parts.append(f'<itemName><![CDATA[{item_data.get("itemName", "")}]]></itemName>')
        xml_parts.append(f'<quantity>{item_data.get("quantity", 1)}</quantity>')
        
        # condition: new, likeNew, veryGood, acceptable, usedGood, refurbished, defect
        condition = item_data.get("condition", "new")
        if condition not in ["new", "likeNew", "veryGood", "acceptable", "usedGood", "refurbished", "defect"]:
            condition = "new"  # По умолчанию новый
        xml_parts.append(f'<condition>{condition}</condition>')
        
        xml_parts.append(f'<description><![CDATA[{item_data.get("description", "")}]]></description>')
        
        # Цены
        if item_data.get("price"):
            xml_parts.append(f'<price>{item_data["price"]}</price>')
        if item_data.get("priceStart"):
            xml_parts.append(f'<priceStart>{item_data["priceStart"]}</priceStart>')
        
        # Идентификаторы
        if item_data.get("ean"):
            xml_parts.append(f'<ean>{item_data["ean"]}</ean>')
        if item_data.get("manufacturer"):
            xml_parts.append(f'<manufacturer>{item_data["manufacturer"]}</manufacturer>')
        if item_data.get("weight"):
            xml_parts.append(f'<weight>{item_data["weight"]}</weight>')
        
        # Изображения (рекомендуется) - поддержка URL и Base64
        if item_data.get("images"):
            xml_parts.append('<images>')
            
            for image_data in item_data["images"]:
                # Если это строка URL
                if isinstance(image_data, str):
                    xml_parts.append(f'<imageURL>{image_data}</imageURL>')
                
                # Если это словарь с детальной информацией
                elif isinstance(image_data, dict):
                    xml_parts.append('<image>')
                    
                    # URL изображения
                    if image_data.get("url"):
                        xml_parts.append(f'<imageURL>{image_data["url"]}</imageURL>')
                    
                    # Base64 изображение
                    if image_data.get("base64"):
                        xml_parts.append(f'<imageBase64>{image_data["base64"]}</imageBase64>')
                    
                    # Детали варианта (если есть)
                    if image_data.get("optionDetails"):
                        xml_parts.append('<optionDetails>')
                        for detail in image_data["optionDetails"]:
                            xml_parts.append('<nameValueList>')
                            xml_parts.append(f'<name><![CDATA[{detail.get("name", "")}]]></name>')
                            xml_parts.append(f'<value><![CDATA[{detail.get("value", "")}]]></value>')
                            xml_parts.append('</nameValueList>')
                        xml_parts.append('</optionDetails>')
                    
                    xml_parts.append('</image>')
            
            xml_parts.append('</images>')
        
        # Варианты продукта (для магазинов Gold/Platinum)
        if item_data.get("productOptions"):
            xml_parts.append('<productOptions>')
            
            for option in item_data["productOptions"]:
                xml_parts.append('<productOption>')
                
                # Основные поля варианта
                if option.get("optionPrice"):
                    xml_parts.append(f'<optionPrice>{option["optionPrice"]}</optionPrice>')
                if option.get("optionQuantity"):
                    xml_parts.append(f'<optionQuantity>{option["optionQuantity"]}</optionQuantity>')
                if option.get("optionItemNumber"):
                    xml_parts.append(f'<optionItemNumber>{option["optionItemNumber"]}</optionItemNumber>')
                if option.get("mpn"):
                    xml_parts.append(f'<mpn>{option["mpn"]}</mpn>')
                if option.get("ean"):
                    xml_parts.append(f'<ean>{option["ean"]}</ean>')
                if option.get("PackagingSize"):
                    xml_parts.append(f'<PackagingSize>{option["PackagingSize"]}</PackagingSize>')
                
                # Детали варианта (обязательно)
                if option.get("optionDetails"):
                    xml_parts.append('<optionDetails>')
                    for detail in option["optionDetails"]:
                        xml_parts.append('<nameValueList>')
                        xml_parts.append(f'<name><![CDATA[{detail.get("name", "")}]]></name>')
                        xml_parts.append(f'<value><![CDATA[{detail.get("value", "")}]]></value>')
                        xml_parts.append('</nameValueList>')
                    xml_parts.append('</optionDetails>')
                
                xml_parts.append('</productOption>')
            
            xml_parts.append('</productOptions>')
        
        # Свойства продукта (до 15 свойств, максимум 30 символов каждое)
        if item_data.get("productProperties"):
            xml_parts.append('<productProperties>')
            
            # Валидируем и ограничиваем свойства
            validated_properties = self._validate_product_properties(item_data["productProperties"])
            
            for prop_name, prop_value in validated_properties.items():
                xml_parts.append('<nameValueList>')
                xml_parts.append(f'<name><![CDATA[{prop_name}]]></name>')
                xml_parts.append(f'<value><![CDATA[{prop_value}]]></value>')
                xml_parts.append('</nameValueList>')
            
            xml_parts.append('</productProperties>')
        
        # Платежи (обязательно для classic и buyItNow, игнорируется для shopProduct)
        if item_mode in ["classic", "buyItNow"]:
            xml_parts.append('<payOptions>')
            
            # Получаем опции оплаты из данных товара или используем по умолчанию
            pay_options = item_data.get("payOptions", ["wireTransfer", "paypal"])
            
            # Проверяем правильность значений
            valid_options = ["wireTransfer", "invoice", "cashOnDelivery", "cash", "paypal", "sofort", "amazon", "klarna"]
            for option in pay_options:
                if option in valid_options:
                    xml_parts.append(f'<option>{option}</option>')
            
            # Если нет валидных опций, используем по умолчанию
            if not any(opt in valid_options for opt in pay_options):
                xml_parts.append('<option>wireTransfer</option>')
                xml_parts.append('<option>paypal</option>')
            
            xml_parts.append('</payOptions>')
        
        # Доставка (обязательно) - используем данные из товара или значения по умолчанию
        xml_parts.append('<shipmethods>')
        
        # Получаем способы доставки из данных товара
        ship_methods = item_data.get("shipMethods", {})
        
        # Если не указаны способы доставки, используем по умолчанию
        if not ship_methods:
            ship_methods = {
                "seeDesc_nat": 5.0,  # См. описание - национальная доставка
                "DHLPacket_nat": 8.0  # DHL Packet - национальная доставка
            }
        
        # Добавляем способы доставки
        for method_name, cost in ship_methods.items():
            xml_parts.append(f'<shipmethod name="{method_name}">')
            xml_parts.append(f'<value>{cost}</value>')
            xml_parts.append('</shipmethod>')
        
        xml_parts.append('</shipmethods>')
        
        # Обязательные временные поля
        from datetime import datetime, timedelta
        start_date = datetime.now() + timedelta(hours=1)  # Начинаем через час
        xml_parts.append(f'<startDate>{start_date.strftime("%d.%m.%Y")}</startDate>')
        xml_parts.append(f'<startTime>{start_date.strftime("%H:%M")}</startTime>')
        xml_parts.append(f'<durationInDays>{item_data.get("durationInDays", 7)}</durationInDays>')
        xml_parts.append(f'<autoRenew>{item_data.get("autoRenew", "no")}</autoRenew>')
        
        # Флаг предотвращения дублирования товаров
        if item_data.get("itemNumberUniqueFlag"):
            xml_parts.append(f'<itemNumberUniqueFlag>{item_data["itemNumberUniqueFlag"]}</itemNumberUniqueFlag>')
        
        # Энергетические метки и технические паспорта (для электронных товаров)
        if item_data.get("energyLabelUrl"):
            xml_parts.append(f'<energyLabelUrl>{item_data["energyLabelUrl"]}</energyLabelUrl>')
        if item_data.get("productInfoUrl"):
            xml_parts.append(f'<productInfoUrl>{item_data["productInfoUrl"]}</productInfoUrl>')
        
        xml_parts.extend(['</item>', '</items>', '</api>'])
        return '\n'.join(xml_parts)
    
    def validate_and_insert_item(self, item_data: Dict[str, Any]) -> Dict[str, Any]:
        """Валидация и добавление товара (рекомендуемый workflow)"""
        logger.info(f"Начинаем валидацию и добавление товара: {item_data.get('itemName', 'Unknown')}")
        
        # Шаг 1: Валидация
        logger.info("Шаг 1: Валидация товара...")
        validation_result = self.item_validate(item_data)
        
        if not validation_result.get('success'):
            logger.error(f"Валидация не прошла: {validation_result.get('error')}")
            return {
                'success': False,
                'step': 'validation',
                'error': validation_result.get('error'),
                'validation_result': validation_result
            }
        
        logger.info("✅ Валидация прошла успешно")
        
        # Показываем стоимость добавления
        if validation_result.get('costs'):
            logger.info(f"💰 Стоимость добавления: {validation_result.get('costs')}")
        
        # Шаг 2: Добавление товара
        logger.info("Шаг 2: Добавление товара...")
        insert_result = self.upload_item(item_data)
        
        if insert_result.get('success'):
            logger.info(f"✅ Товар успешно добавлен (ID: {insert_result.get('item_id')})")
            return {
                'success': True,
                'step': 'completed',
                'item_id': insert_result.get('item_id'),
                'validation_result': validation_result,
                'insert_result': insert_result
            }
        else:
            logger.error(f"Ошибка добавления: {insert_result.get('error')}")
            return {
                'success': False,
                'step': 'insert',
                'error': insert_result.get('error'),
                'validation_result': validation_result,
                'insert_result': insert_result
            }
    
    def get_order_list(self, date_range: Dict[str, str] = None, list_mode: str = 'details', order_id: str = None) -> Dict[str, Any]:
        """Получение списка заказов (только для Hood-Shops)"""
        try:
            # Создаем XML запрос для orderList
            xml_parts = [
                '<?xml version="1.0" encoding="UTF-8"?>',
                f'<api type="public" version="2.0" user="{self.api_user}" password="{self._hash_password(self.api_password)}">',
                f'<accountName>{self.account_name}</accountName>',
                f'<accountPass>{self._hash_password(self.account_pass)}</accountPass>',
                '<function>orderList</function>'
            ]
            
            # Добавляем диапазон дат если указан
            if date_range:
                xml_parts.append('<dateRange>')
                xml_parts.append(f'<type>{date_range.get("type", "orderDate")}</type>')
                xml_parts.append(f'<startDate>{date_range.get("startDate")}</startDate>')
                xml_parts.append(f'<endDate>{date_range.get("endDate")}</endDate>')
                xml_parts.append('</dateRange>')
            
            # Добавляем режим списка
            xml_parts.append(f'<listMode>{list_mode}</listMode>')
            
            # Добавляем фильтр по orderID если указан
            if order_id:
                xml_parts.append(f'<orderID>{order_id}</orderID>')
            
            xml_parts.append('</api>')
            xml_request = '\n'.join(xml_parts)
            
            response = self.session.post(
                self.api_url,
                data=xml_request,
                headers={'Content-Type': 'text/xml; charset=UTF-8'},
                timeout=30
            )
            
            root = self._parse_xml_safely(response.text)
            
            if root is not None:
                # Проверяем на глобальные ошибки
                global_error = root.find('.//globalError')
                if global_error is not None:
                    return {
                        'success': False,
                        'error': global_error.text,
                        'raw_response': response.text
                    }
                
                # Обрабатываем ответ согласно документации
                response_container = root.find('.//response')
                if response_container is not None:
                    orders = response_container.findall('.//order')
                    orders_data = []
                    
                    for order in orders:
                        order_data = self._extract_order_data(order)
                        orders_data.append(order_data)
                    
                    return {
                        'success': True,
                        'orders': orders_data,
                        'order_count': len(orders_data),
                        'raw_response': response.text
                    }
            
            return {
                'success': False,
                'error': 'Не удалось найти данные заказов в ответе',
                'raw_response': response.text
            }
            
        except Exception as e:
            logger.error(f"Order list error: {str(e)}")
            return {
                'success': False,
                'error': f'Ошибка получения списка заказов: {str(e)}',
                'raw_response': ''
            }
    
    def _extract_order_data(self, order_element) -> Dict[str, Any]:
        """Извлекает данные заказа из XML элемента согласно документации"""
        order_data = {}
        
        # Обработка orderItems (товары в заказе)
        order_items = order_element.find('orderItems')
        if order_items is not None:
            items = []
            for item in order_items.findall('item'):
                item_data = {}
                item_fields = [
                    'itemID', 'prodName', 'quantity', 'price', 'weight',
                    'itemNumber', 'salesTax', 'ean', 'isbn', 'mpn'
                ]
                
                for field in item_fields:
                    element = item.find(field)
                    if element is not None and element.text:
                        item_data[field] = element.text
                
                if item_data:
                    items.append(item_data)
            
            if items:
                order_data['orderItems'] = items
        
        # Обработка details (детали заказа)
        details = order_element.find('details')
        if details is not None:
            details_data = {}
            details_fields = [
                'orderID', 'quantity', 'date', 'price', 'discount',
                'shipCost', 'shipMethod', 'shipMethodCode', 'tax',
                'taxIncluded', 'taxTotalValue', 'productOption',
                'orderStatusBuyer', 'orderStatusActionBuyer', 
                'orderStatusSeller', 'orderStatusActionSeller', 
                'paymentProvider', 'paymentTypeCode', 'paymentTransactionID',
                'paymentStatus', 'paymentStatusCode', 'comments',
                'shippedDate', 'paymentDate', 'shippingStatus', 'shippingStatusCode'
            ]
            
            for field in details_fields:
                element = details.find(field)
                if element is not None and element.text:
                    details_data[field] = element.text
            
            if details_data:
                order_data['details'] = details_data
        
        # Обработка buyer (информация о покупателе)
        buyer = order_element.find('buyer')
        if buyer is not None:
            buyer_data = {}
            buyer_fields = [
                'company', 'companyOwner', 'accountName', 'email',
                'salutation', 'firstName', 'lastName', 'comment',
                'address', 'city', 'zip', 'phone', 'country', 'countryTwoDigit'
            ]
            
            for field in buyer_fields:
                element = buyer.find(field)
                if element is not None and element.text:
                    buyer_data[field] = element.text
            
            if buyer_data:
                order_data['buyer'] = buyer_data
        
        # Обработка shipAddress (адрес доставки)
        ship_address = order_element.find('shipAddress')
        if ship_address is not None:
            address_data = {}
            address_fields = [
                'company', 'salutation', 'firstName', 'lastName',
                'comment', 'address', 'city', 'zip', 'country', 'countryTwoDigit'
            ]
            
            for field in address_fields:
                element = ship_address.find(field)
                if element is not None and element.text:
                    address_data[field] = element.text
            
            if address_data:
                order_data['shipAddress'] = address_data
        
        # Обработка paymentInfo (информация об оплате) - если есть
        payment_info = order_element.find('paymentInfo')
        if payment_info is not None:
            payment_data = {}
            payment_fields = [
                'paymentMethod', 'paymentStatus', 'paymentDate',
                'transactionID', 'paymentAmount', 'currency'
            ]
            
            for field in payment_fields:
                element = payment_info.find(field)
                if element is not None and element.text:
                    payment_data[field] = element.text
            
            if payment_data:
                order_data['paymentInfo'] = payment_data
        
        return order_data
    
    def get_orders_by_date_range(self, start_date: str, end_date: str, date_type: str = 'orderDate') -> Dict[str, Any]:
        """Получение заказов по диапазону дат"""
        date_range = {
            'type': date_type,
            'startDate': start_date,
            'endDate': end_date
        }
        
        return self.get_order_list(date_range=date_range, list_mode='details')
    
    def get_orders_by_status_change(self, start_date: str, end_date: str) -> Dict[str, Any]:
        """Получение заказов по дате изменения статуса"""
        return self.get_orders_by_date_range(start_date, end_date, 'statusChange')
    
    def get_all_orders_by_date(self, start_date: str, end_date: str) -> Dict[str, Any]:
        """Получение всех заказов по дате (orderDate и statusChange)"""
        return self.get_orders_by_date_range(start_date, end_date, 'showAll')
    
    def get_order_by_id(self, order_id: str) -> Dict[str, Any]:
        """Получение конкретного заказа по ID"""
        return self.get_order_list(list_mode='details', order_id=order_id)
    
    def get_order_ids_by_date_range(self, start_date: str, end_date: str, date_type: str = 'orderDate') -> Dict[str, Any]:
        """Получение только ID заказов по диапазону дат"""
        date_range = {
            'type': date_type,
            'startDate': start_date,
            'endDate': end_date
        }
        
        return self.get_order_list(date_range=date_range, list_mode='orderIDs')
    
    def get_recent_orders(self, days: int = 7) -> Dict[str, Any]:
        """Получение заказов за последние N дней"""
        from datetime import datetime, timedelta
        
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days)
        
        return self.get_orders_by_date_range(
            start_date.strftime('%m/%d/%Y'),
            end_date.strftime('%m/%d/%Y')
        )
    
    def get_orders_summary(self, start_date: str, end_date: str) -> Dict[str, Any]:
        """Получение сводки по заказам"""
        orders_result = self.get_orders_by_date_range(start_date, end_date)
        
        if not orders_result.get('success'):
            return orders_result
        
        orders = orders_result.get('orders', [])
        
        summary = {
            'total_orders': len(orders),
            'total_amount': 0,
            'status_counts': {},
            'payment_methods': {},
            'shipping_methods': {},
            'date_range': {
                'start': start_date,
                'end': end_date
            }
        }
        
        for order in orders:
            # Получаем детали заказа
            details = order.get('details', {})
            
            # Подсчет общей суммы
            try:
                amount = float(details.get('price', 0))
                summary['total_amount'] += amount
            except (ValueError, TypeError):
                pass
            
            # Подсчет статусов
            status_seller = details.get('orderStatusSeller', 'unknown')
            summary['status_counts'][status_seller] = summary['status_counts'].get(status_seller, 0) + 1
            
            # Подсчет способов оплаты
            payment_provider = details.get('paymentProvider', 'unknown')
            summary['payment_methods'][payment_provider] = summary['payment_methods'].get(payment_provider, 0) + 1
            
            # Подсчет способов доставки
            shipping_method = details.get('shipMethod', 'unknown')
            summary['shipping_methods'][shipping_method] = summary['shipping_methods'].get(shipping_method, 0) + 1
        
        return {
            'success': True,
            'summary': summary,
            'raw_response': orders_result.get('raw_response')
        }
    
    def get_order_items_summary(self, start_date: str, end_date: str) -> Dict[str, Any]:
        """Получение сводки по товарам в заказах"""
        orders_result = self.get_orders_by_date_range(start_date, end_date)
        
        if not orders_result.get('success'):
            return orders_result
        
        orders = orders_result.get('orders', [])
        
        items_summary = {
            'total_items': 0,
            'unique_items': set(),
            'item_counts': {},
            'total_weight': 0,
            'total_sales_tax': 0,
            'date_range': {
                'start': start_date,
                'end': end_date
            }
        }
        
        for order in orders:
            order_items = order.get('orderItems', [])
            for item in order_items:
                items_summary['total_items'] += int(item.get('quantity', 0))
                items_summary['unique_items'].add(item.get('itemID', ''))
                
                # Подсчет количества по товарам
                item_id = item.get('itemID', 'unknown')
                items_summary['item_counts'][item_id] = items_summary['item_counts'].get(item_id, 0) + int(item.get('quantity', 0))
                
                # Подсчет общего веса
                try:
                    weight = float(item.get('weight', 0))
                    items_summary['total_weight'] += weight * int(item.get('quantity', 0))
                except (ValueError, TypeError):
                    pass
                
                # Подсчет налогов
                try:
                    sales_tax = float(item.get('salesTax', 0))
                    items_summary['total_sales_tax'] += sales_tax
                except (ValueError, TypeError):
                    pass
        
        # Преобразуем set в list для JSON сериализации
        items_summary['unique_items'] = list(items_summary['unique_items'])
        
        return {
            'success': True,
            'items_summary': items_summary,
            'raw_response': orders_result.get('raw_response')
        }
    
    def get_buyer_summary(self, start_date: str, end_date: str) -> Dict[str, Any]:
        """Получение сводки по покупателям"""
        orders_result = self.get_orders_by_date_range(start_date, end_date)
        
        if not orders_result.get('success'):
            return orders_result
        
        orders = orders_result.get('orders', [])
        
        buyer_summary = {
            'total_buyers': 0,
            'unique_buyers': set(),
            'buyer_counts': {},
            'countries': {},
            'companies': {},
            'date_range': {
                'start': start_date,
                'end': end_date
            }
        }
        
        for order in orders:
            buyer = order.get('buyer', {})
            if buyer:
                buyer_summary['total_buyers'] += 1
                
                # Уникальные покупатели
                buyer_email = buyer.get('email', 'unknown')
                buyer_summary['unique_buyers'].add(buyer_email)
                
                # Подсчет заказов по покупателям
                buyer_summary['buyer_counts'][buyer_email] = buyer_summary['buyer_counts'].get(buyer_email, 0) + 1
                
                # Подсчет по странам
                country = buyer.get('country', 'unknown')
                buyer_summary['countries'][country] = buyer_summary['countries'].get(country, 0) + 1
                
                # Подсчет по компаниям
                company = buyer.get('company', 'unknown')
                if company != 'unknown':
                    buyer_summary['companies'][company] = buyer_summary['companies'].get(company, 0) + 1
        
        # Преобразуем set в list для JSON сериализации
        buyer_summary['unique_buyers'] = list(buyer_summary['unique_buyers'])
        
        return {
            'success': True,
            'buyer_summary': buyer_summary,
            'raw_response': orders_result.get('raw_response')
        }
    
    def get_order_status_summary(self, start_date: str, end_date: str) -> Dict[str, Any]:
        """Получение сводки по статусам заказов"""
        orders_result = self.get_orders_by_date_range(start_date, end_date)
        
        if not orders_result.get('success'):
            return orders_result
        
        orders = orders_result.get('orders', [])
        
        status_summary = {
            'seller_statuses': {},
            'buyer_statuses': {},
            'seller_actions': {},
            'buyer_actions': {},
            'payment_providers': {},
            'date_range': {
                'start': start_date,
                'end': end_date
            }
        }
        
        for order in orders:
            details = order.get('details', {})
            
            # Статусы продавца
            seller_status = details.get('orderStatusSeller', 'unknown')
            status_summary['seller_statuses'][seller_status] = status_summary['seller_statuses'].get(seller_status, 0) + 1
            
            # Статусы покупателя
            buyer_status = details.get('orderStatusBuyer', 'unknown')
            status_summary['buyer_statuses'][buyer_status] = status_summary['buyer_statuses'].get(buyer_status, 0) + 1
            
            # Действия продавца
            seller_action = details.get('orderStatusActionSeller', 'unknown')
            status_summary['seller_actions'][seller_action] = status_summary['seller_actions'].get(seller_action, 0) + 1
            
            # Действия покупателя
            buyer_action = details.get('orderStatusActionBuyer', 'unknown')
            status_summary['buyer_actions'][buyer_action] = status_summary['buyer_actions'].get(buyer_action, 0) + 1
            
            # Провайдеры оплаты
            payment_provider = details.get('paymentProvider', 'unknown')
            status_summary['payment_providers'][payment_provider] = status_summary['payment_providers'].get(payment_provider, 0) + 1
        
        return {
            'success': True,
            'status_summary': status_summary,
            'raw_response': orders_result.get('raw_response')
        }
    
    def get_order_detailed_info(self, order_id: str) -> Dict[str, Any]:
        """Получение детальной информации о заказе"""
        order_result = self.get_order_by_id(order_id)
        
        if not order_result.get('success'):
            return order_result
        
        orders = order_result.get('orders', [])
        if not orders:
            return {
                'success': False,
                'error': 'Заказ не найден'
            }
        
        order = orders[0]
        
        # Извлекаем детальную информацию
        details = order.get('details', {})
        order_items = order.get('orderItems', [])
        buyer = order.get('buyer', {})
        ship_address = order.get('shipAddress', {})
        payment_info = order.get('paymentInfo', {})
        
        detailed_info = {
            'order_id': order_id,
            'details': details,
            'items': order_items,
            'buyer': buyer,
            'shipping_address': ship_address,
            'payment_info': payment_info,
            'summary': {
                'total_items': sum(int(item.get('quantity', 0)) for item in order_items),
                'total_weight': sum(float(item.get('weight', 0)) * int(item.get('quantity', 0)) for item in order_items),
                'total_price': details.get('price', '0'),
                'ship_cost': details.get('shipCost', '0'),
                'discount': details.get('discount', '0'),
                'tax': details.get('tax', '0'),
                'tax_total': details.get('taxTotalValue', '0')
            }
        }
        
        return {
            'success': True,
            'detailed_info': detailed_info,
            'raw_response': order_result.get('raw_response')
        }
    
    def get_order_payment_analysis(self, start_date: str, end_date: str) -> Dict[str, Any]:
        """Получение анализа платежей по заказам"""
        orders_result = self.get_orders_by_date_range(start_date, end_date)
        
        if not orders_result.get('success'):
            return orders_result
        
        orders = orders_result.get('orders', [])
        
        payment_analysis = {
            'payment_providers': {},
            'payment_types': {},
            'payment_statuses': {},
            'payment_status_codes': {},
            'transaction_ids': [],
            'payment_dates': [],
            'total_transactions': 0,
            'date_range': {
                'start': start_date,
                'end': end_date
            }
        }
        
        for order in orders:
            details = order.get('details', {})
            
            # Анализ провайдеров оплаты
            payment_provider = details.get('paymentProvider', 'unknown')
            payment_analysis['payment_providers'][payment_provider] = payment_analysis['payment_providers'].get(payment_provider, 0) + 1
            
            # Анализ типов оплаты
            payment_type = details.get('paymentTypeCode', 'unknown')
            payment_analysis['payment_types'][payment_type] = payment_analysis['payment_types'].get(payment_type, 0) + 1
            
            # Анализ статусов оплаты
            payment_status = details.get('paymentStatus', 'unknown')
            payment_analysis['payment_statuses'][payment_status] = payment_analysis['payment_statuses'].get(payment_status, 0) + 1
            
            # Анализ кодов статусов оплаты
            payment_status_code = details.get('paymentStatusCode', 'unknown')
            payment_analysis['payment_status_codes'][payment_status_code] = payment_analysis['payment_status_codes'].get(payment_status_code, 0) + 1
            
            # Сбор ID транзакций
            transaction_id = details.get('paymentTransactionID')
            if transaction_id:
                payment_analysis['transaction_ids'].append(transaction_id)
                payment_analysis['total_transactions'] += 1
            
            # Сбор дат оплаты
            payment_date = details.get('paymentDate')
            if payment_date:
                payment_analysis['payment_dates'].append(payment_date)
        
        return {
            'success': True,
            'payment_analysis': payment_analysis,
            'raw_response': orders_result.get('raw_response')
        }
    
    def get_order_shipping_analysis(self, start_date: str, end_date: str) -> Dict[str, Any]:
        """Получение анализа доставки по заказам"""
        orders_result = self.get_orders_by_date_range(start_date, end_date)
        
        if not orders_result.get('success'):
            return orders_result
        
        orders = orders_result.get('orders', [])
        
        shipping_analysis = {
            'shipping_methods': {},
            'shipping_method_codes': {},
            'shipping_statuses': {},
            'shipping_status_codes': {},
            'shipping_costs': [],
            'shipped_dates': [],
            'total_shipping_cost': 0,
            'date_range': {
                'start': start_date,
                'end': end_date
            }
        }
        
        for order in orders:
            details = order.get('details', {})
            
            # Анализ способов доставки
            shipping_method = details.get('shipMethod', 'unknown')
            shipping_analysis['shipping_methods'][shipping_method] = shipping_analysis['shipping_methods'].get(shipping_method, 0) + 1
            
            # Анализ кодов способов доставки
            shipping_method_code = details.get('shipMethodCode', 'unknown')
            shipping_analysis['shipping_method_codes'][shipping_method_code] = shipping_analysis['shipping_method_codes'].get(shipping_method_code, 0) + 1
            
            # Анализ статусов доставки
            shipping_status = details.get('shippingStatus', 'unknown')
            shipping_analysis['shipping_statuses'][shipping_status] = shipping_analysis['shipping_statuses'].get(shipping_status, 0) + 1
            
            # Анализ кодов статусов доставки
            shipping_status_code = details.get('shippingStatusCode', 'unknown')
            shipping_analysis['shipping_status_codes'][shipping_status_code] = shipping_analysis['shipping_status_codes'].get(shipping_status_code, 0) + 1
            
            # Сбор стоимости доставки
            ship_cost = details.get('shipCost')
            if ship_cost:
                try:
                    cost = float(ship_cost)
                    shipping_analysis['shipping_costs'].append(cost)
                    shipping_analysis['total_shipping_cost'] += cost
                except (ValueError, TypeError):
                    pass
            
            # Сбор дат отправки
            shipped_date = details.get('shippedDate')
            if shipped_date:
                shipping_analysis['shipped_dates'].append(shipped_date)
        
        return {
            'success': True,
            'shipping_analysis': shipping_analysis,
            'raw_response': orders_result.get('raw_response')
        }
    
    def get_order_variants_analysis(self, start_date: str, end_date: str) -> Dict[str, Any]:
        """Получение анализа вариантов товаров в заказах"""
        orders_result = self.get_orders_by_date_range(start_date, end_date)
        
        if not orders_result.get('success'):
            return orders_result
        
        orders = orders_result.get('orders', [])
        
        variants_analysis = {
            'orders_with_variants': 0,
            'orders_without_variants': 0,
            'variant_types': {},
            'total_orders': len(orders),
            'date_range': {
                'start': start_date,
                'end': end_date
            }
        }
        
        for order in orders:
            details = order.get('details', {})
            product_option = details.get('productOption')
            
            if product_option:
                variants_analysis['orders_with_variants'] += 1
                variants_analysis['variant_types'][product_option] = variants_analysis['variant_types'].get(product_option, 0) + 1
            else:
                variants_analysis['orders_without_variants'] += 1
        
        return {
            'success': True,
            'variants_analysis': variants_analysis,
            'raw_response': orders_result.get('raw_response')
        }
    
    def get_order_tax_analysis(self, start_date: str, end_date: str) -> Dict[str, Any]:
        """Получение анализа налогов по заказам"""
        orders_result = self.get_orders_by_date_range(start_date, end_date)
        
        if not orders_result.get('success'):
            return orders_result
        
        orders = orders_result.get('orders', [])
        
        tax_analysis = {
            'tax_rates': {},
            'tax_included_counts': {'yes': 0, 'no': 0},
            'total_tax_value': 0,
            'tax_values': [],
            'orders_with_tax': 0,
            'orders_without_tax': 0,
            'date_range': {
                'start': start_date,
                'end': end_date
            }
        }
        
        for order in orders:
            details = order.get('details', {})
            
            # Анализ налоговых ставок
            tax_rate = details.get('tax', 'unknown')
            tax_analysis['tax_rates'][tax_rate] = tax_analysis['tax_rates'].get(tax_rate, 0) + 1
            
            # Анализ включения налогов в цену
            tax_included = details.get('taxIncluded')
            if tax_included == '1':
                tax_analysis['tax_included_counts']['yes'] += 1
            elif tax_included == '0':
                tax_analysis['tax_included_counts']['no'] += 1
            
            # Сбор общей суммы налогов
            tax_total_value = details.get('taxTotalValue')
            if tax_total_value:
                try:
                    tax_value = float(tax_total_value)
                    tax_analysis['tax_values'].append(tax_value)
                    tax_analysis['total_tax_value'] += tax_value
                    tax_analysis['orders_with_tax'] += 1
                except (ValueError, TypeError):
                    pass
            else:
                tax_analysis['orders_without_tax'] += 1
        
        return {
            'success': True,
            'tax_analysis': tax_analysis,
            'raw_response': orders_result.get('raw_response')
        }
    
    def get_order_comprehensive_analysis(self, start_date: str, end_date: str) -> Dict[str, Any]:
        """Получение комплексного анализа заказов"""
        # Получаем все необходимые анализы
        orders_summary = self.get_orders_summary(start_date, end_date)
        items_summary = self.get_order_items_summary(start_date, end_date)
        buyer_summary = self.get_buyer_summary(start_date, end_date)
        status_summary = self.get_order_status_summary(start_date, end_date)
        payment_analysis = self.get_order_payment_analysis(start_date, end_date)
        shipping_analysis = self.get_order_shipping_analysis(start_date, end_date)
        variants_analysis = self.get_order_variants_analysis(start_date, end_date)
        tax_analysis = self.get_order_tax_analysis(start_date, end_date)
        
        comprehensive_analysis = {
            'date_range': {
                'start': start_date,
                'end': end_date
            },
            'orders_summary': orders_summary.get('summary', {}) if orders_summary.get('success') else {},
            'items_summary': items_summary.get('items_summary', {}) if items_summary.get('success') else {},
            'buyer_summary': buyer_summary.get('buyer_summary', {}) if buyer_summary.get('success') else {},
            'status_summary': status_summary.get('status_summary', {}) if status_summary.get('success') else {},
            'payment_analysis': payment_analysis.get('payment_analysis', {}) if payment_analysis.get('success') else {},
            'shipping_analysis': shipping_analysis.get('shipping_analysis', {}) if shipping_analysis.get('success') else {},
            'variants_analysis': variants_analysis.get('variants_analysis', {}) if variants_analysis.get('success') else {},
            'tax_analysis': tax_analysis.get('tax_analysis', {}) if tax_analysis.get('success') else {},
            'success_rates': {
                'orders_summary': orders_summary.get('success', False),
                'items_summary': items_summary.get('success', False),
                'buyer_summary': buyer_summary.get('success', False),
                'status_summary': status_summary.get('success', False),
                'payment_analysis': payment_analysis.get('success', False),
                'shipping_analysis': shipping_analysis.get('success', False),
                'variants_analysis': variants_analysis.get('success', False),
                'tax_analysis': tax_analysis.get('success', False)
            }
        }
        
        return {
            'success': True,
            'comprehensive_analysis': comprehensive_analysis,
            'raw_response': orders_summary.get('raw_response', '')
        }
    
    def get_item_list(self, item_status: str = 'running', start_at: int = 1, group_size: int = 100, 
                     date_range: Dict[str, str] = None) -> Dict[str, Any]:
        """
        Получение списка товаров для пользователей без магазина
        
        Args:
            item_status: Статус товаров ('sold', 'unsuccessful', 'running')
            start_at: Позиция начала списка (для пагинации)
            group_size: Количество записей для возврата (максимум 5000, для running - 20000)
            date_range: Диапазон дат {'startDate': '05/22/2016', 'endDate': '05/23/2016'}
        
        Returns:
            Dict с результатами запроса
        """
        try:
            # Валидация параметров
            valid_statuses = ['sold', 'unsuccessful', 'running']
            if item_status not in valid_statuses:
                return {
                    'success': False,
                    'error': f'Недопустимый статус товара: {item_status}. Допустимые: {valid_statuses}'
                }
            
            # Ограничения на group_size
            max_size = 20000 if item_status == 'running' else 5000
            if group_size > max_size:
                group_size = max_size
            
            # Построение XML запроса
            xml_request = self._build_item_list_xml_request(item_status, start_at, group_size, date_range)
            
            # Отправка запроса
            response = self.session.post(
                self.api_url,
                data=xml_request,
                headers={'Content-Type': 'text/xml; charset=UTF-8'},
                timeout=self.timeout
            )
            
            if response.status_code != 200:
                return {
                    'success': False,
                    'error': f'HTTP ошибка: {response.status_code}',
                    'raw_response': response.text[:500]
                }
            
            # Парсинг ответа
            return self._parse_item_list_response(response.text)
            
        except requests.exceptions.Timeout:
            return {
                'success': False,
                'error': 'Таймаут запроса к API',
                'raw_response': ''
            }
        except requests.exceptions.ConnectionError as e:
            return {
                'success': False,
                'error': f'Ошибка соединения: {str(e)}',
                'raw_response': ''
            }
        except Exception as e:
            return {
                'success': False,
                'error': f'Неожиданная ошибка: {str(e)}',
                'raw_response': ''
            }
    
    def _build_item_list_xml_request(self, item_status: str, start_at: int, group_size: int, 
                                   date_range: Dict[str, str] = None) -> str:
        """Построение XML запроса для itemList"""
        xml_parts = [
            f'<api type="public" version="2.0" user="{self.api_user}" password="{self._hash_password(self.api_password)}">',
            '<function>itemList</function>',
            f'<accountName>{self.account_name}</accountName>',
            f'<accountPass>{self._hash_password(self.account_pass)}</accountPass>',
            f'<itemStatus>{item_status}</itemStatus>',
            f'<startAt>{start_at}</startAt>',
            f'<groupSize>{group_size}</groupSize>'
        ]
        
        # Добавляем dateRange если указан
        if date_range:
            xml_parts.append('<dateRange>')
            if 'startDate' in date_range:
                xml_parts.append(f'<startDate>{date_range["startDate"]}</startDate>')
            if 'endDate' in date_range:
                xml_parts.append(f'<endDate>{date_range["endDate"]}</endDate>')
            xml_parts.append('</dateRange>')
        
        xml_parts.append('</api>')
        
        return '\n'.join(xml_parts)
    
    def _build_item_detail_xml_request(self, item_id: str) -> str:
        """Построение XML запроса для itemDetail согласно документации"""
        xml_parts = [
            '<?xml version="1.0" encoding="UTF-8"?>',
            f'<api type="public" version="2.0" user="{self.api_user}" password="{self._hash_password(self.api_password)}">',
            '<function>itemDetail</function>',
            f'<accountName>{self.account_name}</accountName>',
            f'<accountPass>{self._hash_password(self.account_pass)}</accountPass>',
            '<items>',
            '<item>',
            f'<itemID>{item_id}</itemID>',
            '</item>',
            '</items>',
            '</api>'
        ]
        
        return '\n'.join(xml_parts)
    
    def _parse_item_list_response(self, xml_response: str) -> Dict[str, Any]:
        """Парсинг ответа itemList"""
        try:
            # Проверка на HTML ответ
            if xml_response.strip().startswith('<!DOCTYPE html') or xml_response.strip().startswith('<html'):
                return {
                    'success': False,
                    'error': 'API вернул HTML вместо XML. Возможно, неправильный URL или проблемы с аутентификацией.',
                    'error_type': 'html_response',
                    'raw_response': xml_response[:500]
                }
            
            # Очищаем XML от лишних пробелов и переносов строк
            cleaned_xml = xml_response.strip()
            
            root = ET.fromstring(cleaned_xml)
            
            # Проверка на глобальные ошибки
            global_error = root.find('globalError')
            if global_error is not None:
                return {
                    'success': False,
                    'error': f'Глобальная ошибка API: {global_error.text}',
                    'error_type': 'global_error',
                    'raw_response': xml_response[:500]
                }
            
            # Проверка на ошибки в response
            error_element = root.find('error')
            if error_element is not None and error_element.text == 'globalError':
                info_element = root.find('info')
                error_message = info_element.text if info_element is not None else 'Неизвестная ошибка'
                return {
                    'success': False,
                    'error': f'Ошибка API: {error_message}',
                    'error_type': 'api_error',
                    'raw_response': xml_response[:500]
                }
            
            # Проверяем, является ли корневой элемент response
            if root.tag == 'response':
                response_element = root
            else:
                # Поиск контейнера response
                response_element = root.find('response')
                if response_element is None:
                    return {
                        'success': False,
                        'error': 'Не удалось найти элемент response в ответе API',
                        'error_type': 'missing_response',
                        'raw_response': xml_response[:500]
                    }
            
            # Извлечение общего количества записей
            total_records_element = response_element.find('totalRecords')
            total_records = int(total_records_element.text) if total_records_element is not None else 0
            
            # Извлечение списка товаров
            items_element = response_element.find('items')
            items = []
            
            if items_element is not None:
                for item in items_element.findall('item'):
                    item_data = {}
                    
                    # Извлечение itemID
                    item_id_element = item.find('itemID')
                    if item_id_element is not None:
                        item_data['itemID'] = item_id_element.text
                    
                    # Извлечение recordSet
                    record_set_element = item.find('recordSet')
                    if record_set_element is not None:
                        item_data['recordSet'] = int(record_set_element.text)
                    
                    if item_data:
                        items.append(item_data)
            
            return {
                'success': True,
                'total_records': total_records,
                'items': items,
                'raw_response': xml_response
            }
            
        except ET.ParseError as e:
            return {
                'success': False,
                'error': f'Ошибка парсинга XML: {str(e)}',
                'error_type': 'xml_parse_error',
                'raw_response': xml_response[:500]
            }
        except Exception as e:
            return {
                'success': False,
                'error': f'Ошибка обработки ответа: {str(e)}',
                'error_type': 'processing_error',
                'raw_response': xml_response[:500]
            }
    
    def get_item_status(self, item_ids: List[str], detail_level: List[str] = None) -> Dict[str, Any]:
        """
        Получение детальной информации о товарах
        
        Args:
            item_ids: Список ID товаров для получения информации
            detail_level: Уровень детализации ('image', 'description')
        
        Returns:
            Dict с результатами запроса
        """
        try:
            # Валидация параметров
            if not item_ids:
                return {
                    'success': False,
                    'error': 'Не указаны ID товаров'
                }
            
            if not isinstance(item_ids, list):
                item_ids = [item_ids]
            
            # Валидация detail_level
            valid_detail_levels = ['image', 'description']
            if detail_level:
                invalid_levels = [level for level in detail_level if level not in valid_detail_levels]
                if invalid_levels:
                    return {
                        'success': False,
                        'error': f'Недопустимые уровни детализации: {invalid_levels}. Допустимые: {valid_detail_levels}'
                    }
            
            # Построение XML запроса
            xml_request = self._build_item_status_xml_request(item_ids, detail_level)
            
            # Отправка запроса
            response = self.session.post(
                self.api_url,
                data=xml_request,
                headers={'Content-Type': 'text/xml; charset=UTF-8'},
                timeout=self.timeout
            )
            
            if response.status_code != 200:
                return {
                    'success': False,
                    'error': f'HTTP ошибка: {response.status_code}',
                    'raw_response': response.text[:500]
                }
            
            # Парсинг ответа
            return self._parse_item_status_response(response.text)
            
        except requests.exceptions.Timeout:
            return {
                'success': False,
                'error': 'Таймаут запроса к API',
                'raw_response': ''
            }
        except requests.exceptions.ConnectionError as e:
            return {
                'success': False,
                'error': f'Ошибка соединения: {str(e)}',
                'raw_response': ''
            }
        except Exception as e:
            return {
                'success': False,
                'error': f'Неожиданная ошибка: {str(e)}',
                'raw_response': ''
            }
    
    def _build_item_status_xml_request(self, item_ids: List[str], detail_level: List[str] = None) -> str:
        """Построение XML запроса для itemStatus"""
        xml_parts = [
            '<?xml version="1.0" encoding="UTF-8"?>',
            f'<api type="public" version="2.0" user="{self.api_user}" password="{self._hash_password(self.api_password)}">',
            '<function>itemStatus</function>',
            f'<accountName>{self.account_name}</accountName>',
            f'<accountPass>{self._hash_password(self.account_pass)}</accountPass>'
        ]
        
        # Добавляем detailLevel если указан
        if detail_level:
            detail_level_str = ','.join(detail_level)
            xml_parts.append(f'<detailLevel>{detail_level_str}</detailLevel>')
        
        # Добавляем контейнер items
        xml_parts.append('<items>')
        
        for item_id in item_ids:
            xml_parts.append('<item>')
            xml_parts.append(f'<itemID>{item_id}</itemID>')
            xml_parts.append('</item>')
        
        xml_parts.append('</items>')
        xml_parts.append('</api>')
        
        return '\n'.join(xml_parts)
    
    def _parse_item_status_response(self, xml_response: str) -> Dict[str, Any]:
        """Парсинг ответа itemStatus"""
        try:
            # Проверка на HTML ответ
            if xml_response.strip().startswith('<!DOCTYPE html') or xml_response.strip().startswith('<html'):
                return {
                    'success': False,
                    'error': 'API вернул HTML вместо XML. Возможно, неправильный URL или проблемы с аутентификацией.',
                    'error_type': 'html_response',
                    'raw_response': xml_response[:500]
                }
            
            root = ET.fromstring(xml_response)
            
            # Проверка на глобальные ошибки
            global_error = root.find('globalError')
            if global_error is not None:
                return {
                    'success': False,
                    'error': f'Глобальная ошибка API: {global_error.text}',
                    'error_type': 'global_error',
                    'raw_response': xml_response[:500]
                }
            
            # Проверяем, является ли корневой элемент response
            if root.tag == 'response':
                response_element = root
            else:
                # Поиск контейнера response
                response_element = root.find('response')
                if response_element is None:
                    return {
                        'success': False,
                        'error': 'Не удалось найти элемент response в ответе API',
                        'error_type': 'missing_response',
                        'raw_response': xml_response[:500]
                    }
            
            # Извлечение списка товаров
            items_element = response_element.find('items')
            items = []
            
            if items_element is not None:
                for item in items_element.findall('item'):
                    item_data = self._extract_item_status_data(item)
                    if item_data:
                        items.append(item_data)
            
            return {
                'success': True,
                'items': items,
                'raw_response': xml_response
            }
            
        except ET.ParseError as e:
            return {
                'success': False,
                'error': f'Ошибка парсинга XML: {str(e)}',
                'error_type': 'xml_parse_error',
                'raw_response': xml_response[:500]
            }
        except Exception as e:
            return {
                'success': False,
                'error': f'Ошибка обработки ответа: {str(e)}',
                'error_type': 'processing_error',
                'raw_response': xml_response[:500]
            }
    
    def _extract_item_status_data(self, item_element) -> Dict[str, Any]:
        """Извлечение данных товара из ответа itemStatus"""
        item_data = {}
        
        # Базовые поля товара
        basic_fields = [
            'itemID', 'itemName', 'description', 'price', 'quantity',
            'condition', 'manufacturer', 'weight', 'categoryID', 'categoryName',
            'startDate', 'endDate', 'duration', 'status', 'views', 'bids'
        ]
        
        for field in basic_fields:
            element = item_element.find(field)
            if element is not None and element.text:
                item_data[field] = element.text
        
        # Обработка изображений
        images_element = item_element.find('images')
        if images_element is not None:
            images = []
            for image in images_element.findall('image'):
                image_data = {}
                image_url = image.find('imageURL')
                if image_url is not None:
                    image_data['imageURL'] = image_url.text
                image_base64 = image.find('imageBase64')
                if image_base64 is not None:
                    image_data['imageBase64'] = image_base64.text
                if image_data:
                    images.append(image_data)
            if images:
                item_data['images'] = images
        
        # Обработка свойств товара
        properties_element = item_element.find('productProperties')
        if properties_element is not None:
            properties = []
            for prop in properties_element.findall('nameValueList'):
                prop_data = {}
                name = prop.find('name')
                value = prop.find('value')
                if name is not None and value is not None:
                    prop_data['name'] = name.text
                    prop_data['value'] = value.text
                    properties.append(prop_data)
            if properties:
                item_data['productProperties'] = properties
        
        return item_data
    
    def get_running_items(self, start_at: int = 1, group_size: int = 100, 
                         date_range: Dict[str, str] = None) -> Dict[str, Any]:
        """Получение активных товаров"""
        return self.get_item_list('running', start_at, group_size, date_range)
    
    def get_sold_items(self, start_at: int = 1, group_size: int = 100, 
                      date_range: Dict[str, str] = None) -> Dict[str, Any]:
        """Получение проданных товаров"""
        return self.get_item_list('sold', start_at, group_size, date_range)
    
    def get_unsuccessful_items(self, start_at: int = 1, group_size: int = 100, 
                             date_range: Dict[str, str] = None) -> Dict[str, Any]:
        """Получение товаров, которые не были проданы"""
        return self.get_item_list('unsuccessful', start_at, group_size, date_range)
    
    def get_item_status_with_images(self, item_ids: List[str]) -> Dict[str, Any]:
        """Получение статуса товаров с изображениями"""
        return self.get_item_status(item_ids, ['image'])
    
    def get_item_status_with_description(self, item_ids: List[str]) -> Dict[str, Any]:
        """Получение статуса товаров с описанием"""
        return self.get_item_status(item_ids, ['description'])
    
    def get_item_status_full_details(self, item_ids: List[str]) -> Dict[str, Any]:
        """Получение полной информации о товарах"""
        return self.get_item_status(item_ids, ['image', 'description'])
    
    def get_item_status_by_id(self, item_id: str, detail_level: List[str] = None) -> Dict[str, Any]:
        """Получение статуса одного товара по ID"""
        return self.get_item_status([item_id], detail_level)
    
    def get_items_paginated(self, item_status: str = 'running', page: int = 1, 
                           page_size: int = 100, date_range: Dict[str, str] = None) -> Dict[str, Any]:
        """Получение товаров с пагинацией"""
        start_at = (page - 1) * page_size + 1
        result = self.get_item_list(item_status, start_at, page_size, date_range)
        
        if result.get('success'):
            total_records = result.get('total_records', 0)
            total_pages = (total_records + page_size - 1) // page_size
            
            result['pagination'] = {
                'current_page': page,
                'page_size': page_size,
                'total_records': total_records,
                'total_pages': total_pages,
                'has_next': page < total_pages,
                'has_previous': page > 1
            }
        
        return result
    
    def get_items_by_date_range(self, start_date: str, end_date: str, 
                               item_status: str = 'running') -> Dict[str, Any]:
        """Получение товаров за определенный период"""
        date_range = {
            'startDate': start_date,
            'endDate': end_date
        }
        return self.get_item_list(item_status, 1, 5000, date_range)
    
    def get_recent_items(self, days: int = 7, item_status: str = 'running') -> Dict[str, Any]:
        """Получение товаров за последние N дней"""
        from datetime import datetime, timedelta
        
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days)
        
        date_range = {
            'startDate': start_date.strftime('%m/%d/%Y'),
            'endDate': end_date.strftime('%m/%d/%Y')
        }
        
        return self.get_item_list(item_status, 1, 5000, date_range)
    
    def get_items_summary(self, item_status: str = 'running') -> Dict[str, Any]:
        """Получение сводки по товарам"""
        result = self.get_item_list(item_status, 1, 100)
        
        if not result.get('success'):
            return result
        
        items = result.get('items', [])
        total_records = result.get('total_records', 0)
        
        summary = {
            'total_items': total_records,
            'returned_items': len(items),
            'item_status': item_status,
            'item_ids': [item.get('itemID') for item in items if item.get('itemID')],
            'record_sets': [item.get('recordSet') for item in items if item.get('recordSet')]
        }
        
        return {
            'success': True,
            'summary': summary,
            'raw_response': result.get('raw_response')
        }
    
    def get_items_detailed_status(self, item_ids: List[str]) -> Dict[str, Any]:
        """Получение детального статуса товаров с полной информацией"""
        result = self.get_item_status(item_ids, ['image', 'description'])
        
        if not result.get('success'):
            return result
        
        items = result.get('items', [])
        
        detailed_status = {
            'total_items': len(items),
            'items_with_images': 0,
            'items_with_descriptions': 0,
            'items_with_properties': 0,
            'items_by_status': {},
            'items_by_condition': {},
            'items_by_category': {},
            'price_range': {'min': None, 'max': None, 'avg': None},
            'items': items
        }
        
        prices = []
        
        for item in items:
            # Подсчет товаров с изображениями
            if item.get('images'):
                detailed_status['items_with_images'] += 1
            
            # Подсчет товаров с описанием
            if item.get('description'):
                detailed_status['items_with_descriptions'] += 1
            
            # Подсчет товаров со свойствами
            if item.get('productProperties'):
                detailed_status['items_with_properties'] += 1
            
            # Группировка по статусу
            status = item.get('status', 'unknown')
            detailed_status['items_by_status'][status] = detailed_status['items_by_status'].get(status, 0) + 1
            
            # Группировка по состоянию
            condition = item.get('condition', 'unknown')
            detailed_status['items_by_condition'][condition] = detailed_status['items_by_condition'].get(condition, 0) + 1
            
            # Группировка по категории
            category = item.get('categoryName', 'unknown')
            detailed_status['items_by_category'][category] = detailed_status['items_by_category'].get(category, 0) + 1
            
            # Сбор цен для анализа
            price = item.get('price')
            if price:
                try:
                    price_value = float(price)
                    prices.append(price_value)
                except (ValueError, TypeError):
                    pass
        
        # Анализ цен
        if prices:
            detailed_status['price_range']['min'] = min(prices)
            detailed_status['price_range']['max'] = max(prices)
            detailed_status['price_range']['avg'] = sum(prices) / len(prices)
        
        return {
            'success': True,
            'detailed_status': detailed_status,
            'raw_response': result.get('raw_response')
        }
    
    def compare_items_status(self, item_ids: List[str]) -> Dict[str, Any]:
        """Сравнение статуса нескольких товаров"""
        result = self.get_item_status(item_ids, ['image', 'description'])
        
        if not result.get('success'):
            return result
        
        items = result.get('items', [])
        
        comparison = {
            'total_items': len(items),
            'common_categories': set(),
            'common_conditions': set(),
            'common_statuses': set(),
            'price_comparison': [],
            'items': items
        }
        
        categories = set()
        conditions = set()
        statuses = set()
        
        for item in items:
            # Сбор категорий
            category = item.get('categoryName')
            if category:
                categories.add(category)
            
            # Сбор состояний
            condition = item.get('condition')
            if condition:
                conditions.add(condition)
            
            # Сбор статусов
            status = item.get('status')
            if status:
                statuses.add(status)
            
            # Сбор цен
            price = item.get('price')
            if price:
                try:
                    price_value = float(price)
                    comparison['price_comparison'].append({
                        'itemID': item.get('itemID'),
                        'price': price_value,
                        'itemName': item.get('itemName', 'N/A')
                    })
                except (ValueError, TypeError):
                    pass
        
        comparison['common_categories'] = list(categories)
        comparison['common_conditions'] = list(conditions)
        comparison['common_statuses'] = list(statuses)
        
        # Сортировка по цене
        comparison['price_comparison'].sort(key=lambda x: x['price'])
        
        return {
            'success': True,
            'comparison': comparison,
            'raw_response': result.get('raw_response')
        }