#!/usr/bin/env bash
#
# Бэкап Horse Bio: база, сертификаты Caddy, конфигурация.
#
# Источник истины — этот файл в репозитории; на сервер его кладёт деплой
# (`deploy/**` попадает в /root/horsebio), а зовёт crontab в 3:30. Правки
# вносить здесь, а не на сервере: до 09.09.2026 скрипт жил только в /root,
# и его правки не были видны ни в истории, ни в ревью.
#
# Два вида архива, оба ежедневно:
#   full     — всё, включая зеркало МойСклада и журнал роботов (~30 МБ)
#   valuable — только то, что не восстановится синхронизацией (~3 МБ)
#
# Правило: старое не удаляется, пока новое не создано и не проверено.
#
#   backup.sh              обычный прогон
#   backup.sh --dry-run    показать, что было бы сделано
#
set -euo pipefail

ROOT=/root/backup
LOG=/var/log/horsebio-backup.log
DB_CONTAINER=horsebio_db_prod
DB_NAME=horsebio_db
DB_USER=horsebio
MIN_FREE_MB=2048

# Файл состояния для страницы проверок. Лежит отдельно от архивов и содержит
# ТОЛЬКО метаданные: внутрь архивов попадают .env.prod и приватные ключи,
# поэтому в контейнер приложения монтируется этот каталог, а не весь /root/backup.
STATE_DIR=$ROOT/state
STATE=$STATE_DIR/status.json

KEEP_DAILY=14
KEEP_WEEKLY=8
KEEP_MONTHLY=12
KEEP_VALUABLE=90

# Томов с состоянием роботов больше нет: 06–07.09.2026 всё уехало в Postgres
# и попадает в бэкап вместе с дампом базы. Список убран 09.09.2026 — ровно по
# той причине, что описана ниже: docker run с именованным томом СОЗДАЁТ его,
# если тома нет, и с 08.09 бэкап каждую ночь возрождал семь пустых томов
# и клал в архив семь пустых архивов по 86 байт.
#
# Тома sp_* убраны 02.09.2026 вместе с переездом скриптов StarPony в свой проект.

# ACME-аккаунт и сертификаты. Потеряются — сертификат сразу не выпустить:
# у Let's Encrypt лимит на повторные выпуски.
CADDY_VOLUMES=(caddy_caddy_data caddy_caddy_config)

DRY_RUN=0
[[ "${1:-}" == "--dry-run" ]] && DRY_RUN=1

STAMP=$(date +%F)
STARTED=$(date +%s)
say() { printf '%s  %s\n' "$(date '+%F %T')" "$*" | tee -a "$LOG"; }
# exit не поднимает ловушку ERR, поэтому состояние пишем здесь же и снимаем её,
# чтобы провал не был записан дважды.
die() { say "ОШИБКА: $*"; trap - ERR; write_status false "$*"; exit 1; }

# Состояние пишется и при успехе, и при провале. Молчащий бэкап неотличим
# от несуществующего — ровно так его отсутствие и не замечали семь месяцев.
FAIL_REASON=''
write_status() {
  local ok=$1 reason=$2
  (( DRY_RUN )) && return 0
  mkdir -p "$STATE_DIR"
  local full valuable full_size=0 valuable_size=0 full_at='' valuable_at=''
  full=$(ls -1t "$ROOT/daily"/*.tar.gz 2>/dev/null | head -1 || true)
  valuable=$(ls -1t "$ROOT/valuable"/*.tar.gz 2>/dev/null | head -1 || true)
  [[ -n "$full"     ]] && { full_size=$(stat -c%s "$full");         full_at=$(date -d "@$(stat -c%Y "$full")" --iso-8601=seconds); }
  [[ -n "$valuable" ]] && { valuable_size=$(stat -c%s "$valuable"); valuable_at=$(date -d "@$(stat -c%Y "$valuable")" --iso-8601=seconds); }

  cat > "$STATE.part" <<JSON
{
  "finished_at": "$(date --iso-8601=seconds)",
  "ok": $ok,
  "error": $( [[ -z "$reason" ]] && echo null || printf '"%s"' "${reason//\"/\\\"}" ),
  "duration_sec": $(( $(date +%s) - STARTED )),
  "full":     { "size": $full_size,     "created_at": $( [[ -z "$full_at"     ]] && echo null || printf '"%s"' "$full_at" ) },
  "valuable": { "size": $valuable_size, "created_at": $( [[ -z "$valuable_at" ]] && echo null || printf '"%s"' "$valuable_at" ) },
  "counts": {
    "daily":    $(ls -1 "$ROOT/daily"    2>/dev/null | wc -l),
    "weekly":   $(ls -1 "$ROOT/weekly"   2>/dev/null | wc -l),
    "monthly":  $(ls -1 "$ROOT/monthly"  2>/dev/null | wc -l),
    "valuable": $(ls -1 "$ROOT/valuable" 2>/dev/null | wc -l)
  },
  "keep": { "daily": $KEEP_DAILY, "weekly": $KEEP_WEEKLY, "monthly": $KEEP_MONTHLY, "valuable": $KEEP_VALUABLE },
  "shelves_bytes": $(du -sb "$ROOT" 2>/dev/null | cut -f1),
  "disk_free_mb": $(df -Pm "$ROOT" | awk 'NR==2 {print $4}'),
  "restore_verified_at": $( [[ -f "$STATE_DIR/restore-verified" ]] && printf '"%s"' "$(cat "$STATE_DIR/restore-verified")" || echo null )
}
JSON
  mv -f "$STATE.part" "$STATE"
  chmod 644 "$STATE"          # читается контейнером приложения; секретов внутри нет
}

# Любой обрыв — не тишина, а запись о провале с последней внятной причиной.
on_fail() {
  local code=$?
  write_status false "${FAIL_REASON:-прогон оборвался на строке $BASH_LINENO (код $code)}"
  say "состояние записано: ПРОВАЛ"
}
trap on_fail ERR

run() {
  if (( DRY_RUN )); then printf '        [dry-run] %s\n' "$*"; else eval "$@"; fi
}

say "--- начало ($([[ $DRY_RUN == 1 ]] && echo 'dry-run' || echo 'рабочий прогон')) ---"

free_mb=$(df -Pm "$ROOT" | awk 'NR==2 {print $4}')
(( free_mb >= MIN_FREE_MB )) || die "на диске $free_mb МБ, нужно минимум $MIN_FREE_MB"

mkdir -p "$ROOT"/{daily,weekly,monthly,valuable,tmp}
chmod 700 "$ROOT" "$ROOT"/{daily,weekly,monthly,valuable,tmp}

WORK="$ROOT/tmp/$STAMP.$$"
trap 'rm -rf "$WORK"' EXIT
mkdir -p "$WORK"/{db,caddy,config}

# --- 1. База -----------------------------------------------------------------
# Формат custom: сжат, восстанавливается выборочно, проверяется без разворачивания.

dump_db() {
  local out=$1; shift
  docker exec "$DB_CONTAINER" pg_dump -U "$DB_USER" -d "$DB_NAME" \
      --format=custom --compress=9 "$@" > "$out"
  # Читаемость архива подтверждаем оглавлением: битый дамп здесь и отвалится,
  # а не через полгода при восстановлении.
  local tables
  tables=$(docker exec -i "$DB_CONTAINER" pg_restore --list < "$out" | grep -c 'TABLE DATA' || true)
  (( tables > 0 )) || die "дамп $out нечитаем или пуст"
  say "  база: $(basename "$out") — $(du -h "$out" | cut -f1), таблиц с данными: $tables"
}

if (( DRY_RUN )); then
  say "  [dry-run] pg_dump полный и ценный"
else
  dump_db "$WORK/db/full.dump"
  # Ценный: без зеркала МойСклада (восстановится синком) и без журнала роботов
  # (интерфейс читает 30 последних прогонов, они набегают за час).
  dump_db "$WORK/db/valuable.dump" \
    --exclude-table-data='parser_*' \
    --exclude-table-data='api_checkrunresult'
fi

# --- 2. Тома Caddy -----------------------------------------------------------
# Читаем через временный контейнер: том может быть примонтирован в работающий
# сервис, копировать из /var/lib/docker/volumes напрямую — полагаться на удачу.

tar_volume() {
  local vol=$1 dest=$2
  docker run --rm -v "$vol":/src:ro -v "$dest":/out alpine:3 \
    tar czf "/out/$vol.tar.gz" -C /src . 2>/dev/null
  say "  том $vol — $(du -h "$dest/$vol.tar.gz" | cut -f1)"
}

for v in "${CADDY_VOLUMES[@]}" ; do
  if (( DRY_RUN )); then say "  [dry-run] том $v"; else tar_volume "$v" "$WORK/caddy"; fi
done

# --- 3. Конфигурация ---------------------------------------------------------
# Ничего из этого нет в git: .env.prod с секретами, Caddyfile, крон.
#
# RustDesk (hbbs/hbbr, /root/rustdesk/data) сюда НЕ входит намеренно: он живёт
# на том же диске, но к Horse Bio отношения не имеет. Свой бэкап ему нужен —
# но свой, а не спрятанный внутри чужого архива.

copy_if_exists() {
  local src=$1 dst=$2
  [[ -e "$src" ]] || { say "  ПРОПУЩЕНО (нет): $src"; return 0; }
  if (( DRY_RUN )); then say "  [dry-run] $src"; else cp -a "$src" "$dst"; say "  конфиг: $src"; fi
}

copy_if_exists /root/horsebio/backend/.env.prod   "$WORK/config/backend.env.prod"
copy_if_exists /root/horsebio/frontend/.env.prod  "$WORK/config/frontend.env.prod"
copy_if_exists /root/horsebio/docker-compose.prod.yml "$WORK/config/"
copy_if_exists /root/caddy/Caddyfile              "$WORK/caddy/"
copy_if_exists /root/caddy/docker-compose.caddy.yml "$WORK/caddy/"

if (( DRY_RUN )); then
  say "  [dry-run] crontab"
else
  crontab -l > "$WORK/config/crontab.txt" 2>/dev/null || say "  ПРОПУЩЕНО: crontab пуст"
  say "  конфиг: crontab ($(grep -vc '^\s*#\|^\s*$' "$WORK/config/crontab.txt" || echo 0) заданий)"
fi

# --- 4. Опись ----------------------------------------------------------------
# Чтобы через полгода не гадать, что внутри и чем это разворачивать.

if (( ! DRY_RUN )); then
  {
    echo "Бэкап Horse Bio — $(date '+%F %T %Z')"
    echo "Сервер:    $(hostname) / $(hostname -I | awk '{print $1}')"
    echo "Postgres:  $(docker exec "$DB_CONTAINER" postgres --version)"
    echo "База:      $DB_NAME, размер $(docker exec "$DB_CONTAINER" psql -U "$DB_USER" -d "$DB_NAME" -tAc "SELECT pg_size_pretty(pg_database_size('$DB_NAME'))")"
    echo
    echo "Восстановление базы:"
    echo "  docker exec -i $DB_CONTAINER pg_restore -U $DB_USER -d $DB_NAME --clean --if-exists < db/full.dump"
    echo
    echo "Восстановление тома:"
    echo "  docker run --rm -v <том>:/dst -v \$PWD:/src alpine:3 tar xzf /src/caddy/<том>.tar.gz -C /dst"
    echo
    echo "Состав:"
    find "$WORK" -type f -printf '  %10s  %P\n' | sort -k2
  } > "$WORK/MANIFEST.txt"
fi

# --- 5. Упаковка и укладка ---------------------------------------------------

pack() {
  local kind=$1 target=$2 exclude=$3
  local tmp="$ROOT/tmp/$kind-$STAMP.tar.gz.part"
  tar czf "$tmp" -C "$ROOT/tmp" --exclude="$exclude" "$(basename "$WORK")"
  mv -f "$tmp" "$target"                 # атомарно: либо целый файл, либо старый
  chmod 600 "$target"
  say "  архив $kind: $(du -h "$target" | cut -f1) → $target"
}

if (( DRY_RUN )); then
  say "  [dry-run] упаковка full и valuable"
else
  pack full     "$ROOT/daily/horsebio-full-$STAMP.tar.gz"        'valuable.dump'
  pack valuable "$ROOT/valuable/horsebio-valuable-$STAMP.tar.gz" 'full.dump'

  # Воскресенье и первое число — копии в отдельные полки. Копия, не перенос:
  # суточная полка должна оставаться сплошной.
  [[ $(date +%u) == 7 ]] && cp -a "$ROOT/daily/horsebio-full-$STAMP.tar.gz" "$ROOT/weekly/"  && say "  копия в weekly"
  [[ $(date +%d) == 01 ]] && cp -a "$ROOT/daily/horsebio-full-$STAMP.tar.gz" "$ROOT/monthly/horsebio-full-$(date +%Y-%m).tar.gz" && say "  копия в monthly"
fi

# --- 6. Ротация --------------------------------------------------------------
# Только после успешной упаковки: сюда мы попадаем лишь если всё выше прошло.

prune() {
  local dir=$1 keep=$2 removed
  removed=$(ls -1t "$dir" 2>/dev/null | tail -n "+$((keep+1))" || true)
  [[ -z "$removed" ]] && return 0
  while read -r f; do
    [[ -z "$f" ]] && continue
    if (( DRY_RUN )); then say "  [dry-run] удалить $dir/$f"; else rm -f "$dir/$f"; say "  ротация: удалён $f"; fi
  done <<< "$removed"
}

prune "$ROOT/daily"    "$KEEP_DAILY"
prune "$ROOT/weekly"   "$KEEP_WEEKLY"
prune "$ROOT/monthly"  "$KEEP_MONTHLY"
prune "$ROOT/valuable" "$KEEP_VALUABLE"

trap - ERR
write_status true ''
say "итого на полках: $(du -sh "$ROOT" | cut -f1), свободно на диске $(df -Ph "$ROOT" | awk 'NR==2 {print $4}')"
say "--- конец ---"
