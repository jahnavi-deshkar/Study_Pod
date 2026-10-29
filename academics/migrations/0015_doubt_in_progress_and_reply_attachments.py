import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("academics", "0014_doubt_submission_workflow"),
    ]

    operations = [
        migrations.AlterField(
            model_name="doubtthread",
            name="status",
            field=models.CharField(
                choices=[
                    ("OPEN", "Open"),
                    ("IN_PROGRESS", "In Progress"),
                    ("RESOLVED", "Resolved"),
                ],
                default="OPEN",
                max_length=11,
            ),
        ),
        migrations.AddField(
            model_name="doubtattachment",
            name="reply",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="attachments",
                to="academics.doubtreply",
            ),
        ),
    ]
