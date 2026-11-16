#!/usr/bin/env python3
"""resume_cf_heldout.py — возобновление прогона council-full после внешнего
убийства процесса (SIGKILL на 11-й сессии, .end не записан).

Переиспользует 10 сохранённых выходов (<arm>/role-*.out, <arm>/cross-*.out)
и докручивает оставшиеся сессии протокола council-design §4:
Phase 3 (adversarial) и Phase 4 (synthesizer). Импорт run_ab как модуля —
те же функции run_session/промпты, то есть тот же контракт меток и выходов.

Запуск: python3 eval/resume_cf_heldout.py
Коды: 0 — обе сессии зелёные, final.md и манифест обновлены; 4 — провал.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
ARM_DIR = REPO_ROOT / "eval" / "runs" / "cf-heldout" / "council-full"
BRIEF = (
    REPO_ROOT
    / "eval"
    / "tasks"
    / "heldout-growth-segment"
    / "artifacts"
    / "brief.md"
).read_text(encoding="utf-8-sig", errors="replace")

sys.path.insert(0, str(REPO_ROOT / "eval"))
import run_ab  # noqa: E402


def load_outputs(pattern: str) -> dict[str, str]:
    outputs: dict[str, str] = {}
    for path in sorted(ARM_DIR.glob(pattern)):
        role = path.stem.split("-", 1)[1]
        outputs[role] = path.read_text(encoding="utf-8", errors="replace")
    return outputs


def main() -> int:
    phase1 = load_outputs("role-*.out")
    phase2 = load_outputs("cross-*.out")
    expected = set(run_ab.COUNCIL_FULL_ROLES)
    if set(phase1) != expected or set(phase2) != expected:
        print(f"не хватает выходов: p1={sorted(phase1)} p2={sorted(phase2)}", file=sys.stderr)
        return 4

    roles_block = "\n\n".join(
        f"=== ЛИНЗА {role.upper()} (Phase 1) ===\n{text}" for role, text in phase1.items()
    )
    cross_block = "\n\n".join(
        f"=== ВОЗРАЖЕНИЯ ЛИНЗЫ {role.upper()} (Phase 2) ===\n{text}"
        for role, text in phase2.items()
    )

    code, adversarial = run_ab.run_session(
        run_ab.ADV_PROMPT.format(brief=BRIEF, roles=roles_block, cross=cross_block),
        ARM_DIR,
        "adversarial",
        run_ab.ROLE_MODEL["devil"],
        900,
    )
    if code != 0:
        print(f"adversarial упал exit={code}", file=sys.stderr)
        return code

    code, final = run_ab.run_session(
        run_ab.SYNTH_FULL_PROMPT.format(
            brief=BRIEF, roles=roles_block, cross=cross_block, adversarial=adversarial
        ),
        ARM_DIR,
        "synthesizer",
        run_ab.MODEL,
        900,
    )
    if code != 0:
        print(f"synthesizer упал exit={code}", file=sys.stderr)
        return code

    (ARM_DIR / "final.md").write_text(final, encoding="utf-8")
    print("resume готов: adversarial + synthesizer, final.md записан")
    return 0


if __name__ == "__main__":
    sys.exit(main())
