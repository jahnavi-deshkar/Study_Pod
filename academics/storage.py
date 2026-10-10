from django.conf import settings
from django.core.files.storage import FileSystemStorage
from django.utils.deconstruct import deconstructible


@deconstructible
class PrivateDoubtAttachmentStorage(FileSystemStorage):
    """Keep doubt uploads outside the publicly served MEDIA_ROOT."""

    def __init__(self):
        super().__init__(location=settings.BASE_DIR / "private_doubt_uploads")
