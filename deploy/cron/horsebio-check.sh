#!/bin/bash
#
# Обёртка для запуска проверки по расписанию.
#
# Делает три вещи, которых не умеет голый cron:
#   1. Не даёт двум прогонам наложиться (flock);
#   2. Отличает пропуск от ошибки — своим кодом выхода;
#   3. Пишет итог в журнал с отметкой времени.
#
# Использование: horsebio-check.sh <id проверки>
# Список идентификаторов: docker compose exec -T backend python manage.py run_check --list
set -uo pipefail

ID="${1:?Укажите идентификатор проверки (run_check --list)}"
PROJECT_DIR=/root/horsebio
LOG=/var/log/horsebio_cron.log
LOCK="/var/lock/horsebio-check-$ID.lock"

# Код, которым flock сообщает «замок занят». Свой, а не общий 1: иначе
# пропущенный запуск неотличим от упавшей проверки, и каждый тик
# пятиминутной задачи поднимал бы ложную тревогу, пока идёт долгий прогон.
# Тот же код отдаёт и сама команда, когда видит живой pid-файл, — защита
# двойная: flock экономит процесс, pid-файл защищает данные.
LOCK_BUSY=75

log() { echo "[$(date '+%F %T')] $ID: $*" >> "$LOG"; }

# Контейнер и момент его запуска. Деплой пересоздаёт контейнер прямо посреди
# прогона, `docker compose exec` умирает по SIGKILL с кодом 137 — и в журнале
# это неотличимо от упавшей проверки. Сравнение до и после прогона отличает.
backend_state() {
    local id
    id=$(docker compose -f "$PROJECT_DIR/docker-compose.prod.yml" ps -q backend 2>/dev/null)
    if [ -z "$id" ]; then
        echo "нет контейнера"
        return
    fi
    echo "$id $(docker inspect -f '{{.State.StartedAt}}' "$id" 2>/dev/null)"
}

# Предел времени задаётся не здесь, а в реестре проверок
# (api/services/scripts_registry.py): у каждой задачи он свой, и знание
# о ней должно жить в одном месте. Команда снимает прогон сама и пишет
# об этом в лог прогона, который видно на странице «Проверки».
BEFORE=$(backend_state)
OUTPUT=$(flock -n -E "$LOCK_BUSY" "$LOCK" \
    docker compose -f "$PROJECT_DIR/docker-compose.prod.yml" \
        exec -T backend python manage.py run_check "$ID" 2>&1)
STATUS=$?
AFTER=$(backend_state)

case $STATUS in
  0)
    log "готово"
    ;;
  "$LOCK_BUSY")
    # Предыдущий прогон ещё идёт. Это штатное поведение, а не сбой:
    # очередь проверок хуже пропущенного запуска.
    log "пропуск: предыдущий прогон ещё идёт"
    STATUS=0
    ;;
  124)
    log "ОШИБКА: прогон снят по сроку"
    ;;
  *)
    if [ "$BEFORE" != "$AFTER" ]; then
        # Контейнер сменился, пока шёл прогон: это деплой, а не сбой проверки.
        # Следующий запуск по расписанию отработает как обычно, а сам прогон
        # отметит себя оборванным на странице «Проверки».
        log "пропуск: контейнер пересоздан во время прогона (код $STATUS)"
        STATUS=0
    else
        log "ОШИБКА (код $STATUS): $OUTPUT"
    fi
    ;;
esac

exit $STATUS
