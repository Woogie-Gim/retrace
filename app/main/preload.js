// 렌더러 노출 API (contextIsolation)
const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('retrace', {
  engine: () => ipcRenderer.invoke('engine:status'),
  restart: () => ipcRenderer.invoke('engine:restart'),
  onStatus: (fn) => {
    const listener = (_e, s) => fn(s);
    ipcRenderer.on('engine:status', listener);
    return () => ipcRenderer.removeListener('engine:status', listener);
  },
  copy: (text) => ipcRenderer.invoke('clipboard:write', text),
});
