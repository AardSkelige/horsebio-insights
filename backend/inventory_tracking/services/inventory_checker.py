"""
Core business logic for the daily inventory tracking check.
Supports both current month and arbitrary past months.
"""
import logging
from datetime import date, datetime, timedelta
from typing import Optional

from django.conf import settings
from django.utils import timezone

logger = logging.getLogger(__name__)


def _last_day_of_month(d: date) -> date:
    next_month = (d.replace(day=28) + timedelta(days=4)).replace(day=1)
    return next_month - timedelta(days=1)


def parse_month(month_str: str) -> date:
    """Parse 'YYYY-MM' string into the first day of that month."""
    return datetime.strptime(month_str, "%Y-%m").date()


class InventoryChecker:

    def run(self, triggered_by: str = 'scheduler', month_start: Optional[date] = None):
        """
        Run inventory check for the given month (defaults to current month).
        month_start must be the 1st day of the target month.
        """
        if month_start is None:
            month_start = date.today().replace(day=1)

        month_end = _last_day_of_month(month_start)
        # A run is a month snapshot if it covers a fully completed month
        today = date.today()
        is_month_snapshot = (today > month_end)

        client = self._get_client()

        logger.info(f"Fetching monitored products from MoySklad...")
        products = client.get_monitored_products()

        logger.info(f"Fetching inventories for {month_start} – {month_end}...")
        from_dt = datetime.combine(month_start, datetime.min.time())
        to_dt = datetime.combine(month_end, datetime.max.time().replace(microsecond=0))
        seen_map = client.get_inventoried_products_map(from_dt, to_dt)

        run = self._save_run(
            products=products,
            seen_map=seen_map,
            month_start=month_start,
            triggered_by=triggered_by,
            is_month_snapshot=is_month_snapshot,
        )

        logger.info(
            f"InventoryRun #{run.id} [{month_start}]: total={run.total_products}, "
            f"inventoried={run.inventoried_count}, not_inventoried={run.not_inventoried_count}"
        )
        return run

    def _get_client(self):
        from sync.moysklad.connection import MoySkladAPIClient
        return MoySkladAPIClient(settings.MOYSKLAD_TOKEN)

    def _save_run(self, products, seen_map, month_start, triggered_by, is_month_snapshot):
        from inventory_tracking.models import InventoryRun, ProductInventoryStatus

        seen_pids = set()
        unique_products = []
        for p in products:
            pid = p.get('id')
            if pid and pid not in seen_pids:
                seen_pids.add(pid)
                unique_products.append(p)

        inventoried_count = sum(1 for p in unique_products if p.get('id') in seen_map)
        not_inventoried_count = len(unique_products) - inventoried_count

        run = InventoryRun.objects.create(
            month_start=month_start,
            total_products=len(unique_products),
            inventoried_count=inventoried_count,
            not_inventoried_count=not_inventoried_count,
            is_month_snapshot=is_month_snapshot,
            triggered_by=triggered_by,
        )

        now = timezone.now()
        # For past completed months, measure staleness relative to month end,
        # not today — so "дней" means "days since last inventory as of that period".
        if is_month_snapshot:
            month_end = _last_day_of_month(month_start)
            reference_dt = timezone.make_aware(
                datetime.combine(month_end, datetime.max.time().replace(microsecond=0))
            )
        else:
            reference_dt = now

        statuses = []
        for p in unique_products:
            pid = p.get('id', '')
            inv_data = seen_map.get(pid, {})
            is_inventoried = bool(inv_data)
            last_at = inv_data.get('last_date')

            days_since = None
            if last_at:
                days_since = (reference_dt - last_at).days

            statuses.append(ProductInventoryStatus(
                run=run,
                external_id=pid,
                code=p.get('code', '') or '',
                article=p.get('article', '') or '',
                name=p.get('name', '') or '',
                folder=p.get('_category', ''),
                is_inventoried=is_inventoried,
                inventory_count=inv_data.get('count', 0),
                last_inventoried_at=last_at,
                days_since_last=days_since,
            ))

        ProductInventoryStatus.objects.bulk_create(statuses)

        # For products not inventoried this month, pull their historical last date
        # from any previous run where they were inventoried.
        not_inv_pids = [
            p.get('id', '') for p in unique_products
            if not seen_map.get(p.get('id', ''))
        ]
        if not_inv_pids:
            from django.db.models import Max
            historical = (
                ProductInventoryStatus.objects
                .filter(
                    external_id__in=not_inv_pids,
                    is_inventoried=True,
                    last_inventoried_at__isnull=False,
                )
                .exclude(run=run)
                .values('external_id')
                .annotate(last_inv=Max('last_inventoried_at'))
            )
            historical_map = {h['external_id']: h['last_inv'] for h in historical}

            if historical_map:
                to_update = list(
                    ProductInventoryStatus.objects.filter(
                        run=run,
                        is_inventoried=False,
                        external_id__in=historical_map.keys(),
                    )
                )
                for status in to_update:
                    last_inv = historical_map[status.external_id]
                    status.last_inventoried_at = last_inv
                    status.days_since_last = (reference_dt - last_inv).days
                ProductInventoryStatus.objects.bulk_update(
                    to_update,
                    ['last_inventoried_at', 'days_since_last'],
                )

        return run
