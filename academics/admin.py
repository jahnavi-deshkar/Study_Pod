from django.contrib import admin
from .models import Class, DoubtAttachment, DoubtReply, DoubtThread, LeaveApplication, LeaveAttachment, Subject, TeachingAssignment, Timetable, Notice
from .models import Attendance

admin.site.register(Class)
admin.site.register(Subject)
admin.site.register(TeachingAssignment)
admin.site.register(Notice)
admin.site.register(Attendance)
admin.site.register(DoubtThread)
admin.site.register(DoubtAttachment)
admin.site.register(DoubtReply)
admin.site.register(LeaveApplication)
admin.site.register(LeaveAttachment)
admin.site.register(Timetable)

