from django.db import migrations, models


def initialize_workflow_status(apps, schema_editor):
    Assessment = apps.get_model("academics", "Assessment")
    Assessment.objects.filter(is_published=True).update(workflow_status="PUBLISHED")
    Assessment.objects.filter(is_published=False).update(workflow_status="DRAFT")


class Migration(migrations.Migration):

    dependencies = [
        ("academics", "0017_leaverequest"),
    ]

    operations = [
        migrations.AddField(
            model_name="assessment",
            name="workflow_status",
            field=models.CharField(
                choices=[
                    ("DRAFT", "Draft"),
                    ("PENDING_ADMIN", "Pending Admin Review"),
                    ("PUBLISHED", "Published"),
                ],
                default="DRAFT",
                max_length=20,
            ),
        ),
        migrations.RunPython(
            initialize_workflow_status,
            migrations.RunPython.noop,
        ),
    ]
