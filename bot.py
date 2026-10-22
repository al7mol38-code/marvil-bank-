import os
import random
import logging
from datetime import datetime, timezone, date
import discord
from discord import app_commands
from discord.ext import commands, tasks
import asyncpg

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("bot-albank")

DATABASE_URL = os.getenv("DATABASE_URL")
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
GUILD_ID = os.getenv("GUILD_ID")
STARTING_BALANCE = int(os.getenv("STARTING_BALANCE", "500"))

if not DISCORD_TOKEN:
    raise RuntimeError("Missing DISCORD_TOKEN environment variable")
if not DATABASE_URL:
    raise RuntimeError("Missing DATABASE_URL environment variable")

def normalize_db_url(url: str) -> str:
    # Render sometimes provides postgres://; asyncpg expects postgresql://
    if url.startswith("postgres://"):
        return "postgresql://" + url[len("postgres://"):]
    return url

class BankBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        super().__init__(command_prefix="!", intents=intents)
        self.pool = None

    async def setup_hook(self):
        self.pool = await asyncpg.create_pool(normalize_db_url(DATABASE_URL), min_size=1, max_size=5)
        async with self.pool.acquire() as conn:
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    user_id BIGINT PRIMARY KEY,
                    username TEXT NOT NULL,
                    wallet BIGINT NOT NULL DEFAULT 500 CHECK (wallet >= 0),
                    bank BIGINT NOT NULL DEFAULT 0 CHECK (bank >= 0),
                    level INTEGER NOT NULL DEFAULT 1,
                    xp INTEGER NOT NULL DEFAULT 0,
                    daily_claimed DATE,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                );
                CREATE TABLE IF NOT EXISTS transactions (
                    id BIGSERIAL PRIMARY KEY,
                    user_id BIGINT NOT NULL,
                    kind TEXT NOT NULL,
                    amount BIGINT NOT NULL,
                    note TEXT NOT NULL DEFAULT '',
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                );
                CREATE INDEX IF NOT EXISTS transactions_user_created_idx
                    ON transactions(user_id, created_at DESC);
            """)
        if GUILD_ID and GUILD_ID.isdigit():
            guild = discord.Object(id=int(GUILD_ID))
            self.tree.copy_global_to(guild=guild)
            await self.tree.sync(guild=guild)
            log.info("Synced commands to test guild %s", GUILD_ID)
        else:
            await self.tree.sync()
            log.info("Synced global commands")
        self.daily_economy_check.start()

    async def close(self):
        if self.pool:
            await self.pool.close()
        await super().close()

    async def ensure_user(self, user: discord.abc.User):
        async with self.pool.acquire() as conn:
            await conn.execute("""
                INSERT INTO users (user_id, username, wallet)
                VALUES ($1, $2, $3)
                ON CONFLICT (user_id) DO UPDATE SET
                    username = EXCLUDED.username,
                    updated_at = NOW()
            """, user.id, str(user), STARTING_BALANCE)

    async def record(self, user_id: int, kind: str, amount: int, note: str = ""):
        async with self.pool.acquire() as conn:
            await conn.execute(
                "INSERT INTO transactions (user_id, kind, amount, note) VALUES ($1,$2,$3,$4)",
                user_id, kind, amount, note
            )

    @tasks.loop(hours=24)
    async def daily_economy_check(self):
        # Placeholder for rotating market/news/events; keep the economy predictable until configured.
        log.info("Daily economy tick: %s", datetime.now(timezone.utc).isoformat())

    @daily_economy_check.before_loop
    async def before_daily_economy_check(self):
        await self.wait_until_ready()

bot = BankBot()

@bot.event
async def on_ready():
    log.info("Logged in as %s (%s)", bot.user, bot.user.id)

@bot.tree.command(name="رصيدي", description="عرض رصيد محفظتك والبنك")
async def balance(interaction: discord.Interaction):
    await bot.ensure_user(interaction.user)
    async with bot.pool.acquire() as conn:
        row = await conn.fetchrow("SELECT wallet, bank, level, xp FROM users WHERE user_id=$1", interaction.user.id)
    embed = discord.Embed(title=f"🏦 حساب {interaction.user.display_name}", color=discord.Color.gold())
    embed.add_field(name="المحفظة", value=f"🪙 {row['wallet']:,}", inline=True)
    embed.add_field(name="البنك", value=f"🏛️ {row['bank']:,}", inline=True)
    embed.add_field(name="المستوى", value=f"⭐ {row['level']} · {row['xp']} XP", inline=True)
    await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.tree.command(name="يومي", description="استلم مكافأتك اليومية")
async def daily(interaction: discord.Interaction):
    await bot.ensure_user(interaction.user)
    today = date.today()
    reward = random.randint(250, 450)
    async with bot.pool.acquire() as conn:
        async with conn.transaction():
            row = await conn.fetchrow("SELECT daily_claimed FROM users WHERE user_id=$1 FOR UPDATE", interaction.user.id)
            if row["daily_claimed"] == today:
                await interaction.response.send_message("⏳ استلمت مكافأتك اليوم. ارجع بكرة!", ephemeral=True)
                return
            await conn.execute(
                "UPDATE users SET wallet=wallet+$1, daily_claimed=$2, updated_at=NOW() WHERE user_id=$3",
                reward, today, interaction.user.id
            )
            await conn.execute(
                "INSERT INTO transactions (user_id, kind, amount, note) VALUES ($1,'daily',$2,'مكافأة يومية')",
                interaction.user.id, reward
            )
    await interaction.response.send_message(f"🎁 حصلت على **{reward:,}** عملة كمكافأة يومية!")

@bot.tree.command(name="عمل", description="اشتغل لتحصل على عملات")
async def work(interaction: discord.Interaction):
    await bot.ensure_user(interaction.user)
    reward = random.randint(80, 180)
    async with bot.pool.acquire() as conn:
        await conn.execute("UPDATE users SET wallet=wallet+$1, xp=xp+10, updated_at=NOW() WHERE user_id=$2", reward, interaction.user.id)
        await conn.execute("INSERT INTO transactions (user_id, kind, amount, note) VALUES ($1,'work',$2,'عمل')", interaction.user.id, reward)
    await interaction.response.send_message(f"🛠️ أنجزت عملك وربحت **{reward:,}** عملة و **10 XP**.")

@bot.tree.command(name="إيداع", description="إيداع عملات من المحفظة إلى البنك")
@app_commands.describe(amount="عدد العملات المراد إيداعها")
async def deposit(interaction: discord.Interaction, amount: app_commands.Range[int, 1, 1_000_000_000]):
    await bot.ensure_user(interaction.user)
    async with bot.pool.acquire() as conn:
        async with conn.transaction():
            row = await conn.fetchrow("SELECT wallet FROM users WHERE user_id=$1 FOR UPDATE", interaction.user.id)
            if row["wallet"] < amount:
                await interaction.response.send_message("❌ رصيد المحفظة لا يكفي.", ephemeral=True)
                return
            await conn.execute("UPDATE users SET wallet=wallet-$1, bank=bank+$1, updated_at=NOW() WHERE user_id=$2", amount, interaction.user.id)
            await conn.execute("INSERT INTO transactions (user_id, kind, amount, note) VALUES ($1,'deposit',$2,'إيداع في البنك')", interaction.user.id, amount)
    await interaction.response.send_message(f"🏦 تم إيداع **{amount:,}** عملة في البنك.")

@bot.tree.command(name="سحب", description="سحب عملات من البنك إلى المحفظة")
@app_commands.describe(amount="عدد العملات المراد سحبها")
async def withdraw(interaction: discord.Interaction, amount: app_commands.Range[int, 1, 1_000_000_000]):
    await bot.ensure_user(interaction.user)
    async with bot.pool.acquire() as conn:
        async with conn.transaction():
            row = await conn.fetchrow("SELECT bank FROM users WHERE user_id=$1 FOR UPDATE", interaction.user.id)
            if row["bank"] < amount:
                await interaction.response.send_message("❌ رصيد البنك لا يكفي.", ephemeral=True)
                return
            await conn.execute("UPDATE users SET bank=bank-$1, wallet=wallet+$1, updated_at=NOW() WHERE user_id=$2", amount, interaction.user.id)
            await conn.execute("INSERT INTO transactions (user_id, kind, amount, note) VALUES ($1,'withdraw',$2,'سحب من البنك')", interaction.user.id, amount)
    await interaction.response.send_message(f"💵 تم سحب **{amount:,}** عملة إلى محفظتك.")

@bot.tree.command(name="تحويل", description="حوّل عملات إلى عضو آخر")
@app_commands.describe(member="العضو المستلم", amount="عدد العملات")
async def transfer(interaction: discord.Interaction, member: discord.Member, amount: app_commands.Range[int, 1, 1_000_000_000]):
    if member.bot or member.id == interaction.user.id:
        await interaction.response.send_message("❌ اختر عضوًا آخر غير البوتات.", ephemeral=True)
        return
    await bot.ensure_user(interaction.user)
    await bot.ensure_user(member)
    async with bot.pool.acquire() as conn:
        async with conn.transaction():
            sender = await conn.fetchrow("SELECT wallet FROM users WHERE user_id=$1 FOR UPDATE", interaction.user.id)
            if sender["wallet"] < amount:
                await interaction.response.send_message("❌ رصيدك لا يكفي للتحويل.", ephemeral=True)
                return
            await conn.execute("UPDATE users SET wallet=wallet-$1, updated_at=NOW() WHERE user_id=$2", amount, interaction.user.id)
            await conn.execute("UPDATE users SET wallet=wallet+$1, updated_at=NOW() WHERE user_id=$2", amount, member.id)
            await conn.execute("INSERT INTO transactions (user_id, kind, amount, note) VALUES ($1,'transfer_out',$2,$3)", interaction.user.id, amount, f"تحويل إلى {member.id}")
            await conn.execute("INSERT INTO transactions (user_id, kind, amount, note) VALUES ($1,'transfer_in',$2,$3)", member.id, amount, f"تحويل من {interaction.user.id}")
    await interaction.response.send_message(f"💸 تم تحويل **{amount:,}** عملة إلى {member.mention}.")

@bot.tree.command(name="المتصدرين", description="عرض أغنى 10 أعضاء مسجلين")
async def leaderboard(interaction: discord.Interaction):
    async with bot.pool.acquire() as conn:
        rows = await conn.fetch("SELECT username, wallet+bank AS wealth FROM users ORDER BY wealth DESC LIMIT 10")
    if not rows:
        await interaction.response.send_message("لا توجد بيانات حتى الآن.")
        return
    lines = [f"**{i}.** {r['username']} — 🪙 {r['wealth']:,}" for i, r in enumerate(rows, start=1)]
    embed = discord.Embed(title="🏆 أغنى الأعضاء", description="\n".join(lines), color=discord.Color.gold())
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="سوق", description="عرض حالة سوق التداول التجريبي")
async def market(interaction: discord.Interaction):
    embed = discord.Embed(title="📈 السوق الافتراضي", description="السوق قيد التجهيز. ستضاف الأسهم والأصول المتغيرة في المرحلة التالية.", color=discord.Color.blurple())
    embed.add_field(name="تنبيه", value="العملات والأصول داخل البوت افتراضية ولا تمثل استثمارًا حقيقيًا.")
    await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.tree.command(name="مساعدة", description="عرض أقسام البوت الأساسية")
async def help_command(interaction: discord.Interaction):
    embed = discord.Embed(title="✨ دليل بوت البانك", description="ابدأ بـ `/رصيدي` ثم `/يومي` و`/عمل`. أودع أموالك باستخدام `/إيداع` واسحبها باستخدام `/سحب`.", color=discord.Color.gold())
    embed.add_field(name="الأوامر الحالية", value="`/رصيدي` · `/يومي` · `/عمل` · `/إيداع` · `/سحب` · `/تحويل` · `/المتصدرين` · `/سوق`", inline=False)
    embed.set_footer(text="هذه نسخة البداية؛ ستضاف الأنظمة الأخرى تدريجيًا.")
    await interaction.response.send_message(embed=embed, ephemeral=True)

bot.run(DISCORD_TOKEN)
