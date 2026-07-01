from django.contrib import admin
from django.urls import path, include

admin.site.site_header = "IT HELPDESK"
admin.site.site_title = "IT HELPDESK"
admin.site.index_title = "Administration"

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', include('tickets.urls')),
    path('accounts/', include('accounts.urls')),
    path('assets/', include('assets.urls')),
    path('self-calls/', include('selfcalls.urls')),
]
