// Renders the 1128x191 LinkedIn Lead Gen Form header image.
const { chromium } = require('playwright');
const fs = require('fs'), path = require('path');
const uri = f => 'data:image/png;base64,' + fs.readFileSync(path.join(__dirname, f)).toString('base64');
const html = `<!doctype html><html><head><meta charset="utf-8"><style>
*{margin:0;padding:0;box-sizing:border-box}
body{width:1128px;height:191px;overflow:hidden;font-family:'Inter',sans-serif;background:#f7f8fa;position:relative;-webkit-font-smoothing:antialiased}
.b1{position:absolute;width:700px;height:700px;border-radius:50%;right:-180px;top:-300px;
 background:linear-gradient(135deg,#12b84a,#2fa7a3 50%,#8a7cff);opacity:.22;filter:blur(70px)}
.b2{position:absolute;width:420px;height:420px;border-radius:50%;left:-140px;bottom:-260px;background:#dce8e2;filter:blur(40px)}
.row{position:absolute;inset:0;display:flex;align-items:center;justify-content:space-between;padding:0 120px}
img{height:64px}
.t{font-size:30px;font-weight:800;letter-spacing:-.02em;color:#0b1220;text-align:right}
.t span{background:linear-gradient(135deg,#12b84a,#2fa7a3 50%,#8a7cff);-webkit-background-clip:text;background-clip:text;color:transparent}
</style></head><body><div class="b1"></div><div class="b2"></div>
<div class="row"><img src="${uri('logo-full-color.png')}"><div class="t">Ask your venue <span>anything.</span></div></div></body></html>`;
(async () => {
  const b = await chromium.launch();
  const p = await b.newPage({ viewport: { width: 1128, height: 191 }, deviceScaleFactor: 1 });
  await p.setContent(html, { waitUntil: 'load' });
  await p.evaluate(() => document.fonts.ready);
  await p.screenshot({ path: path.join(__dirname, 'form-header-1128x191.png') });
  await b.close();
})();
