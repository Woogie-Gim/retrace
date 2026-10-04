// 엔진 프로세스 관리 : 기동 · /health 폴링 · 프로세스 트리 종료 (배포 시 demo-shop 포함)
const { spawn, spawnSync } = require('child_process');
const fs = require('fs');
const path = require('path');
const { EventEmitter } = require('events');

const ROOT_DIR = path.resolve(__dirname, '..', '..');
const LOG_LINES = 80;

function readEnvPort(name = 'ENGINE_PORT', fallback = 5200) {
  // 루트 .env 값 (환경변수 우선)
  if (process.env[name]) return Number(process.env[name]);
  try {
    const text = fs.readFileSync(path.join(ROOT_DIR, '.env'), 'utf-8');
    const m = text.match(new RegExp(`^\\s*${name}\\s*=\\s*(\\d+)\\s*$`, 'm'));
    if (m) return Number(m[1]);
  } catch {
    // .env 없음
  }
  return fallback;
}

function engineCommand(isPackaged, reportsDir) {
  // 배포 : resources/engine/engine.exe (시드는 resources/features, 리포트는 userData) / 개발 : engine/.venv 파이썬
  if (isPackaged) {
    const dir = path.join(process.resourcesPath, 'engine');
    const env = { RETRACE_ROOT: process.resourcesPath };
    if (reportsDir) env.RETRACE_REPORTS_DIR = reportsDir;
    return { cmd: path.join(dir, 'engine.exe'), args: [], cwd: dir, env };
  }
  const venv = process.platform === 'win32'
    ? path.join(ROOT_DIR, 'engine', '.venv', 'Scripts', 'python.exe')
    : path.join(ROOT_DIR, 'engine', '.venv', 'bin', 'python');
  const cmd = process.env.RETRACE_PYTHON || venv;
  return { cmd, args: ['-m', 'retrace.server'], cwd: path.join(ROOT_DIR, 'engine'), env: {} };
}

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

function killTree(proc) {
  // 동기 종료 : quit 전에 프로세스 트리 정리 완료 보장
  if (!proc || proc.exitCode !== null) return;
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

const UTF8 = new TextDecoder('utf-8', { fatal: true });
const CP949 = new TextDecoder('euc-kr');  // WHATWG euc-kr = cp949

function decodeChunk(chunk) {
  // Windows 시스템 에러 메시지는 cp949 바이트로 섞여 나옴 → UTF-8 실패 시 cp949
  if (typeof chunk === 'string') return chunk;
  try {
    return UTF8.decode(chunk);
  } catch {
    return CP949.decode(chunk);
  }
}

async function urlAlive(url, timeoutMs = 1000) {
  try {
    return (await fetch(url, { signal: AbortSignal.timeout(timeoutMs) })).ok;
  } catch {
    return false;
  }
}

class Engine extends EventEmitter {
  constructor({ isPackaged = false, port = readEnvPort(), demoPort = readEnvPort('DEMO_SHOP_PORT', 5100), reportsDir = null } = {}) {
    super();
    this.isPackaged = isPackaged;
    this.port = port;
    this.url = `http://127.0.0.1:${port}`;
    this.demoPort = demoPort;
    this.reportsDir = reportsDir;
    this.proc = null;
    this.demoProc = null;  // 배포 모드에서 직접 띄운 demo-shop
    this.owned = false;   // 직접 띄운 프로세스만 종료
    this.logs = [];
    this.status = { state: 'idle' };  // idle / starting / ready / failed / stopped
    this._killed = false;
  }

  _set(state, extra = {}) {
    this.status = { state, url: this.url, port: this.port, owned: this.owned, packaged: this.isPackaged, ...extra };
    this.emit('status', this.status);
  }

  _log(chunk) {
    for (const line of decodeChunk(chunk).split(/\r?\n/)) {
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

  async _startDemo(timeoutMs = 15000) {
    // 배포 모드 전용 : demo-shop.exe 기동 (이미 떠 있으면 그대로 사용), 실패해도 엔진은 계속
    if (!this.isPackaged) return;
    const probe = `http://127.0.0.1:${this.demoPort}/api/config`;
    if (await urlAlive(probe)) return;
    const cmd = path.join(process.resourcesPath, 'demo-shop.exe');
    if (!fs.existsSync(cmd)) {
      this._log(`[demo-shop] 실행 파일 없음: ${cmd}`);
      return;
    }
    let proc;
    try {
      proc = spawn(cmd, [], {
        cwd: process.resourcesPath,
        windowsHide: true,
        detached: process.platform !== 'win32',
        env: { ...process.env, DEMO_SHOP_PORT: String(this.demoPort), PYTHONUNBUFFERED: '1', PYTHONIOENCODING: 'utf-8' },
      });
    } catch (e) {
      this._log(`[demo-shop] 기동 실패: ${e}`);
      return;
    }
    this.demoProc = proc;
    let exited = false;
    proc.on('error', (e) => { exited = true; this._log(`[demo-shop] ${e}`); });
    proc.on('exit', (code) => {
      exited = true;
      if (this.demoProc === proc) this.demoProc = null;
      this._log(`[demo-shop] 종료 (code ${code})`);
    });
    // onefile 압축 해제 시간 고려
    const deadline = Date.now() + timeoutMs;
    while (!exited && Date.now() < deadline) {
      if (await urlAlive(probe)) return;
      await sleep(300);
    }
  }

  async start({ timeoutMs = 20000 } = {}) {
    this.stop();
    this._killed = false;
    this.logs = [];
    this.owned = false;
    this._set('starting');
    const demoReady = this._startDemo();

    // 이미 떠 있는 엔진이면 attach
    const existing = await this.health();
    if (existing) {
      await demoReady;
      this._set('ready', { health: (await this.health()) || existing, attached: true });
      return this.status;
    }

    const { cmd, args, cwd, env } = engineCommand(this.isPackaged, this.reportsDir);
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
        env: { ...process.env, ...env, PYTHONUNBUFFERED: '1', PYTHONIOENCODING: 'utf-8' },
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
        // demo-shop 기동 대기 후 target_alive 재반영
        await demoReady;
        this._set('ready', { health: (await this.health()) || h, attached: false });
        return this.status;
      }
      await sleep(300);
    }
    this.stop();
    this._set('failed', { reason: 'timeout', message: `엔진 응답 없음 (${timeoutMs / 1000}초)`, logs: [...this.logs] });
    return this.status;
  }

  stop() {
    const demo = this.demoProc;
    this.demoProc = null;
    killTree(demo);
    const proc = this.proc;
    if (!proc || !this.owned || proc.exitCode !== null) return;
    this._killed = true;
    this.proc = null;
    killTree(proc);
  }
}

module.exports = { Engine, readEnvPort, ROOT_DIR };
