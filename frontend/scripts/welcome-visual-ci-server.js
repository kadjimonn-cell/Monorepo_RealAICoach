const { express } = require('@realaicoach/web-runtime');
const path = require('path');

const app = express();
const port = Number(process.env.WELCOME_VISUAL_PORT || 4173);
const distRoot = path.resolve(__dirname, '..', 'dist');
const clientRoot = path.join(distRoot, 'client');
const serverRoot = path.join(distRoot, 'server');

app.use(express.static(clientRoot, { extensions: ['html'] }));
app.use(express.static(serverRoot, { extensions: ['html'] }));
app.get(/.*/, (_req, res) => {
  const htmlFile = _req.path.startsWith('/welcome') ? 'welcome.html' : 'index.html';
  res.sendFile(path.join(serverRoot, htmlFile));
});

app.listen(port, '0.0.0.0', () => {
  console.log(`[welcome-visual-ci] serving ${distRoot} on http://127.0.0.1:${port}`);
});