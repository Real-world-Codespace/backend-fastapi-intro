from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from .models import TaskPriority, TaskStatus


class RegisterIn(BaseModel):
    name: str = Field(min_length=2, max_length=100)
    email: EmailStr
    password: str = Field(min_length=10, max_length=128)

    @field_validator("name")
    @classmethod
    def nonempty_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Tên không được để trống")
        return value


class LoginIn(BaseModel):
    email: EmailStr
    password: str


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    email: str


class TaskCreate(BaseModel):
    title: str = Field(min_length=1, max_length=160)
    description: str = Field(default="", max_length=5000)
    priority: TaskPriority = TaskPriority.medium
    due_date: date | None = None
    assignee_id: int | None = None

    @field_validator("title")
    @classmethod
    def nonempty_title(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Tên công việc không được để trống")
        return value


class TaskUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=160)
    description: str | None = Field(default=None, max_length=5000)
    status: TaskStatus | None = None
    priority: TaskPriority | None = None
    due_date: date | None = None
    assignee_id: int | None = None

    @field_validator("title")
    @classmethod
    def nonempty_title(cls, value: str | None) -> str | None:
        if value is None:
            return value
        value = value.strip()
        if not value:
            raise ValueError("Tên công việc không được để trống")
        return value


class TaskOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    description: str
    status: TaskStatus
    priority: TaskPriority
    due_date: date | None
    created_by_id: int
    assignee_id: int
    created_at: datetime
    updated_at: datetime


class ChatIn(BaseModel):
    message: str = Field(min_length=1, max_length=2000)


class ChatOut(BaseModel):
    reply: str


class ChatMessageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    role: str
    content: str
    created_at: datetime
