from collections import defaultdict
from collections.abc import Sequence

from sqlmodel import Session, col, select, tuple_

from fds.models.dataset import Dataset, DatasetReplacement
from fds.models.identity import AuthenticatedUser
from fds.models.shot import Shot
from fds.services.coverage import CoverageMatcher
from fds.services.replacements import not_replaced


class AnnotationService:
    """Find the annotations to include when a dataset or a shot is read.

    An annotation is a Dataset with ``annotates`` set, marking where something
    happens, such as ELM times. It is attached to one of three things:

    - a dataset, named in ``subject_dataset``, such as a mask over one camera
      signal;
    - a shot, such as the ELM times for that shot;
    - a device, with ``applies_to`` naming the shots it covers.

    A dataset read includes the annotations attached to that dataset. A shot
    read includes those attached to the shot and the device annotations that
    cover it, but not those attached to the shot's datasets.

    An annotation is left out when the reader may read one that replaces it, so
    a correction is not shown beside the annotation it corrects.
    """

    def __init__(self, session: Session) -> None:
        self.session = session

    def for_datasets(
        self, datasets: Sequence[Dataset], *, user: AuthenticatedUser
    ) -> list[list[Dataset]]:
        """The annotations attached to each of ``datasets``, in the same order."""
        ids = {dataset.id for dataset in datasets} - {None}
        by_subject: defaultdict[int | None, list[Dataset]] = defaultdict(list)
        if ids:
            statement = select(Dataset).where(
                col(Dataset.subject_dataset).in_(ids),
                not_replaced(self.session, Dataset, DatasetReplacement, user),
            )
            for annotation in self.session.exec(statement):
                by_subject[annotation.subject_dataset].append(annotation)
        return [by_subject[dataset.id] for dataset in datasets]

    def for_shots(
        self, shots: Sequence[Shot], *, user: AuthenticatedUser
    ) -> list[list[Dataset]]:
        """For each of ``shots``, in the same order, the annotations attached to
        it and the device annotations whose ``applies_to`` covers it. All the
        shots are looked up together.
        """
        if not shots:
            return []
        shot_frame = self.session.exec(
            select(Dataset).where(
                tuple_(Dataset.device_name, Dataset.shot_id).in_(
                    {(shot.device_name, shot.id) for shot in shots}
                ),
                col(Dataset.annotates).is_not(None),
                col(Dataset.subject_dataset).is_(None),
                not_replaced(self.session, Dataset, DatasetReplacement, user),
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
                not_replaced(self.session, Dataset, DatasetReplacement, user),
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
