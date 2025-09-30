# 🚀 ДЕПЛОЙ HOOD.DE INTEGRATION SERVICE

## 📋 Обзор

Полное руководство по деплою Hood.de Integration Service на сервер с доменом `hood.automatonsoft.de`.

## 🎯 Цели деплоя

- ✅ Развертывание на домене `hood.automatonsoft.de`
- ✅ Настройка SSL сертификатов
- ✅ Конфигурация PostgreSQL
- ✅ Настройка Redis для кэширования
- ✅ Настройка Nginx как reverse proxy
- ✅ Настройка Gunicorn для WSGI
- ✅ Настройка мониторинга и логирования

## 🛠️ Требования к серверу

### Минимальные требования
- **OS**: Ubuntu 20.04+ или CentOS 8+
- **RAM**: 2GB (рекомендуется 4GB+)
- **CPU**: 2 ядра (рекомендуется 4+)
- **Диск**: 20GB свободного места
- **Python**: 3.11+
- **PostgreSQL**: 13+
- **Redis**: 6+
- **Nginx**: 1.18+

### Рекомендуемые требования
- **RAM**: 8GB+
- **CPU**: 4+ ядра
- **SSD**: 50GB+
- **Сеть**: Статический IP

## 📦 Установка зависимостей

### 1. Обновление системы
```bash
sudo apt update && sudo apt upgrade -y
```

### 2. Установка Python 3.11
```bash
sudo apt install software-properties-common -y
sudo add-apt-repository ppa:deadsnakes/ppa -y
sudo apt update
sudo apt install python3.11 python3.11-venv python3.11-dev -y
```

### 3. Установка PostgreSQL
```bash
sudo apt install postgresql postgresql-contrib -y
sudo systemctl start postgresql
sudo systemctl enable postgresql
```

### 4. Установка Redis
```bash
sudo apt install redis-server -y
sudo systemctl start redis-server
sudo systemctl enable redis-server
```

### 5. Установка Nginx
```bash
sudo apt install nginx -y
sudo systemctl start nginx
sudo systemctl enable nginx
```

## 🔧 Настройка базы данных

### 1. Создание пользователя и базы данных
```bash
sudo -u postgres psql
```

```sql
CREATE DATABASE hood_integration;
CREATE USER hood_user WITH PASSWORD 'secure_password';
GRANT ALL PRIVILEGES ON DATABASE hood_integration TO hood_user;
ALTER USER hood_user CREATEDB;
\q
```

### 2. Настройка PostgreSQL
```bash
sudo nano /etc/postgresql/13/main/postgresql.conf
```

Найдите и измените:
```
listen_addresses = 'localhost'
port = 5432
```

```bash
sudo nano /etc/postgresql/13/main/pg_hba.conf
```

Добавьте:
```
local   hood_integration   hood_user   md5
```

```bash
sudo systemctl restart postgresql
```

## 🌐 Настройка домена и SSL

### 1. Настройка DNS
Настройте DNS записи для домена `hood.automatonsoft.de`:
```
A    hood.automatonsoft.de    -> IP_СЕРВЕРА
A    www.hood.automatonsoft.de -> IP_СЕРВЕРА
```

### 2. Установка SSL сертификата (Let's Encrypt)
```bash
sudo apt install certbot python3-certbot-nginx -y
sudo certbot --nginx -d hood.automatonsoft.de -d www.hood.automatonsoft.de
```

### 3. Автообновление SSL
```bash
sudo crontab -e
```

Добавьте:
```
0 12 * * * /usr/bin/certbot renew --quiet
```

## 🚀 Деплой приложения

### 1. Клонирование репозитория
```bash
cd /var/www
sudo git clone https://github.com/your-repo/hood-integration-service.git hood.automatonsoft.de
sudo chown -R www-data:www-data hood.automatonsoft.de
```

### 2. Настройка виртуального окружения
```bash
cd /var/www/hood.automatonsoft.de
sudo python3.11 -m venv venv
sudo chown -R www-data:www-data venv
```

### 3. Установка зависимостей
```bash
source venv/bin/activate
pip install -r requirements.txt
```

### 4. Настройка переменных окружения
```bash
sudo cp .env.example .env
sudo nano .env
```

Настройте:
```env
DEBUG=False
SECRET_KEY=your-secret-key-here
ALLOWED_HOSTS=hood.automatonsoft.de,www.hood.automatonsoft.de
DATABASE_URL=postgresql://hood_user:secure_password@localhost:5432/hood_integration
REDIS_URL=redis://localhost:6379/0
HOOD_API_USERNAME=your_hood_username
HOOD_API_PASSWORD=your_hood_password
HOOD_ACCOUNT_NAME=your_account_name
HOOD_ACCOUNT_PASS=your_account_password
```

### 5. Применение миграций
```bash
python manage.py migrate
python manage.py collectstatic --noinput
python manage.py createsuperuser
```

## ⚙️ Настройка сервисов

### 1. Настройка Gunicorn
```bash
sudo cp hood-integration.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable hood-integration
sudo systemctl start hood-integration
```

### 2. Настройка Nginx
```bash
sudo cp nginx.conf /etc/nginx/sites-available/hood.automatonsoft.de
sudo ln -s /etc/nginx/sites-available/hood.automatonsoft.de /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl reload nginx
```

### 3. Создание директорий для логов
```bash
sudo mkdir -p /var/log/hood_integration
sudo chown -R www-data:www-data /var/log/hood_integration
```

## 🔄 Автоматический деплой

### Использование скрипта деплоя
```bash
chmod +x deploy.sh
./deploy.sh
```

### Настройка CI/CD (GitHub Actions)
```yaml
name: Deploy to Production

on:
  push:
    branches: [ main ]

jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
    - uses: actions/checkout@v2
    
    - name: Deploy to server
      uses: appleboy/ssh-action@v0.1.5
      with:
        host: ${{ secrets.HOST }}
        username: ${{ secrets.USERNAME }}
        key: ${{ secrets.SSH_KEY }}
        script: |
          cd /var/www/hood.automatonsoft.de
          git pull origin main
          source venv/bin/activate
          pip install -r requirements.txt
          python manage.py collectstatic --noinput
          python manage.py migrate
          sudo systemctl restart hood-integration
```

## 📊 Мониторинг

### 1. Проверка статуса сервисов
```bash
sudo systemctl status hood-integration
sudo systemctl status nginx
sudo systemctl status postgresql
sudo systemctl status redis-server
```

### 2. Просмотр логов
```bash
sudo journalctl -u hood-integration -f
sudo tail -f /var/log/nginx/hood.automatonsoft.de.access.log
sudo tail -f /var/log/hood_integration/django.log
```

### 3. Мониторинг ресурсов
```bash
htop
df -h
free -h
```

## 🔒 Безопасность

### 1. Настройка файрвола
```bash
sudo ufw enable
sudo ufw allow ssh
sudo ufw allow 'Nginx Full'
sudo ufw allow 5432
```

### 2. Настройка SSH
```bash
sudo nano /etc/ssh/sshd_config
```

Измените:
```
Port 2222
PermitRootLogin no
PasswordAuthentication no
```

### 3. Регулярные обновления
```bash
sudo apt update && sudo apt upgrade -y
```

## 🚨 Устранение неполадок

### Проблемы с базой данных
```bash
sudo -u postgres psql -c "\l"
sudo systemctl status postgresql
```

### Проблемы с Nginx
```bash
sudo nginx -t
sudo systemctl status nginx
```

### Проблемы с приложением
```bash
sudo journalctl -u hood-integration --no-pager
```

## 📞 Поддержка

При возникновении проблем:
1. Проверьте логи сервисов
2. Проверьте статус всех сервисов
3. Проверьте конфигурационные файлы
4. Обратитесь к документации Django

---

**🎉 После успешного деплоя сайт будет доступен по адресу: https://hood.automatonsoft.de**
