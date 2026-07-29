#!/usr/bin/env node
// 대화 자동 기록 스크립트 (Stop hook 용)
//
// Claude Code 의 Stop hook 이 매 턴 종료 시 본 스크립트를 호출한다.
// stdin 으로 hook 입력 JSON({session_id, transcript_path, ...})을 받아
// transcript(JSONL)에서 아직 기록되지 않은 사용자 프롬프트·Claude 답변을
// 추출하여 logs/conversations/YYYY-MM-DD.md 에 append 한다.
//
// 수동 백필:
//   node scripts/log_conversation.mjs --full <transcript.jsonl> [출력.md]
//   (세션 전체를 처음부터 다시 내보낸다. 상태 파일은 건드리지 않음)

import fs from 'node:fs';
import path from 'node:path';

const PROJECT_DIR = process.env.CLAUDE_PROJECT_DIR || process.cwd();
const LOG_DIR = path.join(PROJECT_DIR, 'logs', 'conversations');
const STATE_FILE = path.join(LOG_DIR, '.state.json');

function readStdin() {
  try {
    return fs.readFileSync(0, 'utf8');
  } catch {
    return '';
  }
}

// transcript 한 줄(JSON) → {role, text, ts} 또는 null
function extractEntry(line) {
  let e;
  try {
    e = JSON.parse(line);
  } catch {
    return null;
  }
  if (!e || !e.message || e.isMeta) return null;
  const ts = e.timestamp || null;

  if (e.type === 'user') {
    const c = e.message.content;
    let text = '';
    if (typeof c === 'string') {
      text = c;
    } else if (Array.isArray(c)) {
      // tool_result 등은 제외하고 사용자가 직접 입력한 text 만
      text = c
        .filter((b) => b && b.type === 'text' && typeof b.text === 'string')
        .map((b) => b.text)
        .join('\n');
    }
    text = text.trim();
    if (!text) return null;
    // 시스템/하네스 주입 텍스트는 기록 대상에서 제외
    if (
      /^<(system-reminder|local-command-caveat|task-notification|command-name|local-command-stdout)/.test(
        text,
      ) ||
      text.startsWith('Caveat:')
    ) {
      return null;
    }
    return { role: 'user', text, ts };
  }

  if (e.type === 'assistant') {
    const c = e.message.content;
    if (!Array.isArray(c)) return null;
    const text = c
      .filter((b) => b && b.type === 'text' && typeof b.text === 'string')
      .map((b) => b.text)
      .join('\n')
      .trim();
    if (!text) return null; // thinking / tool_use 만 있는 턴은 생략
    return { role: 'assistant', text, ts };
  }

  return null;
}

function fmtTime(ts) {
  if (!ts) return '';
  const d = new Date(ts);
  if (Number.isNaN(d.getTime())) return '';
  const p = (n) => String(n).padStart(2, '0');
  return `${p(d.getHours())}:${p(d.getMinutes())}:${p(d.getSeconds())}`;
}

function fmtDate(ts) {
  if (!ts) return '';
  const d = new Date(ts);
  if (Number.isNaN(d.getTime())) return '';
  const p = (n) => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`;
}

// includeDate: 백필 모드에서는 파일명에 날짜가 없으므로 헤더에 날짜를 포함한다
function renderEntries(entries, sessionId, includeDate = false) {
  const sid = sessionId ? sessionId.slice(0, 8) : 'unknown';
  let out = '';
  for (const { role, text, ts } of entries) {
    const who = role === 'user' ? `🙋 사용자` : `🤖 Claude`;
    const t = fmtTime(ts);
    const stamp = includeDate && t ? `${fmtDate(ts)} ${t}` : t;
    out += `\n## ${who}${stamp ? ` [${stamp}]` : ''} (세션 ${sid})\n\n${text}\n`;
  }
  return out;
}

function main() {
  const argv = process.argv.slice(2);

  // ---- 수동 백필 모드 ----
  if (argv[0] === '--full') {
    const transcriptPath = argv[1];
    if (!transcriptPath || !fs.existsSync(transcriptPath)) {
      console.error('사용법: log_conversation.mjs --full <transcript.jsonl> [출력.md]');
      process.exit(1);
    }
    const lines = fs.readFileSync(transcriptPath, 'utf8').split('\n').filter(Boolean);
    const entries = lines.map(extractEntry).filter(Boolean);
    const sid = path.basename(transcriptPath, '.jsonl');
    const outPath =
      argv[2] || path.join(LOG_DIR, `backfill_${sid.slice(0, 8)}.md`);
    fs.mkdirSync(path.dirname(outPath), { recursive: true });
    fs.writeFileSync(
      outPath,
      `# 대화 전체 백필 — 세션 ${sid}\n` + renderEntries(entries, sid, true),
    );
    console.log(`백필 완료: ${outPath} (${entries.length}개 메시지)`);
    return;
  }

  // ---- Stop hook 모드 ----
  let input;
  try {
    input = JSON.parse(readStdin());
  } catch {
    process.exit(0); // hook 입력이 없으면 조용히 종료
  }
  const transcriptPath = input.transcript_path;
  const sessionId = input.session_id || 'unknown';
  if (!transcriptPath || !fs.existsSync(transcriptPath)) process.exit(0);

  fs.mkdirSync(LOG_DIR, { recursive: true });

  // 세션별로 마지막 처리한 줄 번호를 기억하여 증분 기록
  let state = {};
  try {
    state = JSON.parse(fs.readFileSync(STATE_FILE, 'utf8'));
  } catch {
    state = {};
  }
  const lastLine = state[sessionId] || 0;

  const lines = fs.readFileSync(transcriptPath, 'utf8').split('\n').filter(Boolean);
  if (lines.length <= lastLine) process.exit(0);

  const entries = lines.slice(lastLine).map(extractEntry).filter(Boolean);

  state[sessionId] = lines.length;
  fs.writeFileSync(STATE_FILE, JSON.stringify(state, null, 2));

  if (entries.length === 0) process.exit(0);

  const today = new Date();
  const y = today.getFullYear();
  const m = String(today.getMonth() + 1).padStart(2, '0');
  const d = String(today.getDate()).padStart(2, '0');
  const logFile = path.join(LOG_DIR, `${y}-${m}-${d}.md`);

  let body = '';
  if (!fs.existsSync(logFile)) {
    body += `# 대화 기록 — ${y}-${m}-${d}\n`;
  }
  body += renderEntries(entries, sessionId);
  fs.appendFileSync(logFile, body);
}

try {
  main();
} catch {
  // 기록 실패가 세션 진행을 막아서는 안 됨
  process.exit(0);
}
