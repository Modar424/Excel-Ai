"""Post-deploy check against a LIVE deployment. Usage:
  python scripts/verify_deployment.py https://api.example.com https://site.example.com [--live-ai]
Without --live-ai it makes no AI request (no quota used). With --live-ai it makes 2 real generations (AR+EN)."""
import base64, json, sys, time, urllib.request, urllib.error

def req(url, data=None, headers=None, method=None, timeout=120):
    r = urllib.request.Request(url, data=data, headers=headers or {}, method=method)
    t = time.time()
    try:
        with urllib.request.urlopen(r, timeout=timeout) as resp:
            return resp.status, dict(resp.headers), resp.read(), time.time() - t
    except urllib.error.HTTPError as e:
        return e.code, dict(e.headers), e.read(), time.time() - t

def main():
    api, origin = sys.argv[1].rstrip("/"), sys.argv[2].rstrip("/")
    live = "--live-ai" in sys.argv
    ok = True
    def check(name, cond, detail=""):
        nonlocal ok; ok &= bool(cond); print(("PASS " if cond else "FAIL ") + name, detail)
    s, h, b, dt = req(api + "/health", timeout=180)
    body = json.loads(b or b"{}")
    check("health 200 (cold start incl.)", s == 200, f"{dt:.1f}s")
    check("AI provider is real (openrouter/groq, not mock)", body.get("ai") in ("openrouter", "groq"), str(body))
    s, h, _, _ = req(api + "/api/v1/spreadsheets/generate", headers={"Origin": origin, "Access-Control-Request-Method": "POST",
                     "Access-Control-Request-Headers": "content-type"}, method="OPTIONS")
    check("CORS preflight allows frontend origin", h.get("access-control-allow-origin") == origin, str(s))
    s, h, _, _ = req(api + "/api/v1/spreadsheets/generate", headers={"Origin": "https://evil.example", "Access-Control-Request-Method": "POST"}, method="OPTIONS")
    check("CORS rejects foreign origin", h.get("access-control-allow-origin") in (None, ""))
    if live:
        for lang, prompt in (("en", "Create a monthly household budget template with totals"),
                             ("ar", "أنشئ جدول مصروفات شهري مع الإجماليات")):
            payload = json.dumps({"prompt": prompt, "language": lang, "max_rows": 3000}).encode()
            s, h, b, dt = req(api + "/api/v1/spreadsheets/generate", payload, {"Content-Type": "application/json", "Origin": origin})
            h = {k.lower(): v for k, v in h.items()}
            check(f"live generate [{lang}] 200 + xlsx", s == 200 and b[:2] == b"PK", f"status={s} {dt:.1f}s {len(b)} bytes")
            pv = h.get("x-preview")
            check(f"X-Preview header survives proxy [{lang}]", bool(pv))
            if pv: json.loads(base64.b64decode(pv))
    print("ALL PASSED" if ok else "SOME CHECKS FAILED"); sys.exit(0 if ok else 1)
main()
