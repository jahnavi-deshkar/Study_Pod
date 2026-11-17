from django.contrib import admin
from .models import Class, DoubtAttachment, DoubtReply, DoubtThread, LeaveApplication, LeaveAttachment, LeaveRequest, Subject, TeachingAssignment, Timetable, Notice
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


@admin.register(LeaveRequest)
class LeaveRequestAdmin(admin.ModelAdmin):
    list_display = (
        "applicant",
        "role",
        "start_date",
        "end_date",
        "status",
        "created_at",
    )
    list_filter = ("role", "status", "created_at")
    search_fields = (
        "applicant__username",
        "applicant__first_name",
        "applicant__last_name",
    )
    readonly_fields = (
        "applicant",
        "role",
        "reason",
        "start_date",
        "end_date",
        "created_at",
    )
    list_editable = ("status",)

