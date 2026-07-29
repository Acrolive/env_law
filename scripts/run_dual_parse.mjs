#!/usr/bin/env node
/**
 * 이중 파서 실행: kordoc(HWP→HTML/MD) + pdftotext(PDF→텍스트)
 * data/annex_samples/ 의 파일들을 파싱하여 data/annex_results/ 에 저장
 */

import { parse } from 'kordoc';
import { readFileSync, writeFileSync, mkdirSync, existsSync } from 'fs';
import { execSync } from 'child_process';
import { join } from 'path';

const SAMPLES = 'data/annex_samples';
const RESULTS = 'data/annex_results';
const KORDOC_DIR = join(RESULTS, 'kordoc');
const PDFTEXT_DIR = join(RESULTS, 'pdftotext');

for (const d of [KORDOC_DIR, PDFTEXT_DIR]) {
  mkdirSync(d, { recursive: true });
}

const index = JSON.parse(readFileSync(join(SAMPLES, 'index.json'), 'utf-8'));
console.log(`총 ${index.length}건 파싱 시작`);

const errors = [];
let kordocOk = 0, kordocFail = 0;
let pdftextOk = 0, pdftextFail = 0;

for (let i = 0; i < index.length; i++) {
  const entry = index[i];
  const key = entry.key;
  process.stdout.write(`\r[${i + 1}/${index.length}] ${key}  `);

  // Lane A: kordoc
  const hwpPath = entry.hwp_file;
  if (existsSync(hwpPath)) {
    try {
      const buf = readFileSync(hwpPath);
      const result = await parse(buf, { filename: `${key}.hwp` });
      if (result.success && result.markdown) {
        writeFileSync(join(KORDOC_DIR, `${key}.md`), result.markdown, 'utf-8');
        kordocOk++;
      } else {
        errors.push({ key, engine: 'kordoc', error: 'parse returned success=false', warnings: result.warnings });
        kordocFail++;
      }
    } catch (e) {
      errors.push({ key, engine: 'kordoc', error: e.message?.substring(0, 200) });
      kordocFail++;
    }
  }

  // Lane B: pdftotext
  const pdfPath = entry.pdf_file;
  if (pdfPath && existsSync(pdfPath)) {
    try {
      const text = execSync(`pdftotext -layout "${pdfPath}" -`, {
        encoding: 'utf-8',
        timeout: 10000,
      });
      if (text.trim().length > 0) {
        writeFileSync(join(PDFTEXT_DIR, `${key}.txt`), text, 'utf-8');
        pdftextOk++;
      } else {
        errors.push({ key, engine: 'pdftotext', error: 'empty output' });
        pdftextFail++;
      }
    } catch (e) {
      errors.push({ key, engine: 'pdftotext', error: e.message?.substring(0, 200) });
      pdftextFail++;
    }
  }
}

console.log('\n\n=== 파싱 완료 ===');
console.log(`kordoc:   성공 ${kordocOk}, 실패 ${kordocFail}`);
console.log(`pdftotext: 성공 ${pdftextOk}, 실패 ${pdftextFail}`);
console.log(`에러 총: ${errors.length}건`);

writeFileSync(join(RESULTS, 'errors.json'), JSON.stringify(errors, null, 2), 'utf-8');
writeFileSync(join(RESULTS, 'parse_summary.json'), JSON.stringify({
  total: index.length,
  kordoc: { success: kordocOk, fail: kordocFail },
  pdftotext: { success: pdftextOk, fail: pdftextFail },
  errors: errors.length,
}, null, 2), 'utf-8');
