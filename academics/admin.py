from django.contrib import admin
from .models import Class, DoubtReply, DoubtThread, Subject, TeachingAssignment, Notice
from .models import Attendance

admin.site.register(Class)
admin.site.register(Subject)
admin.site.register(TeachingAssignment)
admin.site.register(Notice)
admin.site.register(Attendance)
admin.site.register(DoubtThread)
admin.site.register(DoubtReply)

