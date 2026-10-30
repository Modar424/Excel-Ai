"""Measure worst-case text contrast over the hero artwork (axe cannot): hide hero text, sample the pixels behind each
text block, take the brightest 3% (worst case for light text), compare with the real text colour. WCAG AA: 4.5 (3.0 for large text)."""
import io
import os
import subprocess
import sys
import time
import urllib.request

from PIL import Image
from playwright.sync_api import sync_playwright

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WEB = "http://localhost:4173"


def lum(c):
    f = lambda v: (v / 255 / 12.92) if v / 255 <= 0.03928 else (((v / 255) + 0.055) / 1.055) ** 2.4  # noqa: E731
    return 0.2126 * f(c[0]) + 0.7152 * f(c[1]) + 0.0722 * f(c[2])


def ratio(a, b):
    la, lb = sorted((lum(a), lum(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


def main():
    fe = subprocess.Popen(["npx", "vite", "preview", "--port", "4173", "--strictPort"], cwd=os.path.join(ROOT, "frontend"), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(60):
        try:
            urllib.request.urlopen(WEB, timeout=1); break
        except Exception:  # noqa: BLE001
            time.sleep(0.5)
    worst = []
    try:
        with sync_playwright() as p:
            b = p.chromium.launch()
            for lang in ("ar", "en"):
                for w, h in [(360, 800), (390, 844), (768, 1024), (1024, 768), (1440, 900)]:
                    pg = b.new_context(viewport={"width": w, "height": h}).new_page()
                    pg.add_init_script(f"localStorage.setItem('sc-lang','{lang}')")
                    pg.goto(WEB); pg.wait_for_selector("#prompt"); pg.wait_for_timeout(900)
                    sel = "header h1, header h1 span, header p, header li span, header nav a span, header nav button"
                    boxes = pg.evaluate("""(sel) => [...document.querySelectorAll(sel)].filter(e => e.offsetParent !== null && e.children.length === 0 && e.innerText.trim()).map(e => {
                        const r = e.getBoundingClientRect(), cs = getComputedStyle(e);
                        return {t: e.innerText.trim().slice(0, 24), x: r.x, y: r.y + scrollY, w: r.width, h: r.height, color: (()=>{const k=document.createElement('canvas').getContext('2d');k.fillStyle='#000';k.fillStyle=cs.color;k.fillRect(0,0,1,1);const d=k.getImageData(0,0,1,1).data;return `rgb(${d[0]},${d[1]},${d[2]})`})(), clip: cs.webkitBackgroundClip === 'text'};})""", sel)
                    pg.add_style_tag(content="header h1, header h1 span, header p, header li span, header nav * {color: transparent !important; -webkit-text-fill-color: transparent !important; background-image: none !important; border-color: transparent !important} header li span, header p {background: none !important}")
                    pg.wait_for_timeout(200)
                    img = Image.open(io.BytesIO(pg.screenshot(full_page=True))).convert("RGB")
                    for bx in boxes:
                        if bx["w"] < 4 or bx["h"] < 4:
                            continue
                        c = (243, 199, 91) if bx["clip"] else tuple(int(float(v)) for v in bx["color"].replace("rgba(", "").replace("rgb(", "").replace(")", "").split(",")[:3])
                        crop = img.crop((max(0, int(bx["x"])), max(0, int(bx["y"])), min(img.width, int(bx["x"] + bx["w"])), min(img.height, int(bx["y"] + bx["h"]))))
                        data = crop.get_flattened_data() if hasattr(crop, 'get_flattened_data') else crop.getdata()
                        px = sorted(lum(q) for q in data)
                        top = px[int(len(px) * 0.97):] or px[-1:]
                        bright = sum(top) / len(top)
                        lt = lum(c)
                        r = (max(lt, bright) + 0.05) / (min(lt, bright) + 0.05)
                        worst.append((round(r, 2), lang, w, bx["t"], c))
            b.close()
    finally:
        fe.terminate()
    worst.sort()
    print("lowest 10 (ratio, lang, width, text, colour):")
    for r in worst[:10]:
        print(" ", r)
    low = [r for r in worst if r[0] < 4.5]
    print(f"\n{len(worst)} text blocks measured; below 4.5:1 → {len(low)}")
    sys.exit(0)


main()
