from __future__ import annotations

import json
from datetime import datetime

from repositories.sqlite_utils import connect


def save_plan(
    db_path: str,
    user_id: int,
    plan_name: str,
    target_exam_date: str,
    math_type: str,
    daily_hours: float,
    weight_config: dict,
    phase: str,
) -> int:
    now_str = datetime.now().strftime("%Y-%m-%d")
    with connect(db_path, row_factory=None) as conn:
        cursor = conn.cursor()
        cursor.execute(
            """INSERT INTO study_plans (
                user_id, plan_name, target_exam_date, math_type, daily_hours,
                subjects_config, current_phase, status, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, 'active', ?, ?)""",
            (
                user_id,
                plan_name,
                target_exam_date,
                math_type,
                daily_hours,
                json.dumps(weight_config, ensure_ascii=False),
                phase,
                now_str,
                now_str,
            ),
        )
        plan_id = cursor.lastrowid
        conn.commit()
    return plan_id


def save_task(
    db_path: str,
    user_id: int,
    plan_id: int,
    task_type: str,
    subject: str,
    task_name: str,
    description: str,
    target_date: str,
    estimated_hours: float,
    priority: int = 3,
) -> None:
    now_str = datetime.now().strftime("%Y-%m-%d")
    with connect(db_path, row_factory=None) as conn:
        conn.execute(
            """INSERT INTO plan_tasks (
                plan_id, user_id, task_type, subject, task_name, description,
                target_date, estimated_hours, priority, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                plan_id,
                user_id,
                task_type,
                subject,
                task_name,
                description,
                target_date,
                estimated_hours,
                priority,
                now_str,
            ),
        )
        conn.commit()


def get_user_tasks(db_path: str, user_id: int) -> list[dict]:
    with connect(db_path) as conn:
        rows = conn.execute(
            """SELECT id, subject, task_name, description, target_date, estimated_hours, status
               FROM plan_tasks WHERE user_id=? ORDER BY target_date""",
            (user_id,),
        ).fetchall()
    return [dict(row) for row in rows]


def update_task_status(db_path: str, task_id: int, new_status: str) -> None:
    completed_at = datetime.now().strftime("%Y-%m-%d") if new_status == "completed" else None
    with connect(db_path, row_factory=None) as conn:
        conn.execute(
            "UPDATE plan_tasks SET status=?, completed_at=? WHERE id=?",
            (new_status, completed_at, task_id),
        )
        conn.commit()


def calculate_progress(db_path: str, user_id: int) -> dict:
    with connect(db_path, row_factory=None) as conn:
        row = conn.execute(
            """SELECT COUNT(*) total,
                      COALESCE(SUM(CASE WHEN status='completed' THEN 1 ELSE 0 END), 0) completed
               FROM plan_tasks WHERE user_id=?""",
            (user_id,),
        ).fetchone()
        total_tasks = row[0] if row else 0
        completed_tasks = row[1] if row else 0

        rows = conn.execute(
            """SELECT subject, COUNT(*) total,
                      COALESCE(SUM(CASE WHEN status='completed' THEN 1 ELSE 0 END), 0) completed
               FROM plan_tasks WHERE user_id=?
               GROUP BY subject""",
            (user_id,),
        ).fetchall()
        subjects = {}
        for subject, total, completed in rows:
            rate = round(completed / max(total, 1) * 100, 1)
            subjects[subject] = {"total": total, "completed": completed, "completion_rate": rate}

        recent = conn.execute(
            """SELECT planned_hours, actual_hours
               FROM plan_progress WHERE user_id=?
               ORDER BY record_date DESC LIMIT 7""",
            (user_id,),
        ).fetchall()

    deviation = 0.0
    if recent:
        total_plan = sum(row[0] for row in recent)
        total_actual = sum(row[1] for row in recent)
        if total_plan > 0:
            deviation = round((total_plan - total_actual) / total_plan * 100, 1)

    completion_rate = round(completed_tasks / max(total_tasks, 1) * 100, 1)
    return {
        "total_tasks": total_tasks,
        "completed_tasks": completed_tasks,
        "completion_rate": completion_rate,
        "deviation": deviation,
        "subjects": subjects,
    }


def calc_tasks_progress(tasks) -> float:
    if not tasks:
        return 0
    done_count = sum(1 for task in tasks if task.get("done"))
    return round(done_count / len(tasks) * 100, 1)


def save_checkin_plan(db_path: str, user_id: int, plan_name: str, target_date: str, tasks) -> None:
    if isinstance(tasks, list):
        progress = calc_tasks_progress(tasks)
        payload = json.dumps(tasks, ensure_ascii=False)
    else:
        progress = 0
        payload = str(tasks)

    with connect(db_path, row_factory=None) as conn:
        conn.execute(
            """INSERT INTO checkin_plans (user_id, plan_name, target_date, tasks, progress, status)
               VALUES (?, ?, ?, ?, ?, 'active')""",
            (user_id, plan_name, target_date, payload, progress),
        )
        conn.commit()


def get_checkin_plans(db_path: str, user_id: int) -> list[dict]:
    with connect(db_path) as conn:
        rows = conn.execute(
            """SELECT * FROM checkin_plans
               WHERE user_id=? AND status='active'
               ORDER BY target_date ASC, id DESC""",
            (user_id,),
        ).fetchall()
    return [dict(row) for row in rows]


def update_plan_tasks(db_path: str, user_id: int, plan_id: int, tasks: list[dict]) -> None:
    progress = calc_tasks_progress(tasks)
    status = "completed" if tasks and progress >= 100 else "active"
    with connect(db_path, row_factory=None) as conn:
        conn.execute(
            """UPDATE checkin_plans SET tasks=?, progress=?, status=?
               WHERE id=? AND user_id=?""",
            (json.dumps(tasks, ensure_ascii=False), progress, status, plan_id, user_id),
        )
        conn.commit()


def delete_plan(db_path: str, user_id: int, plan_id: int) -> None:
    with connect(db_path, row_factory=None) as conn:
        conn.execute(
            "UPDATE checkin_plans SET status='abandoned' WHERE id=? AND user_id=?",
            (plan_id, user_id),
        )
        conn.commit()


def get_checkin_plan_progress(db_path: str, user_id: int) -> float:
    with connect(db_path, row_factory=None) as conn:
        rows = conn.execute(
            "SELECT progress FROM checkin_plans WHERE user_id=? AND status='active'",
            (user_id,),
        ).fetchall()
    if not rows:
        return 0
    return round(sum(float(row[0] or 0) for row in rows) / len(rows))
