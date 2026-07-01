from django.urls import path
from . import views

urlpatterns = [
    path('', views.home, name='home'),
    path('create/', views.create_ticket, name='create_ticket'),
    path('ticket/<int:pk>/', views.ticket_detail, name='ticket_detail'),
    path('ticket/<int:pk>/update/', views.update_ticket, name='update_ticket'),
    path('ticket/<int:pk>/attachments/', views.upload_attachment, name='upload_attachment'),
    path('attachments/<int:pk>/download/', views.download_attachment, name='download_attachment'),
    path('reports/', views.reports_dashboard, name='reports_dashboard'),
    path('audit-log/', views.audit_log, name='audit_log'),
]
