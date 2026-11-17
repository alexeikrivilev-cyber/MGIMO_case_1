# Ревизия артефактов шагов 4–5 по находкам гейтов (TASK-hermes-20)

- старт: 2026-11-17T19:40:52.566678+00:00
- артефакты: eval/runs/t18-case/artifacts
- имена: ['verification-plan.md']
- механизм: patch-сессия + apply_revision.py (integrity-гейт) + перепрогон гейтов этапа; раундов до 3
- причина: дефект области действия — гейты acceptance/actionability винтили только на strategy-product.md; comms/verification/decisions дошли до сдачи без секции приёмного чек-листа и структурных признаков плана (вердикт владельца, BRIEF п.27)

- verification-plan.md: старт sha256=05fa0de3fdf05dbd, 19478 символов
- verification-plan.md: провал гейтов ДО ревизии: ['acceptance']
- verification-plan.md: patch-сессия exit=0
- verification-plan.md: apply_revision exit=0
- verification-plan.md: applied=2 not_found=0 ambiguous=0 rejected=0 fallback=no integrity=ok size_ratio=1.16
- verification-plan.md: гейты зелёные (раунд 1), sha256=b2c198c2335ef607

- ИТОГ: все артефакты зелёные
