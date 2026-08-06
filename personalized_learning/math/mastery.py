"""Explainable mastery scoring for diagnosis and exam evidence."""

import math
from collections import defaultdict
from datetime import datetime, timezone
from typing import Iterable, Mapping

from ..models import MasteryEvidence, MasterySnapshot, clamp, ensure_datetime


def _age_days(answered_at, as_of):
    return max(0.0, (as_of - ensure_datetime(answered_at)).total_seconds() / 86400)


def calculate_mastery(evidence: Iterable[MasteryEvidence], as_of: datetime = None):
    grouped = defaultdict(list)
    for item in evidence:
        grouped[item.knowledge_point_id].append(item)
    as_of = ensure_datetime(as_of or datetime.now(timezone.utc))
    snapshots = {}
    for knowledge_point_id, items in grouped.items():
        ordered = sorted(items, key=lambda item: ensure_datetime(item.answered_at))
        weighted_total = 0.0
        weighted_correct = 0.0
        for item in ordered:
            age = _age_days(item.answered_at, as_of)
            recency = 0.25 + 0.75 * math.exp(-age / 45.0)
            difficulty_weight = 0.8 + 0.8 * (1.0 - item.difficulty_coefficient)
            weight = recency * difficulty_weight
            weighted_total += weight
            weighted_correct += weight if item.is_correct else 0.0

        raw_accuracy = (0.6 * 0.5 + weighted_correct) / (0.6 + weighted_total)
        recent = ordered[-3:]
        recent_accuracy = sum(item.is_correct for item in recent) / len(recent)
        consecutive_correct = 0
        for item in reversed(ordered):
            if not item.is_correct:
                break
            consecutive_correct += 1
        stability_days = min(60.0, 3.0 + consecutive_correct * 5.0)
        last = ordered[-1]
        age = _age_days(last.answered_at, as_of)
        forgetting_risk = clamp(age / (stability_days * 7.0))
        mastery = clamp(raw_accuracy * (1.0 - 0.35 * forgetting_risk))
        snapshots[knowledge_point_id] = MasterySnapshot(
            knowledge_point_id=knowledge_point_id,
            mastery=mastery,
            times_correct=sum(item.is_correct for item in ordered),
            times_wrong=sum(not item.is_correct for item in ordered),
            recent_accuracy=recent_accuracy,
            stability_days=stability_days,
            forgetting_risk=forgetting_risk,
            last_answered_at=ensure_datetime(last.answered_at),
            last_error_type=last.error_type if not last.is_correct else "",
        )
    return snapshots
