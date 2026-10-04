// 엔진 프로세스 관리 : 기동 · /health 폴링 · 프로세스 트리 종료
const { spawn, spawnSync } = require('child_process');
const fs = require('fs');
const path = require('path');
const { EventEmitter } = require('events');

const ROOT_DIR = path.resolve(__dirname, '..', '..');
const LOG_LINES = 80;

function readEnvPort() {
  // 루트 .env의 ENGINE_PORT (환경변수 우선)
  if (process.env.ENGINE_PORT) return Number(process.env.ENGINE_PORT);
  try {
    const text = fs.readFileSync(path.join(ROOT_DIR, '.env'), 'utf-8');
    const m = text.match(/^\s*ENGINE_PORT\s*=\s*(\d+)\s*$/m);
    if (m) return Number(m[1]);
  } catch {
    // .env 없음
  }
  return 5200;
}

function engineCommand(isPackaged) {
  // 배포 : resources/engine/engine.exe / 개발 : engine/.venv 파이썬
  if (isPackaged) {
    const dir = path.join(process.resourcesPath, 'engine');
    return { cmd: path.join(dir, 'engine.exe'), args: [], cwd: dir };
  }
  const venv = process.platform === 'win32'
    ? path.join(ROOT_DIR, 'engine', '.venv', 'Scripts', 'python.exe')
    : path.join(ROOT_DIR, 'engine', '.venv', 'bin', 'python');
  const cmd = process.env.RETRACE_PYTHON || venv;
  return { cmd, args: ['-m', 'retrace.server'], cwd: path.join(ROOT_DIR, 'engine') };
}

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

class Engine extends EventEmitter {
  constructor({ isPackaged = false, port = readEnvPort() } = {}) {
    super();
    this.isPackaged = isPackaged;
    this.port = port;
    this.url = `http://127.0.0.1:${port}`;
    this.proc = null;
    this.owned = false;   // 직접 띄운 프로세스만 종료
    this.logs = [];
    this.status = { state: 'idle' };  // idle / starting / ready / failed / stopped
    this._killed = false;
  }

  _set(state, extra = {}) {
    this.status = { state, url: this.url, port: this.port, owned: this.owned, ...extra };
    this.emit('status', this.status);
  }

  _log(chunk) {
    for (const line of chunk.toString().split(/\r?\n/)) {
      if (!line) continue;
      this.logs.push(line);
      if (this.logs.length > LOG_LINES) this.logs.shift();
    }
  }

  // /health는 데모 서버 확인(최대 1초)을 포함 → 여유 있게 대기
  async health(timeoutMs = 3000) {
    try {
      const res = await fetch(this.url + '/health', { signal: AbortSignal.timeout(timeoutMs) });
      return res.ok ? await res.json() : null;
    } catch {
      return null;
    }
  }

  async start({ timeoutMs = 20000 } = {}) {
    this.stop();
    this._killed = false;
    this.logs = [];
    this.owned = false;
    this._set('starting');

    // 이미 떠 있는 엔진이면 attach
    const existing = await this.health();
    if (existing) {
      this._set('ready', { health: existing, attached: true });
      return this.status;
    }

    const { cmd, args, cwd } = engineCommand(this.isPackaged);
    if (!fs.existsSync(cmd)) {
      this._set('failed', { reason: 'missing', message: `엔진 실행 파일 없음: ${cmd}`, logs: [] });
      return this.status;
    }

    let exited = null;
    try {
      this.proc = spawn(cmd, [...args, '--port', String(this.port)], {
        cwd,
        windowsHide: true,
        detached: process.platform !== 'win32',  // POSIX : 프로세스 그룹 단위 종료
        env: { ...process.env, PYTHONUNBUFFERED: '1', PYTHONIOENCODING: 'utf-8' },
      });
    } catch (e) {
      this._set('failed', { reason: 'spawn', message: String(e), logs: [] });
      return this.status;
    }
    this.owned = true;
    const proc = this.proc;
    proc.stdout.on('data', (d) => this._log(d));
    proc.stderr.on('data', (d) => this._log(d));
    proc.on('error', (e) => { exited = { code: null, error: String(e) }; });
    proc.on('exit', (code, signal) => {
      exited = exited || { code, signal };
      if (this.proc === proc) this.proc = null;
      // 기동 후 비정상 종료 → 렌더러 통지
      if (!this._killed && this.status.state === 'ready') {
        this._set('stopped', { message: `엔진 종료 (code ${code ?? signal})`, logs: [...this.logs] });
      }
    });

    const deadline = Date.now() + timeoutMs;
    while (Date.now() < deadline) {
      if (exited) {
        const portBusy = this.logs.some((l) => /address already in use|10048|Errno 98/i.test(l));
        this._set('failed', {
          reason: portBusy ? 'port' : 'exit',
          message: portBusy
            ? `포트 ${this.port} 이미 사용 중`
            : `엔진 기동 실패 (code ${exited.code ?? exited.error ?? exited.signal})`,
          logs: [...this.logs],
        });
        return this.status;
      }
      const h = await this.health();
      if (h) {
        this._set('ready', { health: h, attached: false });
        return this.status;
      }
      await sleep(300);
    }
    this.stop();
    this._set('failed', { reason: 'timeout', message: `엔진 응답 없음 (${timeoutMs / 1000}초)`, logs: [...this.logs] });
    return this.status;
  }

  stop() {
    // 동기 종료 : quit 전에 프로세스 트리 정리 완료 보장
    const proc = this.proc;
    if (!proc || !this.owned || proc.exitCode !== null) return;
    this._killed = true;
    this.proc = null;
    try {
      if (process.platform === 'win32') {
        // uvicorn + chromedriver + Chrome 하위 트리 일괄 종료
        spawnSync('taskkill', ['/PID', String(proc.pid), '/T', '/F'], { windowsHide: true, timeout: 10000 });
      } else {
        process.kill(-proc.pid, 'SIGTERM');
      }
    } catch {
      try { proc.kill('SIGKILL'); } catch { /* 이미 종료 */ }
    }
  }
}

module.exports = { Engine, readEnvPort, ROOT_DIR };
