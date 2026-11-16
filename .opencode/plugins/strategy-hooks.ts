/**
 * strategy-hooks — хуки «Стратега» для OpenCode (PRD §10, ТЗ О1 п.4).
 *
 * Три хука (лимит ТЗ — 2–4), все — детерминированные гарантии поверх
 * поведения модели:
 *
 *   1. sources-guard (tool.execute.after): после записи/правки файла в
 *      project/*.md запускается scripts/check_sources.py; результат
 *      (exit 0/2) дописывается в вывод инструмента — модель и человек
 *      видят нарушение доказательственной дисциплины сразу.
 *   2. state-guard (tool.execute.after + event): после записи STATE.md и
 *      в конце сеанса (session.idle / session.deleted) запускается
 *      scripts/check_state.py; результат — в вывод инструмента и в
 *      .opencode/hooks.log.
 *   3. cost-append (event message.updated): токены каждого ассистентского
 *      сообщения агрегируются по сессии; строка прод-таблицы COST.md
 *      (между маркерами <!-- cost-rows:begin/end -->) перезаписывается
 *      идемпотентно по sessionID. Оценка $ — по прайсу step-5-preview
 *      (docs/research/llm-pricing-agent-costs.md §1.8):
 *        $ = input·1.00/1M + cache.read·0.10/1M + output·2.70/1M
 *      (в метриках OpenCode input excludes cache-read — сверено с внутренним
 *      cost OpenCode; output включает reasoning).
 *
 * Переменные окружения не читаются, секреты не логируются. Любая ошибка
 * хука гасится (лог в .opencode/hooks.log) — хук never ломает сеанс.
 */

import type { Plugin } from "@opencode-ai/plugin";
import { execFileSync } from "node:child_process";
import { appendFileSync, readFileSync, writeFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const REPO_ROOT = resolve(dirname(fileURLToPath(import.meta.url)), "../..");
const SCRIPTS_DIR = resolve(REPO_ROOT, "scripts");
const COST_MD = resolve(REPO_ROOT, "COST.md");
const STATE_MD = resolve(REPO_ROOT, "STATE.md");
const HOOKS_LOG = resolve(REPO_ROOT, ".opencode/hooks.log");

// Прод-прайс step-5-preview, $ за 1M токенов (§1.8 прайс-документа).
// Формула: input×1.00 + cache.read×0.10 + output×2.70 (в метриках OpenCode
// input excludes cache-read — сверено с внутренним cost OpenCode по прайсам
// models.dev, совпадение до центов; output включает reasoning).
const PRICE = { inputMiss: 1.0, inputHit: 0.1, output: 2.7 };
const MARKER_BEGIN = "<!-- cost-rows:begin -->";
const MARKER_END = "<!-- cost-rows:end -->";

type TokenSnapshot = {
  input: number;
  output: number;
  reasoning: number;
  cacheRead: number;
  cacheWrite: number;
};

type SessionAggregate = TokenSnapshot & { searches: number; model: string };

/** Агрегаты по сессиям: sessionID → накопленные токены. */
const sessions = new Map<string, SessionAggregate>();
/** Уже учтённые сообщения: messageID → токены на момент последнего события. */
const counted = new Map<string, TokenSnapshot>();

function note(message: string): void {
  try {
    appendFileSync(HOOKS_LOG, `${new Date().toISOString()} ${message}\n`);
  } catch {
    // лог хука не критичен
  }
}

function runPython(
  script: string,
  args: string[] = [],
): { code: number; out: string } {
  try {
    const out = execFileSync("python3", [resolve(SCRIPTS_DIR, script), ...args], {
      encoding: "utf-8",
      cwd: REPO_ROOT,
    });
    return { code: 0, out };
  } catch (error) {
    const anyError = error as { status?: number; stdout?: string; stderr?: string };
    return {
      code: typeof anyError.status === "number" ? anyError.status : 1,
      out: `${anyError.stdout ?? ""}${anyError.stderr ?? ""}`,
    };
  }
}

function snapshotFrom(tokens: Record<string, any> | undefined): TokenSnapshot | null {
  if (!tokens || typeof tokens !== "object") return null;
  const cache = (tokens.cache ?? {}) as Record<string, any>;
  const snap: TokenSnapshot = {
    input: Number(tokens.input ?? 0) || 0,
    output: Number(tokens.output ?? 0) || 0,
    reasoning: Number(tokens.reasoning ?? 0) || 0,
    cacheRead: Number(cache.read ?? 0) || 0,
    cacheWrite: Number(cache.write ?? 0) || 0,
  };
  if (
    snap.input === 0 &&
    snap.output === 0 &&
    snap.reasoning === 0 &&
    snap.cacheRead === 0 &&
    snap.cacheWrite === 0
  ) {
    return null;
  }
  return snap;
}

function currentStep(): string {
  try {
    const text = readFileSync(STATE_MD, "utf-8");
    const match = /^##\s*шаг\s*\n+([^\n#]+)/m.exec(text);
    if (!match) return "—";
    const raw = match[1].trim();
    // компактно: «Шаг 0 (РАМКА) — не начат…» → «Шаг 0 (РАМКА)»
    const cut = raw.search(/\s—|\(/);
    const step = cut > 0 ? raw.slice(0, cut).trim() : raw;
    return step.slice(0, 40);
  } catch {
    return "—";
  }
}

function estimateUsd(agg: SessionAggregate): string {
  const usd =
    (agg.input * PRICE.inputMiss +
      agg.cacheRead * PRICE.inputHit +
      agg.output * PRICE.output) /
    1_000_000;
  return `$${usd.toFixed(2)}`;
}

function upsertCostRow(sessionID: string, agg: SessionAggregate): void {
  try {
    const text = readFileSync(COST_MD, "utf-8");
    const lines = text.split("\n");
    // маркеры ищем ЦЕЛЫМИ строками: в шапке COST.md они упомянуты внутри
    // блокцита-документации — substring-поиск ломал бы файл.
    let begin = -1;
    let end = -1;
    for (let i = 0; i < lines.length; i++) {
      const trimmed = lines[i].trim();
      if (trimmed === MARKER_BEGIN && begin === -1) begin = i;
      else if (trimmed === MARKER_END && begin !== -1) {
        end = i;
        break;
      }
    }
    if (begin === -1 || end === -1) {
      note(`cost-append: маркеры-строки не найдены в COST.md, строка не дописана (${sessionID})`);
      return;
    }
    const row =
      `| ${new Date().toISOString().slice(0, 10)} | ${sessionID} | ${currentStep()} | ` +
      `${agg.model || "—"} | ${agg.input} | ${agg.output} | ${agg.reasoning} | ` +
      `${agg.cacheRead} | ${agg.cacheWrite} | ${agg.searches} | ${estimateUsd(agg)} |`;
    const kept = lines
      .slice(begin + 1, end)
      .filter((line: string) => line.trim() && !line.includes(`| ${sessionID} |`));
    const next = [
      ...lines.slice(0, begin + 1),
      ...kept,
      row,
      ...lines.slice(end),
    ].join("\n");
    writeFileSync(COST_MD, next);
    note(`cost-append: ${sessionID} → ${estimateUsd(agg)} (${agg.input} in / ${agg.output} out)`);
  } catch (error) {
    note(`cost-append ошибка (${sessionID}): ${String(error)}`);
  }
}

export const StrategyHooks: Plugin = async () => {
  return {
    "tool.execute.after": async (input, output) => {
      try {
        const args = (input.args ?? {}) as Record<string, any>;
        const filePath = String(args.filePath ?? args.path ?? "");
        if (!filePath) return;

        // 3. учёт поисковых вызовов для cost-append
        if (input.tool === "webfetch" || input.tool === "websearch") {
          const agg = sessions.get(input.sessionID);
          if (agg) agg.searches += 1;
        }

        const abs = resolve(filePath);
        if (abs === STATE_MD) {
          const { code, out } = runPython("check_state.py");
          output.output += `\n\n[hook:state-guard] check_state.py → exit ${code}\n${out.trim()}`;
          note(`state-guard (tool): exit ${code}`);
        } else if (abs.includes("/project/") && abs.endsWith(".md")) {
          const { code, out } = runPython("check_sources.py", [abs]);
          output.output += `\n\n[hook:sources-guard] check_sources.py → exit ${code}\n${out.trim()}`;
          note(`sources-guard: ${abs} → exit ${code}`);
        }
      } catch (error) {
        note(`tool.execute.after ошибка: ${String(error)}`);
      }
    },

    event: async ({ event }) => {
      try {
        if (event.type === "session.idle" || event.type === "session.deleted") {
          const { code, out } = runPython("check_state.py");
          note(
            `state-guard (session end, ${event.type}): check_state.py exit ${code}\n${out.trim()}`,
          );
          return;
        }

        if (event.type !== "message.updated") return;
        const info = (event.properties ?? {}).info as Record<string, any> | undefined;
        if (!info || info.role !== "assistant") return;

        const messageID = String(info.id ?? "");
        const sessionID = String(info.sessionID ?? "");
        if (!messageID || !sessionID) return;

        const snap = snapshotFrom(info.tokens as Record<string, any> | undefined);
        if (!snap) return;

        const agg: SessionAggregate =
          sessions.get(sessionID) ??
          { ...snap, searches: 0, model: String(info.modelID ?? "—") };
        // сообщение могло обновиться стримингом — пересчитываем вклад
        const previous = counted.get(messageID);
        if (previous) {
          agg.input += snap.input - previous.input;
          agg.output += snap.output - previous.output;
          agg.reasoning += snap.reasoning - previous.reasoning;
          agg.cacheRead += snap.cacheRead - previous.cacheRead;
          agg.cacheWrite += snap.cacheWrite - previous.cacheWrite;
        } else {
          agg.input += snap.input;
          agg.output += snap.output;
          agg.reasoning += snap.reasoning;
          agg.cacheRead += snap.cacheRead;
          agg.cacheWrite += snap.cacheWrite;
        }
        agg.model = String(info.modelID ?? agg.model);
        counted.set(messageID, snap);
        sessions.set(sessionID, agg);
        upsertCostRow(sessionID, agg);
      } catch (error) {
        note(`event ошибка (${event.type}): ${String(error)}`);
      }
    },
  };
};
