#!/bin/bash

# Скрипт деплоя для hood.automatonsoft.de с Docker
# Использование: ./deploy.sh

set -e

echo "🚀 НАЧАЛО ДЕПЛОЯ HOOD.DE INTEGRATION SERVICE"
echo "=============================================="

# Переменные
PROJECT_DIR="/home/server/hood_api_integration"

# Переходим в директорию проекта (проект уже загружен на сервер)
echo "📁 Переход в директорию проекта..."
cd $PROJECT_DIR

# Настройка переменных окружения
echo "🔧 Настройка переменных окружения..."
if [ ! -f .env ]; then
    cp env.example .env
    echo "⚠️  Создан файл .env из примера. Пожалуйста, отредактируйте его с вашими настройками!"
    echo "📝 Особенно важно изменить SECRET_KEY и пароли базы данных!"
    echo ""
    echo "🔑 Сгенерируйте новый SECRET_KEY командой:"
    echo "python3 -c \"from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())\""
    echo ""
    echo "После редактирования .env файла запустите скрипт снова."
    exit 1
fi

# Проверяем, что SECRET_KEY изменен
if grep -q "your-super-secret-key-change-this-in-production" .env; then
    echo "❌ ОШИБКА: SECRET_KEY не изменен в файле .env!"
    echo "📝 Пожалуйста, отредактируйте файл .env и измените SECRET_KEY"
    exit 1
fi

# Настройка внешнего Nginx
echo "🌐 Настройка внешнего Nginx..."
sudo cp nginx-server.conf /etc/nginx/sites-available/hood.automatonsoft.de
sudo ln -sf /etc/nginx/sites-available/hood.automatonsoft.de /etc/nginx/sites-enabled/
sudo nginx -t

# Запуск Docker контейнеров
echo "🐳 Запуск Docker контейнеров..."
docker-compose down
docker-compose up -d --build

# Перезапуск внешнего Nginx
echo "🔄 Перезапуск внешнего Nginx..."
sudo systemctl restart nginx

# Проверяем статус
echo "✅ Проверка статуса сервисов..."
docker-compose ps
sudo systemctl status nginx --no-pager -l

echo "🎉 ДЕПЛОЙ ЗАВЕРШЕН!"
echo "🌐 Сайт доступен по адресу: https://hood.automatonsoft.de"
echo "👨‍💼 Админка: https://hood.automatonsoft.de/admin/"
echo "🔑 Логин: admin, Пароль: admin123"
echo ""
echo "📋 Полезные команды:"
echo "  docker-compose logs -f          # Просмотр логов"
echo "  docker-compose restart          # Перезапуск сервисов"
echo "  docker-compose ps               # Статус контейнеров"