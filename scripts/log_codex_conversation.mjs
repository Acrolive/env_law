#!/usr/bin/env node

import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const PROJECT_ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");

function localTimestamp(now = new Date()) {
  const parts = new Intl.DateTimeFormat("en-CA", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: false,
    hourCycle: "h23",
  }).formatToParts(now);
  const value = Object.fromEntries(parts.map(({ type, value: item }) => [type, item]));
  return {
    date: `${value.year}-${value.month}-${value.day}`,
    time: `${value.hour}:${value.minute}:${value.second}`,
  };
}

function eventPayload(input) {
  if (input.hook_event_name === "UserPromptSubmit" && typeof input.prompt === "string") {
    return { role: "user", label: "🙋 사용자", text: input.prompt.trim() };
  }
  if (input.hook_event_name === "Stop" && typeof input.last_assistant_message === "string") {
    return { role: "assistant", label: "🤖 Codex", text: input.last_assistant_message.trim() };
  }
  return null;
}

async function main() {
  const raw = await new Promise((resolve) => {
    let data = "";
    process.stdin.setEncoding("utf8");
    process.stdin.on("data", (chunk) => { data += chunk; });
    process.stdin.on("end", () => resolve(data));
  });
  const input = JSON.parse(raw || "{}");
  const payload = eventPayload(input);
  if (!payload?.text) return;

  const { date, time } = localTimestamp();
  const session = String(input.session_id || "unknown").slice(0, 8);
  const turn = String(input.turn_id || "unknown");
  const eventId = `${session}:${turn}:${payload.role}`;
  const marker = `<!-- codex-event:${eventId} -->`;
  const logDir = process.env.CONVERSATION_LOG_DIR || path.join(PROJECT_ROOT, "logs", "conversations");
  const logPath = path.join(logDir, `${date}.md`);

  fs.mkdirSync(logDir, { recursive: true, mode: 0o700 });
  const existing = fs.existsSync(logPath) ? fs.readFileSync(logPath, "utf8") : "";
  if (existing.includes(marker)) return;

  const prefix = existing ? "\n" : `# 대화 기록 — ${date}\n\n`;
  const entry = `${prefix}${marker}\n## ${payload.label} [${time}] (세션 ${session})\n\n${payload.text}\n`;
  fs.appendFileSync(logPath, entry, { encoding: "utf8", mode: 0o600 });
}

try {
  await main();
} catch {
  // 대화 로깅 실패가 Codex 응답을 중단시키지 않도록 한다.
}

process.stdout.write('{"continue":true}\n');
