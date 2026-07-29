#!/usr/bin/env node
/**
 * kordoc 직접 호출로 HWP/HWPX → HTML 테이블 변환
 *
 * Usage: node scripts/parse_hwp.mjs <hwp_path>
 *
 * stdout: 변환된 마크다운/HTML
 * stderr: 메타데이터 JSON { success, fileType, blocks, warnings }
 */

import { parse } from 'kordoc';
import { readFileSync } from 'fs';

const hwpPath = process.argv[2];
if (!hwpPath) {
  console.error('Usage: node parse_hwp.mjs <hwp_path>');
  process.exit(2);
}

try {
  const buf = readFileSync(hwpPath);
  const result = await parse(buf, { filename: hwpPath });

  // 메타데이터를 stderr로
  const meta = {
    success: result.success,
    fileType: result.fileType,
    blocks: result.blocks?.length || 0,
    warnings: result.warnings || [],
    markdownLength: result.markdown?.length || 0,
  };
  process.stderr.write(JSON.stringify(meta) + '\n');

  if (result.success && result.markdown) {
    process.stdout.write(result.markdown);
  } else {
    console.error('parse failed:', result.warnings);
    process.exit(1);
  }
} catch (e) {
  console.error(JSON.stringify({ success: false, error: e.message }));
  process.exit(1);
}
