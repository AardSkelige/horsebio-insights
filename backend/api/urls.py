from django.urls import path
from . import views, auth
from .views import products, fbo, production  # импорт через views
from .views.abc_analysis import abc_analysis, abc_product_details, export_abc_analysis  # прямой импорт
from .views.cash_flow import cash_flow_report, cash_flow_export  # импорт модуля отчета ДДС
from .views import scripts_monitor, checks
from .views.inventory_tracking import inventory_current, inventory_refresh, inventory_history, inventory_upload_cells, inventory_cells_log
from .views.deadlines import get_deadlines
from .views.site_orders import site_orders_list, site_order_delete


app_name = 'api'

urlpatterns = [
    # Аутентификация
    path('auth/login/', auth.login_view, name='login'),
    path('auth/logout/', auth.logout_view, name='logout'),
    path('auth/check/', auth.check_auth, name='check_auth'),
    path('auth/activity/', auth.activity_view, name='activity'),
    path('auth/track/', auth.track_page_view, name='track_page_view'),
    path('auth/home/', auth.home_preferences_view, name='home_preferences'),
    path('auth/usage/', auth.usage_view, name='usage'),
    path('auth/admin-analytics/', auth.admin_analytics_view, name='admin_analytics'),
    path('auth/pages-access/', auth.pages_access_view, name='pages_access'),
    path('auth/sessions/', auth.sessions_view, name='sessions'),
    path('auth/sessions/<int:session_id>/revoke/', auth.session_revoke_view, name='session_revoke'),
    
    # Отгрузки
    path('shipments/', views.shipment_data, name='shipments'),
    path('stats/', views.get_stats, name='stats'),
    path('latest/', views.get_latest_data, name='latest_data'),
    
    # ABC анализ
    path('analysis/abc/', views.abc_analysis, name='abc_analysis'),
    path('analysis/abc/products/<int:product_id>/', views.abc_product_details, name='abc_product_details'),
    path('analysis/abc/export/', export_abc_analysis, name='export_abc_analysis'),
    
    # Сезонный анализ
    path('analysis/seasonal/', views.seasonal_analysis, name='seasonal_analysis'),
    path('analysis/seasonal/products/<int:product_id>/', views.seasonal_product_details, name='seasonal_product_details'),
    
    # Материалы
    path('materials/', views.material_data, name='materials'),
    path('materials/<int:material_id>/', views.material_details, name='material_details'),
    
    # Поставки
    path('supplies/', views.supply_analytics, name='supplies'),
    path('supplies/materials/', views.supply_materials, name='supply_materials'),
    path('supplies/materials/list/', views.supply_materials_list, name='supply_materials_list'),
    path('supplies/materials/<int:material_id>/details/', views.supply_material_details, name='supply_material_details'),
    path('supplies/suppliers/', views.supply_suppliers_list, name='supply_suppliers_list'),
    path('supplies/suppliers/<int:supplier_id>/details/', views.supply_supplier_details, name='supply_supplier_details'),
    
    # Контрагенты
    path('counterparties/', views.counterparty_data, name='counterparty_data'),
    path('counterparties/<int:counterparty_id>/', views.counterparty_details, name='counterparty_details'),
    path('counterparty-groups/', views.counterparty_groups_analysis, name='counterparty-groups'),
    path('counterparty-groups/<str:category>/', views.counterparty_group_details, name='counterparty-group-details'),
    
    # Товары
    path('products/', views.product_data, name='product_data'),
    path('products/<int:product_id>/', views.product_details, name='product_details'),
    path('products/export/', products.export_products_excel, name='export_products_excel'),  # используем products.

    
    # Анализ закупок
    path('analysis/purchase/', views.purchase_analysis_overview, name='purchase_analysis_overview'),
    path('analysis/purchase/material/<int:material_id>/', views.material_purchase_analysis, name='material_purchase_analysis'),
    path('analysis/purchase/related/<int:material_id>/', views.related_materials_analysis, name='related_materials_analysis'),
    path('analysis/purchase/optimize/<int:material_id>/', views.optimize_purchase_points, name='optimize_purchase_points'),
    path('materials/<int:material_id>/period/', views.update_material_period, name='update_material_period'),

    path('analysis/fbo/', fbo.get_fbo_analysis, name='fbo_analysis'),
    path('analysis/fbo/export/', fbo.export_fbo_excel, name='fbo_export'),

    # Отчет движения денежных средств
    path('analysis/cash-flow/', cash_flow_report, name='cash_flow_report'),
    path('analysis/cash-flow/export/', cash_flow_export, name='cash_flow_export'),

    # Мониторинг скриптов
    path('scripts/', scripts_monitor.scripts_list, name='scripts_list'),
    path('scripts/<str:script_id>/runs/', scripts_monitor.script_runs, name='script_runs'),
    path('scripts/<str:script_id>/runs/<str:run_id>/log/', scripts_monitor.script_log, name='script_log'),
    path('scripts/<str:script_id>/run/', scripts_monitor.script_run_now, name='script_run_now'),
    path('scripts/<str:script_id>/stop/', scripts_monitor.script_stop, name='script_stop'),
    path('scripts/<str:script_id>/runs/<str:run_id>/delete/', scripts_monitor.script_run_delete, name='script_run_delete'),

    # Дашборд проверок /checks
    path('checks/scripts/', checks.checks_overview, name='checks_overview'),
    path('checks/scripts/<str:script_id>/runs/', checks.checks_runs, name='checks_runs'),
    path('checks/scripts/<str:script_id>/runs/<str:run_id>/', checks.checks_run_delete, name='checks_run_delete'),
    path('checks/scripts/<str:script_id>/results/', checks.checks_results, name='checks_results'),
    path('checks/scripts/<str:script_id>/log/', checks.checks_log, name='checks_log'),
    path('checks/scripts/<str:script_id>/run/', checks.checks_run, name='checks_run'),
    path('checks/scripts/<str:script_id>/stop/', checks.checks_stop, name='checks_stop'),
    path('checks/exceptions/', checks.checks_exceptions, name='checks_exceptions'),
    path('checks/exceptions/<int:exc_id>/', checks.checks_exception_detail, name='checks_exception_detail'),

    # Мониторинг инвентаризации
    path('inventory/current/', inventory_current, name='inventory_current'),
    path('inventory/refresh/', inventory_refresh, name='inventory_refresh'),
    path('inventory/history/', inventory_history, name='inventory_history'),
    path('inventory/upload-cells/', inventory_upload_cells, name='inventory_upload_cells'),
    path('inventory/cells-log/', inventory_cells_log, name='inventory_cells_log'),

    # Мониторинг сроков оплаты
    path('deadlines/', get_deadlines, name='deadlines'),

    # Заказы сайта (horse-bio.ru) и их путь в МойСклад
    path('site-orders/', site_orders_list, name='site_orders_list'),
    path('site-orders/<str:order_id>/', site_order_delete, name='site_order_delete'),

    # Расчёт компонентов производства
    path('production/calculate/', production.calculate_components_excel, name='calculate_components_excel'),
    path('production/calculate-json/', production.calculate_components_json, name='calculate_components_json'),
    path('production/calculate-single/', production.calculate_single_product, name='calculate_single_product'),
    path('production/export/', production.export_components_excel, name='export_components_excel'),
    path('production/products/search/', production.search_products_with_recipes, name='search_products_with_recipes'),

]
