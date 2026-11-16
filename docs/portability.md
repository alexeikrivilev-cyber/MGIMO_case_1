# Портируемость (B12) — матрица сред и факты

> Требование (PRD §6, ROADMAP B12): «агент-как-папка» должен открываться
> в средах типа Cursor / Claude Code / GigaCode / Codex / OpenCode.
> Единый источник истины — `AGENTS.md` (стандарт agents.md, 60k+
> репозиториев, Linux Foundation AAIF). Среды, не читающие AGENTS.md,
> получают тонкий адаптер-указатель. Статусы в матрице честно разделены:
> «проверено в практике» (только OpenCode — целевая среда, PO R5) и
> «по документации» (остальные среды не установлены).

## 1. Smoke-матрица (по документации; источники — agentic-ecosystem.md §5)

| Среда | Что грузит | Наши файлы | Статус |
|---|---|---|---|
| OpenCode | `AGENTS.md` (инструкции из конфига), `.opencode/plugins` (хуки), skills вручную по indexPath | `AGENTS.md` (через стейджинг в конфиге), `.opencode/plugins/strategy-hooks.ts` | **проверено в практике**: прогоны шагов 0–4, council, FI — все в OpenCode |
| Cursor | `AGENTS.md` как «простая альтернатива `.cursor/rules`»; `.mdc` optional | `AGENTS.md` | по документации (cursor.com/docs/rules): plain `.md` в `.cursor/rules` игнорируется — поэтому НЕ делаем `.mdc`, полагаемся на AGENTS.md |
| Claude Code | `AGENTS.md` + `CLAUDE.md` оба грузятся как project instructions; skills — `.claude/skills` | `AGENTS.md`; skills — симлинк `.claude/skills` → `knowledge/skills` | по документации (docs.anthropic.com); симлинк создан (см. §3) |
| Codex (OpenAI) | `AGENTS.md` global + per-directory, конкатенация root→leaf, **лимит 32 KiB**; skills — `~/.agents/skills` / `.agents/skills` | `AGENTS.md` (<10 КБ — замер §2); skills — симлинк `.agents/skills` → `knowledge/skills` | по документации (developers.openai.com/codex) |
| GigaCode (Sber) | rules в `.gigacode/rules/*.md`, AGENTS.md не документирован | адаптер-указатель — застейджен в `docs/portability/gigacode-rules-staged.md`, материализацию делает PO (гейт Hermes блокирует прямую запись файлов инструкций) | по документации (gitverse.ru/docs/…/rules) |
| Gemini CLI | по умолчанию `GEMINI.md`; `AGENTS.md** не в списке context.fileName (v0.49.0) — молча игнорируется, пока пользователь не добавит | заметка в README §«Gemini CLI» с однострочной настройкой | по документации + issue #28227 |

Почему адаптеры, а не копии: курсор сам рекомендует «reference, don't
duplicate»; копии инструкций разойдутся при правках. Единственный
источник — `AGENTS.md`; правки — через стейджинг
`docs/agents-md-staged.md`, материализацию делает PO.

## 2. Замер лимита Codex (факт, не оценка)

Codex конкатенирует инструкции root→leaf с лимитом 32 KiB; наш
внутренний ориентир (PRD §6, R4): AGENTS.md <10 КБ и <200 строк.

| Файл | Строк | Байт | Вердикт |
|---|---|---|---|
| `AGENTS.md` (корень, размещён PO) | 98 | 7 557 | <10 КБ ✓, <200 строк ✓ |
| `docs/agents-md-staged.md` (тело после шапки) | 99 | 7 819 | <10 КБ ✓ (запас до 32 KiB — 4×) |

Замер: `wc -c` 2026-11-16. Запас к лимиту Codex с учётом глобального
`~/.codex/AGENTS.override.md` — остаётся ≥20 KiB на глобальный файл.

## 3. Skills: симлинки для сред с другими путями

Наши навыки живут в `knowledge/skills/*/SKILL.md` (единый источник).
Для сред, ожидающих навыки в своём каталоге, созданы симлинки:

- `.claude/skills` → `../knowledge/skills` (Claude Code);
- `.agents/skills` → `../knowledge/skills` (Codex / агенты стандарта).

Симлинк, не копия: правка навыка в `knowledge/skills/` видна всем
средам сразу (Codex docs: skills at `.agents/skills`; Anthropic:
`.claude/skills`). Проверка: `ls -l` показывает ссылку; навыки имеют
frontmatter `name`/`description`, требуемый средами.

## 4. Что НЕ портируемо (честно)

- Хуки (`.opencode/plugins/strategy-hooks.ts`) — механизм OpenCode;
  в других средах проверки запускаются вручную (команды — в адаптере
  GigaCode и в README). Детерминированный гейт при этом не теряется:
  `scripts/check_*.py` — обычные python-скрипты.
- Стоимость: хук cost-append пишет COST.md только в OpenCode; в других
  средах строка прогона дописывается вручную (правило COST.md).
