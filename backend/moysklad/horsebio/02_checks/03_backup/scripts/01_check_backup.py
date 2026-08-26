#!/usr/bin/env python3
"""Проверка: идут ли бэкапы.

Бэкап делает `/root/backup/backup.sh` на хосте по крону и после каждого прогона
пишет `state/status.json` — только метаданные, без секретов (внутрь архивов
попадают `.env.prod` и приватные ключи, поэтому в контейнер монтируется
каталог состояния, а не полка с архивами).

Смысл проверки — не в том, чтобы посмотреть на зелёную галочку, а в том, чтобы
заметить тишину. База Horse Bio не бэкапилась семь месяцев, и это обнаружилось
случайно: дамп, который считали свежим, оказался дампом чужого кластера.
Поэтому отсутствие файла состояния здесь — критическая находка, а не повод
промолчать: проверка, которая не смогла проверить, обязана сказать об этом.
"""
import argparse
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

STATE_FILE = Path("/app/backup-state/status.json")

# Прогон раз в сутки в 03:30. Сутки с запасом на долгий прогон и перезагрузку:
# сработает на второй пропуск, а не на первый же сдвиг расписания.
STALE_HOURS = 36
# Норма полного архива — 21 МБ. Внезапно похудевший вдвое архив означает,
# что дамп снялся не целиком: формально успех, фактически потеря данных.
MIN_FULL_MB = 10
# Ниже этого порога следующий прогон не начнётся — скрипт сам себя остановит.
MIN_FREE_MB = 2048
RESTORE_MAX_AGE_DAYS = 90


def mb(size_bytes):
    return round((size_bytes or 0) / 1024 / 1024, 1)


def human_age(delta):
    hours = delta.total_seconds() / 3600
    if hours < 1:
        return f"{int(delta.total_seconds() // 60)} мин назад"
    if hours < 48:
        return f"{int(hours)} ч назад"
    return f"{int(hours // 24)} дн назад"


def category(key, title, severity, note, detail, obj="Бэкап"):
    return {
        "key": key, "title": title, "severity": severity,
        "kind": None, "ms_type": None, "count": 1, "note": note,
        "items": [{"key": key, "ms_id": "", "ms_href": "",
                   "object": obj, "severity": severity, "detail": detail}],
    }


def read_state():
    """Прочитать состояние. Вернуть (состояние, причина недоступности)."""
    if not STATE_FILE.exists():
        return None, (
            f"файла {STATE_FILE} нет. Либо бэкап ни разу не отработал, либо каталог "
            f"состояния не примонтирован в контейнер"
        )
    try:
        return json.loads(STATE_FILE.read_text(encoding="utf-8")), None
    except (OSError, ValueError) as e:
        return None, f"файл состояния нечитаем: {e}"


def build_payload(state, unavailable):
    categories = []

    # ── Состояния нет: проверять нечего, и это само по себе плохая новость ──
    if unavailable:
        categories.append(category(
            "no_state", "Проверка не видит бэкап", "critical",
            "Страница не может подтвердить, что бэкапы идут. Это не значит «всё хорошо» — "
            "это значит «неизвестно». Проверить на сервере: "
            "`ls -la /root/backup/state/` и `tail /var/log/horsebio-backup.log`. "
            "Если каталог есть, а контейнер его не видит — не хватает монтирования "
            "`/root/backup/state:/app/backup-state:ro` в docker-compose.prod.yml.",
            unavailable, obj="Состояние бэкапа",
        ))
        return {
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "params": {"state_file": str(STATE_FILE)},
            "summary": {
                "critical": 1, "important": 0, "warnings": 0, "ok": 0,
                "stats": [{"label": "Состояние бэкапа", "value": "недоступно",
                           "tone": "critical", "cat": "no_state"}],
                "view": "snapshot",
                "empty_note": "",
            },
            "categories": categories,
        }

    finished_raw = state.get("finished_at")
    try:
        finished = datetime.fromisoformat(finished_raw) if finished_raw else None
    except ValueError:
        finished = None
    age = datetime.now(finished.tzinfo) - finished if finished else None

    full_mb = mb(state.get("full", {}).get("size"))
    valuable_mb = mb(state.get("valuable", {}).get("size"))
    free_mb = state.get("disk_free_mb") or 0
    counts = state.get("counts", {})
    keep = state.get("keep", {})

    # ── Последний прогон провалился ──
    if state.get("ok") is False:
        categories.append(category(
            "failed", "Последний бэкап не удался", "critical",
            "Прогон оборвался, свежей копии за этот день нет. Предыдущие архивы на месте — "
            "ротация выполняется только после успешной упаковки. "
            "Смотреть `/var/log/horsebio-backup.log`, затем запустить вручную: "
            "`/root/backup/backup.sh`.",
            state.get("error") or "причина не записана",
        ))

    # ── Прогонов давно не было ──
    if age is None:
        categories.append(category(
            "no_time", "В состоянии нет времени прогона", "important",
            "Файл состояния есть, но без даты — понять, свежий ли бэкап, нельзя. "
            "Похоже на повреждённый или недописанный файл.",
            f"finished_at = {finished_raw!r}",
        ))
    elif age > timedelta(hours=STALE_HOURS):
        categories.append(category(
            "stale", "Бэкап давно не делался", "critical",
            f"Последний прогон был {human_age(age)}, а расписание — ежедневно в 03:30. "
            "Значит крон не отработал или скрипт молча падает до записи состояния. "
            "Проверить `crontab -l | grep backup` и `tail /var/log/horsebio-backup.log`.",
            f"последний успешный прогон: {finished.strftime('%d.%m.%Y %H:%M')} ({human_age(age)})",
        ))

    # ── Архив аномально мал ──
    if state.get("ok") and 0 < full_mb < MIN_FULL_MB:
        categories.append(category(
            "tiny", "Полный архив подозрительно мал", "important",
            f"Норма — около 21 МБ, сейчас {full_mb} МБ. Прогон завершился успешно, "
            "то есть дамп прочитался, но попасть в него могло не всё. "
            "Развернуть архив на временном контейнере и сверить счётчики таблиц "
            "с боевой базой (команды — в MANIFEST.txt внутри архива).",
            f"{full_mb} МБ при ожидаемых ~21 МБ",
        ))

    # ── Место на диске ──
    if 0 < free_mb < MIN_FREE_MB:
        categories.append(category(
            "disk", "Мало места под бэкапы", "important",
            f"Скрипт не начинает прогон, если свободно меньше {MIN_FREE_MB} МБ — "
            "чтобы не оставить полурезанный архив вместо целого вчерашнего. "
            "То есть следующий бэкап просто не пойдёт. Освободить место или уменьшить "
            "глубину хранения в начале `/root/backup/backup.sh`.",
            f"свободно {free_mb} МБ, порог {MIN_FREE_MB} МБ",
        ))

    # ── Восстановление давно не проверяли ──
    verified_raw = state.get("restore_verified_at")
    verified = None
    if verified_raw:
        try:
            verified = datetime.strptime(verified_raw.strip(), "%Y-%m-%d").date()
        except ValueError:
            verified = None
    if verified is None:
        categories.append(category(
            "restore_unknown", "Восстановление ни разу не проверяли", "warning",
            "Бэкап, который не пробовали восстановить, бэкапом не является. "
            "Развернуть последний архив на временном контейнере, сверить счётчики "
            "с боевой базой и записать дату: "
            "`date +%F > /root/backup/state/restore-verified`.",
            "отметки о проверке нет", obj="Проверка восстановлением",
        ))
    elif (datetime.now().date() - verified).days > RESTORE_MAX_AGE_DAYS:
        days = (datetime.now().date() - verified).days
        categories.append(category(
            "restore_stale", "Восстановление давно не проверяли", "warning",
            f"Последняя проверка была {days} дн. назад. За это время могла смениться "
            "версия Postgres или схема базы. Повторить разворачивание на временном "
            "контейнере и обновить отметку.",
            f"последняя проверка: {verified.strftime('%d.%m.%Y')} ({days} дн назад)",
            obj="Проверка восстановлением",
        ))

    critical = sum(1 for c in categories if c["severity"] == "critical")
    important = sum(1 for c in categories if c["severity"] == "important")
    warnings = sum(1 for c in categories if c["severity"] == "warning")

    stats = [
        {"label": "Последний бэкап",
         "value": human_age(age) if age else "неизвестно",
         "tone": "critical" if (age is None or age > timedelta(hours=STALE_HOURS)) else "ok"},
        {"label": "Полный архив", "value": f"{full_mb} МБ",
         "tone": "important" if (0 < full_mb < MIN_FULL_MB) else "neutral"},
        {"label": "Ценный архив", "value": f"{valuable_mb} МБ", "tone": "neutral"},
        {"label": "Копий на полках",
         "value": f"{counts.get('daily', 0)}/{keep.get('daily', '?')} сут · "
                  f"{counts.get('weekly', 0)}/{keep.get('weekly', '?')} нед · "
                  f"{counts.get('monthly', 0)}/{keep.get('monthly', '?')} мес",
         "tone": "neutral"},
        {"label": "Свободно на диске", "value": f"{free_mb} МБ",
         "tone": "important" if (0 < free_mb < MIN_FREE_MB) else "neutral"},
        {"label": "Восстановление проверено",
         "value": verified.strftime("%d.%m.%Y") if verified else "никогда",
         "tone": "warning" if verified is None else "neutral"},
    ]

    return {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "params": {"stale_hours": STALE_HOURS, "state_file": str(STATE_FILE)},
        "summary": {
            "critical": critical, "important": important, "warnings": warnings,
            "ok": 1 if not categories else 0,
            "stats": stats, "view": "snapshot",
            "empty_note": (
                f"Бэкап отработал {human_age(age)}: полный архив {full_mb} МБ, "
                f"ценный {valuable_mb} МБ. Восстановление проверялось "
                f"{verified.strftime('%d.%m.%Y') if verified else 'никогда'}."
            ) if age else "",
        },
        "categories": categories,
    }


def main():
    parser = argparse.ArgumentParser(description="Проверка состояния бэкапов")
    parser.add_argument("--results-out", dest="results_out")
    args = parser.parse_args()

    state, unavailable = read_state()
    payload = build_payload(state, unavailable)
    s = payload["summary"]

    print("=" * 64)
    print("  Бэкапы Horse Bio")
    print("=" * 64)
    if unavailable:
        print(f"  СОСТОЯНИЕ НЕДОСТУПНО: {unavailable}")
    else:
        for stat in s["stats"]:
            print(f"  {stat['label']:<26} {stat['value']}")
    if payload["categories"]:
        print()
        for c in payload["categories"]:
            print(f"  [{c['severity'].upper()}] {c['title']}")
            for item in c["items"]:
                print(f"      {item['detail']}")
    else:
        print("\n  Замечаний нет")
    print("=" * 64)

    if args.results_out:
        try:
            Path(args.results_out).write_text(
                json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        except OSError as e:
            print(f"Ошибка сохранения результатов JSON: {e}")

    # Ненулевой код — чтобы падение было видно и в логе крона, а не только на странице
    return 1 if s["critical"] else 0


if __name__ == "__main__":
    sys.exit(main())
