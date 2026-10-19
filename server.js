import { spawn } from 'node:child_process';
import { createRequire } from 'node:module';
import 'dotenv/config';

const require = createRequire(import.meta.url);
const nextCli = require.resolve('next/dist/bin/next');
const port = process.env.PORT || '3001';
const server = spawn(process.execPath, [nextCli, 'start', '-p', port], {
  stdio: 'inherit',
  env: process.env,
});

server.on('error', error => {
  console.error('Unable to start the Next.js server:', error.message);
  process.exitCode = 1;
});
server.on('exit', code => { process.exitCode = code ?? 1; });

for (const signal of ['SIGINT', 'SIGTERM']) {
  process.once(signal, () => server.kill(signal));
}
