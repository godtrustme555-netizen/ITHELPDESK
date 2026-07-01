from django.contrib import admin
from .models import Comment, Ticket, TicketActivity, TicketAttachment

admin.site.register(Ticket)
admin.site.register(Comment)
admin.site.register(TicketAttachment)
admin.site.register(TicketActivity)
