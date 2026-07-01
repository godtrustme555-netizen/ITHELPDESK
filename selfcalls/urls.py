from django.urls import path
from . import views

urlpatterns = [
    path('', views.self_call_dashboard, name='self_call_dashboard'),
    path('create/', views.create_self_call, name='create_self_call'),
    path('<int:pk>/', views.self_call_detail, name='self_call_detail'),
    path('<int:pk>/update/', views.update_self_call, name='update_self_call'),
    path('<int:pk>/attachments/', views.upload_attachment, name='upload_self_call_attachment'),
    path('attachments/<int:pk>/download/', views.download_attachment, name='download_self_call_attachment'),
    path('reports/', views.reports, name='self_call_reports'),
    path('export/', views.export_self_calls, name='export_self_calls'),
]
