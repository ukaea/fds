from collections.abc import Sequence
from typing import Any, Generic, Type, TypeVar

from sqlmodel import Session, SQLModel, inspect, select

ModelType = TypeVar("ModelType", bound=SQLModel)
CreateSchemaType = TypeVar("CreateSchemaType", bound=SQLModel)
UpdateSchemaType = TypeVar("UpdateSchemaType", bound=SQLModel)


class BaseService(Generic[ModelType, CreateSchemaType, UpdateSchemaType]):
    def __init__(self, model: Type[ModelType], session: Session):
        """
        Base service for CRUD operations.

        :param model: The SQLModel class
        :param session: The database session
        """
        self.model = model
        self.session = session

    def get(self, id: Any) -> ModelType | None:
        """
        Get a single object by ID.
        """
        return self.session.get(self.model, id)

    def get_multi(self, *, offset: int = 0, limit: int = 100) -> Sequence[ModelType]:
        """
        Get multiple objects with pagination, ordered by primary key.

        Without a deterministic order the database may return rows in any
        order, so paging over an unordered set can repeat or skip rows between
        requests.
        """
        statement = (
            select(self.model)
            .order_by(*inspect(self.model).primary_key)
            .offset(offset)
            .limit(limit)
        )
        result = self.session.exec(statement)
        objects = result.all()
        return objects

    def create_unchecked(self, obj_in: CreateSchemaType) -> ModelType:
        """
        Unchecked persistence helper for creating a new object.

        Bypasses service-layer authorization and business-rule enforcement.
        Call this only from service methods that have already completed the
        required validation and authorization checks.
        """
        db_obj = self.model.model_validate(obj_in)
        self.session.add(db_obj)
        self.session.commit()
        self.session.refresh(db_obj)
        return db_obj

    def update_unchecked(
        self, *, db_obj: ModelType, obj_in: UpdateSchemaType
    ) -> ModelType:
        """
        Unchecked persistence helper for updating an existing object.

        Bypasses service-layer authorization and business-rule enforcement.
        Call this only from service methods that have already completed the
        required validation and authorization checks.
        """
        update_data = obj_in.model_dump(exclude_unset=True)
        db_obj.sqlmodel_update(update_data)
        self.session.add(db_obj)
        self.session.commit()
        self.session.refresh(db_obj)
        return db_obj

    def delete_unchecked(self, id: Any) -> bool:
        """
        Unchecked persistence helper for deleting an object.

        Bypasses service-layer authorization and business-rule enforcement.
        Call this only from service methods that have already completed the
        required validation and authorization checks.
        """
        db_obj = self.session.get(self.model, id)
        if not db_obj:
            return False
        self.session.delete(db_obj)
        self.session.commit()
        return True
