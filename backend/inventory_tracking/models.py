from django.db import models


class InventoryRun(models.Model):
    run_at = models.DateTimeField(auto_now_add=True)
    month_start = models.DateField()
    total_products = models.IntegerField(default=0)
    inventoried_count = models.IntegerField(default=0)
    not_inventoried_count = models.IntegerField(default=0)
    is_month_snapshot = models.BooleanField(default=False)
    triggered_by = models.CharField(max_length=20, default='scheduler')

    class Meta:
        ordering = ['-run_at']

    def __str__(self):
        return f"InventoryRun {self.run_at.strftime('%Y-%m-%d %H:%M')} ({self.triggered_by})"


class ProductInventoryStatus(models.Model):
    run = models.ForeignKey(InventoryRun, on_delete=models.CASCADE, related_name='products')
    external_id = models.CharField(max_length=255)
    code = models.CharField(max_length=255, blank=True)      # МойСклад code field (used in XLS exports)
    article = models.CharField(max_length=255, blank=True)
    name = models.CharField(max_length=500)
    folder = models.CharField(max_length=100)
    is_inventoried = models.BooleanField()
    inventory_count = models.IntegerField(default=0)
    last_inventoried_at = models.DateTimeField(null=True, blank=True)
    days_since_last = models.IntegerField(null=True, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=['run', 'is_inventoried']),
            models.Index(fields=['run', 'folder']),
        ]

    def __str__(self):
        status = '✓' if self.is_inventoried else '✗'
        return f"{status} {self.article or self.name}"


class CellsUploadLog(models.Model):
    """Tracks each manually uploaded 'Инвентаризация с ячейками' XLS file."""
    run = models.ForeignKey(InventoryRun, on_delete=models.CASCADE, related_name='cells_uploads')
    inventory_name = models.CharField(max_length=50)   # e.g. "00022"
    inventory_date = models.DateField()
    warehouse = models.CharField(max_length=255, blank=True)
    matched_count = models.IntegerField(default=0)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['inventory_date']

    def __str__(self):
        return f"Cells {self.inventory_name} ({self.inventory_date})"
