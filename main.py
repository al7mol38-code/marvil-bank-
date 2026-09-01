import os
import random
import aiosqlite
import discord
from discord.ext import commands, tasks

# =========================
# إعدادات البوت والقرص المدفوع
# =========================
# المسار المخصص للقرص المدفوع في Render
DB_NAME = "/var/data/bot-data/points.db"
CURRENCY_NAME = "فابريونيوم"

# أسعار السوق المبدئية
stock_price = 100  # السعر الافتراضي للسهم
stock_trend = "➡️ ثبات"  # اتجاه السوق

intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix="=", intents=intents, help_command=None)

# =========================
# قاعدة البيانات
# =========================
async def init_db():
    # التأكد من إنشاء المجلد الخاص بالقرص إن لم يكن موجوداً
    db_dir = os.path.dirname(DB_NAME)
    if db_dir and not os.path.exists(db_dir):
        os.makedirs(db_dir, exist_ok=True)

    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS economy (
                user_id TEXT PRIMARY KEY,
                wallet INTEGER DEFAULT 100,
                bank INTEGER DEFAULT 0,
                stocks INTEGER DEFAULT 0
            )
        """)
        await db.commit()

async def get_user_data(user_id: int):
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute("SELECT wallet, bank, stocks FROM economy WHERE user_id = ?", (str(user_id),)) as cursor:
            row = await cursor.fetchone()
            if row:
                return row[0], row[1], row[2]
            else:
                await db.execute("INSERT INTO economy (user_id, wallet, bank, stocks) VALUES (?, ?, ?, ?)", (str(user_id), 100, 0, 0))
                await db.commit()
                return 100, 0, 0

async def update_user(user_id: int, wallet_change: int = 0, bank_change: int = 0, stocks_change: int = 0):
    wallet, bank, stocks = await get_user_data(user_id)
    new_wallet = max(0, wallet + wallet_change)
    new_bank = max(0, bank + bank_change)
    new_stocks = max(0, stocks + stocks_change)
    
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute(
            "UPDATE economy SET wallet = ?, bank = ?, stocks = ? WHERE user_id = ?",
            (new_wallet, new_bank, new_stocks, str(user_id))
        )
        await db.commit()

# =========================
# التحديث التلقائي للسوق (كل 5 دقائق)
# =========================
@tasks.loop(minutes=5)
async def update_stock_market():
    global stock_price, stock_trend
    change_percent = random.randint(-30, 30)
    
    old_price = stock_price
    change_amount = int(stock_price * (change_percent / 100))
    stock_price = max(10, stock_price + change_amount)
    
    if stock_price > old_price:
        stock_trend = f"📈 ارتفاع (+{change_percent}%)"
    elif stock_price < old_price:
        stock_trend = f"📉 هبوط ({change_percent}%)"
    else:
        stock_trend = "➡️ ثبات"

# =========================
# الأحداث
# =========================
@bot.event
async def on_ready():
    await init_db()
    if not update_stock_market.is_running():
        update_stock_market.start()
    print(f"✅ البوت شغال ومربوط بالقرص المدفوع بنجاح باسم: {bot.user}")

# =========================
# الأوامر
# =========================

@bot.command(name="مساعدة")
async def help_cmd(ctx):
    embed = discord.Embed(
        title="💎 أوامر فابريونيوم",
        description=(
            "**البنك والفلوس:**\n"
            "• `=فلوس` ➜ معرفة رصيدك والأسهم\n"
            "• `=راتب` ➜ راتبك اليومي (500)\n"
            "• `=عمل` ➜ تشتغل وتجيب كاش\n"
            "• `=ضم [المبلغ]` ➜ تحط فلوسك بالبنك\n"
            "• `=سحب [المبلغ]` ➜ تسحب فلوسك من البنك\n"
            "• `=تحويل @العضو [المبلغ]` ➜ تحول لشخص\n"
            "• `=سرقة @العضو` ➜ تسرق شخص\n"
            "• `=حظ [المبلغ]` ➜ تلعب على المبلغ\n\n"
            "**سوق الأسهم (يتغير كل 5 دقائق):**\n"
            "• `=سوق` ➜ سعر سهم الفابريونيوم الآن\n"
            "• `=شراء [عدد الأسهم]` ➜ شراء أسهم\n"
            "• `=بيع [عدد الأسهم]` ➜ بيع أسهمك\n"
            "• `=اسهمي` ➜ معرفة عدد أسهمك\n"
            "• `=توب` ➜ أغنى الأعضاء"
        ),
        color=discord.Color.purple()
    )
    await ctx.send(embed=embed)

@bot.command(name="سوق", aliases=["اسهم", "market"])
async def market(ctx):
    embed = discord.Embed(title="📊 سوق أسهم الفابريونيوم", color=discord.Color.blue())
    embed.add_field(name="🏷️ سعر السهم الحالي:", value=f"**{stock_price:,}** {CURRENCY_NAME}", inline=False)
    embed.add_field(name="الحالة العامة:", value=f"**{stock_trend}**", inline=False)
    embed.set_footer(text="يتغير السعر تلقائياً كل 5 دقائق!")
    await ctx.send(embed=embed)

@bot.command(name="شراء", aliases=["buy"])
async def buy_stocks(ctx, amount: int):
    if amount <= 0:
        await ctx.send("❌ أدخل عدد أسهم صحيح!")
        return

    cost = amount * stock_price
    wallet, _, _ = await get_user_data(ctx.author.id)

    if wallet < cost:
        await ctx.send(f"❌ الكاش ما يكفي! تحتاج **{cost:,}** {CURRENCY_NAME} لشراء {amount} أسهم.")
        return

    await update_user(ctx.author.id, wallet_change=-cost, stocks_change=amount)
    await ctx.send(f"✅ اشتريت **{amount}** أسهم بـ **{cost:,}** {CURRENCY_NAME}!")

@bot.command(name="بيع", aliases=["sell"])
async def sell_stocks(ctx, amount: int):
    if amount <= 0:
        await ctx.send("❌ أدخل عدد أسهم صحيح!")
        return

    _, _, stocks = await get_user_data(ctx.author.id)

    if stocks < amount:
        await ctx.send(f"❌ ما عندك هذا العدد من الأسهم! تملك **{stocks}** أسهم فقط.")
        return

    revenue = amount * stock_price
    await update_user(ctx.author.id, wallet_change=revenue, stocks_change=-amount)
    await ctx.send(f"💰 بعت **{amount}** أسهم واستلمت **{revenue:,}** {CURRENCY_NAME} كاش!")

@bot.command(name="اسهمي", aliases=["my-stocks"])
async def my_stocks(ctx):
    _, _, stocks = await get_user_data(ctx.author.id)
    total_value = stocks * stock_price
    await ctx.send(f"📈 تملك **{stocks}** أسهم وقيمتها الحالية في السوق: **{total_value:,}** {CURRENCY_NAME}.")

@bot.command(name="فلوس", aliases=["رصيد", "bal"])
async def balance(ctx, member: discord.Member = None):
    target = member or ctx.author
    wallet, bank, stocks = await get_user_data(target.id)
    stocks_val = stocks * stock_price
    
    embed = discord.Embed(title=f"💳 رصيد {target.display_name}", color=discord.Color.purple())
    embed.add_field(name="💵 كاش:", value=f"**{wallet:,}** {CURRENCY_NAME}", inline=True)
    embed.add_field(name="🏦 بنك:", value=f"**{bank:,}** {CURRENCY_NAME}", inline=True)
    embed.add_field(name="📈 قيمة الأسهم:", value=f"**{stocks_val:,}** {CURRENCY_NAME} ({stocks} سهم)", inline=False)
    embed.add_field(name="💎 الثروة الكلية:", value=f"**{wallet + bank + stocks_val:,}** {CURRENCY_NAME}", inline=False)
    await ctx.send(embed=embed)

@bot.command(name="راتب", aliases=["يومي"])
@commands.cooldown(1, 86400, commands.BucketType.user)
async def daily(ctx):
    await update_user(ctx.author.id, wallet_change=500)
    await ctx.send(f"🎉 أخذت راتبك اليومي **500** {CURRENCY_NAME}!")

@daily.error
async def daily_error(ctx, error):
    if isinstance(error, commands.CommandOnCooldown):
        hours = int(error.retry_after // 3600)
        await ctx.send(f"⏳ راتبك الجاي بعد **{hours}** ساعة.")

@bot.command(name="عمل")
@commands.cooldown(1, 3600, commands.BucketType.user)
async def work(ctx):
    earnings = random.randint(50, 200)
    await update_user(ctx.author.id, wallet_change=earnings)
    await ctx.send(f"💼 اشتغلت وكسبت **{earnings}** {CURRENCY_NAME}!")

@work.error
async def work_error(ctx, error):
    if isinstance(error, commands.CommandOnCooldown):
        minutes = int(error.retry_after // 60)
        await ctx.send(f"⏳ تقدر تشتغل بعد **{minutes}** دقيقة.")

@bot.command(name="ضم", aliases=["إيداع", "ادخار"])
async def deposit(ctx, amount: str):
    wallet, _, _ = await get_user_data(ctx.author.id)
    amt = wallet if amount.lower() in ["الكل", "all"] else (int(amount) if amount.isdigit() else 0)

    if amt <= 0 or wallet < amt:
        await ctx.send("❌ ما عندك هذا المبلغ بالكاش!")
        return

    await update_user(ctx.author.id, wallet_change=-amt, bank_change=amt)
    await ctx.send(f"🏦 ضمت **{amt:,}** {CURRENCY_NAME} بالبنك!")

@bot.command(name="سحب")
async def withdraw(ctx, amount: str):
    _, bank, _ = await get_user_data(ctx.author.id)
    amt = bank if amount.lower() in ["الكل", "all"] else (int(amount) if amount.isdigit() else 0)

    if amt <= 0 or bank < amt:
        await ctx.send("❌ ما عندك هذا المبلغ بالبنك!")
        return

    await update_user(ctx.author.id, wallet_change=amt, bank_change=-amt)
    await ctx.send(f"💵 سحبت **{amt:,}** {CURRENCY_NAME} من البنك!")

@bot.command(name="تحويل")
async def transfer(ctx, member: discord.Member, amount: int):
    if member.bot or member.id == ctx.author.id or amount <= 0:
        await ctx.send("❌ أمر خاطئ!")
        return

    wallet, _, _ = await get_user_data(ctx.author.id)
    if wallet < amount:
        await ctx.send("❌ الكاش ما يكفي!")
        return

    await update_user(ctx.author.id, wallet_change=-amount)
    await update_user(member.id, wallet_change=amount)
    await ctx.send(f"💸 حولت **{amount:,}** {CURRENCY_NAME} لـ {member.mention}!")

@bot.command(name="سرقة")
@commands.cooldown(1, 7200, commands.BucketType.user)
async def rob(ctx, member: discord.Member):
    if member.bot or member.id == ctx.author.id:
        await ctx.send("❌ ما تقدر تسرق البوت أو نفسك!")
        return

    target_wallet, _, _ = await get_user_data(member.id)
    if target_wallet < 100:
        await ctx.send("❌ مطفر، ما معه كاش يستهل تسرقه!")
        return

    if random.random() < 0.40:
        stolen = random.randint(10, int(target_wallet * 0.5))
        await update_user(member.id, wallet_change=-stolen)
        await update_user(ctx.author.id, wallet_change=stolen)
        await ctx.send(f"🥷 سرقت **{stolen:,}** {CURRENCY_NAME} من {member.mention}!")
    else:
        await update_user(ctx.author.id, wallet_change=-50)
        await ctx.send(f"🚨 مسكتك الشرطة وغرمتك **50** {CURRENCY_NAME}!")

@bot.command(name="حظ")
async def gamble(ctx, amount: int):
    wallet, _, _ = await get_user_data(ctx.author.id)
    if amount <= 0 or wallet < amount:
        await ctx.send("❌ ما عندك المبلغ بالكاش!")
        return

    if random.choice([True, False]):
        await update_user(ctx.author.id, wallet_change=amount)
        await ctx.send(f"🎰 فزت بـ **{amount * 2:,}** {CURRENCY_NAME}!")
    else:
        await update_user(ctx.author.id, wallet_change=-amount)
        await ctx.send(f"💀 خسرت **{amount:,}** {CURRENCY_NAME}!")

@bot.command(name="توب")
async def leaderboard(ctx):
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute("SELECT user_id, (wallet + bank + (stocks * ?)) AS total FROM economy ORDER BY total DESC LIMIT 10", (stock_price,)) as cursor:
            users = await cursor.fetchall()

    if not users:
        await ctx.send("📭 ما فيه أحد مسجل.")
        return

    desc = ""
    for idx, (user_id, total) in enumerate(users, start=1):
        member = ctx.guild.get_member(int(user_id))
        name = member.display_name if member else f"<@{user_id}>"
        desc += f"**{idx}.** {name} — 💎 **{total:,}** {CURRENCY_NAME}\n"

    embed = discord.Embed(title="🏆 قائمة الأثرياء (مع الأسهم)", description=desc, color=discord.Color.purple())
    await ctx.send(embed=embed)

# =========================
# التشغيل
# =========================
if __name__ == "__main__":
    token = os.getenv("DISCORD_TOKEN")
    if token:
        bot.run(token)
    else:
        print("❌ Token مفقود!")
