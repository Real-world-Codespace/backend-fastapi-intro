from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..dependencies import current_user, get_db
from ..models import Task, User, now_utc
from ..schemas import TaskCreate, TaskOut, TaskUpdate
from ..task_service import visible_task, visible_tasks_query

router = APIRouter(prefix="/api", tags=["tasks"])


@router.get("/users")
def users(db: Session = Depends(get_db), _: User = Depends(current_user)):
    return [{"id": user.id, "name": user.name} for user in db.scalars(select(User).order_by(User.name)).all()]


@router.get("/tasks", response_model=list[TaskOut])
def list_tasks(db: Session = Depends(get_db), user: User = Depends(current_user)):
    query = visible_tasks_query(user.id).order_by(Task.created_at.desc(), Task.id.desc())
    return db.scalars(query).all()


@router.post("/tasks", response_model=TaskOut, status_code=201)
def create_task(payload: TaskCreate, db: Session = Depends(get_db), user: User = Depends(current_user)):
    assignee_id = payload.assignee_id or user.id
    if db.get(User, assignee_id) is None:
        raise HTTPException(status_code=422, detail="Người được giao không tồn tại")
    task = Task(
        title=payload.title, description=payload.description,
        priority=payload.priority.value, due_date=payload.due_date,
        created_by_id=user.id, assignee_id=assignee_id,
    )
    db.add(task)
    db.commit()
    db.refresh(task)
    return task


@router.get("/tasks/{task_id}", response_model=TaskOut)
def get_task(task_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    return visible_task(task_id, db, user)


@router.patch("/tasks/{task_id}", response_model=TaskOut)
def update_task(task_id: int, payload: TaskUpdate, db: Session = Depends(get_db), user: User = Depends(current_user)):
    task = visible_task(task_id, db, user)
    changes = payload.model_dump(exclude_unset=True)
    if user.id != task.created_by_id and set(changes) != {"status"}:
        raise HTTPException(status_code=403, detail="Người được giao chỉ được đổi trạng thái")
    for field, value in changes.items():
        if field != "due_date" and value is None:
            raise HTTPException(status_code=422, detail=f"{field} không được để trống")
        if field == "assignee_id" and db.get(User, value) is None:
            raise HTTPException(status_code=422, detail="Người được giao không tồn tại")
        if field in ("status", "priority"):
            value = value.value
        setattr(task, field, value)
    task.updated_at = now_utc()
    db.commit()
    db.refresh(task)
    return task


@router.delete("/tasks/{task_id}", status_code=204)
def delete_task(task_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    task = visible_task(task_id, db, user)
    if task.created_by_id != user.id:
        raise HTTPException(status_code=403, detail="Chỉ người tạo được xóa công việc")
    db.delete(task)
    db.commit()
