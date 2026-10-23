const { contextBridge, ipcRenderer } = require('electron')

const subscribe = (channel) => (cb) => {
  const listener = (_e, data) => cb(data)
  ipcRenderer.on(channel, listener)
  return () => ipcRenderer.removeListener(channel, listener)
}

contextBridge.exposeInMainWorld('edge', {
  onMedia: subscribe('media:state'),
  onTheme: subscribe('app:theme'),
  getConfig: () => ipcRenderer.invoke('app:config'),
  command: (cmd, arg) => ipcRenderer.invoke('media:command', cmd, arg),
  setShape: (rect) => ipcRenderer.send('island:shape', rect)
})
