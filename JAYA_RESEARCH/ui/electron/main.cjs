const { app, BrowserWindow } = require('electron');

let mainWindow;

function trustedStartUrl() {
  const rawUrl = process.env.ELECTRON_START_URL;
  if (!rawUrl) {
    throw new Error('ELECTRON_START_URL is required; start Electron through an npm launcher script.');
  }
  const parsed = new URL(rawUrl);
  const loopbackHosts = new Set(['localhost', '127.0.0.1', '[::1]']);
  if (parsed.protocol !== 'http:' || !loopbackHosts.has(parsed.hostname)) {
    throw new Error('ELECTRON_START_URL must use HTTP on an explicit loopback host.');
  }
  return parsed.toString();
}

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1400,
    height: 900,
    webPreferences: {
      nodeIntegration: false,
      contextIsolation: true,
      sandbox: true,
    },
    titleBarStyle: 'hidden', // Modern look
    titleBarOverlay: {
      color: '#0f172a',
      symbolColor: '#ffffff',
    },
  });

  mainWindow.loadURL(trustedStartUrl());

  mainWindow.on('closed', function () {
    mainWindow = null;
  });
}

app.on('ready', () => {
  // Backend is now managed by the external Launcher (src/launcher.py)
  createWindow();
});

app.on('window-all-closed', function () {
  if (process.platform !== 'darwin') {
    app.quit();
  }
});

app.on('activate', function () {
  if (mainWindow === null) {
    createWindow();
  }
});
