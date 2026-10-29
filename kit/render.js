// Render a post kit (carousel PNGs + caption, script, X post) with the engine's own slide code.
//   node kit/render.js post.json out/dir [--handle @you] [--theme auto|dawn|...]
const fs = require("fs");
const path = require("path");
const { chromium } = require("playwright");

const root = path.resolve(__dirname, "..");
const fontsDir = path.join(root, "brand", "fonts");
const FACES = [
  ["Barlow Condensed", 800, "normal", "BarlowCondensed-ExtraBold.ttf"],
  ["Barlow Condensed", 700, "normal", "BarlowCondensed-Bold.ttf"],
  ["Barlow", 700, "normal", "Barlow-Bold.ttf"],
  ["Newsreader", 400, "normal", "Newsreader-Regular.ttf"],
  ["Newsreader", 500, "normal", "Newsreader-Medium.ttf"],
  ["Newsreader", 400, "italic", "Newsreader-Italic.ttf"],
];
const PILLAR_SHORT = { 1: "Faith", 2: "Rhythms", 3: "Gut & Food", 4: "Table", 5: "Strength", 6: "Home & Discernment", 7: "Community", 8: "Calling" };

function arg(name, fallback) {
  const i = process.argv.indexOf(name);
  return i > 0 ? process.argv[i + 1] : fallback;
}

(async () => {
  const [postPath, outDir] = process.argv.slice(2);
  if (!postPath || !outDir) { console.error("usage: node kit/render.js post.json out/dir [--handle @you] [--theme auto]"); process.exit(1); }
  const post = JSON.parse(fs.readFileSync(postPath, "utf8"));
  const settings = { handle: arg("--handle", "@yourhandle"), theme: arg("--theme", "auto") };
  fs.mkdirSync(outDir, { recursive: true });

  const css = FACES.map(([fam, wt, st, file]) =>
    `@font-face{font-family:"${fam}";font-weight:${wt};font-style:${st};src:url(data:font/ttf;base64,${fs.readFileSync(path.join(fontsDir, file)).toString("base64")})}`).join("");
  const renderer = fs.readFileSync(path.join(root, "render", "slides.generated.js"), "utf8");

  const browser = await chromium.launch();
  const page = await browser.newPage();
  await page.setContent(`<style>${css}</style><script>
    const settings = ${JSON.stringify(settings)};
    const P = Object.fromEntries(Object.entries(${JSON.stringify(PILLAR_SHORT)}).map(([n, short]) => [n, { short }]));
    ${renderer}
  </script>`);
  const pngs = await page.evaluate(async post => {
    post.cover = null; // Photos live in the engine's asset store; add them there.
    await loadFonts();
    return post.slides.map((_, i) => { const c = document.createElement("canvas"); c.width = W; c.height = H; drawSlide(c, post, i); return c.toDataURL("image/png"); });
  }, post);
  await browser.close();

  const slug = (post.title || "post").toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "").slice(0, 40);
  pngs.forEach((u, i) => fs.writeFileSync(path.join(outDir, `${slug}-${String(i + 1).padStart(2, "0")}.png`), Buffer.from(u.split(",")[1], "base64")));
  const tags = (post.hashtags || []).map(h => "#" + h).join(" ");
  fs.writeFileSync(path.join(outDir, "caption.txt"), post.caption + (tags ? "\n\n" + tags : ""));
  fs.writeFileSync(path.join(outDir, "video-script.txt"), post.script || "");
  fs.writeFileSync(path.join(outDir, "x-post.txt"), post.xpost || "");
  console.log(`${pngs.length} slides + caption, script, X post -> ${outDir}`);
})();
