import { spawnSync } from 'node:child_process';
import { existsSync } from 'node:fs';
import path from 'node:path';

const python = process.platform === 'win32'
  ? path.join('.venv', 'Scripts', 'python.exe')
  : path.join('.venv', 'bin', 'python');

if (!existsSync(python)) {
  console.error('Project virtual environment is missing. Create .venv and install requirements.txt first.');
  process.exit(1);
}

const result = spawnSync(python, ['-m', 'unittest', 'discover', '-s', 'solver', '-v'], { stdio: 'inherit', windowsHide: true });
if (result.error) {
  console.error(result.error.message);
  process.exit(1);
}
process.exit(result.status ?? 1);
