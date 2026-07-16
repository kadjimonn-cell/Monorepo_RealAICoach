/* eslint-env node */
/* SEO post-processor: injects titles, meta descriptions, canonical, OpenGraph/Twitter cards
   into the static export's server/*.html pages, and generates sitemap.xml + robots.txt.
   Usage: node scripts/seo.js <dist_dir>   (dist_dir contains client/ and server/) */
const fs = require('fs');
const path = require('path');

const DIST = path.resolve(process.argv[2] || path.join(__dirname, '..', 'dist'));
const SERVER_DIR = path.join(DIST, 'server');
const CLIENT_DIR = path.join(DIST, 'client');

function readEnvBaseUrl() {
  if (process.env.SEO_BASE_URL) return process.env.SEO_BASE_URL.replace(/\/$/, '');
  try {
    const env = fs.readFileSync(path.join(__dirname, '..', '.env'), 'utf8');
    const m = env.match(/^REACT_APP_BACKEND_URL=(.+)$/m);
    if (m) return m[1].trim().replace(/\/$/, '');
  } catch { /* noop */ }
  return 'https://realaicoach.app';
}
const BASE = readEnvBaseUrl();

const SITE_NAME = 'RealAICoach';
const DEFAULT_DESC = 'RealAICoach offers enterprise-grade AI tools for coaching, productivity, health, finance, and career growth. AI-powered insights, progress tracking, and personalized guidance.';
const OG_IMAGE = `${BASE}/og-image.png`;

const t = (s) => `${s} | ${SITE_NAME}`;
const PAGES = {
  '': { title: 'RealAICoach — AI-Powered Coaching & Productivity Platform', desc: DEFAULT_DESC },
  'welcome': { title: 'RealAICoach — Elevate Your Professional Trajectory', desc: 'AI-driven coaching, live performance intelligence, and precision growth plans engineered for professionals.' },
  'about': { title: t('About'), desc: 'Learn about RealAICoach — the enterprise AI operating layer for coaching, growth, and productivity.' },
  'about-us': { title: t('About Us'), desc: 'The team and mission behind RealAICoach, the enterprise AI coaching platform.' },
  'careers': { title: t('Careers'), desc: 'Build the future with an enterprise AI team. Explore open roles at RealAICoach.' },
  'career': { title: t('Career Hub'), desc: 'AI-powered career coaching, job search intelligence, and professional growth tools.' },
  'blog': { title: t('Blog'), desc: 'Insights on AI coaching, productivity, career growth, and the future of work.' },
  'faq': { title: t('FAQ'), desc: 'Frequently asked questions about RealAICoach plans, security, and features.' },
  'features': { title: t('All Features'), desc: 'Explore 37+ AI-powered tools: coaching, health, finance, travel, learning, and more.' },
  'features/travel-visa': { title: t('Travel Visa Coach'), desc: 'Global visa learning platform: country visa tracks, AI document checklists, interview simulation, and embassy directory for 30 countries.' },
  'features/assistant': { title: t('AI Personal Assistant'), desc: 'Your always-on AI assistant for tasks, planning, and productivity.' },
  'features/ai-chatbot': { title: t('AI Chatbot'), desc: 'Conversational AI assistant powered by leading language models.' },
  'features/ai-writer': { title: t('AI Writer'), desc: 'Draft, edit, and polish professional content with AI assistance.' },
  'features/ai-copywriter': { title: t('AI Copywriter'), desc: 'High-converting marketing copy generated and refined by AI.' },
  'features/ai-search': { title: t('AI Search'), desc: 'Answer-focused AI search across knowledge and the web.' },
  'features/ai-private-search': { title: t('Private AI Search'), desc: 'Privacy-first AI search with no tracking.' },
  'features/ai-vision': { title: t('AI Vision'), desc: 'Image understanding and visual analysis powered by AI.' },
  'features/ai-photo': { title: t('AI Photo Studio'), desc: 'AI-powered photo enhancement and creative editing.' },
  'features/ai-video': { title: t('AI Video Studio'), desc: 'Create and analyze video content with AI.' },
  'features/ai-speech': { title: t('AI Speech Studio'), desc: 'Text-to-speech and voice AI tools for creators and teams.' },
  'features/audio-studio': { title: t('Audio Studio'), desc: 'Podcasts, audio learning, and AI-assisted audio tools.' },
  'features/my-podcasts': { title: t('My Podcasts'), desc: 'Discover, follow, and listen to podcasts with AI summaries.' },
  'features/ai-cognitive': { title: t('Cognitive Training'), desc: 'AI-driven brain training and cognitive performance tracking.' },
  'features/ai-automations': { title: t('AI Automations'), desc: 'Automate workflows with intelligent AI-powered triggers.' },
  'features/ai-enterprise': { title: t('Enterprise Copilot'), desc: 'AI copilot for enterprise operations, insights, and decisions.' },
  'features/ai-found-love': { title: t('AI Relationship Coach'), desc: 'AI-guided relationship insights and coaching.' },
  'features/analytics-reports': { title: t('Analytics & Reports'), desc: 'Performance analytics, KPIs, and AI-generated reports.' },
  'features/bill-generator': { title: t('Bill Generator'), desc: 'Create professional invoices and bills in seconds.' },
  'features/buy-smart-home': { title: t('Smart Home Buying'), desc: 'AI guidance for real-estate decisions and smart home purchases.' },
  'features/content-studio': { title: t('Content Studio'), desc: 'Plan, create, and optimize content with AI workflows.' },
  'features/daily-meditation': { title: t('Daily Meditation'), desc: 'Guided meditations and mindfulness with AI personalization.' },
  'features/decision-coach': { title: t('Decision Coach'), desc: 'Structured AI frameworks for better decisions.' },
  'features/fitness': { title: t('Fitness Coach'), desc: 'AI workout plans, tracking, and fitness coaching.' },
  'features/health-dashboard': { title: t('Health Dashboard'), desc: 'Unified health metrics with AI wellness insights.' },
  'features/medimate': { title: t('MediMate'), desc: 'AI health guide for symptoms, wellness, and medical literacy.' },
  'features/lexicon-intelligence': { title: t('Lexicon Intelligence'), desc: 'Vocabulary, language mastery, and AI word intelligence.' },
  'features/pennypilot': { title: t('PennyPilot Finance'), desc: 'Personal finance tracking and AI money coaching.' },
  'features/school-tutor': { title: t('School Tutor'), desc: 'AI tutoring across subjects for students of all levels.' },
  'features/smart-cars': { title: t('Smart Cars'), desc: 'AI car buying guidance, comparisons, and ownership insights.' },
  'features/smartbuy': { title: t('SmartBuy'), desc: 'AI-assisted purchasing decisions and product comparisons.' },
  'features/sports': { title: t('Sports Hub'), desc: 'Live sports insights, predictions, and AI analysis.' },
  'features/travelpal': { title: t('TravelPal'), desc: 'AI travel planning: itineraries, budgets, and destination intel.' },
  'features/watch-videos': { title: t('Watch & Learn Videos'), desc: 'Curated learning videos with AI summaries and progress tracking.' },
  'features/flappy-bird': { title: t('Flappy Bird Game'), desc: 'Take a break with the classic Flappy Bird game.' },
  'features/fps-game': { title: t('FPS Game'), desc: 'Browser FPS mini-game for quick breaks.' },
};

const SKIP_PREFIXES = ['admin', 'auth/', '(tabs)', '+not-found', '_sitemap', 'api'];

function esc(s) {
  return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/"/g, '&quot;');
}

function buildTags(route, title, desc) {
  const url = route ? `${BASE}/${route}` : `${BASE}/`;
  return [
    `<link rel="canonical" href="${url}"/>`,
    `<meta property="og:site_name" content="${SITE_NAME}"/>`,
    `<meta property="og:type" content="website"/>`,
    `<meta property="og:url" content="${url}"/>`,
    `<meta property="og:title" content="${esc(title)}"/>`,
    `<meta property="og:description" content="${esc(desc)}"/>`,
    `<meta property="og:image" content="${OG_IMAGE}"/>`,
    `<meta property="og:image:width" content="1264"/>`,
    `<meta property="og:image:height" content="848"/>`,
    `<meta name="twitter:card" content="summary_large_image"/>`,
    `<meta name="twitter:title" content="${esc(title)}"/>`,
    `<meta name="twitter:description" content="${esc(desc)}"/>`,
    `<meta name="twitter:image" content="${OG_IMAGE}"/>`,
  ].join('');
}

function processHtml(filePath, route) {
  let html = fs.readFileSync(filePath, 'utf8');
  if (html.includes('property="og:title"')) {
    html = html.replace(/<link rel="canonical"[^>]*\/>|<meta (?:property="og:[^"]*"|name="twitter:[^"]*")[^>]*\/>/g, '');
  }
  const mapped = PAGES[route];
  const existingTitle = (html.match(/<title>([^<]*)<\/title>/) || [])[1] || SITE_NAME;
  const existingDesc = (html.match(/<meta name="description" content="([^"]*)"/) || [])[1] || DEFAULT_DESC;
  const title = mapped ? mapped.title : existingTitle;
  const desc = mapped ? mapped.desc : existingDesc;
  if (mapped) {
    html = html.replace(/<title>[^<]*<\/title>/, `<title>${esc(title)}</title>`);
    if (html.includes('<meta name="description"')) {
      html = html.replace(/<meta name="description" content="[^"]*"\s*\/?>/, `<meta name="description" content="${esc(desc)}"/>`);
    } else {
      html = html.replace('</title>', `</title><meta name="description" content="${esc(desc)}"/>`);
    }
  }
  html = html.replace('</head>', `${buildTags(route, title, desc)}</head>`);
  fs.writeFileSync(filePath, html);
  for (const ext of ['.br', '.gz']) {
    const pre = `${filePath}${ext}`;
    if (fs.existsSync(pre)) fs.rmSync(pre);
  }
}

function collectRoutes() {
  const out = [];
  const walk = (dir, prefix) => {
    for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
      const rel = prefix ? `${prefix}/${entry.name}` : entry.name;
      if (entry.isDirectory()) { walk(path.join(dir, entry.name), rel); continue; }
      if (!entry.name.endsWith('.html')) continue;
      let route = rel.replace(/\.html$/, '');
      if (route.endsWith('/index')) route = route.slice(0, -6);
      if (route === 'index') route = '';
      if (route.includes('[')) continue;
      if (SKIP_PREFIXES.some((p) => route === p.replace(/\/$/, '') || route.startsWith(p))) continue;
      out.push({ route, file: path.join(dir, entry.name) });
    }
  };
  walk(SERVER_DIR, '');
  return out;
}

function writeSitemapAndRobots() {
  const publicRoutes = ['', 'welcome', 'about', 'about-us', 'careers', 'career', 'blog', 'faq', 'features',
    ...Object.keys(PAGES).filter((r) => r.startsWith('features/'))];
  const now = new Date().toISOString().slice(0, 10);
  const urls = [...new Set(publicRoutes)]
    .map((r) => `  <url><loc>${r ? `${BASE}/${r}` : `${BASE}/`}</loc><lastmod>${now}</lastmod><changefreq>weekly</changefreq></url>`)
    .join('\n');
  fs.writeFileSync(path.join(CLIENT_DIR, 'sitemap.xml'),
    `<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n${urls}\n</urlset>\n`);
  fs.writeFileSync(path.join(CLIENT_DIR, 'robots.txt'),
    `User-agent: *\nAllow: /\nDisallow: /admin\nDisallow: /auth\nDisallow: /api\n\nSitemap: ${BASE}/sitemap.xml\n`);
}

function copyOgImage() {
  const src = path.join(__dirname, '..', 'assets', 'og-image.png');
  if (fs.existsSync(src)) fs.copyFileSync(src, path.join(CLIENT_DIR, 'og-image.png'));
}

if (!fs.existsSync(SERVER_DIR) || !fs.existsSync(CLIENT_DIR)) {
  console.error(`FATAL: ${DIST} does not contain server/ + client/ dirs`);
  process.exit(1);
}

const routes = collectRoutes();
routes.forEach(({ route, file }) => processHtml(file, route));
writeSitemapAndRobots();
copyOgImage();
console.log(`SEO injected into ${routes.length} pages (base=${BASE}); sitemap.xml + robots.txt + og-image written to ${CLIENT_DIR}`);
