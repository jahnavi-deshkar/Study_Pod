import logging

from django.db import transaction
from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver

logger = logging.getLogger(__name__)


def _resource_signature(resource):
    return (
        resource.file.name if resource.file else "",
        resource.student_class_id,
        resource.subject_id,
        resource.teacher_id,
        resource.title,
    )


@receiver(pre_save, sender="academics.Resource")
def remember_resource_changes(sender, instance, **kwargs):
    if not instance.pk:
        instance._ai_needs_indexing = True
        return

    previous = sender.objects.filter(pk=instance.pk).first()
    instance._ai_needs_indexing = (
        previous is None
        or _resource_signature(previous) != _resource_signature(instance)
    )


@receiver(post_save, sender="academics.Resource")
def index_saved_resource(sender, instance, created, **kwargs):
    if not created and not getattr(instance, "_ai_needs_indexing", False):
        return

    resource_id = instance.pk
    transaction.on_commit(lambda: _index_resource(resource_id))


def _index_resource(resource_id):
    from academics.models import Resource
    from ai_suggestions.services.vector_store import StudyPodVectorStore

    try:
        resource = Resource.objects.select_related(
            "student_class",
            "subject",
            "teacher",
        ).get(pk=resource_id)

        if not resource.file:
            return

        metadata = {
            "class_id": resource.student_class_id,
            "subject": resource.subject.name,
            "subject_id": resource.subject_id,
            "teacher_id": resource.teacher_id,
            "title": resource.title,
        }

        indexed_chunks = StudyPodVectorStore().ingest_resource(
            resource_id=resource.pk,
            file_path=resource.file.path,
            metadata=metadata,
        )
        logger.info(
            "Indexed StudyPod resource %s into %s chunks.",
            resource.pk,
            indexed_chunks,
        )
    except Exception:
        logger.exception("Could not index StudyPod resource %s.", resource_id)
