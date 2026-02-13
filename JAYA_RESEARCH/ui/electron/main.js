const { app, BrowserWindow } = require('electron');
const path = require('path');
const { spawn } = require('child_process');

let mainWindow;
let apiProcess;

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1400,
    height: 900,
    webPreferences: {
      nodeIntegration: true,
      contextIsolation: false, // For MVP ease
    },
    titleBarStyle: 'hidden', // Modern look
    titleBarOverlay: {
      color: '#0f172a',
      symbolColor: '#ffffff',
    },
  });

  const startUrl = process.env.ELECTRON_START_URL || `file://${path.join(__dirname, '../dist/index.html')}`;
  mainWindow.loadURL(startUrl);

  mainWindow.on('closed', function () {
    mainWindow = null;
  });
}

function startPythonBackend() {
  const scriptPath = path.join(__dirname, '../../src/network/research_api.py');
  // Adjust python command based on env (python/python3)
  apiProcess = spawn('python', [scriptPath]);

  apiProcess.stdout.on('data', (data) => {
    console.log(`[API]: ${data}`);
  });

  apiProcess.stderr.on('data', (data) => {
    console.error(`[API Error]: ${data}`);
  });
}

app.on('ready', () => {
  // Backend is now managed by the external Launcher (src/launcher.py)
  createWindow();
});

app.on('window-all-closed', function () {
  if (process.platform !== 'darwin') {
    if (apiProcess) apiProcess.kill();
    app.quit();
  }
});

app.on('activate', function () {
  if (mainWindow === null) {
    createWindow();
  }
});
