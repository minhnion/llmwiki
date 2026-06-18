from math import ceil

from backend.app.domain.compiler import CompilationPassPlan, SourceManifest


class ManifestPlanner:
    """Repairs pass-budget and coverage omissions without adding domain semantics."""

    def ensure_complete_plan(
        self,
        manifest: SourceManifest,
        max_passes: int | None = None,
    ) -> SourceManifest:
        if max_passes is not None and max_passes < 1:
            raise ValueError("Compiler max_passes must be at least 1.")

        unit_order = [unit.local_id for unit in manifest.content_units]
        unit_ids = set(unit_order)
        plans = list(manifest.compilation_plan)
        if max_passes is not None and len(plans) > max_passes:
            retained = plans[: max_passes - 1]
            retained_units = {
                unit_id
                for plan in retained
                for unit_id in plan.target_unit_ids
            }
            remaining_units = [
                unit_id for unit_id in unit_order if unit_id not in retained_units
            ]
            plans = [
                *retained,
                self._fallback_pass(
                    "pass_budget_consolidated_units",
                    remaining_units,
                ),
            ]

        planned_unit_ids = {
            unit_id
            for plan in plans
            for unit_id in plan.target_unit_ids
        }
        uncovered = [
            unit_id for unit_id in unit_order if unit_id not in planned_unit_ids
        ]
        if uncovered:
            available = (
                len(uncovered)
                if max_passes is None
                else max_passes - len(plans)
            )
            if available <= 0:
                last = plans[-1]
                plans[-1] = last.model_copy(
                    update={
                        "objective": (
                            f"{last.objective}\n\nĐồng thời biên dịch các semantic units "
                            "bị profiler bỏ ngoài pass budget."
                        ),
                        "target_unit_ids": list(
                            dict.fromkeys([*last.target_unit_ids, *uncovered])
                        ),
                    }
                )
            else:
                group_count = min(available, len(uncovered))
                group_size = ceil(len(uncovered) / group_count)
                groups = [
                    uncovered[start : start + group_size]
                    for start in range(0, len(uncovered), group_size)
                ]
                plans.extend(
                    self._fallback_pass(f"pass_uncovered_units_{index}", group)
                    for index, group in enumerate(groups, start=1)
                )

        normalized = manifest.model_copy(update={"compilation_plan": plans})
        normalized_planned = {
            unit_id
            for plan in normalized.compilation_plan
            for unit_id in plan.target_unit_ids
        }
        if normalized_planned != unit_ids:
            missing = unit_ids - normalized_planned
            raise ValueError(
                f"Source manifest plan still omits units: {sorted(missing)}"
            )
        if max_passes is not None and len(plans) > max_passes:
            raise ValueError("Normalized compilation plan exceeds max_passes.")
        return normalized

    @staticmethod
    def _fallback_pass(pass_id: str, target_unit_ids: list[str]) -> CompilationPassPlan:
        return CompilationPassPlan(
            pass_id=pass_id,
            objective=(
                "Biên dịch đầy đủ các semantic source units mà source profiler đã nhận diện "
                "nhưng chưa đưa vào compilation plan. Giữ mọi dữ kiện, công thức, điều kiện, "
                "ngoại lệ, quan hệ và provenance quan trọng của từng unit."
            ),
            target_unit_ids=target_unit_ids,
            expected_outputs=[
                "grounded evidence for every target unit",
                "source-backed artifacts with atomic statements",
                "semantic nodes and artifact relations when present",
            ],
        )
