"""Architecture acceptance runner for repeated local verification."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv


ROOT = Path(__file__).resolve().parents[1]


def _run(command: list[str], timeout: int = 600) -> dict:
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    result = subprocess.run(
        command,
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
    )
    return {
        "command": command,
        "returncode": result.returncode,
        "stdout": result.stdout,
        "stderr": result.stderr,
    }


def main() -> int:
    load_dotenv(ROOT / ".env")
    outputs = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "py_compile": _run([sys.executable, "-m", "py_compile", "app.py", "knowledge_base.py"]),
        "unit_tests": _run(
            [
                sys.executable,
                "-m",
                "unittest",
                "tests.test_checkin_planning_service",
                "tests.test_math_qa_orchestrator",
                "tests.test_english_tools_service",
                "tests.test_profile_service",
                "tests.test_skill_prompt_service",
                "tests.test_study_plan_repo",
                "tests.test_knowledge_match_service",
                "tests.test_professional_knowledge_task_service",
            ],
            timeout=120,
        ),
        "benchmark_knowledge": _run([sys.executable, "benchmark_knowledge.py"], timeout=600),
        "benchmark_qa": _run([sys.executable, "benchmark_qa.py"], timeout=600),
    }

    out_file = ROOT / "benchmarks" / f"acceptance_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    out_file.write_text(json.dumps(outputs, ensure_ascii=False, indent=2), encoding="utf-8")
    print(out_file)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
