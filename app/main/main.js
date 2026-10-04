// Electron main : 엔진 기동 → /health 확인 후 창 표시, 종료 시 엔진 정리
const { app, BrowserWindow, ipcMain, clipboard, shell } = require('electron');
const path = require('path');
const { Engine } = require('./engine');

const engine = new Engine({ isPackaged: app.isPackaged });
let win = null;

function createWindow() {
  win = new BrowserWindow({
    width: 1360,
    height: 880,
    minWidth: 1040,
    minHeight: 680,
    show: false,
    backgroundColor: '#0d1117',
    title: 'Retrace',
    autoHideMenuBar: true,
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
    },
  });
  win.loadFile(path.join(__dirname, '..', 'renderer', 'index.html'));
  // 외부 링크는 기본 브라우저로
  win.webContents.setWindowOpenHandler(({ url }) => {
    shell.openExternal(url);
    return { action: 'deny' };
  });
  win.on('closed', () => { win = null; });
}

function showWindow() {
  if (!win) return;
  if (win.webContents.isLoading()) win.webContents.once('did-finish-load', () => win && win.show());
  else win.show();
}

engine.on('status', (s) => {
  if (win && !win.isDestroyed()) win.webContents.send('engine:status', s);
});

ipcMain.handle('engine:status', () => engine.status);
ipcMain.handle('engine:restart', () => engine.start());
ipcMain.handle('clipboard:write', (_e, text) => {
  clipboard.writeText(String(text ?? ''));
  return true;
});

// 단일 인스턴스 : 엔진 중복 기동 방지
if (!app.requestSingleInstanceLock()) {
  app.quit();
} else {
  app.on('second-instance', () => {
    if (win) {
      if (win.isMinimized()) win.restore();
      win.focus();
    }
  });

  app.whenReady().then(async () => {
    createWindow();
    await engine.start();
    // 성공 · 실패 모두 창 표시 (실패 시 렌더러가 에러 화면)
    showWindow();
  });
}

// 종료 경로 전부에서 엔진 정리 (좀비 방지)
app.on('window-all-closed', () => app.quit());
app.on('before-quit', () => engine.stop());
app.on('will-quit', () => engine.stop());
process.on('exit', () => engine.stop());
for (const sig of ['SIGINT', 'SIGTERM', 'SIGHUP']) {
  process.on(sig, () => {
    engine.stop();
    app.quit();
  });
}
