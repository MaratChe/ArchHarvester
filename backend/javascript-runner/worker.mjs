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
const AsyncFunction = Object.getPrototypeOf(async function() {}).constructor;
await new AsyncFunction('document', 'params', 'emit', 'warnings', 'toMarkdown', 'saveMarkdown', workerData.code)(
  workerData.document, workerData.params, emit, warnings, toMarkdown, saveMarkdown,
);
parentPort.postMessage({proposals, warnings, files});
