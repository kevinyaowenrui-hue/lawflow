"""
LawFlow 智律工作台 - 演示数据种子
仅在 LAWFLOW_SEED_DEMO=1 或 python -m gateway.seed_demo 时写入。
演示记录标题统一带【演示】前缀，便于识别与一键清空。
"""
from __future__ import annotations

import os
import sys


def should_seed_demo() -> bool:
    return os.environ.get("LAWFLOW_SEED_DEMO", "").strip() in ("1", "true", "True", "yes", "YES")


def seed_all_demo_data() -> dict:
    """写入案件、利冲底档、阅卷表、任务等演示数据（幂等：仅当库为空或缺失时补充）。"""
    os.environ["LAWFLOW_SEED_DEMO"] = "1"
    from gateway.utils.matter_vault_db import seed_demo_matters
    from gateway.utils.conflict_checker import seed_demo_conflict_cases
    from gateway.utils.review_table_engine import seed_demo_review_tables
    from gateway.utils.agent_task_db import seed_demo_agent_tasks

    results = {
        "matters": seed_demo_matters(),
        "conflict_cases": seed_demo_conflict_cases(),
        "review_tables": seed_demo_review_tables(),
        "agent_tasks": seed_demo_agent_tasks(),
    }
    return results


def main() -> None:
    results = seed_all_demo_data()
    print("演示数据已写入:", results)


if __name__ == "__main__":
    # 允许 python -m gateway.seed_demo
    if __package__ is None:
        sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    main()
