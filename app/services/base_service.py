from collections.abc import Sequence
from typing import Any, Generic, Type, TypeVar

from sqlmodel import Session, SQLModel, select

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
        Get multiple objects with pagination.
        """
        statement = select(self.model).offset(offset).limit(limit)
        result = self.session.exec(statement)
        objects = result.all()
        return objects

    def create(self, obj_in: CreateSchemaType) -> ModelType:
        """
        Create a new object.
        """
        db_obj = self.model.model_validate(obj_in)
        self.session.add(db_obj)
        self.session.commit()
        self.session.refresh(db_obj)
        return db_obj

    def update(self, *, db_obj: ModelType, obj_in: UpdateSchemaType) -> ModelType:
        """
        Update an existing object.
        """
        update_data = obj_in.model_dump(exclude_unset=True)
        db_obj.sqlmodel_update(update_data)
        self.session.add(db_obj)
        self.session.commit()
        self.session.refresh(db_obj)
        return db_obj

    def delete(self, id: Any) -> bool:
        """
        Delete an existing object.
        """
        db_obj = self.session.get(self.model, id)
        if not db_obj:
            return False
        self.session.delete(db_obj)
        self.session.commit()
        return True
