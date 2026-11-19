from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError


PIPELINE = (
    ("import_dsp_roster", "Stage 1/3: importing academy roster, batches, subjects, and timetable"),
    ("import_dsp_marks", "Stage 2/3: importing assessments, scores, and attendance"),
    ("import_dsp_community", "Stage 3/3: importing notices, resources, and doubt discussions"),
)


class Command(BaseCommand):
    help = "Rebuild the DSP recruiter demo data from the source workbooks."

    def add_arguments(self, parser):
        parser.add_argument("--data-dir", default="raw_data")

    def handle(self, *args, **options):
        data_dir = options["data_dir"]
        for command_name, progress in PIPELINE:
            self.stdout.write(self.style.MIGRATE_HEADING(progress))
            try:
                command_options = {"stdout": self.stdout, "stderr": self.stderr}
                if command_name != "import_dsp_community":
                    command_options["data_dir"] = data_dir
                call_command(command_name, **command_options)
            except CommandError as exc:
                raise CommandError(f"{command_name} failed: {exc}") from exc
        self.stdout.write(self.style.SUCCESS("DSP recruiter demo data is ready."))
