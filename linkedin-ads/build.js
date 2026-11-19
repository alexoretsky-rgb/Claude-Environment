// Renders the accesso Intelligence warm-layer LinkedIn ads to PNG.
// Usage: node build.js   (run from this folder)
const { chromium } = require('playwright');
const path = require('path');
const fs = require('fs');
const uri = f => 'data:image/png;base64,' + fs.readFileSync(path.join(__dirname, f)).toString('base64');
const LOGO = uri('logo-full-color.png'), ROUNDEL = uri('roundel.png');

const C = {
  teal: '#2fa7a3', peri: '#8a7cff', green: '#12b84a',
  midnight: '#0b1220', slate: '#485563', mist: '#dce8e2', cloud: '#f7f8fa',
};
const GRAD = `linear-gradient(135deg, ${C.green} 0%, ${C.teal} 50%, ${C.peri} 100%)`;

const css = `
* { box-sizing: border-box; margin: 0; padding: 0; }
html, body { width: 1080px; height: 1080px; }
body { font-family: 'Inter', sans-serif; color: ${C.midnight}; background: ${C.cloud};
  position: relative; overflow: hidden; -webkit-font-smoothing: antialiased; }
.blob { position: absolute; width: 760px; height: 760px; border-radius: 50%;
  background: ${GRAD}; opacity: .16; filter: blur(90px); top: -300px; right: -260px; }
.blob2 { position: absolute; width: 520px; height: 520px; border-radius: 50%;
  background: ${C.mist}; filter: blur(60px); bottom: -220px; left: -160px; opacity: .9; }
.wrap { position: absolute; inset: 0; padding: 72px 76px 64px; display: flex; flex-direction: column; }
.eyebrow { font-size: 22px; font-weight: 700; letter-spacing: .12em; text-transform: uppercase; color: ${C.teal}; }
h1 { font-size: 64px; line-height: 1.05; font-weight: 800; letter-spacing: -.025em; margin-top: 18px; }
h1 .g { background: ${GRAD}; -webkit-background-clip: text; background-clip: text; color: transparent; }
.ask { margin-top: 44px; display: flex; align-items: center; gap: 18px; background: #fff;
  border-radius: 999px; padding: 18px 18px 18px 22px; box-shadow: 0 10px 30px rgba(11,18,32,.08);
  border: 2px solid rgba(138,124,255,.35); }
.ask img { width: 46px; height: 46px; object-fit: contain; }
.ask .q { flex: 1; font-size: 31px; font-weight: 600; letter-spacing: -.01em; }
.ask .send { width: 58px; height: 58px; border-radius: 50%; background: ${C.peri};
  display: grid; place-items: center; }
.card { margin-top: 22px; background: #fff; border-radius: 28px; padding: 32px 36px 34px;
  box-shadow: 0 18px 50px rgba(11,18,32,.10); flex: 1; display: flex; flex-direction: column; }
.card .lbl { display: flex; align-items: center; gap: 10px; font-size: 18px; font-weight: 700;
  color: ${C.slate}; letter-spacing: .02em; }
.card .lbl i { width: 10px; height: 10px; border-radius: 50%; background: ${GRAD}; display: inline-block; }
.card p { font-size: 27px; line-height: 1.38; margin-top: 14px; color: ${C.midnight}; }
.card p b { font-weight: 700; }
.chart { margin-top: auto; padding-top: 18px; }
.foot { margin-top: 30px; display: flex; align-items: center; justify-content: space-between; }
.foot .logo { height: 58px; }
.foot .pill { font-size: 22px; font-weight: 700; color: #fff; background: ${GRAD};
  padding: 16px 30px; border-radius: 999px; }
.foot .step { font-size: 20px; font-weight: 600; color: ${C.slate}; }
.legend { display: flex; gap: 22px; font-size: 19px; color: ${C.slate}; font-weight: 600; margin-bottom: 10px; }
.legend span { display: inline-flex; align-items: center; gap: 8px; }
.sw { width: 16px; height: 16px; border-radius: 4px; display: inline-block; }
.hrow { display: grid; grid-template-columns: 250px 1fr 100px; align-items: center; gap: 18px;
  font-size: 25px; font-weight: 600; margin-top: 26px; }
.track { height: 44px; border-radius: 8px; background: ${C.cloud}; position: relative; overflow: hidden; }
.fill { position: absolute; left: 0; top: 0; bottom: 0; border-radius: 8px; }
.delta { text-align: right; color: ${C.slate}; font-weight: 700; }
`;

const send = `<svg width="26" height="26" viewBox="0 0 24 24" fill="none"><path d="M5 12h13M12 5l7 7-7 7" stroke="#fff" stroke-width="2.6" stroke-linecap="round" stroke-linejoin="round"/></svg>`;

// Hourly forecast vs actual, dip from early afternoon.
function attendanceChart(h = 190) {
  const hours = ['10a','11a','12p','1p','2p','3p','4p','5p'];
  const fc = [62, 88, 100, 96, 90, 80, 64, 44];
  const ac = [60, 86, 97, 72, 58, 55, 49, 36];
  const W = 856, gap = 22, bw = (W - gap * (hours.length - 1)) / hours.length;
  let s = `<svg width="${W}" height="${h + 34}" viewBox="0 0 ${W} ${h + 34}">`;
  s += `<defs><linearGradient id="ga" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="${C.green}"/><stop offset=".5" stop-color="${C.teal}"/><stop offset="1" stop-color="${C.peri}"/></linearGradient></defs>`;
  hours.forEach((t, i) => {
    const x = i * (bw + gap), fh = fc[i] / 100 * h, ah = ac[i] / 100 * h;
    s += `<rect x="${x}" y="${h - fh}" width="${bw}" height="${fh}" rx="8" fill="${C.mist}"/>`;
    s += `<rect x="${x + 12}" y="${h - ah}" width="${bw - 24}" height="${ah}" rx="6" fill="${i >= 3 ? C.peri : C.teal}"/>`;
    s += `<text x="${x + bw / 2}" y="${h + 28}" text-anchor="middle" font-size="18" font-weight="600" fill="${C.slate}" font-family="Inter">${t}</text>`;
  });
  return `<div class="legend"><span><i class="sw" style="background:${C.mist}"></i>Forecast</span><span><i class="sw" style="background:${C.teal}"></i>Actual</span><span><i class="sw" style="background:${C.peri}"></i>Rain from 1pm</span></div>` + s + `</svg>`;
}

function hbars(rows) {
  return rows.map(r => `<div class="hrow"><span>${r[0]}</span><div class="track"><div class="fill" style="width:${r[1]}%;background:${r[3] || C.teal}"></div></div><span class="delta">${r[2]}</span></div>`).join('');
}

const staffChart = () => `<div class="legend"><span>Forecast visitors vs. last Saturday, 11am to 3pm</span></div>` + hbars([
  ['Food &amp; beverage', 92, '+22%', C.peri],
  ['Main entrance', 78, '+15%', C.peri],
  ['Rides &amp; attractions', 60, '+6%', C.teal],
  ['Retail', 44, '+2%', C.teal],
]);

const reviewChart = () => `<div class="legend"><span>Share of visitor review mentions, this month</span></div>` + hbars([
  ['Queue times', 88, '▲ 18%', C.peri],
  ['Food prices', 58, '▲ 6%', C.teal],
  ['Parking', 40, '▲ 3%', C.teal],
  ['Cleanliness', 26, '▼ 9%', C.mist],
]);

const logo = `<img class="logo" src="${LOGO}">`;

function questionCard({ eyebrow, title, q, answer, chart, foot }) {
  return `<div class="blob"></div><div class="blob2"></div><div class="wrap">
    <div class="eyebrow">${eyebrow}</div>
    ${title ? `<h1>${title}</h1>` : ''}
    <div class="ask"><img src="${ROUNDEL}"><div class="q">${q}</div><div class="send">${send}</div></div>
    <div class="card"><div class="lbl"><i></i>accesso Intelligence</div><p>${answer}</p><div class="chart">${chart}</div></div>
    <div class="foot">${logo}${foot}</div></div>`;
}

const ads = {
  'ad1-single-image-1200': {
    size: 1200,
    html: questionCard({
      eyebrow: 'Decision intelligence for attractions',
      title: 'Ask your venue <span class="g">anything.</span>',
      q: 'Why did attendance dip last Saturday?',
      answer: 'Attendance finished <b>14% below forecast</b>. Rain from 1pm cut walk-up sales while advance tickets held steady. Visitor reviews that day mention long indoor queues.',
      chart: attendanceChart(190),
      foot: `<span class="pill">Request a demo</span>`,
    }),
  },
  'carousel-1-attendance': {
    size: 1080,
    html: questionCard({
      eyebrow: 'Questions operators ask',
      q: 'Why did attendance dip last Saturday?',
      answer: 'Attendance finished <b>14% below forecast</b>. Rain from 1pm cut walk-up sales while advance tickets held steady.',
      chart: attendanceChart(300),
      foot: `<span class="step">1 / 3 &nbsp;→</span>`,
    }),
  },
  'carousel-2-staffing': {
    size: 1080,
    html: questionCard({
      eyebrow: 'Questions operators ask',
      q: 'Where will we need more staff this weekend?',
      answer: 'Saturday midday is forecast <b>22% busier</b> at food &amp; beverage. Sunny weather and a school holiday are driving demand. Consider adding to the lunch shift.',
      chart: staffChart(),
      foot: `<span class="step">2 / 3 &nbsp;→</span>`,
    }),
  },
  'carousel-3-reviews': {
    size: 1080,
    html: questionCard({
      eyebrow: 'Questions operators ask',
      q: 'What are visitors complaining about most?',
      answer: '<b>Queue times</b>, up 18% in reviews this month, mostly at your two headline rides. Mentions of cleanliness are down.',
      chart: reviewChart(),
      foot: `<span class="step">3 / 3 &nbsp;→</span>`,
    }),
  },
  'carousel-4-cta': {
    size: 1080,
    html: `<div class="blob" style="opacity:.22"></div><div class="blob2"></div>
    <div class="wrap" style="justify-content:center;align-items:flex-start">
      <img src="${ROUNDEL}" style="height:120px;margin-bottom:44px">
      <div class="eyebrow">Your turn</div>
      <h1 style="font-size:76px">See it answer the questions <span class="g">you ask most.</span></h1>
      <p style="font-size:32px;line-height:1.4;color:${C.slate};margin-top:28px;max-width:820px">A 30-minute demo built around your venue type and your priorities for 2027.</p>
      <div class="foot" style="width:100%;margin-top:auto">${logo}<span class="pill" style="font-size:26px;padding:20px 38px">Request a demo</span></div>
    </div>`,
  },
};

(async () => {
  const browser = await chromium.launch();
  for (const [name, ad] of Object.entries(ads)) {
    const page = await browser.newPage({ viewport: { width: 1080, height: 1080 }, deviceScaleFactor: ad.size / 1080 });
    const html = `<!doctype html><html><head><meta charset="utf-8"><base href="file://${__dirname}/"><style>${css}</style></head><body>${ad.html}</body></html>`;
    await page.setContent(html, { waitUntil: 'load' });
    await page.evaluate(() => document.fonts.ready);
    await page.screenshot({ path: path.join(__dirname, `${name}.png`) });
    await page.close();
    console.log('wrote', name);
  }
  await browser.close();
})();
