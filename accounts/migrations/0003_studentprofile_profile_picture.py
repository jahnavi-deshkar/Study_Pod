from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0002_parentprofile_studentprofile_teacherprofile"),
    ]

    operations = [
        migrations.AddField(
            model_name="studentprofile",
            name="profile_picture",
            field=models.ImageField(blank=True, upload_to="student_profiles/"),
        ),
    ]
