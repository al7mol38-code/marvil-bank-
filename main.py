import os
import aiosqlite
import discord
from discord.ext import commands

# ----------------------------------------------------
# 1. إعدادات البوت وقاعدة البيانات والرومات
# ----------------------------------------------------
TOKEN = os.getenv("DISCORD_TOKEN")
DB_NAME = "points.db"

# ID الروم المخصص للأوامر فقط
ALLOWED_CHANNEL_ID = 1544385495310540881

# أسعار الأسهم الافتراضية
STOCK_PRICES = {
    "aramco": 30,
    "apple": 150,
    "tesla": 200,
    "nvidia": 120,
    "disney": 90,
    "boeing": 180,
    "crypto": 50000,
}

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents, help_command=None)

# ----------------------------------------------------
# 2. إنشاء وتحديث قاعدة البيانات تلقائياً (Auto Migration)
# ----------------------------------------------------
async def init_db():
    db_dir = os.path.dirname(DB_NAME)
    if db_dir and not os.path.exists(db_dir):
        os.makedirs(db_dir, exist_ok=True)

    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS economy (
                user_id TEXT PRIMARY KEY,
                wallet INTEGER DEFAULT 100,
                bank INTEGER DEFAULT 0
            )
        """)
        await db.commit()

        async with db.execute("PRAGMA table_info(economy)") as cursor:
            columns_info = await cursor.fetchall()
            existing_columns = [column[1] for column in columns_info]

        required_columns = ["aramco", "apple", "tesla", "nvidia", "disney", "boeing", "crypto"]

        for col in required_columns:
            if col not in existing_columns:
                await db.execute(f"ALTER TABLE economy ADD COLUMN {col} INTEGER DEFAULT 0")
        
        await db.commit()

# ----------------------------------------------------
# 3. تقييد البوت بروم معين فقط لكل الأوامر
# ----------------------------------------------------
@bot.check
async def check_channel(ctx):
    if ctx.channel.id != ALLOWED_CHANNEL_ID:
        await ctx.send(f"❌ عفواً {ctx.author.mention}، الأوامر تعمل فقط في الروم المخصص: <#{ALLOWED_CHANNEL_ID}>", delete_after=5)
        return False
    return True

# ----------------------------------------------------
# 4. الدوال المساعدة للقراءة والتحديث
# ----------------------------------------------------
async def get_user_data(user_id: int):
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute(
            "SELECT wallet, bank, aramco, apple, tesla, nvidia, disney, boeing, crypto FROM economy WHERE user_id = ?",
            (str(user_id),)
        ) as cursor:
            row = await cursor.fetchone()
            
        if row is None:
            await db.execute("INSERT INTO economy (user_id) VALUES (?)", (str(user_id),))
            await db.commit()
            return {
                "wallet": 100, "bank": 0, "aramco": 0, "apple": 0,
                "tesla": 0, "nvidia": 0, "disney": 0, "boeing": 0, "crypto": 0
            }
        
        return {
            "wallet": row[0], "bank": row[1], "aramco": row[2], "apple": row[3],
            "tesla": row[4], "nvidia": row[5], "disney": row[6], "boeing": row[7], "crypto": row[8]
        }

async def update_user(user_id: int, column: str, amount: int):
    await get_user_data(user_id)
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute(
            f"UPDATE economy SET {column} = {column} + ? WHERE user_id = ?",
            (amount, str(user_id))
        )
        await db.commit()

async def reset_user_data(user_id: int):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("""
            UPDATE economy 
            SET wallet = 0, bank = 0, aramco = 0, apple = 0, tesla = 0, nvidia = 0, disney = 0, boeing = 0, crypto = 0 
            WHERE user_id = ?
        """, (str(user_id),))
        await db.commit()

# ----------------------------------------------------
# 5. زر واستلام الهدايا (UI)
# ----------------------------------------------------
class EventClaimView(discord.ui.View):
    def __init__(self, amount: int = 50, timeout: float = 60.0):
        super().__init__(timeout=timeout)
        self.amount = amount

    @discord.ui.button(label="استلام الهدية 🎉", style=discord.ButtonStyle.success, emoji="🎁", custom_id="claim_button")
    async def claim_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await update_user(interaction.user.id, "wallet", self.amount)
        button.disabled = True
        await interaction.response.edit_message(view=self)
        await interaction.followup.send(f"🎉 مبروك {interaction.user.mention}! حصلت على {self.amount} ريال!", ephemeral=True)

# ----------------------------------------------------
# 6. أحداث وتجاهل الأخطاء
# ----------------------------------------------------
@bot.event
async def on_ready():
    await init_db()
    print(f"✅ تم تشغيل البوت بنجاح باسم: {bot.user}")

@bot.event
async def on_command_error(ctx, error):
    # تجاهل الأوامر غير الموجودة أو عدم استيفاء شروط الروم والصلاحيات
    if isinstance(error, (commands.CommandNotFound, commands.CheckFailure)):
        return
    if isinstance(error, commands.MissingPermissions):
        await ctx.send("❌ هذا الأمر خاص بالإدارة فقط!", delete_after=5)
        return
    print(f"حدث خطأ غير متوقع: {error}")

# ----------------------------------------------------
# 7. أوامر الأعضاء العامة
# ----------------------------------------------------

# أمر المساعدة العام
@bot.command(name="مساعدة", aliases=["help", "اوامر", "الأوامر"])
async def help_command(ctx):
    embed = discord.Embed(
        title="📖 دليل استخدام البوت",
        description="إليك قائمة بالأوامر المتاحة للاستخدام:",
        color=discord.Color.teal()
    )
    embed.add_field(name="💰 `!فلوس`", value="عرض الكاش والبنك والأسهم الخاصة بك.", inline=False)
    embed.add_field(name="📈 `!اسهم`", value="استعراض قائمة أسعار الأسهم والممتلكات.", inline=False)
    embed.add_field(name="🏆 `!توب`", value="عرض قائمة أثرى 10 أعضاء بالسيرفر.", inline=False)
    embed.add_field(name="🎁 `!هدية [المبلغ]`", value="إنشاء فعالية توزيع هدية مالية.", inline=False)
    embed.set_footer(text="استخدم الأوامر فقط داخل الروم المخصص 💬")
    await ctx.send(embed=embed)

# أمر الاستعلام عن الرصيد: !فلوس
@bot.command(name="فلوس", aliases=["رصيد", "balance"])
async def balance(ctx, target: discord.Member = None):
    target = target or ctx.author
    data = await get_user_data(target.id)
    
    embed = discord.Embed(title=f"💳 محفظة {target.display_name}", color=discord.Color.gold())
    embed.add_field(name="💵 الكاش", value=f"{data['wallet']} ريال", inline=True)
    embed.add_field(name="🏦 البنك", value=f"{data['bank']} ريال", inline=True)
    
    stocks_text = (
        f"⛽ أرامكو: {data['aramco']}\n"
        f"🍎 أبل: {data['apple']}\n"
        f"🚗 تسلا: {data['tesla']}\n"
        f"💚 إنفيديا: {data['nvidia']}\n"
        f"🏰 ديزني: {data['disney']}\n"
        f"✈️ بوينغ: {data['boeing']}\n"
        f"🪙 كريبتو: {data['crypto']}"
    )
    embed.add_field(name="📊 الأسهم والممتلكات", value=stocks_text, inline=False)
    await ctx.send(embed=embed)

# أمر استعراض الأسهم: !اسهم
@bot.command(name="اسهم", aliases=["أسهم", "stocks"])
async def stocks_list(ctx):
    p = STOCK_PRICES
    embed = discord.Embed(title="📈 قائمة أسعار الأسهم الحالية", color=discord.Color.green())
    embed.add_field(name="⛽ أرامكو (aramco)", value=f"{p['aramco']} ريال", inline=True)
    embed.add_field(name="🍎 أبل (apple)", value=f"{p['apple']} ريال", inline=True)
    embed.add_field(name="🚗 تسلا (tesla)", value=f"{p['tesla']} ريال", inline=True)
    embed.add_field(name="💚 إنفيديا (nvidia)", value=f"{p['nvidia']} ريال", inline=True)
    embed.add_field(name="🏰 ديزني (disney)", value=f"{p['disney']} ريال", inline=True)
    embed.add_field(name="✈️ بوينغ (boeing)", value=f"{p['boeing']} ريال", inline=True)
    embed.add_field(name="🪙 كريبتو (crypto)", value=f"{p['crypto']} ريال", inline=True)
    await ctx.send(embed=embed)

# أمر المتصدرين: !توب
@bot.command(name="توب", aliases=["leaderboard", "top"])
async def leaderboard(ctx):
    p = STOCK_PRICES
    query = """
    SELECT user_id, 
           (wallet + bank + (aramco * ?) + (apple * ?) + (tesla * ?) + (nvidia * ?) + (disney * ?) + (boeing * ?) + (crypto * ?)) AS total 
    FROM economy 
    ORDER BY total DESC 
    LIMIT 10
    """
    params = (p["aramco"], p["apple"], p["tesla"], p["nvidia"], p["disney"], p["boeing"], p["crypto"])
    
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute(query, params) as cursor:
            top_users = await cursor.fetchall()

    embed = discord.Embed(title="🏆 قائمة أثرى أثرياء السيرفر", color=discord.Color.blue())
    for idx, (user_id, total) in enumerate(top_users, start=1):
        user = ctx.guild.get_member(int(user_id))
        name = user.display_name if user else f"مستخدم ({user_id})"
        embed.add_field(name=f"#{idx} {name}", value=f"💰 الثروة الإجمالية: {total:,} ريال", inline=False)

    await ctx.send(embed=embed)

# أمر إرسال هدية: !هدية
@bot.command(name="هدية")
async def give_gift(ctx, amount: int = 100):
    view = EventClaimView(amount=amount)
    await ctx.send(f"🎁 **فعالية جديدة!** اضغط على الزر أدناه للحصول على **{amount}** ريال!", view=view)

# ----------------------------------------------------
# 8. أوامر الإدارة (مخفية من قائمة المساعدة)
# ----------------------------------------------------
@bot.command(name="اعطاء", aliases=["addmoney", "givemoney"])
@commands.has_permissions(administrator=True)
async def add_money(ctx, target: discord.Member, amount: int):
    if amount <= 0:
        await ctx.send("❌ يجب أن يكون المبلغ أكبر من صفر!")
        return
    await update_user(target.id, "wallet", amount)
    await ctx.send(f"✅ تم إضافة **{amount:,}** ريال إلى محفظة {target.mention} بنجاح!")

@bot.command(name="سحب", aliases=["removemoney", "take"])
@commands.has_permissions(administrator=True)
async def remove_money(ctx, target: discord.Member, amount: int):
    if amount <= 0:
        await ctx.send("❌ يجب أن يكون المبلغ أكبر من صفر!")
        return
    await update_user(target.id, "wallet", -amount)
    await ctx.send(f"💸 تم سحب **{amount:,}** ريال من محفظة {target.mention} بنجاح!")

@bot.command(name="تصفير", aliases=["reset", "clearuser"])
@commands.has_permissions(administrator=True)
async def reset_user(ctx, target: discord.Member):
    await reset_user_data(target.id)
    await ctx.send(f"⚠️ تم تصفير كافة أموال وأسهم وممتلكات {target.mention} بنجاح!")

# ----------------------------------------------------
# 9. تشغيل البوت
# ----------------------------------------------------
if __name__ == "__main__":
    bot.run(TOKEN)
