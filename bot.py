"""بوت البانك — اقتصاد وألعاب ونقابات وسوق افتراضي."""
import os, random, logging, asyncio
from datetime import datetime, timezone, date, timedelta
import discord
from discord import app_commands
from discord.ext import commands, tasks
import asyncpg

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("bot-albank")
TOKEN = os.getenv("DISCORD_TOKEN")
DATABASE_URL = os.getenv("DATABASE_URL")
GUILD_ID = os.getenv("GUILD_ID", "")
STARTING_BALANCE = max(0, int(os.getenv("STARTING_BALANCE", "500")))
if not TOKEN: raise RuntimeError("Missing DISCORD_TOKEN environment variable")
if not DATABASE_URL: raise RuntimeError("Missing DATABASE_URL environment variable")

def normalize_db_url(url):
    return "postgresql://" + url[len("postgres://"):] if url.startswith("postgres://") else url

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
 user_id BIGINT PRIMARY KEY, username TEXT NOT NULL, wallet BIGINT NOT NULL DEFAULT 500 CHECK(wallet>=0),
 bank BIGINT NOT NULL DEFAULT 0 CHECK(bank>=0), level INTEGER NOT NULL DEFAULT 1, xp INTEGER NOT NULL DEFAULT 0,
 daily_claimed DATE, daily_streak INTEGER NOT NULL DEFAULT 0, created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE TABLE IF NOT EXISTS transactions (id BIGSERIAL PRIMARY KEY,user_id BIGINT NOT NULL,kind TEXT NOT NULL,amount BIGINT NOT NULL,note TEXT NOT NULL DEFAULT '',created_at TIMESTAMPTZ NOT NULL DEFAULT NOW());
CREATE INDEX IF NOT EXISTS transactions_user_created_idx ON transactions(user_id,created_at DESC);
ALTER TABLE users ADD COLUMN IF NOT EXISTS daily_streak INTEGER NOT NULL DEFAULT 0;
CREATE TABLE IF NOT EXISTS cooldowns (user_id BIGINT NOT NULL, action TEXT NOT NULL, expires_at TIMESTAMPTZ NOT NULL, PRIMARY KEY(user_id,action));
CREATE TABLE IF NOT EXISTS shop_items (item_id TEXT PRIMARY KEY,name TEXT NOT NULL,description TEXT NOT NULL,price BIGINT NOT NULL CHECK(price>=0),emoji TEXT NOT NULL DEFAULT '📦',stock INTEGER NOT NULL DEFAULT -1);
CREATE TABLE IF NOT EXISTS inventory (user_id BIGINT NOT NULL,item_id TEXT NOT NULL,quantity INTEGER NOT NULL DEFAULT 0 CHECK(quantity>=0),PRIMARY KEY(user_id,item_id));
CREATE TABLE IF NOT EXISTS stocks (symbol TEXT PRIMARY KEY,name TEXT NOT NULL,price BIGINT NOT NULL CHECK(price>0),previous_price BIGINT NOT NULL,updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW());
CREATE TABLE IF NOT EXISTS stock_holdings (user_id BIGINT NOT NULL,symbol TEXT NOT NULL,quantity INTEGER NOT NULL DEFAULT 0 CHECK(quantity>=0),PRIMARY KEY(user_id,symbol));
CREATE TABLE IF NOT EXISTS player_guilds (guild_id BIGSERIAL PRIMARY KEY,name TEXT UNIQUE NOT NULL,leader_id BIGINT NOT NULL,treasury BIGINT NOT NULL DEFAULT 0,created_at TIMESTAMPTZ NOT NULL DEFAULT NOW());
CREATE TABLE IF NOT EXISTS guild_members (guild_id BIGINT NOT NULL REFERENCES player_guilds(guild_id) ON DELETE CASCADE,user_id BIGINT UNIQUE NOT NULL,role TEXT NOT NULL DEFAULT 'عضو',joined_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),PRIMARY KEY(guild_id,user_id));
CREATE TABLE IF NOT EXISTS seasons (season_id BIGSERIAL PRIMARY KEY,name TEXT NOT NULL,starts_at TIMESTAMPTZ NOT NULL,ends_at TIMESTAMPTZ NOT NULL,active BOOLEAN NOT NULL DEFAULT TRUE);
CREATE TABLE IF NOT EXISTS season_scores (season_id BIGINT NOT NULL REFERENCES seasons(season_id) ON DELETE CASCADE,user_id BIGINT NOT NULL,score BIGINT NOT NULL DEFAULT 0,PRIMARY KEY(season_id,user_id));
"""

ITEMS = [
 ("pickaxe", "معول المغامر", "يزيد فرص الحصول على غنائم في المغامرات.", 900, "⛏️", -1),
 ("lucky_charm", "تميمة الحظ", "قطعة نادرة للزينة داخل المخزون.", 1500, "🍀", -1),
 ("bank_card", "بطاقة مصرفية فاخرة", "عنصر تجميلي لحسابك.", 2200, "💳", -1),
 ("treasure_box", "صندوق كنز", "افتحه لتحصل على مكافأة عشوائية.", 650, "🎁", -1),
]
STOCKS = [("ALB", "البانك القابضة", 100, 100), ("GOLD", "الذهب الافتراضي", 250, 250), ("TECH", "تقنيات المستقبل", 180, 180), ("FOOD", "سوق الغذاء", 75, 75)]

class BankBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix="!", intents=discord.Intents.default())
        self.pool = None
    async def setup_hook(self):
        self.pool = await asyncpg.create_pool(normalize_db_url(DATABASE_URL), min_size=1, max_size=5, command_timeout=30)
        async with self.pool.acquire() as c:
            await c.execute(SCHEMA)
            for item in ITEMS:
                await c.execute("INSERT INTO shop_items(item_id,name,description,price,emoji,stock) VALUES($1,$2,$3,$4,$5,$6) ON CONFLICT(item_id) DO NOTHING", *item)
            for stock in STOCKS:
                await c.execute("INSERT INTO stocks(symbol,name,price,previous_price) VALUES($1,$2,$3,$4) ON CONFLICT(symbol) DO NOTHING", *stock)
            active = await c.fetchval("SELECT season_id FROM seasons WHERE active=TRUE LIMIT 1")
            if not active:
                now = datetime.now(timezone.utc)
                await c.execute("INSERT INTO seasons(name,starts_at,ends_at,active) VALUES($1,$2,$3,TRUE)", f"الموسم {now.strftime('%Y-%m')}", now, now+timedelta(days=30))
        self.add_view(BankPanelView())
        if GUILD_ID.isdigit():
            g = discord.Object(id=int(GUILD_ID)); self.tree.copy_global_to(guild=g); await self.tree.sync(guild=g)
            log.info("Synced commands to test guild %s", GUILD_ID)
        else:
            await self.tree.sync(); log.info("Synced global commands")
        self.market_tick.start()
    async def close(self):
        if self.pool: await self.pool.close()
        await super().close()
    async def ensure_user(self, user):
        async with self.pool.acquire() as c:
            await c.execute("INSERT INTO users(user_id,username,wallet) VALUES($1,$2,$3) ON CONFLICT(user_id) DO UPDATE SET username=EXCLUDED.username,updated_at=NOW()", user.id, str(user), STARTING_BALANCE)
    async def cooldown(self, user_id, action, seconds):
        async with self.pool.acquire() as c:
            async with c.transaction():
                row = await c.fetchrow("SELECT expires_at FROM cooldowns WHERE user_id=$1 AND action=$2 FOR UPDATE", user_id, action)
                now = datetime.now(timezone.utc)
                if row and row['expires_at'] > now: return int((row['expires_at']-now).total_seconds())
                await c.execute("INSERT INTO cooldowns(user_id,action,expires_at) VALUES($1,$2,$3) ON CONFLICT(user_id,action) DO UPDATE SET expires_at=EXCLUDED.expires_at", user_id, action, now+timedelta(seconds=seconds))
        return 0
    async def transaction_log(self, uid, kind, amount, note=''):
        async with self.pool.acquire() as c: await c.execute("INSERT INTO transactions(user_id,kind,amount,note) VALUES($1,$2,$3,$4)", uid,kind,amount,note)
    async def add_xp(self, uid, xp):
        async with self.pool.acquire() as c:
            row = await c.fetchrow("UPDATE users SET xp=xp+$1 WHERE user_id=$2 RETURNING level,xp", xp, uid)
            if not row: return None
            new_level = min(100, 1 + row['xp']//100)
            if new_level > row['level']:
                await c.execute("UPDATE users SET level=$1 WHERE user_id=$2",new_level,uid)
            season_id = await c.fetchval("SELECT season_id FROM seasons WHERE active=TRUE ORDER BY season_id DESC LIMIT 1")
            if season_id:
                await c.execute("INSERT INTO season_scores(season_id,user_id,score) VALUES($1,$2,$3) ON CONFLICT(season_id,user_id) DO UPDATE SET score=season_scores.score+EXCLUDED.score", season_id, uid, xp)
            if new_level > row['level']:
                return new_level
        return None
    @tasks.loop(hours=6)
    async def market_tick(self):
        async with self.pool.acquire() as c:
            rows = await c.fetch("SELECT symbol,price FROM stocks")
            for r in rows:
                change = random.uniform(-0.12,0.12)
                price = max(10, int(r['price']*(1+change)))
                await c.execute("UPDATE stocks SET previous_price=price,price=$1,updated_at=NOW() WHERE symbol=$2",price,r['symbol'])
            now = datetime.now(timezone.utc)
            expired = await c.fetchrow("SELECT season_id,name FROM seasons WHERE active=TRUE AND ends_at <= $1 ORDER BY season_id DESC LIMIT 1 FOR UPDATE", now)
            if expired:
                await c.execute("UPDATE seasons SET active=FALSE WHERE season_id=$1", expired['season_id'])
                await c.execute("INSERT INTO seasons(name,starts_at,ends_at,active) VALUES($1,$2,$3,TRUE)", f"الموسم {now.strftime('%Y-%m-%d')}", now, now+timedelta(days=30))
        log.info("Virtual market updated")
    @market_tick.before_loop
    async def before_market_tick(self): await self.wait_until_ready()

bot = BankBot()

@bot.event
async def on_ready(): log.info("Logged in as %s (%s)", bot.user, bot.user.id)

@bot.tree.command(name="رصيدي", description="عرض رصيد المحفظة والبنك والمستوى")
async def balance(i: discord.Interaction):
    await bot.ensure_user(i.user)
    async with bot.pool.acquire() as c: r=await c.fetchrow("SELECT wallet,bank,level,xp FROM users WHERE user_id=$1",i.user.id)
    e=discord.Embed(title=f"🏦 حساب {i.user.display_name}",color=discord.Color.gold())
    e.add_field(name="المحفظة",value=f"🪙 {r['wallet']:,}"); e.add_field(name="البنك",value=f"🏛️ {r['bank']:,}"); e.add_field(name="المستوى",value=f"⭐ {r['level']} · {r['xp']} XP")
    await i.response.send_message(embed=e,ephemeral=True)

@bot.tree.command(name="يومي", description="استلم مكافأتك اليومية مع سلسلة الاستلام")
async def daily(i: discord.Interaction):
    await bot.ensure_user(i.user); today=date.today(); reward=random.randint(250,450)
    async with bot.pool.acquire() as c:
        async with c.transaction():
            r=await c.fetchrow("SELECT daily_claimed,daily_streak FROM users WHERE user_id=$1 FOR UPDATE",i.user.id)
            if r['daily_claimed']==today:
                await i.response.send_message("⏳ استلمت مكافأتك اليوم. ارجع غدًا!",ephemeral=True); return
            streak=(r['daily_streak']+1) if r['daily_claimed']==today-timedelta(days=1) else 1
            reward += min(streak*10,200)
            await c.execute("UPDATE users SET wallet=wallet+$1,daily_claimed=$2,daily_streak=$3,updated_at=NOW() WHERE user_id=$4",reward,today,streak,i.user.id)
            await c.execute("INSERT INTO transactions(user_id,kind,amount,note) VALUES($1,'daily',$2,$3)",i.user.id,reward,f"مكافأة يومية - سلسلة {streak}")
    await bot.add_xp(i.user.id,10)
    await i.response.send_message(f"🎁 حصلت على **{reward:,}** عملة! سلسلة الاستلام: **{streak}** يوم.")

@bot.tree.command(name="عمل", description="اشتغل لتحصل على عملات (تبريد 60 ثانية)")
async def work(i: discord.Interaction):
    await bot.ensure_user(i.user); wait=await bot.cooldown(i.user.id,'work',60)
    if wait: await i.response.send_message(f"⏳ انتظر {wait} ثانية قبل العمل مجددًا.",ephemeral=True); return
    reward=random.randint(80,180)
    async with bot.pool.acquire() as c:
        await c.execute("UPDATE users SET wallet=wallet+$1,updated_at=NOW() WHERE user_id=$2",reward,i.user.id)
        await c.execute("INSERT INTO transactions(user_id,kind,amount,note) VALUES($1,'work',$2,'عمل')",i.user.id,reward)
    level=await bot.add_xp(i.user.id,15)
    msg=f"🛠️ ربحت **{reward:,}** عملة و **15 XP**."
    if level: msg+=f" 🎉 وصلت للمستوى **{level}**!"
    await i.response.send_message(msg)

async def move_money(i, amount, mode):
    await bot.ensure_user(i.user)
    src='wallet' if mode=='deposit' else 'bank'; dst='bank' if mode=='deposit' else 'wallet'
    async with bot.pool.acquire() as c:
        async with c.transaction():
            r=await c.fetchrow(f"SELECT {src} FROM users WHERE user_id=$1 FOR UPDATE",i.user.id)
            if r[src]<amount: await i.response.send_message("❌ الرصيد غير كافٍ.",ephemeral=True); return
            await c.execute(f"UPDATE users SET {src}={src}-$1,{dst}={dst}+$1,updated_at=NOW() WHERE user_id=$2",amount,i.user.id)
            await c.execute("INSERT INTO transactions(user_id,kind,amount,note) VALUES($1,$2,$3,$4)",i.user.id,mode,amount,"تحويل داخلي بين المحفظة والبنك")
    await i.response.send_message(f"✅ تم {'إيداع' if mode=='deposit' else 'سحب'} **{amount:,}** عملة.")

@bot.tree.command(name="إيداع",description="إيداع عملات من المحفظة إلى البنك")
async def deposit(i:discord.Interaction, amount:app_commands.Range[int,1,1000000000]): await move_money(i,amount,'deposit')
@bot.tree.command(name="سحب",description="سحب عملات من البنك إلى المحفظة")
async def withdraw(i:discord.Interaction, amount:app_commands.Range[int,1,1000000000]): await move_money(i,amount,'withdraw')

@bot.tree.command(name="تحويل",description="حوّل عملات إلى عضو آخر")
async def transfer(i:discord.Interaction, member:discord.Member, amount:app_commands.Range[int,1,1000000000]):
    if member.bot or member.id==i.user.id: await i.response.send_message("❌ اختر عضوًا آخر.",ephemeral=True); return
    await bot.ensure_user(i.user); await bot.ensure_user(member)
    async with bot.pool.acquire() as c:
        async with c.transaction():
            r=await c.fetchrow("SELECT wallet FROM users WHERE user_id=$1 FOR UPDATE",i.user.id)
            if r['wallet']<amount: await i.response.send_message("❌ رصيد محفظتك لا يكفي.",ephemeral=True); return
            await c.execute("UPDATE users SET wallet=wallet-$1 WHERE user_id=$2",amount,i.user.id); await c.execute("UPDATE users SET wallet=wallet+$1 WHERE user_id=$2",amount,member.id)
            await c.execute("INSERT INTO transactions(user_id,kind,amount,note) VALUES($1,'transfer_out',$2,$3),($4,'transfer_in',$2,$5)",i.user.id,amount,f"إلى {member.id}",member.id,f"من {i.user.id}")
    await i.response.send_message(f"💸 حوّلت **{amount:,}** عملة إلى {member.mention}.")

@bot.tree.command(name="متصدرين",description="أعلى 10 أعضاء حسب الثروة")
async def leaderboard(i:discord.Interaction):
    async with bot.pool.acquire() as c: rows=await c.fetch("SELECT username,wallet+bank AS wealth FROM users ORDER BY wealth DESC LIMIT 10")
    lines=[f"**{n}.** {r['username']} — 🪙 {r['wealth']:,}" for n,r in enumerate(rows,1)] or ["لا توجد بيانات بعد."]
    await i.response.send_message(embed=discord.Embed(title="🏆 أغنى الأعضاء",description="\n".join(lines),color=discord.Color.gold()))

@bot.tree.command(name="متجر",description="عرض العناصر المتاحة للشراء")
async def shop(i:discord.Interaction):
    async with bot.pool.acquire() as c: rows=await c.fetch("SELECT * FROM shop_items ORDER BY price")
    e=discord.Embed(title="🛍️ متجر بوت البانك",description="للشراء استخدم `/شراء` مع معرّف العنصر.",color=discord.Color.blurple())
    for r in rows: e.add_field(name=f"{r['emoji']} {r['name']} — {r['price']:,}",value=f"`{r['item_id']}` · {r['description']}",inline=False)
    await i.response.send_message(embed=e,ephemeral=True)

@bot.tree.command(name="شراء",description="اشتر عنصرًا من المتجر باستخدام معرّفه")
@app_commands.describe(item_id="معرّف العنصر الظاهر في /متجر")
async def buy(i:discord.Interaction,item_id:str):
    await bot.ensure_user(i.user); item_id=item_id.lower().strip()
    async with bot.pool.acquire() as c:
        async with c.transaction():
            item=await c.fetchrow("SELECT * FROM shop_items WHERE item_id=$1 FOR UPDATE",item_id)
            if not item: await i.response.send_message("❌ هذا العنصر غير موجود. استخدم `/متجر`.",ephemeral=True); return
            u=await c.fetchrow("SELECT wallet FROM users WHERE user_id=$1 FOR UPDATE",i.user.id)
            if u['wallet']<item['price']: await i.response.send_message("❌ رصيدك لا يكفي.",ephemeral=True); return
            if item['stock']==0: await i.response.send_message("نفد المخزون.",ephemeral=True); return
            await c.execute("UPDATE users SET wallet=wallet-$1 WHERE user_id=$2",item['price'],i.user.id)
            await c.execute("INSERT INTO inventory(user_id,item_id,quantity) VALUES($1,$2,1) ON CONFLICT(user_id,item_id) DO UPDATE SET quantity=inventory.quantity+1",i.user.id,item_id)
            if item['stock']>0: await c.execute("UPDATE shop_items SET stock=stock-1 WHERE item_id=$1",item_id)
            await c.execute("INSERT INTO transactions(user_id,kind,amount,note) VALUES($1,'purchase',$2,$3)",i.user.id,-item['price'],item['name'])
    await i.response.send_message(f"✅ اشتريت {item['emoji']} **{item['name']}** مقابل **{item['price']:,}** عملة.")

@bot.tree.command(name="مخزني",description="عرض العناصر التي تملكها")
async def inventory(i:discord.Interaction):
    async with bot.pool.acquire() as c:
        rows=await c.fetch("SELECT s.emoji,s.name,s.item_id,inv.quantity FROM inventory inv JOIN shop_items s USING(item_id) WHERE inv.user_id=$1 AND inv.quantity>0 ORDER BY s.name",i.user.id)
    text='\n'.join(f"{r['emoji']} **{r['name']}** × {r['quantity']} (`{r['item_id']}`)" for r in rows) or "مخزنك فارغ. استخدم `/متجر` لشراء العناصر."
    await i.response.send_message(embed=discord.Embed(title=f"🎒 مخزن {i.user.display_name}",description=text,color=discord.Color.green()),ephemeral=True)

@bot.tree.command(name="افتح_الصندوق",description="افتح صندوق كنز من مخزونك")
async def open_box(i:discord.Interaction):
    await bot.ensure_user(i.user); reward=random.randint(150,1300)
    async with bot.pool.acquire() as c:
        async with c.transaction():
            r=await c.fetchrow("SELECT quantity FROM inventory WHERE user_id=$1 AND item_id='treasure_box' FOR UPDATE",i.user.id)
            if not r or r['quantity']<1: await i.response.send_message("❌ تحتاج صندوق كنز من `/متجر` أولًا.",ephemeral=True); return
            await c.execute("UPDATE inventory SET quantity=quantity-1 WHERE user_id=$1 AND item_id='treasure_box'",i.user.id)
            await c.execute("UPDATE users SET wallet=wallet+$1 WHERE user_id=$2",reward,i.user.id)
            await c.execute("INSERT INTO transactions(user_id,kind,amount,note) VALUES($1,'treasure',$2,'فتح صندوق كنز')",i.user.id,reward)
    await i.response.send_message(f"🎉 فتحت الصندوق وربحت **{reward:,}** عملة!")

@bot.tree.command(name="مغامرة",description="انطلق في مغامرة للحصول على غنائم (تبريد 5 دقائق)")
async def adventure(i:discord.Interaction):
    await bot.ensure_user(i.user); wait=await bot.cooldown(i.user.id,'adventure',300)
    if wait: await i.response.send_message(f"🧭 تحتاج للراحة {wait} ثانية قبل المغامرة التالية.",ephemeral=True); return
    success=random.random()<0.78
    if success:
        reward=random.randint(180,520)
        async with bot.pool.acquire() as c:
            has_pick=await c.fetchval("SELECT quantity>0 FROM inventory WHERE user_id=$1 AND item_id='pickaxe'",i.user.id)
            if has_pick: reward=int(reward*1.2)
            await c.execute("UPDATE users SET wallet=wallet+$1 WHERE user_id=$2",reward,i.user.id)
            await c.execute("INSERT INTO transactions(user_id,kind,amount,note) VALUES($1,'adventure',$2,'غنيمة مغامرة')",i.user.id,reward)
        await bot.add_xp(i.user.id,25)
        await i.response.send_message(f"🗺️ نجحت المغامرة! عثرت على **{reward:,}** عملة و25 XP.")
    else:
        loss=random.randint(30,100)
        async with bot.pool.acquire() as c:
            await c.execute("UPDATE users SET wallet=GREATEST(0,wallet-$1) WHERE user_id=$2",loss,i.user.id)
            await c.execute("INSERT INTO transactions(user_id,kind,amount,note) VALUES($1,'adventure_loss',$2,'خسارة مغامرة')",i.user.id,-loss)
        await i.response.send_message(f"🌧️ لم يحالفك الحظ هذه المرة، فقدت حتى **{loss:,}** عملة من محفظتك.")

@bot.tree.command(name="رهان",description="راهن بجزء من محفظتك على الحظ (افتراضي فقط)")
async def gamble(i:discord.Interaction, amount:app_commands.Range[int,10,100000]):
    await bot.ensure_user(i.user)
    async with bot.pool.acquire() as c:
        async with c.transaction():
            u=await c.fetchrow("SELECT wallet FROM users WHERE user_id=$1 FOR UPDATE",i.user.id)
            if u['wallet']<amount: await i.response.send_message("❌ رصيدك لا يكفي.",ephemeral=True); return
            won=random.random()<0.45
            if won: delta=amount
            else: delta=-amount
            await c.execute("UPDATE users SET wallet=wallet+$1 WHERE user_id=$2",delta,i.user.id)
            await c.execute("INSERT INTO transactions(user_id,kind,amount,note) VALUES($1,'gamble',$2,$3)",i.user.id,delta,"ربح رهان" if won else "خسارة رهان")
    await i.response.send_message((f"🎉 ربحت **{amount:,}** عملة!" if won else f"🎲 خسرت **{amount:,}** عملة. حظ أوفر المرة القادمة!")+" تذكير: هذه عملات افتراضية داخل البوت.")

@bot.tree.command(name="سوق",description="عرض أسعار الأصول الافتراضية")
async def market(i:discord.Interaction):
    async with bot.pool.acquire() as c: rows=await c.fetch("SELECT symbol,name,price,previous_price FROM stocks ORDER BY symbol")
    lines=[]
    for r in rows:
        delta=r['price']-r['previous_price']; emoji='📈' if delta>0 else ('📉' if delta<0 else '➖')
        lines.append(f"{emoji} **{r['symbol']}** — {r['name']}: **{r['price']:,}** (التغير {delta:+,})")
    e=discord.Embed(title="📊 سوق البانك الافتراضي",description='\n'.join(lines),color=discord.Color.blurple())
    e.set_footer(text="أسعار افتراضية تتغير كل 6 ساعات؛ لا تمثل أصولًا حقيقية.")
    await i.response.send_message(embed=e)

@bot.tree.command(name="شراء_سهم",description="شراء أسهم افتراضية من السوق")
async def stock_buy(i:discord.Interaction,symbol:str,quantity:app_commands.Range[int,1,10000]):
    await bot.ensure_user(i.user); symbol=symbol.upper().strip()
    async with bot.pool.acquire() as c:
        async with c.transaction():
            s=await c.fetchrow("SELECT price,name FROM stocks WHERE symbol=$1 FOR UPDATE",symbol)
            if not s: await i.response.send_message("❌ رمز غير معروف. راجع `/سوق`.",ephemeral=True); return
            total=s['price']*quantity; u=await c.fetchrow("SELECT wallet FROM users WHERE user_id=$1 FOR UPDATE",i.user.id)
            if u['wallet']<total: await i.response.send_message(f"❌ تحتاج {total:,} عملة.",ephemeral=True); return
            await c.execute("UPDATE users SET wallet=wallet-$1 WHERE user_id=$2",total,i.user.id)
            await c.execute("INSERT INTO stock_holdings(user_id,symbol,quantity) VALUES($1,$2,$3) ON CONFLICT(user_id,symbol) DO UPDATE SET quantity=stock_holdings.quantity+EXCLUDED.quantity",i.user.id,symbol,quantity)
            await c.execute("INSERT INTO transactions(user_id,kind,amount,note) VALUES($1,'stock_buy',$2,$3)",i.user.id,-total,f"شراء {quantity} من {symbol}")
    await i.response.send_message(f"📈 اشتريت **{quantity}** من **{symbol}** مقابل **{total:,}** عملة افتراضية.")

@bot.tree.command(name="بيع_سهم",description="بيع أسهم تملكها بسعر السوق الحالي")
async def stock_sell(i:discord.Interaction,symbol:str,quantity:app_commands.Range[int,1,10000]):
    symbol=symbol.upper().strip()
    async with bot.pool.acquire() as c:
        async with c.transaction():
            s=await c.fetchrow("SELECT price FROM stocks WHERE symbol=$1 FOR UPDATE",symbol)
            if not s: await i.response.send_message("❌ رمز غير معروف. راجع `/سوق`.",ephemeral=True); return
            h=await c.fetchrow("SELECT quantity FROM stock_holdings WHERE user_id=$1 AND symbol=$2 FOR UPDATE",i.user.id,symbol)
            if not h or h['quantity']<quantity: await i.response.send_message("❌ لا تملك هذه الكمية.",ephemeral=True); return
            total=s['price']*quantity
            await c.execute("UPDATE stock_holdings SET quantity=quantity-$1 WHERE user_id=$2 AND symbol=$3",quantity,i.user.id,symbol)
            await c.execute("UPDATE users SET wallet=wallet+$1 WHERE user_id=$2",total,i.user.id)
            await c.execute("INSERT INTO transactions(user_id,kind,amount,note) VALUES($1,'stock_sell',$2,$3)",i.user.id,total,f"بيع {quantity} من {symbol}")
    await i.response.send_message(f"💰 بعت **{quantity}** من **{symbol}** وربحت **{total:,}** عملة بسعر السوق الحالي.")

@bot.tree.command(name="محفظة_الأسهم",description="عرض الأسهم التي تملكها")
async def stock_portfolio(i:discord.Interaction):
    async with bot.pool.acquire() as c: rows=await c.fetch("SELECT h.symbol,h.quantity,s.name,s.price,h.quantity*s.price AS value FROM stock_holdings h JOIN stocks s USING(symbol) WHERE h.user_id=$1 AND h.quantity>0",i.user.id)
    desc='\n'.join(f"**{r['symbol']}** {r['name']} × {r['quantity']} — {r['value']:,} عملة" for r in rows) or "لا تملك أسهمًا حاليًا."
    await i.response.send_message(embed=discord.Embed(title="📂 محفظة الأسهم",description=desc,color=discord.Color.blurple()),ephemeral=True)

@bot.tree.command(name="إنشاء_نقابة",description="أنشئ نقابة خاصة بك بتكلفة 5000 عملة")
async def guild_create(i:discord.Interaction,name:str):
    name=name.strip()
    if len(name)<3 or len(name)>32: await i.response.send_message("❌ اسم النقابة يجب أن يكون بين 3 و32 حرفًا.",ephemeral=True); return
    await bot.ensure_user(i.user)
    async with bot.pool.acquire() as c:
        async with c.transaction():
            member=await c.fetchval("SELECT guild_id FROM guild_members WHERE user_id=$1",i.user.id)
            if member: await i.response.send_message("❌ أنت عضو في نقابة بالفعل.",ephemeral=True); return
            u=await c.fetchrow("SELECT wallet FROM users WHERE user_id=$1 FOR UPDATE",i.user.id)
            if u['wallet']<5000: await i.response.send_message("❌ تحتاج 5,000 عملة لإنشاء نقابة.",ephemeral=True); return
            taken = await c.fetchval("SELECT 1 FROM player_guilds WHERE LOWER(name)=LOWER($1)", name)
            if taken:
                await i.response.send_message("❌ اسم النقابة مستخدم بالفعل.",ephemeral=True); return
            gid=await c.fetchval("INSERT INTO player_guilds(name,leader_id) VALUES($1,$2) RETURNING guild_id",name,i.user.id)
            await c.execute("INSERT INTO guild_members(guild_id,user_id,role) VALUES($1,$2,'قائد')",gid,i.user.id)
            await c.execute("UPDATE users SET wallet=wallet-5000 WHERE user_id=$1",i.user.id)
    await i.response.send_message(f"🏰 تم إنشاء نقابة **{name}** بنجاح! تكلفة الإنشاء 5,000 عملة.")

@bot.tree.command(name="نقابة",description="عرض معلومات نقابتك")
async def guild_info(i:discord.Interaction):
    async with bot.pool.acquire() as c:
        r=await c.fetchrow("SELECT g.name,g.treasury,g.leader_id,COUNT(m.user_id) AS members FROM guild_members m JOIN player_guilds g USING(guild_id) WHERE m.user_id=$1 GROUP BY g.guild_id",i.user.id)
    if not r: await i.response.send_message("لست عضوًا في نقابة. استخدم `/إنشاء_نقابة` لإنشاء واحدة.",ephemeral=True); return
    await i.response.send_message(embed=discord.Embed(title=f"🏰 نقابة {r['name']}",description=f"الأعضاء: **{r['members']}**\nخزينة النقابة: **{r['treasury']:,}** 🪙\nالقائد: <@{r['leader_id']}>",color=discord.Color.purple()))


@bot.tree.command(name="قائمة_النقابات",description="عرض النقابات المتاحة للانضمام")
async def guild_list(i:discord.Interaction):
    async with bot.pool.acquire() as c:
        rows=await c.fetch("SELECT g.name,g.treasury,COUNT(m.user_id) AS members FROM player_guilds g LEFT JOIN guild_members m USING(guild_id) GROUP BY g.guild_id ORDER BY members DESC LIMIT 15")
    desc='\n'.join(f"🏰 **{r['name']}** — {r['members']} عضو · الخزينة {r['treasury']:,}" for r in rows) or "لا توجد نقابات بعد."
    await i.response.send_message(embed=discord.Embed(title="🏰 نقابات بوت البانك",description=desc,color=discord.Color.purple()),ephemeral=True)

@bot.tree.command(name="انضمام_نقابة",description="انضم إلى نقابة موجودة بالاسم")
async def guild_join(i:discord.Interaction,name:str):
    await bot.ensure_user(i.user)
    async with bot.pool.acquire() as c:
        async with c.transaction():
            existing=await c.fetchval("SELECT guild_id FROM guild_members WHERE user_id=$1",i.user.id)
            if existing: await i.response.send_message("❌ أنت عضو في نقابة بالفعل.",ephemeral=True); return
            g=await c.fetchrow("SELECT guild_id,name FROM player_guilds WHERE LOWER(name)=LOWER($1) FOR UPDATE",name.strip())
            if not g: await i.response.send_message("❌ لم أجد نقابة بهذا الاسم. استخدم `/قائمة_النقابات`.",ephemeral=True); return
            await c.execute("INSERT INTO guild_members(guild_id,user_id,role) VALUES($1,$2,'عضو')",g['guild_id'],i.user.id)
    await i.response.send_message(f"🎉 انضممت إلى نقابة **{g['name']}**!")

@bot.tree.command(name="تبرع_للنقابة",description="أودع عملات في خزينة نقابتك")
async def guild_donate(i:discord.Interaction,amount:app_commands.Range[int,1,100000000]):
    async with bot.pool.acquire() as c:
        async with c.transaction():
            m=await c.fetchrow("SELECT guild_id FROM guild_members WHERE user_id=$1",i.user.id)
            if not m: await i.response.send_message("❌ لست عضوًا في نقابة.",ephemeral=True); return
            u=await c.fetchrow("SELECT wallet FROM users WHERE user_id=$1 FOR UPDATE",i.user.id)
            if not u or u['wallet']<amount: await i.response.send_message("❌ رصيدك لا يكفي.",ephemeral=True); return
            await c.execute("UPDATE users SET wallet=wallet-$1 WHERE user_id=$2",amount,i.user.id)
            await c.execute("UPDATE player_guilds SET treasury=treasury+$1 WHERE guild_id=$2",amount,m['guild_id'])
    await i.response.send_message(f"🤝 تبرعت بـ **{amount:,}** عملة لخزينة النقابة.")

@bot.tree.command(name="الموسم",description="عرض الموسم الحالي وترتيب نقاطه")
async def season(i:discord.Interaction):
    async with bot.pool.acquire() as c:
        s=await c.fetchrow("SELECT * FROM seasons WHERE active=TRUE ORDER BY season_id DESC LIMIT 1")
        rows=[] if not s else await c.fetch("SELECT u.username,ss.score FROM season_scores ss JOIN users u USING(user_id) WHERE ss.season_id=$1 ORDER BY ss.score DESC LIMIT 10",s['season_id'])
    if not s: await i.response.send_message("لا يوجد موسم نشط حاليًا.",ephemeral=True); return
    end=s['ends_at'].strftime('%Y-%m-%d %H:%M UTC')
    lines='\n'.join(f"**{n}.** {r['username']} — {r['score']} نقطة" for n,r in enumerate(rows,1)) or "لم تُسجّل نقاط بعد. العب واربح نقاط الموسم!"
    await i.response.send_message(embed=discord.Embed(title=f"🏁 {s['name']}",description=f"ينتهي في: **{end}**\n\n{lines}",color=discord.Color.gold()))

@bot.tree.command(name="سجل_عملياتي",description="عرض آخر 10 عمليات مالية لك")
async def history(i:discord.Interaction):
    async with bot.pool.acquire() as c: rows=await c.fetch("SELECT kind,amount,note,created_at FROM transactions WHERE user_id=$1 ORDER BY created_at DESC LIMIT 10",i.user.id)
    desc='\n'.join(f"`{r['created_at'].strftime('%m-%d %H:%M')}` · {r['kind']} · **{r['amount']:+,}** · {r['note']}" for r in rows) or "لا توجد عمليات مسجلة بعد."
    await i.response.send_message(embed=discord.Embed(title="🧾 آخر العمليات",description=desc,color=discord.Color.dark_teal()),ephemeral=True)

# واجهات تفاعلية عامة: بطاقات + شبكة أزرار.
GAME_EMOJIS = ["👾", "🦆", "🤡", "🚩", "🥜", "⚔️", "🧠", "🦫", "🏓"]

class EmojiGameView(discord.ui.View):
    def __init__(self, owner_id: int, correct: str):
        super().__init__(timeout=90)
        self.owner_id, self.correct, self.finished = owner_id, correct, False
        for idx, emoji in enumerate(GAME_EMOJIS):
            button = discord.ui.Button(label=emoji, style=discord.ButtonStyle.primary if idx == 0 else discord.ButtonStyle.danger, row=idx // 3, custom_id=f"bank_emoji_{owner_id}_{idx}")
            button.callback = self.make_callback(emoji)
            self.add_item(button)

    def make_callback(self, chosen: str):
        async def callback(interaction: discord.Interaction):
            if interaction.user.id != self.owner_id:
                await interaction.response.send_message("هذه الجولة ليست لك؛ ابدأ جولتك بالأمر `/لعبة_الإيموجي`.", ephemeral=True)
                return
            if self.finished:
                await interaction.response.send_message("انتهت هذه الجولة بالفعل. ابدأ جولة جديدة!", ephemeral=True)
                return
            self.finished = True
            won = chosen == self.correct
            reward = random.randint(80, 160) if won else 0
            await bot.ensure_user(interaction.user)
            if won:
                async with bot.pool.acquire() as c:
                    await c.execute("UPDATE users SET wallet=wallet+$1,updated_at=NOW() WHERE user_id=$2", reward, interaction.user.id)
                    await c.execute("INSERT INTO transactions(user_id,kind,amount,note) VALUES($1,$2,$3,$4)", interaction.user.id, "لعبة الإيموجي", reward, "فوز في لعبة الإيموجي")
                await bot.add_xp(interaction.user.id, 10)
            for item in self.children:
                item.disabled = True
                if isinstance(item, discord.ui.Button) and item.label == self.correct:
                    item.style = discord.ButtonStyle.success
                elif isinstance(item, discord.ui.Button) and item.label == chosen and not won:
                    item.style = discord.ButtonStyle.danger
            e = discord.Embed(title="🎮 لعبة الإيموجي · النتيجة", description=f"{interaction.user.mention}\n\n" + (f"🎉 **اختيار صحيح!** ربحت **{reward:,}** 🪙" if won else "😔 **لم يحالفك الحظ!**") + f"\n\n🚩 الإيموجي الصحيح: **{self.correct}**", color=discord.Color.gold() if won else discord.Color.dark_red())
            e.set_thumbnail(url=interaction.user.display_avatar.url)
            e.set_footer(text="بوت البانك • لعبة الإيموجي")
            await interaction.response.edit_message(embed=e, view=self)
        return callback

    async def on_timeout(self):
        for item in self.children:
            item.disabled = True

class BankPanelView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="لعبة الإيموجي", emoji="🎮", style=discord.ButtonStyle.primary, custom_id="albank_panel_game")
    async def game(self, interaction: discord.Interaction, button: discord.ui.Button):
        await send_emoji_game(interaction, ephemeral=False)

    @discord.ui.button(label="رصيدي", emoji="💰", style=discord.ButtonStyle.success, custom_id="albank_panel_balance")
    async def balance_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await bot.ensure_user(interaction.user)
        async with bot.pool.acquire() as c:
            r = await c.fetchrow("SELECT wallet,bank,level,xp FROM users WHERE user_id=$1", interaction.user.id)
        e = discord.Embed(title=f"💳 محفظة {interaction.user.display_name}", color=discord.Color.gold())
        e.add_field(name="المحفظة", value=f"🪙 {r['wallet']:,}")
        e.add_field(name="البنك", value=f"🏦 {r['bank']:,}")
        e.add_field(name="المستوى", value=f"⭐ {r['level']} · {r['xp']} XP")
        e.set_thumbnail(url=interaction.user.display_avatar.url)
        await interaction.response.send_message(embed=e, ephemeral=True)

    @discord.ui.button(label="المتصدرون", emoji="🏆", style=discord.ButtonStyle.secondary, custom_id="albank_panel_leaderboard")
    async def leaderboard(self, interaction: discord.Interaction, button: discord.ui.Button):
        async with bot.pool.acquire() as c:
            rows = await c.fetch("SELECT username,wallet+bank AS wealth FROM users ORDER BY wealth DESC LIMIT 10")
        lines = [f"**{n}.** {r['username']} — 🪙 **{r['wealth']:,}**" for n, r in enumerate(rows, 1)]
        e = discord.Embed(title="🏆 أغنى أعضاء بوت البانك", description="\n".join(lines) or "لا توجد بيانات بعد.", color=discord.Color.gold())
        await interaction.response.edit_message(embed=e, view=self)

    @discord.ui.button(label="المتجر", emoji="🛍️", style=discord.ButtonStyle.secondary, custom_id="albank_panel_shop")
    async def shop(self, interaction: discord.Interaction, button: discord.ui.Button):
        async with bot.pool.acquire() as c:
            rows = await c.fetch("SELECT name,description,price,emoji,stock FROM shop_items ORDER BY price")
        lines = [f"{r['emoji']} **{r['name']}** — 🪙 {r['price']:,}\n{r['description']}" + (" · نفد المخزون" if r['stock'] == 0 else "") for r in rows]
        e = discord.Embed(title="🛍️ متجر البانك", description="\n\n".join(lines) or "المتجر فارغ حاليًا.", color=discord.Color.gold())
        e.set_footer(text="تفاصيل الشراء وإتمامه تبقى خاصة بصاحب الحساب")
        await interaction.response.edit_message(embed=e, view=self)

async def send_emoji_game(interaction: discord.Interaction, ephemeral: bool):
    correct = random.choice(GAME_EMOJIS)
    e = discord.Embed(title="🎯 اختر الإيموجي الصحيح", description=f"{interaction.user.mention}، اختر واحدًا من الأزرار التسعة.\n\n**الجائزة:** 80–160 🪙\n**المحاولات:** محاولة واحدة", color=discord.Color.blurple())
    e.set_thumbnail(url=interaction.user.display_avatar.url)
    e.set_footer(text="النتيجة تظهر للجميع • لا تخصم العملات عند الخسارة")
    await interaction.response.send_message(embed=e, view=EmojiGameView(interaction.user.id, correct), ephemeral=ephemeral)

@bot.tree.command(name="لوحة_البانك", description="نشر لوحة بوت البانك التفاعلية في القناة")
@app_commands.default_permissions(manage_guild=True)
async def bank_panel(i: discord.Interaction):
    e = discord.Embed(title="🏦 بوت البانك", description="**اقتصادك. ألعابك. منافستك.**\n\nاختر أحد الأقسام من الأزرار أدناه.\n\n🎮 ألعاب تفاعلية\n💰 رصيد شخصي خاص\n🏆 ترتيب عام للأعضاء\n🛍️ متجر الاقتصاد", color=discord.Color.from_rgb(225, 190, 35))
    e.set_footer(text="بوت البانك • العملات افتراضية")
    await i.response.send_message(embed=e, view=BankPanelView())

@bot.tree.command(name="لعبة_الإيموجي", description="ابدأ لعبة إيموجي تفاعلية واربح عملات")
async def emoji_game(i: discord.Interaction):
    await send_emoji_game(i, ephemeral=False)

@bot.tree.command(name="مساعدة",description="عرض أنظمة وأوامر بوت البانك")
async def help_command(i:discord.Interaction):
    e=discord.Embed(title="🏦 بوت البانك — دليل الأوامر",description="اقتصاد افتراضي وألعاب ومغامرات ومتجر وأسهم ونقابات ومواسم.",color=discord.Color.gold())
    e.add_field(name="💰 الاقتصاد",value="`/رصيدي` `/يومي` `/عمل` `/إيداع` `/سحب` `/تحويل` `/متصدرين` `/سجل_عملياتي`",inline=False)
    e.add_field(name="🧭 الألعاب",value="`/مغامرة` `/رهان` `/افتح_الصندوق`",inline=False)
    e.add_field(name="🛍️ المتجر والمخزون",value="`/متجر` `/شراء` `/مخزني`",inline=False)
    e.add_field(name="📈 السوق",value="`/سوق` `/شراء_سهم` `/بيع_سهم` `/محفظة_الأسهم`",inline=False)
    e.add_field(name="🏰 النقابات والمواسم",value="`/إنشاء_نقابة` `/قائمة_النقابات` `/انضمام_نقابة` `/نقابة` `/تبرع_للنقابة` `/الموسم`",inline=False)
    e.set_footer(text="كل العملات والأسهم افتراضية ولا تمثل أموالًا أو استثمارات حقيقية.")
    await i.response.send_message(embed=e,ephemeral=True)

@bot.tree.error
async def on_app_command_error(i:discord.Interaction,error:app_commands.AppCommandError):
    log.exception("App command failed",exc_info=error)
    msg="حدث خطأ غير متوقع. جرّب مرة أخرى، وإذا تكرر راجع سجلات Render."
    if i.response.is_done(): await i.followup.send(msg,ephemeral=True)
    else: await i.response.send_message(msg,ephemeral=True)

bot.run(TOKEN)
