from collections import defaultdict
from collections.abc import Sequence

from sqlmodel import Session, col, select, tuple_

from app.models.dataset import Dataset
from app.models.shot import Shot
from app.services.coverage import CoverageMatcher


class AnnotationService:
    """Resolve annotations for a subject, within its frame.

    An annotation ``Dataset`` (``annotates`` set) localises a property in a subject's
    frame. Resolution never crosses frames: a dataset resolves only its own
    dataset-frame annotations; a shot resolves its shot-frame annotations plus the
    device-level (shot-ranged) annotations whose coverage includes it. FDS never
    re-frames, so a shot-frame annotation is never surfaced on a dataset read.
    """

    def __init__(self, session: Session) -> None:
        self.session = session

    def for_datasets(self, datasets: Sequence[Dataset]) -> list[list[Dataset]]:
        """Dataset-frame annotations for each of ``datasets``, in order: those
        whose subject is that dataset."""
        ids = {dataset.id for dataset in datasets} - {None}
        by_subject: defaultdict[int | None, list[Dataset]] = defaultdict(list)
        if ids:
            statement = select(Dataset).where(col(Dataset.subject_dataset_id).in_(ids))
            for annotation in self.session.exec(statement):
                by_subject[annotation.subject_dataset_id].append(annotation)
        return [by_subject[dataset.id] for dataset in datasets]

    def for_shots(self, shots: Sequence[Shot]) -> list[list[Dataset]]:
        """Shot-frame plus device-frame annotations for each of ``shots``, in order.

        Shot-frame annotations belong to the shot and have no dataset subject (the
        subject is the shot itself). Device-frame annotations are device-level
        (``shot_id`` null) and included when their ``applies_to`` covers the shot,
        reusing the shared ``CoverageMatcher``. Dataset-frame annotations that merely
        live in the shot are excluded. All the shots are resolved together.
        """
        if not shots:
            return []
        shot_frame = self.session.exec(
            select(Dataset).where(
                tuple_(Dataset.device_name, Dataset.shot_id).in_(
                    {(shot.device_name, shot.id) for shot in shots}
                ),
                col(Dataset.annotates).is_not(None),
                col(Dataset.subject_dataset_id).is_(None),
            )
        ).all()
        by_shot: defaultdict[tuple[str | None, str | None], list[Dataset]] = (
            defaultdict(list)
        )
        for annotation in shot_frame:
            by_shot[annotation.device_name, annotation.shot_id].append(annotation)

        device_level = self.session.exec(
            select(Dataset).where(
                col(Dataset.device_name).in_({shot.device_name for shot in shots}),
                col(Dataset.shot_id).is_(None),
                col(Dataset.annotates).is_not(None),
            )
        ).all()
        coverage = CoverageMatcher(self.session)
        coverage.load(device_level)
        return [
            by_shot[shot.device_name, shot.id]
            + [
                version
                for version in device_level
                if version.device_name == shot.device_name
                and coverage.covers_version(version, shot)
            ]
            for shot in shots
        ]
