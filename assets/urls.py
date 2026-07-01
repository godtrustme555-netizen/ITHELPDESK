from django.urls import path
from . import views

urlpatterns = [
    path('', views.assets_dashboard, name='assets_dashboard'),
    path('my-assets/', views.my_assets, name='my_assets'),
    path('import/', views.import_assets_csv, name='import_assets_csv'),
    path('export/', views.export_assets_csv, name='export_assets_csv'),
    path('add/', views.add_asset, name='add_asset'),
    path('<int:pk>/', views.asset_detail, name='asset_detail'),
    path('<int:pk>/edit/', views.edit_asset, name='edit_asset'),
    path('<int:pk>/delete/', views.delete_asset, name='delete_asset'),
    path('<int:pk>/assign/', views.assign_asset, name='assign_asset'),
    path('<int:pk>/return/', views.return_asset, name='return_asset'),
    path('<int:pk>/history/', views.asset_history, name='asset_history'),
    path('<int:pk>/status/<str:status>/', views.change_asset_status, name='change_asset_status'),
]
