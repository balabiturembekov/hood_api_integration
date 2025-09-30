# Исправление ошибки CSRF (403 Forbidden)

## Проблема
```
Ошибка доступа (403)
Ошибка проверки CSRF. Запрос отклонён.
Origin checking failed - https://hood.automatonsoft.de does not match any trusted origins.
```

## Решение

### Вариант 1: Обновить код и перезапустить контейнеры

На сервере выполните:

```bash
cd /home/server/hood_api_integration

# Обновить код
git pull origin main

# Перезапустить контейнеры
docker-compose down
docker-compose up -d --build
```

### Вариант 2: Добавить CSRF_TRUSTED_ORIGINS в .env

Если обновление кода не помогло:

```bash
# Добавить CSRF_TRUSTED_ORIGINS в .env файл
echo "CSRF_TRUSTED_ORIGINS=https://hood.automatonsoft.de,https://www.hood.automatonsoft.de" >> .env

# Перезапустить контейнеры
docker-compose down
docker-compose up -d --build
```

### Вариант 3: Проверить переменные окружения

```bash
# Проверить содержимое .env файла
cat .env | grep -E "(ALLOWED_HOSTS|CSRF_TRUSTED_ORIGINS)"

# Проверить переменные в контейнере
docker-compose exec web env | grep -E "(ALLOWED_HOSTS|CSRF_TRUSTED_ORIGINS)"
```

### Вариант 4: Временное отключение CSRF (НЕ РЕКОМЕНДУЕТСЯ)

Только для тестирования, добавьте в .env:
```bash
echo "CSRF_COOKIE_SECURE=False" >> .env
echo "SESSION_COOKIE_SECURE=False" >> .env
```

## Проверка

После исправления проверьте:

1. **Статус контейнеров:**
   ```bash
   docker-compose ps
   ```

2. **Логи приложения:**
   ```bash
   docker-compose logs web | tail -20
   ```

3. **Доступность сайта:**
   ```bash
   curl -I https://hood.automatonsoft.de/
   ```

4. **Тест CSRF:**
   - Откройте https://hood.automatonsoft.de/
   - Попробуйте войти в админку
   - Проверьте, что формы работают

## Дополнительные настройки CSRF

Если проблема остается, проверьте:

1. **Настройки сессий:**
   ```bash
   # В .env файле должны быть:
   SESSION_COOKIE_SECURE=True
   CSRF_COOKIE_SECURE=True
   ```

2. **Настройки прокси:**
   ```bash
   # В nginx конфигурации должны быть заголовки:
   proxy_set_header X-Forwarded-Proto $scheme;
   proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
   ```

3. **Проверка SSL:**
   ```bash
   # Убедитесь, что SSL работает
   curl -I https://hood.automatonsoft.de/
   ```

## Полезные команды

```bash
# Просмотр всех переменных окружения
docker-compose exec web env

# Просмотр логов в реальном времени
docker-compose logs -f web

# Перезапуск только web контейнера
docker-compose restart web

# Проверка конфигурации nginx
sudo nginx -t
```
