import discord
from discord.ext import commands
import os

intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix="", intents=intents)

# روم الـ bank المخصص للأوامر
ALLOWED_CHANNEL_ID = 1544385495310540881

@bot.event
async def on_ready():
    print(f"تم تسجيل الدخول بنجاح باسم {bot.user}")

# شرط لتقييد الأوامر داخل الروم المخصص فقط
def in_allowed_channel():
    async def predicate(ctx):
        if ctx.channel.id != ALLOWED_CHANNEL_ID:
            return False
        return True
    return commands.check(predicate)

@bot.command(name="مساعدة")
@in_allowed_channel()
async def help_cmd(ctx):
    embed = discord.Embed(
        title="الأسعار و الأوامر | Central Bank",
        description="سيتم تحديث الاسعار بعد : 05:32.8",
        color=discord.Color.dark_theme()
    )
    embed.add_field(name="🚗 سيارات", value="📉 111,110 $", inline=False)
    embed.add_field(name="📊 أسهم", value="📉 38,853 $", inline=False)
    embed.add_field(name="🏙️ أراضي", value="📈 391,193 $", inline=False)
    
    view = discord.ui.View()
    button = discord.ui.Button(label="معلومات الاسعار", style=discord.ButtonStyle.secondary)
    view.add_item(button)
    
    await ctx.send(embed=embed, view=view)

# التعامل مع محاولة استخدام الأوامر في روم غير مخصص (تجاهل أو تفاعل صامت)
@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.CheckFailure):
        await ctx.message.add_reaction("❌")

# تشغيل البوت باستخدام توكن البيئة في Render
bot.run(os.getenv("DISCORD_TOKEN"))
