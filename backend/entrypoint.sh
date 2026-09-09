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

# Если переданы аргументы командной строки, выполняем их.
# Иначе поднимаем сервер на внутреннем порту 8000.
if [ $# -gt 0 ]; then
    echo "Executing command: $@"
    exec "$@"
fi

if [ "${DJANGO_DEV_SERVER}" = "1" ]; then
    # Машина разработчика: runserver сам перечитывает изменённый код.
    # --insecure: DEBUG здесь False, а статику админки с 09.09.2026 отдавать
    # некому — локальный nginx убран, на боевом её отдаёт Caddy из тома.
    echo "Starting Django development server..."
    exec python manage.py runserver --insecure 0.0.0.0:8000
fi

# Боевой сервер. Параметры — те же, что у StarPony, они там обкатаны:
#   preload        — код читается один раз до форка, экономит память;
#   gthread        — потоки вместо процессов там, где запрос ждёт чужой ответ;
#   max-requests   — воркер перезапускается, чтобы утечки не копились;
#   worker-tmp-dir — heartbeat в память, а не на диск: на дисковой ФС он
#                    иногда блокирует воркеры, и сервис «зависает на ровном
#                    месте» без единой ошибки в логах.
#
# timeout больше StarPony (там 300): у Horse Bio есть тяжёлые страницы —
# прогноз и ABC-анализ считаются прямо в запросе. Тот же предел стоит
# и у Caddy, дальше него ждать всё равно некому.
#
# Перезапуск воркера по счётчику запросов стал безопасен только теперь:
# и синхронизация, и скрипты проверок ушли из веб-процесса в отдельные.
# Раньше он оборвал бы их на середине, молча.
echo "Starting gunicorn..."
exec gunicorn config.wsgi:application \
    --bind 0.0.0.0:8000 \
    --workers 2 \
    --worker-class gthread \
    --threads 4 \
    --timeout 600 \
    --preload \
    --max-requests 1000 \
    --max-requests-jitter 100 \
    --worker-tmp-dir /dev/shm \
    --access-logfile - \
    --error-logfile -
