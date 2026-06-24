from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path


TASKS_DIR = Path("data/tasks/professional_knowledge")


@dataclass
class ProfessionalKnowledgeTask:
    task_id: str
    user_id: int
    subject: str
    chapter_name: str
    filename: str
    material_id: int | None = None
    source_type: str = ""
    process_method: str = ""
    status: str = "pending"
    warning_count: int = 0
    notes: list[str] = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.now().isoformat(timespec="seconds"))
    updated_at: str = field(default_factory=lambda: datetime.now().isoformat(timespec="seconds"))


def _task_path(task_id: str) -> Path:
    return TASKS_DIR / f"{task_id}.json"


def _touch_task(task: ProfessionalKnowledgeTask) -> ProfessionalKnowledgeTask:
    task.updated_at = datetime.now().isoformat(timespec="seconds")
    return task


def save_task(task: ProfessionalKnowledgeTask) -> ProfessionalKnowledgeTask:
    TASKS_DIR.mkdir(parents=True, exist_ok=True)
    task = _touch_task(task)
    _task_path(task.task_id).write_text(
        json.dumps(asdict(task), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return task


def create_task(
    *,
    user_id: int,
    subject: str,
    chapter_name: str,
    filename: str,
    material_id: int | None = None,
) -> ProfessionalKnowledgeTask:
    task = ProfessionalKnowledgeTask(
        task_id=f"pk_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}",
        user_id=user_id,
        subject=subject,
        chapter_name=chapter_name,
        filename=filename,
        material_id=material_id,
    )
    return save_task(task)


def load_task(task_id: str) -> ProfessionalKnowledgeTask | None:
    path = _task_path(task_id)
    if not path.exists():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    return ProfessionalKnowledgeTask(**payload)


def update_task_status(task_id: str, status: str, note: str | None = None, **updates) -> ProfessionalKnowledgeTask | None:
    task = load_task(task_id)
    if not task:
        return None
    task.status = status
    for key, value in updates.items():
        if hasattr(task, key):
            setattr(task, key, value)
    if note:
        task.notes.append(note)
    return save_task(task)


def list_recent_tasks(user_id: int, limit: int = 10) -> list[ProfessionalKnowledgeTask]:
    if not TASKS_DIR.exists():
        return []
    tasks = []
    for path in sorted(TASKS_DIR.glob("pk_*.json"), reverse=True):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        if payload.get("user_id") != user_id:
            continue
        tasks.append(ProfessionalKnowledgeTask(**payload))
        if len(tasks) >= limit:
            break
    return tasks
