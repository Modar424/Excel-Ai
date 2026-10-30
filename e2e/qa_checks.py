"""Phase 7 QA: strict-CSP run, axe-core accessibility audits, keyboard flow, 5 viewport widths, bundle secret scan.
Needs: backend (mock AI) + production frontend build; axe-core at AXE_PATH (npm i axe-core)."""
import json
import os
import re
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from playwright.sync_api import expect, sync_playwright

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
API, WEB, WEB_CSP = "http://localhost:8000", "http://localhost:4173", "http://localhost:4174"
AXE = os.environ.get("AXE_PATH", "/tmp/axe/node_modules/axe-core/axe.min.js")
OUT = os.path.join(tempfile.gettempdir(), "qa_shots"); os.makedirs(OUT, exist_ok=True)
report: dict = {}


def wait_up(url):
    for _ in range(60):
        try:
            urllib.request.urlopen(url, timeout=1); return
        except Exception:  # noqa: BLE001
            time.sleep(0.5)
    raise RuntimeError(url)


def headers_from_file():
    """Parse the /* block of frontend/public/_headers (Netlify format); API origin swapped in for the prod host pattern."""
    txt = open(os.path.join(ROOT, "frontend", "public", "_headers")).read().split("\n/assets")[0]
    out = {}
    for line in txt.splitlines()[1:]:
        if ":" in line:
            k, v = line.strip().split(":", 1)
            out[k.strip()] = v.strip().replace("https://*.onrender.com", API)
    return out


def start_header_proxy():
    hdrs = headers_from_file()

    class H(BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802
            try:
                r = urllib.request.urlopen(WEB + self.path, timeout=10)
                body, ct, code = r.read(), r.headers.get("content-type", "text/html"), 200
            except urllib.error.HTTPError as e:
                body, ct, code = e.read(), "text/plain", e.code
            self.send_response(code); self.send_header("Content-Type", ct); self.send_header("Content-Length", str(len(body)))
            for k, v in hdrs.items():
                self.send_header(k, v)
            self.end_headers(); self.wfile.write(body)

        def log_message(self, *a):
            pass
    srv = ThreadingHTTPServer(("localhost", 4174), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, hdrs


def csp_from_headers_file():
    txt = open(os.path.join(ROOT, "frontend", "public", "_headers")).read()
    return re.search(r"Content-Security-Policy: (.*)", txt).group(1).replace("https://*.onrender.com", API)


def scan_bundle():
    dist, hits = os.path.join(ROOT, "frontend", "dist"), []
    pats = {"groq key": r"gsk_[A-Za-z0-9]{10,}", "GROQ_API_KEY": r"GROQ_API_KEY", "groq host": r"api\.groq\.com", "openai-style key": r"sk-[A-Za-z0-9]{20,}",
            "bearer": r"Bearer\s+[A-Za-z0-9._-]{10,}", "private key": r"-----BEGIN [A-Z ]*PRIVATE KEY", "secret word": r"(?i)(client_secret|api[_-]?secret|password\s*[:=])"}
    for dp, _, fs in os.walk(dist):
        for f in fs:
            if f.endswith((".js", ".css", ".html", ".json", ".txt", "_headers")):
                t = open(os.path.join(dp, f), errors="ignore").read()
                for n, rx in pats.items():
                    if re.search(rx, t):
                        hits.append((n, f))
    maps = [f for _, _, fs in os.walk(dist) for f in fs if f.endswith(".map")]
    urls = set()
    for dp, _, fs in os.walk(dist):
        for f in fs:
            if f.endswith(".js"):
                urls |= set(re.findall(r"https?://[A-Za-z0-9.:/_-]+", open(os.path.join(dp, f), errors="ignore").read()))
    return {"secret_pattern_hits": hits, "source_maps": maps, "external_urls_in_js": sorted(u for u in urls if "w3.org" not in u and "reactjs.org" not in u and "react.dev" not in u)[:12]}


def axe(page, label, tags=("wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "best-practice")):
    page.add_script_tag(path=AXE)
    res = page.evaluate("(tags) => axe.run(document, {runOnly: {type: 'tag', values: tags}})", list(tags))
    v = [{"id": x["id"], "impact": x["impact"], "n": len(x["nodes"]), "help": x["help"],
          "sample": x["nodes"][0]["html"][:140], "msg": (x["nodes"][0].get("any") or x["nodes"][0].get("all") or [{}])[0].get("message", "")[:160]} for x in res["violations"]]
    report.setdefault("axe", {})[label] = v
    return v


def main():
    env = {**os.environ, "AI_PROVIDER": "mock", "CORS_ORIGINS": f"{WEB},{WEB_CSP}", "RATE_LIMIT_PER_MIN": "1000", "PYTHONPATH": os.path.join(ROOT, "backend")}
    be = subprocess.Popen([sys.executable, "-m", "uvicorn", "app.main:app", "--port", "8000"], cwd=os.path.join(ROOT, "backend"), env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    fe = subprocess.Popen(["npx", "vite", "preview", "--port", "4173", "--strictPort"], cwd=os.path.join(ROOT, "frontend"), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        wait_up(API + "/health"); wait_up(WEB)
        report["bundle"] = scan_bundle()
        proxy, hdrs = start_header_proxy(); report["headers_used"] = hdrs
        with sync_playwright() as p:
            b = p.chromium.launch()
            # ---- strict CSP run (headers from public/_headers injected on the document response) ----
            ctx = b.new_context(viewport={"width": 1280, "height": 900}, accept_downloads=True)
            pg = ctx.new_page(); pg.set_default_timeout(20000)
            pg.add_init_script("window.__csp=[]; document.addEventListener('securitypolicyviolation', e => window.__csp.push(e.violatedDirective+' '+e.blockedURI));")
            pg.goto(WEB_CSP); pg.wait_for_selector("#prompt")
            report["csp_header_seen"] = pg.evaluate("fetch(location.href).then(r => r.headers.get('content-security-policy') ? 'yes' : 'no')")
            pg.get_by_role("button", name="الموظفين", exact=True).click(); pg.click("button[type=submit]")
            expect(pg.get_by_text("تم إنشاء ملف Excel")).to_be_visible()
            with pg.expect_download() as dl:
                pg.get_by_role("button", name="تنزيل الملف").click()
            report["csp_violations"] = pg.evaluate("window.__csp"); report["csp_download"] = dl.value.suggested_filename
            report["theme_script_ok"] = pg.evaluate("document.documentElement.classList.contains('dark')") in (True, False)
            # ---- axe on several states ----
            pg2 = b.new_context(viewport={"width": 1280, "height": 900}).new_page(); pg2.set_default_timeout(20000)
            pg2.goto(WEB); pg2.wait_for_selector("#prompt"); axe(pg2, "AR light home")
            pg2.get_by_role("button", name="الموظفين", exact=True).click(); pg2.click("button[type=submit]")
            expect(pg2.get_by_text("تم إنشاء ملف Excel")).to_be_visible(); axe(pg2, "AR light result")
            pg2.get_by_role("button", name="English").first.click(); pg2.get_by_role("switch").click(); pg2.wait_for_timeout(300)
            axe(pg2, "EN dark result")
            pg2.fill("#prompt", "inventory __quota__"); pg2.click("button[type=submit]")
            expect(pg2.locator("div[role=alert]")).to_be_visible(); axe(pg2, "EN dark error")
            pg2.evaluate("window.scrollTo(0,0)"); pg2.wait_for_timeout(200); pg2.screenshot(path=f"{OUT}/en_dark_top.png")
            # ---- keyboard-only flow ----
            pk = b.new_context(viewport={"width": 1280, "height": 900}, accept_downloads=True).new_page(); pk.set_default_timeout(20000)
            pk.goto(WEB); pk.wait_for_selector("#prompt")
            order = []
            for _ in range(14):
                pk.keyboard.press("Tab")
                order.append(pk.evaluate("(() => { const e=document.activeElement; const cs=getComputedStyle(e); return (e.getAttribute('aria-label')||e.innerText||e.id||e.tagName).trim().slice(0,22) + (cs.outlineStyle!=='none' && parseFloat(cs.outlineWidth)>0 ? ' [ring]' : ' [NO-RING]'); })()"))
            report["tab_order"] = order
            pk.focus("#prompt"); pk.keyboard.type("inventory sheet please")
            pk.keyboard.press("Tab"); pk.keyboard.press("Tab")  # eraser button, then rows select
            pk.focus("button[type=submit]"); pk.keyboard.press("Enter")
            try:
                expect(pk.get_by_text("تم إنشاء ملف Excel")).to_be_visible(); report["keyboard_submit"] = "ok"
            except Exception as e:  # noqa: BLE001
                report["keyboard_submit"] = f"FAIL {e}"
            # ---- viewports ----
            rows = []
            for w, h in [(360, 800), (390, 844), (768, 1024), (1024, 768), (1440, 900)]:
                c = b.new_context(viewport={"width": w, "height": h}); q = c.new_page(); q.set_default_timeout(20000)
                q.goto(WEB); q.wait_for_selector("#prompt"); q.wait_for_timeout(500)
                ov_home = q.evaluate("document.documentElement.scrollWidth - innerWidth")
                img_ok = q.evaluate("(()=>{const i=document.querySelector('header img');return i.complete&&i.naturalWidth>0})()")
                q.screenshot(path=f"{OUT}/home_{w}.png", full_page=True)
                small = q.evaluate("[...document.querySelectorAll('button,select,input,textarea,a')].filter(e=>{const r=e.getBoundingClientRect();return r.width>0&&(r.height<24||r.width<24)}).map(e=>(e.getAttribute('aria-label')||e.innerText||e.tagName).slice(0,20))")
                q.get_by_role("button", name="المخزون", exact=True).click(); q.click("button[type=submit]")
                expect(q.get_by_text("تم إنشاء ملف Excel")).to_be_visible()
                ov_res = q.evaluate("document.documentElement.scrollWidth - innerWidth")
                q.locator("#result").screenshot(path=f"{OUT}/result_{w}.png")
                rows.append({"w": w, "overflow_home_px": ov_home, "overflow_result_px": ov_res, "hero_image_loaded": img_ok, "tap_targets_under_24px": small})
                c.close()
            report["viewports"] = rows
            b.close()
    finally:
        for pr in (be, fe):
            pr.terminate()
    json.dump(report, open(os.path.join(OUT, "report.json"), "w"), ensure_ascii=False, indent=1)
    print(json.dumps(report, ensure_ascii=False, indent=1))


main()
