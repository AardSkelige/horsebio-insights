# sync/migrations/0014_move_models_to_core.py
# This migration removes models from parser's state (they now live in core)
# Uses SeparateDatabaseAndState: state_operations remove from Django's model registry,
# database_operations are empty (tables remain as parser_*)

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('parser', '0013_synclock'),
        ('core', '0001_initial'),  # core migration claims these models
    ]

    operations = [
        # Use SeparateDatabaseAndState to remove models from parser state without touching DB
        migrations.SeparateDatabaseAndState(
            state_operations=[
                # Remove indexes first (reverse order of creation)
                migrations.RemoveIndex(
                    model_name='purchaseorderitem',
                    name='parser_purc_purchas_1b762a_idx',
                ),
                migrations.RemoveIndex(
                    model_name='purchaseorder',
                    name='parser_purc_status_1d5c59_idx',
                ),
                migrations.RemoveIndex(
                    model_name='purchaseorder',
                    name='parser_purc_created_72dee0_idx',
                ),
                migrations.RemoveIndex(
                    model_name='purchaseorder',
                    name='parser_purc_date_d70cd0_idx',
                ),
                migrations.RemoveIndex(
                    model_name='rawmaterialusage',
                    name='parser_rawm_quantit_a5ce9d_idx',
                ),
                migrations.RemoveIndex(
                    model_name='rawmaterialusage',
                    name='parser_rawm_raw_mat_491235_idx',
                ),
                migrations.RemoveIndex(
                    model_name='rawmaterialusage',
                    name='parser_rawm_shipmen_628013_idx',
                ),
                migrations.RemoveIndex(
                    model_name='rawmaterialusage',
                    name='parser_rawm_raw_mat_4371d8_idx',
                ),
                migrations.RemoveIndex(
                    model_name='rawmaterial',
                    name='parser_rawm_group_2767a3_idx',
                ),
                migrations.RemoveIndex(
                    model_name='shipmentitem',
                    name='parser_ship_product_cff5d6_idx',
                ),
                migrations.RemoveIndex(
                    model_name='shipment',
                    name='parser_ship_date_a99af4_idx',
                ),
                migrations.RemoveIndex(
                    model_name='shipmentitem',
                    name='parser_ship_shipmen_249687_idx',
                ),
                migrations.RemoveIndex(
                    model_name='shipment',
                    name='parser_ship_number_4e3ee6_idx',
                ),
                migrations.RemoveIndex(
                    model_name='shipment',
                    name='parser_ship_date_88a116_idx',
                ),
                migrations.RemoveIndex(
                    model_name='product',
                    name='parser_prod_group_d9292b_idx',
                ),
                migrations.RemoveIndex(
                    model_name='product',
                    name='parser_prod_group_d2736a_idx',
                ),
                # Remove foreign key fields (alter unique_together first where needed)
                migrations.AlterUniqueTogether(
                    name='processingplanmaterial',
                    unique_together=set(),
                ),
                migrations.AlterUniqueTogether(
                    name='processingplanproduct',
                    unique_together=set(),
                ),
                # Delete models (children first, then parents)
                migrations.DeleteModel(
                    name='SupplyItem',
                ),
                migrations.DeleteModel(
                    name='PurchaseOrderItem',
                ),
                migrations.DeleteModel(
                    name='RawMaterialUsage',
                ),
                migrations.DeleteModel(
                    name='ShipmentItem',
                ),
                migrations.DeleteModel(
                    name='ProcessingPlanProduct',
                ),
                migrations.DeleteModel(
                    name='ProcessingPlanMaterial',
                ),
                migrations.DeleteModel(
                    name='PurchaseOrder',
                ),
                migrations.DeleteModel(
                    name='Supply',
                ),
                migrations.DeleteModel(
                    name='Shipment',
                ),
                migrations.DeleteModel(
                    name='ProcessingPlan',
                ),
                migrations.DeleteModel(
                    name='RawMaterial',
                ),
                migrations.DeleteModel(
                    name='Product',
                ),
                migrations.DeleteModel(
                    name='SyncLock',
                ),
                migrations.DeleteModel(
                    name='Counterparty',
                ),
            ],
            database_operations=[],  # No database changes - tables remain
        ),
    ]
