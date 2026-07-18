#!/bin/bash

set -e

# Функция для проверки доступности PostgreSQL
postgres_ready() {
python << END
import sys
import psycopg2
try:
    psycopg2.connect(
        dbname="${POSTGRES_DB}",
        user="${POSTGRES_USER}",
        password="${POSTGRES_PASSWORD}",
        host="${POSTGRES_HOST}",
        port="5432"
    )
except psycopg2.OperationalError:
    sys.exit(-1)
sys.exit(0)
END
}

# Ждём готовности PostgreSQL
until postgres_ready; do
  echo "Waiting for PostgreSQL..."
  sleep 1
done
echo "PostgreSQL is ready!"

# Применяем миграции
python manage.py migrate

# Собираем статику
python manage.py collectstatic --noinput

# Создаем директорию для кэша
mkdir -p /app/cache

# Автосинхронизация будет интегрирована в Django сервер

# Если переданы аргументы командной строки, выполняем их
# Иначе запускаем сервер на порту 8000 (внутренний порт)
if [ $# -eq 0 ]; then
    echo "No command provided, starting Django server..."
    python manage.py runserver 0.0.0.0:8000
else
    echo "Executing command: $@"
    exec "$@"
fi
