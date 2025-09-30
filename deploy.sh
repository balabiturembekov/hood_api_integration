#!/bin/bash

# Скрипт деплоя для hood.automatonsoft.de
# Использование: ./deploy.sh

set -e

echo "🚀 НАЧАЛО ДЕПЛОЯ HOOD.DE INTEGRATION SERVICE"
echo "=============================================="

# Переменные
PROJECT_NAME="hood_integration"
PROJECT_DIR="/var/www/hood.automatonsoft.de"
VENV_DIR="/var/www/hood.automatonsoft.de/venv"
REPO_URL="https://github.com/your-repo/hood-integration-service.git"

# Создаем директории
echo "📁 Создание директорий..."
sudo mkdir -p $PROJECT_DIR
sudo mkdir -p $PROJECT_DIR/static
sudo mkdir -p $PROJECT_DIR/media
sudo mkdir -p $PROJECT_DIR/logs
sudo mkdir -p /var/log/hood_integration

# Клонируем репозиторий (если первый раз)
if [ ! -d "$PROJECT_DIR/.git" ]; then
    echo "📥 Клонирование репозитория..."
    sudo git clone $REPO_URL $PROJECT_DIR
fi

# Переходим в директорию проекта
cd $PROJECT_DIR

# Обновляем код
echo "🔄 Обновление кода..."
sudo git pull origin main

# Создаем виртуальное окружение (если не существует)
if [ ! -d "$VENV_DIR" ]; then
    echo "🐍 Создание виртуального окружения..."
    sudo python3 -m venv $VENV_DIR
fi

# Активируем виртуальное окружение
echo "🔧 Активация виртуального окружения..."
source $VENV_DIR/bin/activate

# Устанавливаем зависимости
echo "📦 Установка зависимостей..."
pip install -r requirements.txt

# Копируем .env файл
if [ ! -f "$PROJECT_DIR/.env" ]; then
    echo "⚙️ Создание .env файла..."
    sudo cp .env.example .env
    echo "⚠️  Не забудьте настроить .env файл!"
fi

# Собираем статические файлы
echo "📄 Сбор статических файлов..."
python manage.py collectstatic --noinput

# Применяем миграции
echo "🗄️ Применение миграций..."
python manage.py migrate

# Создаем суперпользователя (если не существует)
echo "👤 Создание суперпользователя..."
python manage.py shell -c "
from django.contrib.auth import get_user_model
User = get_user_model()
if not User.objects.filter(username='admin').exists():
    User.objects.create_superuser('admin', 'admin@automatonsoft.de', 'admin123')
    print('Суперпользователь создан')
else:
    print('Суперпользователь уже существует')
"

# Настройка переменных окружения
echo "🔧 Настройка переменных окружения..."
if [ ! -f .env ]; then
    cp env.example .env
    echo "⚠️  Создан файл .env из примера. Пожалуйста, отредактируйте его с вашими настройками!"
    echo "📝 Особенно важно изменить SECRET_KEY и пароли базы данных!"
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
