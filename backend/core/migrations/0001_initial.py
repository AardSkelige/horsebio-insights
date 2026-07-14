# This migration transfers model ownership from parser to core
# Uses SeparateDatabaseAndState: state_operations update Django's model registry,
# database_operations are empty (tables already exist as parser_*)

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    initial = True

    # Depend on parser's final migration to ensure tables exist
    dependencies = [
        ('parser', '0013_synclock'),
    ]

    operations = [
        # Use SeparateDatabaseAndState to register models in core without touching DB
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.CreateModel(
                    name='Counterparty',
                    fields=[
                        ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                        ('name', models.CharField(max_length=255, verbose_name='Наименование контрагента (покупателя)')),
                        ('external_id', models.CharField(max_length=255, unique=True, verbose_name='Внешний ID')),
                        ('is_legacy', models.BooleanField(default=False, help_text='Отметьте, если это старая версия существующего контрагента', verbose_name='Старый контрагент')),
                        ('main_counterparty', models.ForeignKey(blank=True, help_text='Укажите основную версию контрагента, если это старая версия', null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='legacy_records', to='core.counterparty', verbose_name='Основной контрагент')),
                    ],
                    options={
                        'verbose_name': 'Контрагент (покупатель)',
                        'verbose_name_plural': 'Контрагенты (покупатели)',
                        'db_table': 'parser_counterparty',
                    },
                ),
                migrations.CreateModel(
                    name='Product',
                    fields=[
                        ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                        ('name', models.CharField(max_length=255, verbose_name='Наименование')),
                        ('external_id', models.CharField(max_length=255, unique=True, verbose_name='Внешний ID')),
                        ('uom_name', models.CharField(blank=True, max_length=50, null=True, verbose_name='Единица измерения')),
                        ('uom_description', models.CharField(blank=True, max_length=255, null=True, verbose_name='Описание единицы измерения')),
                        ('group', models.CharField(blank=True, choices=[('Тара', 'Тара'), ('Пробники', 'Пробники'), ('Материалы для производства', 'Материалы для производства'), ('Товары', 'Товары'), ('Этикетки', 'Этикетки')], max_length=50, null=True, verbose_name='Группа')),
                        ('subgroup', models.CharField(blank=True, max_length=255, null=True, verbose_name='Подгруппа')),
                        ('article', models.CharField(blank=True, max_length=255, null=True, verbose_name='Артикул')),
                        ('code', models.CharField(blank=True, max_length=255, null=True, verbose_name='Код')),
                        ('description', models.TextField(blank=True, null=True, verbose_name='Описание')),
                    ],
                    options={
                        'verbose_name': 'Товар',
                        'verbose_name_plural': 'Товары',
                        'db_table': 'parser_product',
                        'ordering': ['group', 'subgroup', 'name'],
                    },
                ),
                migrations.CreateModel(
                    name='RawMaterial',
                    fields=[
                        ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                        ('name', models.CharField(max_length=255, verbose_name='Наименование')),
                        ('external_id', models.CharField(max_length=255, unique=True, verbose_name='Внешний ID')),
                        ('uom_name', models.CharField(blank=True, max_length=50, null=True, verbose_name='Единица измерения')),
                        ('uom_description', models.CharField(blank=True, max_length=255, null=True, verbose_name='Описание единицы измерения')),
                        ('group', models.CharField(blank=True, choices=[('Тара', 'Тара'), ('Пробники', 'Пробники'), ('Материалы для производства', 'Материалы для производства'), ('Товары', 'Товары'), ('Этикетки', 'Этикетки')], max_length=50, null=True, verbose_name='Группа')),
                        ('article', models.CharField(blank=True, max_length=255, null=True, verbose_name='Артикул')),
                        ('code', models.CharField(blank=True, max_length=255, null=True, verbose_name='Код')),
                        ('description', models.TextField(blank=True, null=True, verbose_name='Описание')),
                    ],
                    options={
                        'verbose_name': 'Материал для производства',
                        'verbose_name_plural': 'Материалы для производства',
                        'db_table': 'parser_rawmaterial',
                    },
                ),
                migrations.CreateModel(
                    name='ProcessingPlan',
                    fields=[
                        ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                        ('external_id', models.CharField(max_length=255, unique=True, verbose_name='Внешний ID')),
                        ('name', models.CharField(max_length=255, verbose_name='Наименование')),
                        ('created', models.DateTimeField(auto_now_add=True, verbose_name='Создано')),
                        ('updated', models.DateTimeField(auto_now=True, verbose_name='Обновлено')),
                        ('moysklad_updated', models.DateTimeField(blank=True, null=True, verbose_name='Обновлено в МойСклад')),
                    ],
                    options={
                        'verbose_name': 'Техкарта',
                        'verbose_name_plural': 'Техкарты',
                        'db_table': 'parser_processingplan',
                    },
                ),
                migrations.CreateModel(
                    name='Supply',
                    fields=[
                        ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                        ('external_id', models.CharField(max_length=255, unique=True, verbose_name='Внешний ID')),
                        ('number', models.CharField(blank=True, max_length=255, null=True, verbose_name='Номер')),
                        ('date', models.DateTimeField(verbose_name='Дата')),
                        ('sum', models.DecimalField(decimal_places=2, max_digits=15, verbose_name='Сумма')),
                        ('moysklad_updated', models.DateTimeField(blank=True, null=True, verbose_name='Обновлено в МойСклад')),
                        ('counterparty', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='core.counterparty', verbose_name='Поставщик')),
                    ],
                    options={
                        'verbose_name': 'Приемка',
                        'verbose_name_plural': 'Приемки',
                        'db_table': 'parser_supply',
                        'ordering': ['-date'],
                    },
                ),
                migrations.CreateModel(
                    name='Shipment',
                    fields=[
                        ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                        ('external_id', models.CharField(max_length=255, unique=True, verbose_name='Внешний ID')),
                        ('number', models.CharField(blank=True, max_length=255, null=True, verbose_name='Номер отгрузки')),
                        ('date', models.DateTimeField(verbose_name='Дата')),
                        ('moysklad_updated', models.DateTimeField(blank=True, null=True, verbose_name='Обновлено в МойСклад')),
                        ('counterparty', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='core.counterparty', verbose_name='Контрагент (покупатель)')),
                    ],
                    options={
                        'verbose_name': 'Отгрузка',
                        'verbose_name_plural': 'Отгрузки',
                        'db_table': 'parser_shipment',
                    },
                ),
                migrations.CreateModel(
                    name='SyncLock',
                    fields=[
                        ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                        ('lock_type', models.CharField(choices=[('moysklad_sync', 'Синхронизация МойСклад')], max_length=50, unique=True, verbose_name='Тип блокировки')),
                        ('is_locked', models.BooleanField(default=False, verbose_name='Заблокировано')),
                        ('locked_at', models.DateTimeField(blank=True, null=True, verbose_name='Время блокировки')),
                        ('locked_by', models.CharField(blank=True, max_length=255, null=True, verbose_name='Источник блокировки')),
                    ],
                    options={
                        'verbose_name': 'Блокировка синхронизации',
                        'verbose_name_plural': 'Блокировки синхронизации',
                        'db_table': 'parser_synclock',
                    },
                ),
                migrations.CreateModel(
                    name='ShipmentItem',
                    fields=[
                        ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                        ('quantity', models.DecimalField(decimal_places=2, max_digits=10, verbose_name='Количество')),
                        ('price', models.DecimalField(decimal_places=2, default=0, max_digits=10, verbose_name='Цена')),
                        ('product', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='core.product', verbose_name='Продукт')),
                        ('shipment', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='items', to='core.shipment', verbose_name='Отгрузка')),
                    ],
                    options={
                        'verbose_name': 'Позиция отгрузки',
                        'verbose_name_plural': 'Позиции отгрузки',
                        'db_table': 'parser_shipmentitem',
                    },
                ),
                migrations.CreateModel(
                    name='RawMaterialUsage',
                    fields=[
                        ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                        ('quantity', models.DecimalField(decimal_places=2, max_digits=10, verbose_name='Количество')),
                        ('raw_material', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='core.rawmaterial', verbose_name='Сырьё')),
                        ('shipment_item', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='raw_material_usages', to='core.shipmentitem', verbose_name='Позиция отгрузки')),
                    ],
                    options={
                        'verbose_name': 'Использование материала для производства',
                        'verbose_name_plural': 'Использование материалов для производства',
                        'db_table': 'parser_rawmaterialusage',
                    },
                ),
                migrations.CreateModel(
                    name='PurchaseOrder',
                    fields=[
                        ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                        ('external_id', models.CharField(max_length=255, unique=True, verbose_name='Внешний ID')),
                        ('number', models.CharField(blank=True, max_length=255, null=True, verbose_name='Номер заказа')),
                        ('date', models.DateTimeField(verbose_name='Дата')),
                        ('created', models.DateTimeField(verbose_name='Дата создания')),
                        ('status', models.CharField(blank=True, max_length=50, null=True, verbose_name='Статус')),
                        ('sum', models.DecimalField(decimal_places=2, max_digits=15, verbose_name='Сумма')),
                        ('moysklad_updated', models.DateTimeField(blank=True, null=True, verbose_name='Обновлено в МойСклад')),
                        ('counterparty', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='core.counterparty', verbose_name='Поставщик')),
                        ('supplies', models.ManyToManyField(blank=True, related_name='purchase_orders', to='core.supply', verbose_name='Связанные приемки')),
                    ],
                    options={
                        'verbose_name': 'Заказ поставщику',
                        'verbose_name_plural': 'Заказы поставщикам',
                        'db_table': 'parser_purchaseorder',
                        'ordering': ['-date'],
                    },
                ),
                migrations.CreateModel(
                    name='ProcessingPlanProduct',
                    fields=[
                        ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                        ('quantity', models.DecimalField(decimal_places=3, max_digits=10, verbose_name='Количество')),
                        ('processing_plan', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='products', to='core.processingplan', verbose_name='Техкарта')),
                        ('product', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='core.product', verbose_name='Продукт')),
                    ],
                    options={
                        'verbose_name': 'Продукт техкарты',
                        'verbose_name_plural': 'Продукты техкарты',
                        'db_table': 'parser_processingplanproduct',
                        'unique_together': {('processing_plan', 'product')},
                    },
                ),
                migrations.CreateModel(
                    name='ProcessingPlanMaterial',
                    fields=[
                        ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                        ('quantity', models.DecimalField(decimal_places=3, max_digits=10, verbose_name='Количество')),
                        ('material', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='core.rawmaterial', verbose_name='Материал')),
                        ('processing_plan', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='materials', to='core.processingplan', verbose_name='Техкарта')),
                    ],
                    options={
                        'verbose_name': 'Материал техкарты',
                        'verbose_name_plural': 'Материалы техкарты',
                        'db_table': 'parser_processingplanmaterial',
                        'unique_together': {('processing_plan', 'material')},
                    },
                ),
                migrations.CreateModel(
                    name='SupplyItem',
                    fields=[
                        ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                        ('quantity', models.DecimalField(decimal_places=3, max_digits=10, verbose_name='Количество')),
                        ('price', models.DecimalField(decimal_places=2, max_digits=15, verbose_name='Цена')),
                        ('total', models.DecimalField(decimal_places=2, max_digits=15, verbose_name='Сумма')),
                        ('raw_material', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='core.rawmaterial', verbose_name='Материал')),
                        ('supply', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='items', to='core.supply', verbose_name='Приемка')),
                    ],
                    options={
                        'verbose_name': 'Позиция приемки',
                        'verbose_name_plural': 'Позиции приемки',
                        'db_table': 'parser_supplyitem',
                    },
                ),
                migrations.CreateModel(
                    name='PurchaseOrderItem',
                    fields=[
                        ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                        ('quantity', models.DecimalField(decimal_places=3, max_digits=10, verbose_name='Количество')),
                        ('price', models.DecimalField(decimal_places=2, max_digits=15, verbose_name='Цена')),
                        ('total', models.DecimalField(decimal_places=2, max_digits=15, verbose_name='Сумма')),
                        ('shipped_quantity', models.DecimalField(decimal_places=3, default=0, max_digits=10, verbose_name='Принято')),
                        ('waiting_quantity', models.DecimalField(decimal_places=3, default=0, max_digits=10, verbose_name='В ожидании')),
                        ('purchase_order', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='items', to='core.purchaseorder', verbose_name='Заказ поставщику')),
                        ('raw_material', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='core.rawmaterial', verbose_name='Материал')),
                    ],
                    options={
                        'verbose_name': 'Позиция заказа поставщику',
                        'verbose_name_plural': 'Позиции заказа поставщику',
                        'db_table': 'parser_purchaseorderitem',
                    },
                ),
                # Add indexes (state only, tables already have them)
                migrations.AddIndex(
                    model_name='product',
                    index=models.Index(fields=['group'], name='parser_prod_group_d2736a_idx'),
                ),
                migrations.AddIndex(
                    model_name='product',
                    index=models.Index(fields=['group', 'subgroup'], name='parser_prod_group_d9292b_idx'),
                ),
                migrations.AddIndex(
                    model_name='rawmaterial',
                    index=models.Index(fields=['group'], name='parser_rawm_group_2767a3_idx'),
                ),
                migrations.AddIndex(
                    model_name='shipment',
                    index=models.Index(fields=['date'], name='parser_ship_date_88a116_idx'),
                ),
                migrations.AddIndex(
                    model_name='shipment',
                    index=models.Index(fields=['number'], name='parser_ship_number_4e3ee6_idx'),
                ),
                migrations.AddIndex(
                    model_name='shipment',
                    index=models.Index(fields=['date', 'counterparty'], name='parser_ship_date_a99af4_idx'),
                ),
                migrations.AddIndex(
                    model_name='shipmentitem',
                    index=models.Index(fields=['shipment', 'product'], name='parser_ship_shipmen_249687_idx'),
                ),
                migrations.AddIndex(
                    model_name='shipmentitem',
                    index=models.Index(fields=['product'], name='parser_ship_product_cff5d6_idx'),
                ),
                migrations.AddIndex(
                    model_name='rawmaterialusage',
                    index=models.Index(fields=['raw_material', 'shipment_item'], name='parser_rawm_raw_mat_4371d8_idx'),
                ),
                migrations.AddIndex(
                    model_name='rawmaterialusage',
                    index=models.Index(fields=['shipment_item'], name='parser_rawm_shipmen_628013_idx'),
                ),
                migrations.AddIndex(
                    model_name='rawmaterialusage',
                    index=models.Index(fields=['raw_material'], name='parser_rawm_raw_mat_491235_idx'),
                ),
                migrations.AddIndex(
                    model_name='rawmaterialusage',
                    index=models.Index(fields=['quantity'], name='parser_rawm_quantit_a5ce9d_idx'),
                ),
                migrations.AddIndex(
                    model_name='purchaseorder',
                    index=models.Index(fields=['date'], name='parser_purc_date_d70cd0_idx'),
                ),
                migrations.AddIndex(
                    model_name='purchaseorder',
                    index=models.Index(fields=['created'], name='parser_purc_created_72dee0_idx'),
                ),
                migrations.AddIndex(
                    model_name='purchaseorder',
                    index=models.Index(fields=['status'], name='parser_purc_status_1d5c59_idx'),
                ),
                migrations.AddIndex(
                    model_name='purchaseorderitem',
                    index=models.Index(fields=['purchase_order', 'raw_material'], name='parser_purc_purchas_1b762a_idx'),
                ),
            ],
            database_operations=[],  # No database changes - tables already exist
        ),
    ]
