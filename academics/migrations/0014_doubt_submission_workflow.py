# Generated for the doubt submission workflow.

import academics.storage
import django.core.validators
import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("academics", "0013_timetable"),
    ]

    operations = [
        migrations.AddField(
            model_name="doubtthread",
            name="category",
            field=models.CharField(
                choices=[
                    ("SYLLABUS_TOPIC", "Syllabus / Topic"),
                    ("ASSIGNMENT_HOMEWORK", "Assignment / Homework"),
                    ("NOTICE_ANNOUNCEMENT", "Notice / Announcement"),
                    ("STUDY_RESOURCE", "Study Resource"),
                ],
                default="SYLLABUS_TOPIC",
                max_length=24,
            ),
        ),
        migrations.AddField(
            model_name="doubtthread",
            name="is_public",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="doubtthread",
            name="document_link",
            field=models.URLField(blank=True),
        ),
        migrations.CreateModel(
            name="DoubtAttachment",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("file", models.FileField(blank=True, storage=academics.storage.PrivateDoubtAttachmentStorage(), upload_to="doubt_attachments/%Y/%m/", validators=[django.core.validators.FileExtensionValidator(["png", "jpg", "jpeg", "pdf"])])),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("thread", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="attachments", to="academics.doubtthread")),
            ],
            options={"ordering": ("created_at", "pk")},
        ),
    ]
