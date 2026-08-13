from collections.abc import Sequence

from fastapi import APIRouter, status

from app.api.deps import (
    ActivityServiceDep,
    CurrentUserDep,
    DatasetServiceDep,
    SourceServiceDep,
)
from app.models.activity import (
    ActivityAgent,
    ActivityAgentRead,
    ActivityCreate,
    ActivityDelegation,
    ActivityDelegationRead,
    ActivityInput,
    ActivityInputRead,
    ActivityInstrument,
    ActivityInstrumentRead,
    ActivityRead,
    ActivityUpdate,
    AgentRole,
)
from app.models.dataset import DatasetRead
from app.models.source import SourceRead

router = APIRouter()


@router.post("/", response_model=ActivityRead, status_code=status.HTTP_201_CREATED)
def create_activity(
    *,
    activity_in: ActivityCreate,
    activity_service: ActivityServiceDep,
    user: CurrentUserDep,
) -> ActivityRead:
    """
    Create a new Activity and declare its provenance in one request —
    the inputs it used, the instruments it used, and any additional agents.
    Each can also be added or removed later via the sub-resources below.
    Requires global admin.
    """
    activity = activity_service.create(activity_in, user)
    return ActivityRead.model_validate(activity)


@router.get("/{activity_id}", response_model=ActivityRead)
def read_activity(
    *,
    activity_id: int,
    activity_service: ActivityServiceDep,
) -> ActivityRead:
    """Retrieve a single Activity by ID."""
    from app.services.exceptions import ResourceNotFoundError

    activity = activity_service.get(activity_id)
    if not activity:
        raise ResourceNotFoundError(f"Activity {activity_id} not found")
    return ActivityRead.model_validate(activity)


@router.put("/{activity_id}", response_model=ActivityRead)
def update_activity(
    *,
    activity_id: int,
    activity_in: ActivityUpdate,
    activity_service: ActivityServiceDep,
    user: CurrentUserDep,
) -> ActivityRead:
    """Update an Activity. Requires global admin."""
    activity = activity_service.update(id=activity_id, obj_in=activity_in, user=user)
    return ActivityRead.model_validate(activity)


@router.delete("/{activity_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_activity(
    *,
    activity_id: int,
    activity_service: ActivityServiceDep,
    user: CurrentUserDep,
) -> None:
    """Delete an Activity. Requires global admin."""
    activity_service.delete(activity_id, user)
    return None


@router.post(
    "/{activity_id}/inputs/{dataset_id}",
    response_model=ActivityInputRead,
    status_code=status.HTTP_201_CREATED,
)
def add_activity_input(
    *,
    activity_id: int,
    dataset_id: int,
    activity_service: ActivityServiceDep,
    user: CurrentUserDep,
) -> ActivityInput:
    """Add an input dataset the Activity used (prov:used). Requires global admin."""
    return activity_service.add_input(
        activity_id=activity_id, dataset_id=dataset_id, user=user
    )


@router.get(
    "/{activity_id}/inputs",
    response_model=list[DatasetRead],
    response_model_exclude_none=True,
)
def list_activity_inputs(
    *,
    activity_id: int,
    activity_service: ActivityServiceDep,
    dataset_service: DatasetServiceDep,
    offset: int = 0,
    limit: int = 100,
) -> list[DatasetRead]:
    """List the datasets an Activity used as inputs."""
    datasets = activity_service.get_inputs(activity_id, offset=offset, limit=limit)
    return dataset_service.to_read_models(list(datasets))


@router.delete(
    "/{activity_id}/inputs/{dataset_id}", status_code=status.HTTP_204_NO_CONTENT
)
def remove_activity_input(
    *,
    activity_id: int,
    dataset_id: int,
    activity_service: ActivityServiceDep,
    user: CurrentUserDep,
) -> None:
    """Unlink an input dataset from an Activity. Requires global admin."""
    activity_service.remove_input(
        activity_id=activity_id, dataset_id=dataset_id, user=user
    )
    return None


@router.post(
    "/{activity_id}/instruments/{source_id}",
    response_model=ActivityInstrumentRead,
    status_code=status.HTTP_201_CREATED,
)
def add_activity_instrument(
    *,
    activity_id: int,
    source_id: int,
    activity_service: ActivityServiceDep,
    user: CurrentUserDep,
) -> ActivityInstrument:
    """Add an instrument (a kind=instrument Source) the Activity used. Requires admin."""
    return activity_service.add_instrument(
        activity_id=activity_id, source_id=source_id, user=user
    )


@router.get("/{activity_id}/instruments", response_model=list[SourceRead])
def list_activity_instruments(
    *,
    activity_id: int,
    activity_service: ActivityServiceDep,
    source_service: SourceServiceDep,
    offset: int = 0,
    limit: int = 100,
) -> list[SourceRead]:
    """List the instruments an Activity used."""
    instruments = activity_service.get_instruments(
        activity_id, offset=offset, limit=limit
    )
    return source_service.to_read_models(list(instruments))


@router.delete(
    "/{activity_id}/instruments/{source_id}", status_code=status.HTTP_204_NO_CONTENT
)
def remove_activity_instrument(
    *,
    activity_id: int,
    source_id: int,
    activity_service: ActivityServiceDep,
    user: CurrentUserDep,
) -> None:
    """Unlink an instrument from an Activity. Requires global admin."""
    activity_service.remove_instrument(
        activity_id=activity_id, source_id=source_id, user=user
    )
    return None


@router.post(
    "/{activity_id}/agents/{source_id}",
    response_model=ActivityAgentRead,
    status_code=status.HTTP_201_CREATED,
)
def add_activity_agent(
    *,
    activity_id: int,
    source_id: int,
    role: AgentRole,
    activity_service: ActivityServiceDep,
    user: CurrentUserDep,
) -> ActivityAgent:
    """Associate an additional agent (with a role) with the Activity. Requires admin."""
    return activity_service.add_agent(
        activity_id=activity_id, source_id=source_id, role=role, user=user
    )


@router.get("/{activity_id}/agents", response_model=list[ActivityAgentRead])
def list_activity_agents(
    *,
    activity_id: int,
    activity_service: ActivityServiceDep,
) -> Sequence[ActivityAgent]:
    """List the additional agent associations (with roles) for an Activity."""
    return activity_service.get_agents(activity_id)


@router.delete(
    "/{activity_id}/agents/{source_id}", status_code=status.HTTP_204_NO_CONTENT
)
def remove_activity_agent(
    *,
    activity_id: int,
    source_id: int,
    activity_service: ActivityServiceDep,
    user: CurrentUserDep,
) -> None:
    """Unlink an additional agent from an Activity. Requires global admin."""
    activity_service.remove_agent(
        activity_id=activity_id, source_id=source_id, user=user
    )
    return None


@router.post(
    "/{activity_id}/delegations/{subordinate_source_id}/{responsible_source_id}",
    response_model=ActivityDelegationRead,
    status_code=status.HTTP_201_CREATED,
)
def add_activity_delegation(
    *,
    activity_id: int,
    subordinate_source_id: int,
    responsible_source_id: int,
    activity_service: ActivityServiceDep,
    user: CurrentUserDep,
) -> ActivityDelegation:
    """Record that one agent acted on behalf of another (prov:actedOnBehalfOf) for
    this Activity. Both must be agents and must differ. Requires global admin."""
    return activity_service.add_delegation(
        activity_id=activity_id,
        subordinate_source_id=subordinate_source_id,
        responsible_source_id=responsible_source_id,
        user=user,
    )


@router.get("/{activity_id}/delegations", response_model=list[ActivityDelegationRead])
def list_activity_delegations(
    *,
    activity_id: int,
    activity_service: ActivityServiceDep,
) -> Sequence[ActivityDelegation]:
    """List the delegation edges (actedOnBehalfOf) for an Activity."""
    return activity_service.get_delegations(activity_id)


@router.delete(
    "/{activity_id}/delegations/{subordinate_source_id}/{responsible_source_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def remove_activity_delegation(
    *,
    activity_id: int,
    subordinate_source_id: int,
    responsible_source_id: int,
    activity_service: ActivityServiceDep,
    user: CurrentUserDep,
) -> None:
    """Remove a delegation edge from an Activity. Requires global admin."""
    activity_service.remove_delegation(
        activity_id=activity_id,
        subordinate_source_id=subordinate_source_id,
        responsible_source_id=responsible_source_id,
        user=user,
    )
    return None
