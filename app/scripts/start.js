'use strict';
// `npm start`: launches the app with ELECTRON_RUN_AS_NODE removed. Editors
// built on Electron (VS Code among them) export it to child processes, and
// inherited it starts Electron as plain Node instead of opening the window.
const path = require('node:path');
const { spawn } = require('node:child_process');
const electron = require('electron');

const env = { ...process.env };
delete env.ELECTRON_RUN_AS_NODE;

const child = spawn(electron, [path.join(__dirname, '..')], { env, stdio: 'inherit', windowsHide: false });
child.on('close', (code) => process.exit(code ?? 0));
