# Исправление ошибки DisallowedHost

## Проблема
```
DisallowedHost at /
Invalid HTTP_HOST header: 'hood.automatonsoft.de'. You may need to add 'hood.automatonsoft.de' to ALLOWED_HOSTS.
```

## Решение

### Вариант 1: Проверить переменные окружения в .env

На сервере выполните:

```bash
cd /home/server/hood_api_integration

# Проверьте содержимое .env файла
cat .env | grep ALLOWED_HOSTS

# Если ALLOWED_HOSTS не настроен, добавьте его:
echo "ALLOWED_HOSTS=hood.automatonsoft.de,www.hood.automatonsoft.de,localhost,127.0.0.1" >> .env
```

### Вариант 2: Перезапустить контейнеры

```bash
# Остановить контейнеры
docker-compose down

# Запустить заново
docker-compose up -d --build
```

### Вариант 3: Проверить логи контейнера

```bash
# Посмотреть логи web контейнера
docker-compose logs web

# Посмотреть логи nginx
docker-compose logs nginx
```

### Вариант 4: Проверить переменные окружения в контейнере

```bash
# Войти в контейнер
docker-compose exec web bash

# Проверить переменные окружения
env | grep ALLOWED_HOSTS
env | grep DEBUG
```

## Проверка

После исправления проверьте:

1. **Статус контейнеров:**
   ```bash
   docker-compose ps
   ```

2. **Доступность сайта:**
   ```bash
   curl -I http://localhost:8282/
   curl -I https://hood.automatonsoft.de/
   ```

3. **Логи приложения:**
   ```bash
   docker-compose logs -f web
   ```

## Если проблема не решается

1. **Проверьте DNS:**
   ```bash
   nslookup hood.automatonsoft.de
   ```

2. **Проверьте файрвол:**
   ```bash
   sudo ufw status
   ```

3. **Проверьте nginx:**
   ```bash
   sudo nginx -t
   sudo systemctl status nginx
   ```
