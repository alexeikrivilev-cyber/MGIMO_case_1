# Самоулучшающиеся навыки: дизайн и реализация-минимум (TASK-hermes-14 §2)

> Решение владельца 2026-11-17 12:34 (BRIEF п.26): «Изучить механику
> самоулучшающихся скиллов и внедрить — прямо возьмите из Гермеса, она там
> работает (механика learned-скиллов: версионирование, патчи, откат)».
> Дизайн + реализация-минимум: `product/agent/`. Предохранитель
> «самоулучшение только по замеру» — адаптация под strategy-agent,
> её аналога в Hermes нет (обоснование — §3).
> Предрегистрация пользы — measurements.md §28 (ДО любого замера).

## 1. Что изучено в Hermes (внешний артефакт, локально)

Источник: `~/.hermes/hermes-agent/tools/` (проверено 2026-11-17). Дословные
цитаты — из докстрингов и кода; путь файла указан у каждой.

| Механика Hermes | Где | Как устроена (цитата) |
|---|---|---|
| Журнал мутаций | `tools/skill_ledger.py` | «Per-mutation skill audit ledger + single-edit rollback. Every skill mutation (any actor) appends one JSONL entry to `~/.hermes/skills/.curator_ledger.jsonl` with before/after file manifests whose contents are stored content-addressed (sha256-deduped) under `~/.hermes/.curator_backups/blobs/`. JSONL, not the state DB: durable, greppable, survives DB resets.» |
| Телеметрия ≠ гейт | там же | «TELEMETRY, NOT A GATE: every public write path swallows and logs — except `rollback_entry`, which FAILS CLOSED when its safety capture fails.» |
| Актор мутации | там же | `_VALID_ACTORS = {"curator", "agent", "user"}`; в записи — `actor` + `evidence.session_id` |
| Контент-адресуемые блобы | там же | `_store_blob`: имя файла = sha256 содержимого; `read_blob` валидирует hex |
| Исключения из снимка | там же | `TRANSIENT_DIRS` (.venv, node_modules, __pycache__, .git …): «a stray venv or node_modules turns a multi-KB ledger capture into gigabytes of blobs» |
| Блокировка журнала | там же | `_ledger_lock` — flock на `<skills>/.locks/ledger.lock`, «re-entrant, no-op where neither fcntl nor msvcrt exists» |
| Статистика использования | `tools/skill_usage.py` | `bump_patch`: `patch_count`, `patch_generation`, `last_patched_at`; `record_created`: `created_by` ∈ {agent, learn, installed} |
| Предохранители записи | `tools/skill_manager_guards.py` | `_pinned_guard`, `_locked_guard`, `_background_review_read_before_write_guard` («read-before-write»), `_curator_consolidation_delete_guard` |
| Обучение по запросу | `hermes_cli/cli_commands_mixin.py` | `/learn` — «distill a reusable skill from anything the user describes»; созданные так скиллы помечаются `created_by="learn"` («a learning-signal marker, NOT the curator-management opt-in») |
| Версия видна в индексе | `~/.hermes/skills/taste-skill/SKILL.md` | версия в `description`: «tasteskill 2.5.1, the anti-slop frontend skill…» |

## 2. Что взято в реализацию-минимум (`product/agent/`)

| Механика Hermes | Реализация strategy-agent | Файл |
|---|---|---|
| JSONL-журнал + блобы sha256 | `ledger.jsonl` + `blobs/<sha256>` в `knowledge/skills/.evolution/` (журнал едет с навыками в git — откат на любом клоне) | `product/agent/skill_ledger.py` |
| before/after-манифесты | `snapshot_skill()` — {path относительно knowledge/skills, sha256}; транзитные каталоги исключены | там же |
| Откат fail-closed | `rollback_entry()`: все блобы before проверены ДО любых изменений; добавленные в after файлы удаляются; откат сам = запись журнала (action=rollback, parent=id) | там же |
| flock на журнале | `<skills>/.evolution/.locks/ledger.lock` | там же |
| Статистика использования | `usage_record()`: patch_count / rollback_count / patch_generation / evidence-список — ИЗ ЖУРНАЛА, без второго источника правды | там же |
| Verify-проверка | `verify()`: все блобы на месте, id уникальны, parent существует | там же |
| Точечный патч | `skill_evolve.py apply` — old_string/new_string, единственность вхождения обязательна | `product/agent/skill_evolve.py` |
| Версия | журнал = история версий; `patch_generation` = номер поколения патчей (аналог semver-минора) | — |

Отдельно: `product/agent/skill_guard.py` — предохранитель (§3). CLI-контракт
и коды возврата — в докстринге `skill_evolve.py`; тесты —
`tests/test_skill_evolution.py` (12 штук, включая негативный контроль:
файл-«заметка» вместо артефакта замера → отказ).

## 3. Предохранитель «самоулучшение только по замеру» — адаптация, не копия

Почему НЕ скопированы гейты Hermes как есть: Hermes защищает от ДРУГИх
угроз (pinned/locked/read-before-write — конфликты куратора и агента), а
мутацию по решению агента допускает всегда («TELEMETRY, NOT A GATE»).
Главный измеренный риск strategy-agent — другой: четыре последовательных
отрицательных измерения улучшательных гипотез (critic-loop: §22.4,
§22.7, §23.6, H-C2 §25.7) показали, что правки «по ощущению» не дают
прироста, а гейт целостности отклоняет 2/3 ревизий. Агент, который сам
пишет себе инструкции без замера, дрейфует незаметно — это и есть сценарий,
который предохранитель запрещает.

Правило (fail-closed):

    патч навыка допускается ТОЛЬКО с evidence, резолвирующимся в артефакт
    ЗАМЕРА: путь к непустому файлу в репозитории, несущему след вердикта
    (вердикт / замер / предрегистрация / итог / Δ / MDD / sd / p=), либо
    ссылку на секцию measurements.md («measurements.md §N», «§N»).

Что считается evidence НЕДОСТАТОЧНЫМ (все — отказ):
- пустая строка или «подумал и решил»;
- путь к несуществующему/пустому файлу;
- файл без следа замера (негативный контроль в тестах: заметка без
  вердикта → отказ, даже если файл есть);
- §N, которой нет в measurements.md.

Дополнительные предохранители (уроки стенда):
- old_string обязан быть единственным в файле (урок integrity-гейта:
  неоднозначная замена — источник «плавающих» правок);
- повторная проверка единственности между propose и apply (гонка);
- откат fail-closed при потере блоба (урок Hermes, воспроизведён тестом).

Чего в минимуме НЕТ (названо, чтобы не принять за пробел): автоматического
куратора, фонового ревью, pinned/locked-навыков, веб-хаба установки,
семантических версий в frontmatter. Это следующий слоя механика — по
результатам предрегистрации §28, не «на всякий случай».

## 4. Как этим пользоваться (операционная инструкция)

1. Замер закрыт и дал вердикт (measurements.md §N или артефакт в
   `eval/runs/...`).
2. `python3 product/agent/skill_evolve.py propose --skill <name> --old ... --new ... --evidence "..."` —
   дифф + проверка допуска; файл не меняется.
3. Согласование: правка СКИЛЛА = изменение метода работы агента. Для
   правок, меняющих поведение на шагах workflow, — решение PO/владельца
   (аналог стейджинга AGENTS.md: инструмент писать может, размещать —
   человек). Для правок-уточнений внутри навыка по замеру — допускается
   автономно (actor=agent).
4. `apply` — снимок before → патч → снимок after → запись журнала.
5. `rollback --entry <id>` — если правка не прижилась; `verify` — в
   проверки репозитория; `status --skill <name>` — сколько раз навык
   правился и на каких основаниях.

## 5. Предрегистрация пользы (measurements.md §28)

Гипотеза H-SI1: агент, который фиксирует уроки и правит свои инструкции
ТОЛЬКО по замеру, даёт лучший артефакт на N-й итерации, чем без этого.
Дизайн, порог решения и стоимость — measurements.md §28 (предрегистрировано
ДО прогонов; в этой очереди НЕ запускалось).

## 6. Ограничения

- Источники этого документа — локальные файлы (пути в бэктиках) и секции
  measurements.md; это проверяемые ссылки внутри репозитория. Гейт
  `scripts/check_sources.py` по устройству хука
  (`.opencode/plugins/strategy-hooks.ts`, фильтр `/project/`) применяется
  к `project/*.md`, а не к `docs/research/`; для docs-артефактов
  ссылкой считается путь в репозитории (как правило C для
  measurements.md) [ограничение названо].
- Реализация-минимум проверена юнит-тестами на временном корне, но не
  пробована в боевом прогоне очереди: первое боевое применение — при
  закрытии TASK-hermes-15, с записью в журнал [ограничение названо].
- Порог «похож на артефакт замера» — эвристика по маркерам вердикта;
  замер её ложных срабатываний не делался [ограничение]. Гейт ловит
  «патч по ощущению», но не заменяет критика.
- Сравнение с Hermes — по коду и докстрингам на 2026-11-17; других
  реализаций learned-скиллов не изучалось [ограничение].
