import os
import asyncpg
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from starlette.middleware.sessions import SessionMiddleware
from urllib.parse import urlencode
import httpx

DATABASE_URL = os.getenv("DATABASE_URL", "")
DISCORD_CLIENT_ID = os.getenv("DISCORD_CLIENT_ID", "")
DISCORD_CLIENT_SECRET = os.getenv("DISCORD_CLIENT_SECRET", "")
DISCORD_REDIRECT_URI = os.getenv("DISCORD_REDIRECT_URI", "")
SESSION_SECRET = os.getenv("SESSION_SECRET", "change-this-to-a-long-random-secret")
GUILD_ID = os.getenv("GUILD_ID", "")

def normalize_db_url(url: str) -> str:
    return ("postgresql://" + url[len("postgres://"):]) if url.startswith("postgres://") else url

app = FastAPI(title="Kingdom Economy Dashboard")
app.add_middleware(SessionMiddleware, secret_key=SESSION_SECRET, same_site="lax", https_only=True)
pool = None

@app.on_event("startup")
async def startup():
    global pool
    if DATABASE_URL:
        pool = await asyncpg.create_pool(normalize_db_url(DATABASE_URL), min_size=1, max_size=4)

@app.on_event("shutdown")
async def shutdown():
    if pool:
        await pool.close()

def page(title, body, user=None):
    nav = '<a href="/">الرئيسية</a><a href="/leaderboard">المتصدرون</a>'
    if user:
        nav += f'<span class="user">مسجل الدخول: {user.get("username","عضو")}</span><a href="/logout">خروج</a>'
    else:
        nav += '<a class="login" href="/login">تسجيل الدخول بديسكورد</a>'
    return f"""<!doctype html><html lang="ar" dir="rtl"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>{title}</title>
<style>
:root{{--bg:#0c0d12;--panel:#171923;--gold:#e8bd62;--muted:#a9adbb;--line:#2a2d3a}}
*{{box-sizing:border-box}}body{{margin:0;background:radial-gradient(circle at top,#222033,var(--bg) 50%);color:#f5f5f7;font-family:Tahoma,Arial,sans-serif}}
header{{display:flex;gap:20px;align-items:center;flex-wrap:wrap;padding:20px max(5vw,20px);border-bottom:1px solid var(--line);background:#101118cc}}
.brand{{font-size:20px;font-weight:bold;color:var(--gold);margin-left:auto}}a{{color:#f4d58e;text-decoration:none;margin-left:16px}}main{{max-width:1050px;margin:36px auto;padding:0 18px}}
h1{{font-size:clamp(26px,5vw,42px);margin:8px 0 12px}}p{{color:var(--muted);line-height:1.8}}
.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(210px,1fr));gap:14px;margin:24px 0}}
.card{{background:linear-gradient(145deg,#1b1d29,#14151d);border:1px solid var(--line);border-radius:18px;padding:22px;box-shadow:0 12px 32px #0003}}
.label{{color:var(--muted);font-size:14px}}.value{{font-size:28px;font-weight:bold;color:var(--gold);margin-top:10px}}
table{{width:100%;border-collapse:collapse;background:var(--panel);border-radius:14px;overflow:hidden}}td,th{{padding:14px;text-align:right;border-bottom:1px solid var(--line)}}th{{color:var(--gold)}}
.btn{{display:inline-block;background:var(--gold);color:#17130a;padding:12px 18px;border-radius:10px;font-weight:bold;margin:12px 0}}
footer{{color:var(--muted);text-align:center;padding:36px 12px;font-size:12px}}
</style></head><body><header><div class="brand">👑 مملكة الاقتصاد</div>{nav}</header><main>{body}</main>
<footer>اقتصاد وألعاب افتراضية داخل Discord · لا تمثل الأرصدة أو السوق أموالًا أو استثمارات حقيقية.</footer></body></html>"""

@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    user = request.session.get("discord_user")
    stats = {"users": 0, "wealth": 0}
    if pool:
        async with pool.acquire() as conn:
            stats["users"] = await conn.fetchval("SELECT COUNT(*) FROM users") or 0
            stats["wealth"] = await conn.fetchval("SELECT COALESCE(SUM(wallet+bank),0) FROM users") or 0
    body = f"""
    <section class="card"><div class="label">عالمك الاقتصادي في مكان واحد</div><h1>ابنِ ثروتك. استثمر. نافس.</h1>
    <p>لوحة متابعة لاقتصاد البوت، ثروات الأعضاء وترتيبهم. هذه نسخة البداية، وستضاف صفحات المخزون والنقابات والاستثمارات مع توسع المشروع.</p>
    <a class="btn" href="/leaderboard">عرض المتصدرين ←</a></section>
    <section class="grid">
      <div class="card"><div class="label">الأعضاء المسجلون</div><div class="value">{stats['users']:,}</div></div>
      <div class="card"><div class="label">إجمالي الثروة الافتراضية</div><div class="value">{stats['wealth']:,} 🪙</div></div>
      <div class="card"><div class="label">حالة لوحة التحكم</div><div class="value">متصلة</div></div>
    </section>
    """
    if not user:
        body += '<section class="card"><h2>اربط حسابك</h2><p>تسجيل دخول Discord سيتيح تخصيص الصفحات الشخصية في المرحلة التالية.</p><a class="btn" href="/login">تسجيل الدخول عبر Discord</a></section>'
    return page("الرئيسية", body, user)

@app.get("/leaderboard", response_class=HTMLResponse)
async def leaderboard(request: Request):
    user = request.session.get("discord_user")
    rows = []
    if pool:
        async with pool.acquire() as conn:
            rows = await conn.fetch("SELECT username, wallet, bank, wallet+bank AS wealth FROM users ORDER BY wealth DESC LIMIT 50")
    if rows:
        trs = "".join(f"<tr><td>{i}</td><td>{r['username']}</td><td>{r['wallet']:,}</td><td>{r['bank']:,}</td><td><b>{r['wealth']:,}</b></td></tr>" for i, r in enumerate(rows, 1))
    else:
        trs = '<tr><td colspan="5">لا توجد بيانات بعد. استخدم أوامر البوت لبدء الاقتصاد.</td></tr>'
    body = f'<h1>🏆 المتصدرون</h1><p>ترتيب الأعضاء حسب إجمالي المحفظة والبنك.</p><div class="card"><table><thead><tr><th>#</th><th>العضو</th><th>المحفظة</th><th>البنك</th><th>الثروة</th></tr></thead><tbody>{trs}</tbody></table></div>'
    return page("المتصدرون", body, user)

@app.get("/login")
async def login(request: Request):
    if not (DISCORD_CLIENT_ID and DISCORD_REDIRECT_URI):
        return HTMLResponse(page("إعداد تسجيل الدخول", '<h1>إعداد تسجيل الدخول</h1><p>أضف DISCORD_CLIENT_ID وDISCORD_CLIENT_SECRET وDISCORD_REDIRECT_URI إلى متغيرات Render لإكمال OAuth.</p>'), status_code=503)
    params = {
        "client_id": DISCORD_CLIENT_ID,
        "redirect_uri": DISCORD_REDIRECT_URI,
        "response_type": "code",
        "scope": "identify"
    }
    return RedirectResponse("https://discord.com/oauth2/authorize?" + urlencode(params))

@app.get("/oauth/callback")
async def oauth_callback(request: Request):
    code = request.query_params.get("code")
    if not code:
        return RedirectResponse("/")
    async with httpx.AsyncClient(timeout=15) as client:
        token_response = await client.post("https://discord.com/api/oauth2/token", data={
            "client_id": DISCORD_CLIENT_ID,
            "client_secret": DISCORD_CLIENT_SECRET,
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": DISCORD_REDIRECT_URI,
        }, headers={"Content-Type": "application/x-www-form-urlencoded"})
        if token_response.status_code != 200:
            return HTMLResponse(page("تعذر تسجيل الدخول", "<h1>تعذر تسجيل الدخول</h1><p>راجع إعدادات OAuth في Discord Developer Portal.</p>"), status_code=400)
        token = token_response.json()["access_token"]
        user_response = await client.get("https://discord.com/api/users/@me", headers={"Authorization": f"Bearer {token}"})
    if user_response.status_code != 200:
        return RedirectResponse("/login")
    request.session["discord_user"] = user_response.json()
    return RedirectResponse("/")

@app.get("/logout")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/")
