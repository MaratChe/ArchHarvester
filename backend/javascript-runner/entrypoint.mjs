import {Worker} from 'node:worker_threads';
let input = '';
for await (const chunk of process.stdin) {
  input += chunk;
  if (Buffer.byteLength(input) > 16 * 1024 * 1024) process.exit(1);
}
const worker = new Worker(new URL('./worker.mjs', import.meta.url), {
  workerData: JSON.parse(input),
  resourceLimits: {maxOldGenerationSizeMb: 128, stackSizeMb: 4},
  stdout: true, stderr: true,
});
// Drain user logs without contaminating the StepResult protocol.
worker.stdout.resume(); worker.stderr.resume();
const timer = setTimeout(() => {worker.terminate(); process.exit(1);}, 25000);
worker.once('message', result => {
  clearTimeout(timer);
  const output = JSON.stringify(result);
  if (Buffer.byteLength(output) > 1024 * 1024) process.exit(1);
  process.stdout.write(output, () => process.exit(0));
});
worker.once('error', () => {clearTimeout(timer); process.exit(1);});
worker.once('exit', () => {clearTimeout(timer); process.exit(1);});
