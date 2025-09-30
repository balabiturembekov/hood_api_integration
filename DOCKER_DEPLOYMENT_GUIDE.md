# Инструкции по деплою Hood.de Integration Service с Docker

## Архитектура деплоя

```
Внешний мир → Внешний Nginx (443) → Docker Nginx (8282) → Django App (8000)
```

## Подготовка сервера

1. **Установка Docker и Docker Compose:**
```bash
# Обновляем систему
sudo apt update && sudo apt upgrade -y

# Устанавливаем Docker
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh
sudo usermod -aG docker $USER

# Устанавливаем Docker Compose
sudo curl -L "https://github.com/docker/compose/releases/download/v2.20.0/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
sudo chmod +x /usr/local/bin/docker-compose
```

2. **Установка Nginx:**
```bash
sudo apt install nginx -y
sudo systemctl enable nginx
```

3. **SSL сертификаты (Let's Encrypt):**
```bash
sudo apt install certbot python3-certbot-nginx -y
sudo certbot --nginx -d hood.automatonsoft.de
```

## Деплой приложения

1. **Клонирование репозитория:**
```bash
git clone <your-repo-url> /opt/hood-integration
cd /opt/hood-integration/hood_integration_service
```

2. **Настройка переменных окружения:**
```bash
cp env.example .env
nano .env  # Отредактируйте переменные
```

**Важные переменные для продакшена:**
- `SECRET_KEY` - сгенерируйте новый секретный ключ
- `DEBUG=False` - обязательно для продакшена
- `DB_PASSWORD` - надежный пароль для базы данных
- `ALLOWED_HOSTS` - домены вашего сайта

3. **Запуск деплоя:**
```bash
chmod +x deploy.sh
./deploy.sh
```

## Структура файлов

- `docker-compose.yml` - основная конфигурация Docker
- `nginx-docker.conf` - конфигурация Nginx внутри контейнера
- `nginx-server.conf` - конфигурация внешнего Nginx на сервере
- `Dockerfile` - образ Django приложения
- `deploy.sh` - скрипт автоматического деплоя

## Порты

- **8282** - порт Docker Nginx (внутренний)
- **443** - порт внешнего Nginx (HTTPS)
- **80** - порт внешнего Nginx (HTTP, редирект на HTTPS)

## Мониторинг

```bash
# Статус контейнеров
docker-compose ps

# Логи приложения
docker-compose logs -f web

# Логи Nginx
docker-compose logs -f nginx

# Статус внешнего Nginx
sudo systemctl status nginx
```

## Обновление

```bash
cd /opt/hood-integration/hood_integration_service
git pull
docker-compose down
docker-compose up -d --build
sudo systemctl reload nginx
```

## Резервное копирование

```bash
# База данных
docker-compose exec db pg_dump -U postgres hood_integration > backup_$(date +%Y%m%d).sql

# Медиа файлы
tar -czf media_backup_$(date +%Y%m%d).tar.gz media/
```

## Восстановление

```bash
# База данных
docker-compose exec -T db psql -U postgres hood_integration < backup_20250101.sql

# Медиа файлы
tar -xzf media_backup_20250101.tar.gz
```
