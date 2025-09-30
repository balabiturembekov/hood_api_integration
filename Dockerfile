# Dockerfile для Hood.de Integration Service

FROM python:3.11-slim

# Устанавливаем системные зависимости
RUN apt-get update && apt-get install -y \
    postgresql-client \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Создаем пользователя для безопасности
RUN useradd --create-home --shell /bin/bash app

# Устанавливаем рабочую директорию
WORKDIR /app

# Копируем requirements и устанавливаем зависимости
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Копируем код приложения
COPY . .

# Меняем владельца файлов
RUN chown -R app:app /app
USER app

# Создаем директории для статических файлов
RUN mkdir -p /app/staticfiles /app/media

# Открываем порт
EXPOSE 8000

# Команда запуска с ожиданием базы данных и продакшн настройками
CMD ["sh", "-c", "python manage.py migrate --noinput && python manage.py collectstatic --noinput && python manage.py shell -c \"from django.contrib.auth import get_user_model; User = get_user_model(); User.objects.filter(username='admin').exists() or User.objects.create_superuser('admin', 'admin@automatonsoft.de', 'admin123')\" && gunicorn --bind 0.0.0.0:8000 --access-logfile - --error-logfile - --workers 3 hood_integration_service.wsgi:application"]
