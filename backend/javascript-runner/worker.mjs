import {parentPort, workerData} from 'node:worker_threads';
import TurndownService from 'turndown';
import gfmPlugin from 'turndown-plugin-gfm';

// Docker is the security boundary. Worker/AsyncFunction are not sandboxes.
const converter = new TurndownService({headingStyle: 'atx', codeBlockStyle: 'fenced'});
converter.use(gfmPlugin.gfm);
converter.remove(['script', 'style', 'iframe', 'object', 'embed']);
const proposals = [], warnings = [], files = [];
const emit = (field, value, block_ids) => {
  if (proposals.length >= 200) throw Error('Too many proposals');
  proposals.push({field, value, block_ids});
};
const saveMarkdown = (name, content) => {
  if (files.length >= 5 || typeof content !== 'string' || Buffer.byteLength(content) > 256 * 1024) throw Error('File limit');
  files.push({name, content});
};
const toMarkdown = html => {
  if (typeof html !== 'string') throw Error('HTML is unavailable');
  return converter.turndown(html);
};
let output = null;
const set_output = value => {
  // Reject values that JSON.stringify would silently drop or coerce.
  const seen = new Set();
  const check = v => {
    if (v === null || typeof v === 'string' || typeof v === 'boolean') return;
    if (typeof v === 'number' && Number.isFinite(v)) return;
    if (typeof v !== 'object' || seen.has(v) || (!Array.isArray(v) && Object.getPrototypeOf(v) !== Object.prototype)) throw Error('Output must be JSON');
    seen.add(v);
    for (const item of Object.values(v)) check(item);
    seen.delete(v);
  };
  check(value);
  const serialized = JSON.stringify(value);
  if (Buffer.byteLength(serialized) > 256 * 1024) throw Error('Output limit');
  output = JSON.parse(serialized);
};
const AsyncFunction = Object.getPrototypeOf(async function() {}).constructor;
await new AsyncFunction('document', 'params', 'emit', 'warnings', 'toMarkdown', 'saveMarkdown', 'previous_results', 'set_output', workerData.code)(
  workerData.document, workerData.params, emit, warnings, toMarkdown, saveMarkdown,
  workerData.previous_results || {fields: {}, steps: [], conflicts: []}, set_output,
);
parentPort.postMessage({proposals, warnings, files, output});
