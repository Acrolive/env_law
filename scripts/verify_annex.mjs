#!/usr/bin/env node
/**
 * 별표 유사도 검증 스크립트
 *
 * Usage: node scripts/verify_annex.mjs <hwp_path> <pdf_path>
 *
 * 1. kordoc으로 HWP → HTML/마크다운 변환
 * 2. pdftotext로 PDF → 텍스트 변환
 * 3. HTML 태그 제거 후 텍스트 유사도 비교
 * 4. 결과 JSON 출력: { similarity, level, kordoc_md, warning }
 */

import { parse } from 'kordoc';
import { readFileSync } from 'fs';
import { execFileSync } from 'child_process';

const THRESHOLD_OK = 0.70;
const THRESHOLD_WARN = 0.50;

function stripHtml(html) {
  return html
    .replace(/<br\s*\/?>/gi, ' ')
    .replace(/<[^>]+>/g, ' ')
    .replace(/\s+/g, ' ')
    .trim();
}

function similarity(a, b) {
  if (!a && !b) return 1;
  if (!a || !b) return 0;
  // LCS-based similarity (lightweight)
  const len1 = a.length, len2 = b.length;
  if (len1 === 0 || len2 === 0) return 0;
  let matches = 0;
  const windowSize = 3;
  const set = new Set();
  for (let i = 0; i <= len1 - windowSize; i++) {
    set.add(a.substring(i, i + windowSize));
  }
  for (let i = 0; i <= len2 - windowSize; i++) {
    if (set.has(b.substring(i, i + windowSize))) matches++;
  }
  const maxPossible = Math.max(len1, len2) - windowSize + 1;
  return maxPossible > 0 ? matches / maxPossible : 0;
}

async function main() {
  const [hwpPath, pdfPath] = process.argv.slice(2);
  if (!hwpPath) {
    console.error('Usage: node verify_annex.mjs <hwp_path> [pdf_path]');
    process.exit(2);
  }

  const result = {
    hwp_path: hwpPath,
    pdf_path: pdfPath || null,
    kordoc_success: false,
    kordoc_md: '',
    pdftotext_success: false,
    similarity: null,
    level: 'unknown',
    warning: null,
    pdf_download_url: null,
  };

  // Lane A: kordoc
  try {
    const buf = readFileSync(hwpPath);
    const parsed = await parse(buf, { filename: hwpPath });
    if (parsed.success && parsed.markdown) {
      result.kordoc_success = true;
      result.kordoc_md = parsed.markdown;
    }
  } catch (e) {
    result.warning = `kordoc 파싱 실패: ${e.message?.substring(0, 100)}`;
  }

  // Lane B: pdftotext (있으면)
  let pdfText = '';
  if (pdfPath) {
    try {
      pdfText = execFileSync('pdftotext', ['-layout', pdfPath, '-'], {
        encoding: 'utf-8',
        timeout: 10000,
      }).replace(/\s+/g, ' ').trim();
      result.pdftotext_success = pdfText.length > 0;
    } catch (e) {
      // pdftotext 실패는 치명적이지 않음
    }
  }

  // 유사도 계산
  if (result.kordoc_success && result.pdftotext_success) {
    const kordocText = stripHtml(result.kordoc_md);
    const sim = similarity(kordocText, pdfText);
    result.similarity = Math.round(sim * 10000) / 10000;

    if (sim >= THRESHOLD_OK) {
      result.level = 'ok';
    } else if (sim >= THRESHOLD_WARN) {
      result.level = 'warn';
      result.warning = `⚠ 유사도 ${(sim * 100).toFixed(1)}% — 이 별표는 복잡한 표 구조로 변환 정확도가 낮을 수 있습니다. 원본 PDF를 함께 확인하세요.`;
    } else {
      result.level = 'critical';
      result.warning = `🚨 유사도 ${(sim * 100).toFixed(1)}% — 변환 결과가 원본과 크게 다릅니다. 반드시 원본 확인 필요.`;
    }
  } else if (result.kordoc_success && !pdfPath) {
    result.level = 'ok_no_pdf';
  } else if (!result.kordoc_success) {
    result.level = 'fail';
    result.warning = result.warning || 'kordoc 파싱 실패';
  }

  // kordoc_md는 stdout이 커지므로 별도 제거하고 요약만 출력
  const output = { ...result, kordoc_md_length: result.kordoc_md.length };
  delete output.kordoc_md;
  console.log(JSON.stringify(output, null, 2));

  // kordoc 마크다운은 stderr로 출력 (파이프로 캡처 가능)
  if (result.kordoc_md) {
    process.stderr.write(result.kordoc_md);
  }
}

main();
