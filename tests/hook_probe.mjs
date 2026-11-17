// hook_probe.mjs — проба TS-хука strategy-hooks (TASK-hermes-15 П.4).
//
// Имитирует событие tool.execute.after на «записи файла» и печатает
// дописанный гейтами вывод как JSON на stdout. Нужен, потому что хук
// живёт в .ts и грузится только внутри opencode: тест на python не
// может импортировать его напрямую, а сломать хук = сломать живую
// проверку всех будущих сессий (причина, по которой проводка гейтов
// откладывалась в TASK-hermes-14).
//
// Использование: node tests/hook_probe.mjs <путь-к-файлу>
// Вывод (одна строка JSON): {"appended": "..."}

import { resolve } from "node:path";
import { StrategyHooks } from "../.opencode/plugins/strategy-hooks.ts";

const filePath = resolve(process.argv[2]);
const plugin = await StrategyHooks({});
const output = { output: "" };
await plugin["tool.execute.after"](
  { tool: "write", sessionID: "hook-probe", args: { filePath } },
  output,
);
console.log(JSON.stringify({ appended: output.output }));
