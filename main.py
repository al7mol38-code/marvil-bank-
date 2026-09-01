import os
import random
import asyncio
import aiosqlite
import discord
from discord.ext import commands, tasks

# =========================
# إعدادات البوت والقرص المدفوع
# =========================
DB_NAME = "/var/data/bot-data/points.db"
CURRENCY_NAME = "فابريونيوم"

# الرتب المصرح لها بإقامة الفعاليات
EVENT_ROLE_IDS = [1533463570564649121, 1533463569683845160]

# سوق الأسهم - 7 شركات متنوعة
STOCKS = {
    "aramco": {"name": "أرامكو 🛢️", "price": 100, "trend": "➡️ ثبات", "volatility": 8},
    "apple":  {"name": "أبل 🍎", "price": 180, "trend": "➡️ ثبات", "volatility": 15},
    "tesla":  {"name": "تسلا 🚗", "price": 250, "trend": "➡️ ثبات", "volatility": 25},
    "nvidia": {"name": "إنفيديا 💻", "price": 400, "trend": "➡️ ثبات", "volatility": 30},
    "disney": {"name": "ديزني 🏰", "price": 120, "trend": "➡️ ثبات", "volatility": 18},
    "boeing": {"name": "بوينج ✈️", "price": 210, "trend": "➡️ ثبات", "volatility": 22},
    "crypto": {"name": "كريبتو 🪙", "price": 500, "trend": "➡️ ثبات", "volatility": 50}
}

# صور وفيديوهات GIF لتزيين الـ Embeds
GIFS = {
    "bank": "https://media.giphy.com/media/l0HFkA6omUyjVYqw8/giphy.gif",
    "market": "https://media.giphy.com/media/JtBZm3Get439xMJqbe/giphy.gif",
    "casino": "https://media.giphy.com/media/26fdY5h321e1LiaQ8/giphy.gif",
    "slots": "https://media.giphy.com/media/l2Je2M4NfritVJ3va/giphy.gif",
    "race": "https://media.giphy.com/media/3o7TKr3nzbh5WgCFxe/giphy.gif",
    "rich": "https://media.giphy.com/media/xT1R9LUBvRE90p3M1W/giphy.gif",
    "work": "https://media.giphy.com/media/3o72FfM5HJydzaM69a/giphy.gif",
    "gift": "https://media.giphy.com/media/3o6fJ1BM7R2EBRDnxK/giphy.gif"
}

intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix="=", intents=intents, help_command=None)

# =========================
# قاعدة البيانات
# =========================
async def init_db():
    db_dir = os.path.dirname(DB_NAME)
    if db_dir and not os.path.exists(db_dir):
        os.makedirs(db_dir, exist_ok=True)

    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS economy (
                user_id TEXT PRIMARY KEY,
                wallet INTEGER DEFAULT 100,
                bank INTEGER DEFAULT 0,
                aramco INTEGER DEFAULT 0,
                apple INTEGER DEFAULT 0,
                tesla INTEGER DEFAULT 0,
                nvidia INTEGER DEFAULT 0,
                disney INTEGER DEFAULT 0,
                boeing INTEGER DEFAULT 0,
                crypto INTEGER DEFAULT 0
            )
        """)
        await db.commit()

async def get_user_data(user_id: int):
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute(
            "SELECT wallet, bank, aramco, apple, tesla, nvidia, disney, boeing, crypto FROM economy WHERE user_id = ?",
            (str(user_id),)
        ) as cursor:
            row = await cursor.fetchone()
            if row:
                return {
                    "wallet": row[0], "bank": row[1],
                    "aramco": row[2], "apple": row[3], "tesla": row[4],
                    "nvidia": row[5], "disney": row[6], "boeing": row[7], "crypto": row[8]
                }
            else:
                await db.execute(
                    "INSERT INTO economy (user_id, wallet, bank, aramco, apple, tesla, nvidia, disney, boeing, crypto) "
                    "VALUES (?, 100, 0, 0, 0, 0, 0, 0, 0, 0)",
                    (str(user_id),)
                )
                await db.commit()
                return {
                    "wallet": 100, "bank": 0,
                    "aramco": 0, "apple": 0, "tesla": 0,
                    "nvidia": 0, "disney": 0, "boeing": 0, "crypto": 0
                }

async def update_user(user_id: int, field: str, amount: int):
    data = await get_user_data(user_id)
    new_val = max(0, data[field] + amount)
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute(f"UPDATE economy SET {field} = ? WHERE user_id = ?", (new_val, str(user_id)))
        await db.commit()

# =========================
# التحديث التلقائي للسوق (كل 5 دقائق)
# =========================
@tasks.loop(minutes=5)
async def update_stock_market():
    for key, stock in STOCKS.items():
        vol = stock["volatility"]
        change_percent = random.randint(-vol, vol)
        
        old_price = stock["price"]
        change_amount = int(stock["price"] * (change_percent / 100))
        stock["price"] = max(10, stock["price"] + change_amount)
        
        if stock["price"] > old_price:
            stock["trend"] = f"📈 (+{change_percent}%)"
        elif stock["price"] < old_price:
            stock["trend"] = f"📉 ({change_percent}%)"
        else:
            stock["trend"] = "➡️ ثبات"

# =========================
# زر الفعالية التفاعلي
# =========================
class EventClaimView(discord.ui.View):
    def __init__(self, amount: int):
        super().__init__(timeout=60.0)
        self.amount = amount
        self.claimed_users = set()

    @discord.ui.button(label="استلام الهدية 🎉", style=discord.ButtonStyle.success, emoji="🎁")
    async def claim_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        user_id = interaction.user.id
        if user_id in self.claimed_users:
            await interaction.response.send_message("❌ استلمت هذه الهدية من قبل!", ephemeral=True)
            return

        self.claimed_users.add(user_id)
        await update_user(user_id, "wallet", self.amount)
        await interaction.response.send_message(
            f"🎉 **مبروك!** استلمت **{self.amount:,}** {CURRENCY_NAME} في محفظتك!",
            ephemeral=True
        )

    async on_timeout(self):
        for item in self.children:
            item.disabled = True

# =========================
# الأحداث والأوامر
# =========================
@bot.event
async def on_ready():
    await init_db()
    if not update_stock_market.is_running():
        update_stock_market.start()
    print(f"✅ البوت شغال مع نظام الفعاليات الخاص باسم: {bot.user}")

@bot.command(name="فعالية", aliases=["حدث", "event"])
async def start_event(ctx, amount: int):
    # التحقق من الرتب المصرح لها
    user_role_ids = [role.id for role in ctx.author.roles]
    if not any(role_id in user_role_ids for role_id in EVENT_ROLE_IDS):
        await ctx.send("❌ هذا الأمر مخصص لإدارة الفعاليات فقط!")
        return

    if amount <= 0:
        await ctx.send("❌ حدد مبلغ جائزة صحيح!")
        return

    embed = discord.Embed(
        title="🎉 فعالية خاصة بالجميع! 🎉",
        description=(
            f"أقام الإداري {ctx.author.mention} فعالية سريعة للجميع!\n\n"
            f"💰 **الجائزة لكل شخص:** **{amount:,}** {CURRENCY_NAME}\n"
            "⏳ **المدة:** 60 ثانية فقط!\n\n"
            "اضغط على الزر بالأسفل لاستلام حصتك فوراً! 👇"
        ),
        color=discord.Color.gold()
    )
    embed.set_thumbnail(url=GIFS["gift"])
    embed.set_footer(text="ينتهي العرض بعد دقيقة واحدة")

    view = EventClaimView(amount)
    await ctx.send(content="@everyone 🔔 **فعالية جديدة!**", embed=embed, view=view)

@bot.command(name="مساعدة")
async def help_cmd(ctx):
    embed = discord.Embed(
        title="💎 دليل أوامر البوت المطور",
        description=(
            "**💵 الاقتصاد والبنك:**\n"
            "• `=فلوس` ➜ معرفة رصيدك الكلي\n"
            "• `=راتب` ➜ راتبك اليومي (500)\n"
            "• `=عمل` ➜ الحصول على كاش\n"
            "• `=ضم [المبلغ]` / `=سحب [المبلغ]` ➜ البنك\n"
            "• `=تحويل @العضو [المبلغ]` ➜ تحويل فلوس\n"
            "• `=سرقة @العضو` ➜ محاولة سرقة كاش\n\n"
            "**🎰 الألعاب والمراهنات:**\n"
            "• `=حظ [المبلغ]` ➜ لعبة 50/50\n"
            "• `=قمار [المبلغ]` ➜ لعبة الروليت (أحمر، أسود، أخضر)\n"
            "• `=سلوت [المبلغ]` ➜ آلة القمار بـ 3 رموز\n"
            "• `=سباق [المبلغ]` ➜ سباق الأحصنة والرهان\n\n"
            "**📈 بورصة الأسهم:**\n"
            "• `=سوق` ➜ أسعار الأسهم العالمية\n"
            "• `=شراء [الشركة] [العدد]` | `=بيع [الشركة] [العدد]`\n"
            "• `=اسهمي` ➜ محفظتك | `=توب` ➜ قائمة الأثرياء\n\n"
            "**🎉 الفعاليات (للإدارة فقط):**\n"
            "• `=فعالية [المبلغ]` ➜ إقامة فعالية وإعطاء جوائز للجميع"
        ),
        color=discord.Color.gold()
    )
    embed.set_thumbnail(url=GIFS["casino"])
    await ctx.send(embed=embed)

# =========================
# قسم الألعاب والسرقة
# =========================

@bot.command(name="حظ")
async def gamble(ctx, amount: int):
    data = await get_user_data(ctx.author.id)
    if amount <= 0 or data["wallet"] < amount:
        await ctx.send("❌ ما عندك هذا المبلغ بالكاش!")
        return

    embed = discord.Embed(title="🎲 لعبة الحظ")
    if random.choice([True, False]):
        await update_user(ctx.author.id, "wallet", amount)
        embed.color = discord.Color.green()
        embed.description = f"🎉 **فوز ساحق!** فزت بـ **{amount * 2:,}** {CURRENCY_NAME}!"
        embed.set_image(url=GIFS["rich"])
    else:
        await update_user(ctx.author.id, "wallet", -amount)
        embed.color = discord.Color.red()
        embed.description = f"💀 **خسارة!** راحت عليك **{amount:,}** {CURRENCY_NAME}."
    
    await ctx.send(embed=embed)

@bot.command(name="قمار", aliases=["روليت"])
async def roulette(ctx, amount: int):
    data = await get_user_data(ctx.author.id)
    if amount <= 0 or data["wallet"] < amount:
        await ctx.send("❌ ما عندك هذا المبلغ بالكاش!")
        return

    embed_start = discord.Embed(
        title="🎡 عجلة الروليت",
        description=f"الرهان: **{amount:,}** {CURRENCY_NAME}\n\n"
                    "1️⃣ **أحمر** (ضعف المبلغ 2x)\n"
                    "2️⃣ **أسود** (ضعف المبلغ 2x)\n"
                    "3️⃣ **أخضر** (14 ضعف المبلغ 14x 🔥)\n\n"
                    "اكتب اسم اللون أو رقمه خلال 15 ثانية!",
        color=discord.Color.purple()
    )
    embed_start.set_thumbnail(url=GIFS["casino"])
    await ctx.send(embed=embed_start)

    def check(m):
        return m.author == ctx.author and m.channel == ctx.channel and m.content in ["1", "2", "3", "أحمر", "احمر", "أسود", "اسود", "أخضر", "اخضر"]

    try:
        choice_msg = await bot.wait_for("message", timeout=15.0, check=check)
        choice = choice_msg.content.lower()
    except asyncio.TimeoutError:
        await ctx.send("⏰ انتهى الوقت! تم إلغاء الرهان.")
        return

    outcome = random.choices(["أحمر", "أسود", "أخضر"], weights=[47, 47, 6], k=1)[0]
    
    user_choice = ""
    if choice in ["1", "أحمر", "احمر"]: user_choice = "أحمر"
    elif choice in ["2", "أسود", "اسود"]: user_choice = "أسود"
    elif choice in ["3", "أخضر", "اخضر"]: user_choice = "أخضر"

    embed_res = discord.Embed(title="🎡 نتيجة الروليت")
    embed_res.set_thumbnail(url=GIFS["casino"])

    if outcome == user_choice:
        multiplier = 14 if outcome == "أخضر" else 2
        win_amt = amount * (multiplier - 1)
        await update_user(ctx.author.id, "wallet", win_amt)
        embed_res.color = discord.Color.green()
        embed_res.description = f"وقفت العجلة على **{outcome}**! 🎉 فزت بـ **{win_amt + amount:,}** {CURRENCY_NAME}!"
    else:
        await update_user(ctx.author.id, "wallet", -amount)
        embed_res.color = discord.Color.red()
        embed_res.description = f"وقفت العجلة على **{outcome}**! 💀 خسرت **{amount:,}** {CURRENCY_NAME}."

    await ctx.send(embed=embed_res)

@bot.command(name="سلوت", aliases=["آلة"])
async def slot(ctx, amount: int):
    data = await get_user_data(ctx.author.id)
    if amount <= 0 or data["wallet"] < amount:
        await ctx.send("❌ ما عندك هذا المبلغ بالكاش!")
        return

    emojis = ["🍒", "🍋", "💎", "🔔", "7️⃣"]
    r1, r2, r3 = random.choice(emojis), random.choice(emojis), random.choice(emojis)

    embed = discord.Embed(title="🎰 آلة القمار السحرية", description=f"# [ {r1} | {r2} | {r3} ]", color=discord.Color.gold())
    embed.set_thumbnail(url=GIFS["slots"])
    
    if r1 == r2 == r3:
        mult = 10 if r1 == "7️⃣" else 5
        win_amt = amount * mult
        await update_user(ctx.author.id, "wallet", win_amt)
        embed.add_field(name="النتيجة:", value=f"🎉 **جاك بوت كاسح!** فزت بـ **{win_amt:,}** {CURRENCY_NAME}!")
    elif r1 == r2 or r2 == r3 or r1 == r3:
        win_amt = int(amount * 0.5)
        await update_user(ctx.author.id, "wallet", win_amt)
        embed.add_field(name="النتيجة:", value=f"✨ رمزان متطابقان! استرجعت **{win_amt:,}** {CURRENCY_NAME}!")
    else:
        await update_user(ctx.author.id, "wallet", -amount)
        embed.add_field(name="النتيجة:", value=f"💀 الحظ ما حالفك! خسرت **{amount:,}** {CURRENCY_NAME}.")

    await ctx.send(embed=embed)

@bot.command(name="سباق", aliases=["خيل"])
async def race(ctx, amount: int):
    data = await get_user_data(ctx.author.id)
    if amount <= 0 or data["wallet"] < amount:
        await ctx.send("❌ ما عندك هذا المبلغ بالكاش!")
        return

    horses = ["1️⃣ الحصان الأبيض 🐎", "2️⃣ الحصان الأسود 🐎", "3️⃣ الحصان الذهبي 🐎", "4️⃣ الحصان السريع 🐎"]
    embed = discord.Embed(
        title="🏇 ميدان سباق الأحصنة",
        description=f"الرهان: **{amount:,}** {CURRENCY_NAME}\n\nاختر رقم حصانك (1 - 4):\n" + "\n".join(horses),
        color=discord.Color.dark_gold()
    )
    embed.set_thumbnail(url=GIFS["race"])
    await ctx.send(embed=embed)

    def check(m):
        return m.author == ctx.author and m.channel == ctx.channel and m.content in ["1", "2", "3", "4"]

    try:
        choice_msg = await bot.wait_for("message", timeout=15.0, check=check)
        user_horse = int(choice_msg.content) - 1
    except asyncio.TimeoutError:
        await ctx.send("⏰ انتهى الوقت!")
        return

    race_embed = discord.Embed(title="🏁 السباق مشتعل الآن!", description="🏇 💨 💨 💨 الأحصنة تركض بسرعة!", color=discord.Color.blue())
    race_embed.set_image(url=GIFS["race"])
    race_msg = await ctx.send(embed=race_embed)
    await asyncio.sleep(3)

    winner = random.randint(0, 3)
    
    res_embed = discord.Embed(title="🏆 خط النهاية!")
    res_embed.set_thumbnail(url=GIFS["race"])

    if user_horse == winner:
        win_amt = amount * 3
        await update_user(ctx.author.id, "wallet", win_amt)
        res_embed.color = discord.Color.green()
        res_embed.description = f"فاز **{horses[winner]}**!\n🎉 كسبت **{win_amt:,}** {CURRENCY_NAME}!"
    else:
        await update_user(ctx.author.id, "wallet", -amount)
        res_embed.color = discord.Color.red()
        res_embed.description = f"فاز **{horses[winner]}**!\n💀 خسرت رهانك بـ **{amount:,}** {CURRENCY_NAME}."

    await race_msg.edit(embed=res_embed)

# =========================
# باقي الأوامر والبورصة
# =========================

@bot.command(name="سوق", aliases=["اسهم", "market"])
async def market(ctx):
    embed = discord.Embed(title="📊 بورصة فابريونيوم العالمية", color=discord.Color.blue())
    embed.set_thumbnail(url=GIFS["market"])
    for key, stock in STOCKS.items():
        embed.add_field(
            name=f"{stock['name']} (`{key}`)",
            value=f"السعر: **{stock['price']:,}** {CURRENCY_NAME} | **{stock['trend']}**",
            inline=False
        )
    embed.set_footer(text="تتغير الأسعار تلقائياً كل 5 دقائق!")
    await ctx.send(embed=embed)

def get_stock_key(name: str):
    name = name.lower()
    mapping = {
        "aramco": "aramco", "أرامكو": "aramco", "ارامكو": "aramco",
        "apple": "apple", "أبل": "apple", "ابل": "apple",
        "tesla": "tesla", "تسلا": "tesla",
        "nvidia": "nvidia", "إنفيديا": "nvidia", "انفيديا": "nvidia",
        "disney": "disney", "ديزني": "disney",
        "boeing": "boeing", "بوينج": "boeing", "بوينغ": "boeing",
        "crypto": "crypto", "كريبتو": "crypto"
    }
    return mapping.get(name, None)

@bot.command(name="شراء", aliases=["buy"])
async def buy_stocks(ctx, stock_name: str, amount: int):
    key = get_stock_key(stock_name)
    if not key or amount <= 0:
        await ctx.send("❌ شركة غير صحيحة! اكتب `=سوق` لمعرفة أسماء الشركات المتاحة.")
        return

    stock = STOCKS[key]
    cost = amount * stock["price"]
    data = await get_user_data(ctx.author.id)

    if data["wallet"] < cost:
        await ctx.send(f"❌ الكاش ما يكفي! تحتاج **{cost:,}** {CURRENCY_NAME}.")
        return

    await update_user(ctx.author.id, "wallet", -cost)
    await update_user(ctx.author.id, key, amount)
    
    embed = discord.Embed(title="📈 صفقة ناجحة!", description=f"اشتريت **{amount}** أسهم في **{stock['name']}** بـ **{cost:,}** {CURRENCY_NAME}!", color=discord.Color.green())
    embed.set_thumbnail(url=GIFS["market"])
    await ctx.send(embed=embed)

@bot.command(name="بيع", aliases=["sell"])
async def sell_stocks(ctx, stock_name: str, amount: int):
    key = get_stock_key(stock_name)
    if not key or amount <= 0:
        await ctx.send("❌ شركة غير صحيحة! اكتب `=سوق` لمعرفة أسماء الشركات المتاحة.")
        return

    stock = STOCKS[key]
    data = await get_user_data(ctx.author.id)

    if data[key] < amount:
        await ctx.send(f"❌ ما عندك هذا العدد! تملك **{data[key]}** أسهم فقط في {stock['name']}.")
        return

    revenue = amount * stock["price"]
    await update_user(ctx.author.id, "wallet", revenue)
    await update_user(ctx.author.id, key, -amount)

    embed = discord.Embed(title="💰 بيع أسهم", description=f"بعت **{amount}** أسهم من **{stock['name']}** واستلمت **{revenue:,}** {CURRENCY_NAME}!", color=discord.Color.gold())
    embed.set_thumbnail(url=GIFS["market"])
    await ctx.send(embed=embed)

@bot.command(name="اسهمي", aliases=["my-stocks"])
async def my_stocks(ctx):
    data = await get_user_data(ctx.author.id)
    total_val = 0
    desc = ""
    
    for key, stock in STOCKS.items():
        count = data[key]
        val = count * stock["price"]
        total_val += val
        if count > 0:
            desc += f"• **{stock['name']}:** {count} أسهم (بقيمة {val:,} {CURRENCY_NAME})\n"

    if not desc:
        desc = "لا تمتلك أي أسهم حالياً! استخدم أمر `=سوق` للاستثمار."

    embed = discord.Embed(title=f"📈 محفظة {ctx.author.display_name} الاستثمارية", description=desc, color=discord.Color.green())
    embed.set_thumbnail(url=GIFS["market"])
    embed.add_field(name="💎 إجمالي قيمة أسهمك:", value=f"**{total_val:,}** {CURRENCY_NAME}")
    await ctx.send(embed=embed)

@bot.command(name="فلوس", aliases=["رصيد", "bal"])
async def balance(ctx, member: discord.Member = None):
    target = member or ctx.author
    data = await get_user_data(target.id)
    
    stocks_val = sum(data[key] * STOCKS[key]["price"] for key in STOCKS)
    total = data["wallet"] + data["bank"] + stocks_val

    embed = discord.Embed(title=f"💳 الحساب البنكي لـ {target.display_name}", color=discord.Color.purple())
    embed.set_thumbnail(url=GIFS["bank"])
    embed.add_field(name="💵 كاش المحفظة:", value=f"**{data['wallet']:,}** {CURRENCY_NAME}", inline=True)
    embed.add_field(name="🏦 الرصيد في البنك:", value=f"**{data['bank']:,}** {CURRENCY_NAME}", inline=True)
    embed.add_field(name="📈 قيمة الأسهم:", value=f"**{stocks_val:,}** {CURRENCY_NAME}", inline=False)
    embed.add_field(name="💎 صافي الثروة:", value=f"**{total:,}** {CURRENCY_NAME}", inline=False)
    await ctx.send(embed=embed)

@bot.command(name="راتب", aliases=["يومي"])
@commands.cooldown(1, 86400, commands.BucketType.user)
async def daily(ctx):
    await update_user(ctx.author.id, "wallet", 500)
    embed = discord.Embed(title="🎉 الراتب اليومي", description=f"أخذت راتبك اليومي بقيمة **500** {CURRENCY_NAME}!", color=discord.Color.green())
    embed.set_thumbnail(url=GIFS["rich"])
    await ctx.send(embed=embed)

@daily.error
async def daily_error(ctx, error):
    if isinstance(error, commands.CommandOnCooldown):
        hours = int(error.retry_after // 3600)
        await ctx.send(f"⏳ راتبك الجاي بعد **{hours}** ساعة.")

@bot.command(name="عمل")
@commands.cooldown(1, 3600, commands.BucketType.user)
async def work(ctx):
    earnings = random.randint(50, 200)
    await update_user(ctx.author.id, "wallet", earnings)
    embed = discord.Embed(title="💼 دوام العمل", description=f"اشتغلت بجد وكسبت **{earnings}** {CURRENCY_NAME}!", color=discord.Color.blue())
    embed.set_thumbnail(url=GIFS["work"])
    await ctx.send(embed=embed)

@work.error
async def work_error(ctx, error):
    if isinstance(error, commands.CommandOnCooldown):
        minutes = int(error.retry_after // 60)
        await ctx.send(f"⏳ تقدر تشتغل بعد **{minutes}** دقيقة.")

@bot.command(name="ضم", aliases=["إيداع"])
async def deposit(ctx, amount: str):
    data = await get_user_data(ctx.author.id)
    amt = data["wallet"] if amount.lower() in ["الكل", "all"] else (int(amount) if amount.isdigit() else 0)

    if amt <= 0 or data["wallet"] < amt:
        await ctx.send("❌ ما عندك هذا المبلغ بالكاش!")
        return

    await update_user(ctx.author.id, "wallet", -amt)
    await update_user(ctx.author.id, "bank", amt)
    
    embed = discord.Embed(title="🏦 إيداع بنكي", description=f"ضمت **{amt:,}** {CURRENCY_NAME} في البنك لحمايتها!", color=discord.Color.teal())
    embed.set_thumbnail(url=GIFS["bank"])
    await ctx.send(embed=embed)

@bot.command(name="سحب")
async def withdraw(ctx, amount: str):
    data = await get_user_data(ctx.author.id)
    amt = data["bank"] if amount.lower() in ["الكل", "all"] else (int(amount) if amount.isdigit() else 0)

    if amt <= 0 or data["bank"] < amt:
        await ctx.send("❌ ما عندك هذا المبلغ بالبنك!")
        return

    await update_user(ctx.author.id, "bank", -amt)
    await update_user(ctx.author.id, "wallet", amt)

    embed = discord.Embed(title="💵 سحب نقدي", description=f"سحبت **{amt:,}** {CURRENCY_NAME} من البنك للمحفظة!", color=discord.Color.gold())
    embed.set_thumbnail(url=GIFS["bank"])
    await ctx.send(embed=embed)

@bot.command(name="تحويل")
async def transfer(ctx, member: discord.Member, amount: int):
    if member.bot or member.id == ctx.author.id or amount <= 0:
        await ctx.send("❌ أمر خاطئ!")
        return

    data = await get_user_data(ctx.author.id)
    if data["wallet"] < amount:
        await ctx.send("❌ الكاش ما يكفي!")
        return

    await update_user(ctx.author.id, "wallet", -amount)
    await update_user(member.id, "wallet", amount)
    
    embed = discord.Embed(title="💸 تحويل مال", description=f"حولت **{amount:,}** {CURRENCY_NAME} إلى {member.mention}!", color=discord.Color.green())
    await ctx.send(embed=embed)

@bot.command(name="سرقة")
@commands.cooldown(1, 7200, commands.BucketType.user)
async def rob(ctx, member: discord.Member):
    if member.bot or member.id == ctx.author.id:
        await ctx.send("❌ ما تقدر تسرق البوت أو نفسك!")
        return

    target_data = await get_user_data(member.id)
    if target_data["wallet"] < 100:
        await ctx.send("❌ مطفر، ما معه كاش يستهل تسرقه!")
        return

    embed = discord.Embed(title="🥷 عملية سرقة")
    if random.random() < 0.40:
        stolen = random.randint(10, int(target_data["wallet"] * 0.5))
        await update_user(member.id, "wallet", -stolen)
        await update_user(ctx.author.id, "wallet", stolen)
        embed.color = discord.Color.green()
        embed.description = f"نجحت السرقة! سرقت **{stolen:,}** {CURRENCY_NAME} من {member.mention}!"
    else:
        await update_user(ctx.author.id, "wallet", -50)
        embed.color = discord.Color.red()
        embed.description = f"🚨 مسكتك الشرطة وغرمتك **50** {CURRENCY_NAME}!"

    await ctx.send(embed=embed)

@bot.command(name="توب")
async def leaderboard(ctx):
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute(
            "SELECT user_id, (wallet + bank + (aramco * ?) + (apple * ?) + (tesla * ?) + (nvidia * ?) + (disney * ?) + (boeing * ?) + (crypto * ?)) AS total FROM economy ORDER BY total DESC LIMIT 10",
            (
                STOCKS["aramco"]["price"], STOCKS["apple"]["price"], STOCKS["tesla"]["price"],
                STOCKS["nvidia"]["price"], STOCKS["disney"]["price"], STOCKS["boeing"]["price"],
                STOCKS["crypto"]["price"]
            )
        ) as cursor:
            users = await cursor.fetchall()

    if not users:
        await ctx.send("📭 ما فيه أحد مسجل.")
        return

    desc = ""
    for idx, (user_id, total) in enumerate(users, start=1):
        member = ctx.guild.get_member(int(user_id))
        name = member.display_name if member else f"<@{user_id}>"
        desc += f"**#{idx}** {name} — 💎 **{total:,}** {CURRENCY_NAME}\n"

    embed = discord.Embed(title="🏆 قائـمة أثرى أثريـاء السيرفر", description=desc, color=discord.Color.gold())
    embed.set_thumbnail(url=GIFS["rich"])
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
