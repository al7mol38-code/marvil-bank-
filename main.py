import os
import random
import asyncio
import aiosqlite
import discord
from discord.ext import commands, tasks

# =========================
# إعدادات البوت والقرص المدفوع
# =========================
DB_NAME = "points.db"  # مسار قاعدة البيانات
CURRENCY_NAME = "فابريونيوم"

# ID الروم المخصص للأوامر فقط
ALLOWED_CHANNEL_ID = 1544385495310540881

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
# قاعدة البيانات والتحقق
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

async def reset_user_data(user_id: int):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("""
            UPDATE economy 
            SET wallet = 0, bank = 0, aramco = 0, apple = 0, tesla = 0, nvidia = 0, disney = 0, boeing = 0, crypto = 0 
            WHERE user_id = ?
        """, (str(user_id),))
        await db.commit()

# تقييد البوت بروم معين
@bot.check
async def check_channel(ctx):
    if ctx.channel.id != ALLOWED_CHANNEL_ID:
        await ctx.send(f"❌ عفواً {ctx.author.mention}، الأوامر تعمل فقط في الروم المخصص: <#{ALLOWED_CHANNEL_ID}>", delete_after=5)
        return False
    return True

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

    async def on_timeout(self):
        for item in self.children:
            item.disabled = True

# =========================
# الأحداث وتجاهل الأخطاء
# =========================
@bot.event
async def on_ready():
    await init_db()
    if not update_stock_market.is_running():
        update_stock_market.start()
    print(f"✅ البوت شغال بنجاح باسم: {bot.user}")

@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, (commands.CommandNotFound, commands.CheckFailure)):
        return
    if isinstance(error, commands.MissingPermissions):
        await ctx.send("❌ هذا الأمر خاص بالإدارة فقط!", delete_after=5)
        return
    print(f"خطأ: {error}")

# =========================
# الأوامر الرئيسية والمساعدة
# =========================

@bot.command(name="مساعدة", aliases=["help", "اوامر", "الأوامر"])
async def help_cmd(ctx):
    embed = discord.Embed(
        title="💎 دليل أوامر البوت المطور",
        description=(
            "**💵 الاقتصاد والبنك:**\n"
            "• `=فلوس` ➜ معرفة رصيدك الكلي والأسهم\n"
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
            "• `=اسهمي` ➜ محفظتك | `=توب` ➜ قائمة الأثرياء"
        ),
        color=discord.Color.gold()
    )
    embed.set_thumbnail(url=GIFS["casino"])
    await ctx.send(embed=embed)

@bot.command(name="فعالية", aliases=["حدث", "event"])
async def start_event(ctx, amount: int):
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
        await ctx.send("❌ ما عندك هذا المبلغ بالكاش
