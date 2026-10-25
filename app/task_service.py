from fastapi import HTTPException
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from .models import Task, User


def visible_tasks_query(user_id: int):
    return select(Task).where(or_(Task.created_by_id == user_id, Task.assignee_id == user_id))


def visible_task(task_id: int, db: Session, user: User) -> Task:
    task = db.get(Task, task_id)
    if task is None or user.id not in (task.created_by_id, task.assignee_id):
        raise HTTPException(status_code=404, detail="Không tìm thấy công việc")
    return task
