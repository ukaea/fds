from sqlmodel import Session, col, select

from app.models.dataset import Dataset
from app.models.shot import Shot
from app.services.coverage import CoverageMatcher


class AnnotationService:
    """Resolve feature annotations for a subject, within its frame.

    An annotation ``Dataset`` (``annotates`` set) localises a feature in a subject's
    frame. Resolution never crosses frames: a dataset resolves only its own
    dataset-frame annotations; a shot resolves its shot-frame annotations plus the
    device-level (shot-ranged) annotations whose coverage includes it. FDS never
    re-frames, so a shot-frame annotation is never surfaced on a dataset read.
    """

    def __init__(self, session: Session) -> None:
        self.session = session

    def for_dataset(self, dataset: Dataset) -> list[Dataset]:
        """Dataset-frame annotations: those whose subject is this dataset."""
        if dataset.id is None:
            return []
        return list(
            self.session.exec(
                select(Dataset).where(Dataset.subject_dataset_id == dataset.id)
            ).all()
        )

    def for_shot(self, shot: Shot) -> list[Dataset]:
        """Shot-frame plus device-frame annotations for ``shot``.

        Shot-frame annotations belong to the shot and have no dataset subject (the
        subject is the shot itself). Device-frame annotations are device-level
        (``shot_id`` null) and included when their ``applies_to`` covers the shot,
        reusing the shared ``CoverageMatcher``. Dataset-frame annotations that merely
        live in the shot are excluded.
        """
        shot_frame = self.session.exec(
            select(Dataset).where(
                Dataset.device_name == shot.device_name,
                Dataset.shot_id == shot.id,
                col(Dataset.annotates).is_not(None),
                col(Dataset.subject_dataset_id).is_(None),
            )
        ).all()

        coverage = CoverageMatcher(self.session)
        device_level = self.session.exec(
            select(Dataset).where(
                Dataset.device_name == shot.device_name,
                col(Dataset.shot_id).is_(None),
                col(Dataset.annotates).is_not(None),
            )
        ).all()
        device_frame = [
            version
            for version in device_level
            if coverage.covers_version(version, shot)
        ]
        return list(shot_frame) + device_frame
