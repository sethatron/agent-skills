const { spawn } = require('child_process');
const http = require('http');
const fs = require('fs');
const path = require('path');

const OUT_DIR = '/tmp/kb-dag-test';
const TEST_PORT = 9909;
const KB_DAG_PY = path.resolve(__dirname, '../../../kb-dag.py');
const FIXTURE_KB = path.resolve(__dirname, '../fixtures/test-kb.yaml');

function generateFixture() {
  return new Promise((resolve, reject) => {
    const proc = spawn('python3', [
      KB_DAG_PY,
      '--kb', FIXTURE_KB,
      '--output', path.join(OUT_DIR, 'index.html'),
      '--no-serve',
      '--no-open'
    ]);
    let stderr = '';
    proc.stderr.on('data', d => stderr += d);
    proc.on('close', code => {
      if (code === 0) resolve();
      else reject(new Error(`kb-dag.py exited ${code}: ${stderr}`));
    });
  });
}

function startServer(port) {
  return new Promise((resolve, reject) => {
    const mimeTypes = {
      '.html': 'text/html',
      '.js': 'application/javascript',
      '.css': 'text/css',
      '.json': 'application/json',
      '.png': 'image/png',
    };
    const server = http.createServer((req, res) => {
      const urlPath = req.url.split('?')[0];
      const filePath = path.join(OUT_DIR, urlPath === '/' ? 'index.html' : urlPath);
      const ext = path.extname(filePath);
      fs.readFile(filePath, (err, data) => {
        if (err) {
          res.writeHead(404);
          res.end('Not found');
          return;
        }
        res.writeHead(200, { 'Content-Type': mimeTypes[ext] || 'application/octet-stream' });
        res.end(data);
      });
    });
    server.listen(port, () => resolve(server));
    server.on('error', reject);
  });
}

module.exports = { generateFixture, startServer, OUT_DIR, TEST_PORT };
