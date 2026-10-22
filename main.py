import discord
from discord.ext import commands
import os
import random
import asyncio

intents = discord.Intents.default()
intents.message_content = True
intents.members = True

# استخدام بادئة فارغة أو علامة تعجب حسب رغبتك (هنا وضعنا علامة ! للأوامر لتجنب التداخل)
bot = commands.Bot(command_prefix="!", intents=intents)

# روم الـ bank المخصص للأوامر
ALLOWED_CHANNEL_ID = 1544385495310540881

# قاعدة بيانات مؤقتة لتخزين أرصدة المستخدمين (يمكن لاحقاً ربطها بـ MongoDB أو SQLite)
user_balances = {}
user_properties = {}

def get_balance(user_id):
    return user_balances.get(user_id, 1000) # الرصيد الافتتاحي 1000$

def set_balance(user_id, amount):
    user_balances[user_id] = amount

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

# 1. أمر المساعدة والأسعار الرئيسي (مشابه لصور البوت)
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
    embed.add_field(name="🚆 قطارات", value="📈 886,324 $", inline=False)
    embed.add_field(name="✈️ طائرات", value="📉 152,344 $", inline=False)
    embed.add_field(name="🏟️ ملاعب", value="📉 3,819,391 $", inline=False)
    
    view = discord.ui.View()
    price_info_button = discord.ui.Button(label="معلومات الاسعار", style=discord.ButtonStyle.secondary)
    view.add_item(price_info_button)
    
    await ctx.send(embed=embed, view=view)

# 2. أمر الرصيد (كشف)
@bot.command(name="رصيد")
@in_allowed_channel()
async def balance_cmd(ctx):
    bal = get_balance(ctx.author.id)
    embed = discord.Embed(
        title="حسابك المصرفي | Central Bank",
        description=f"رصيدك الحالي: **{bal:,} $**",
        color=discord.Color.gold()
    )
    await ctx.send(embed=embed)

# 3. أمر لعبة الإيموجي التفاعلية (مشابه لتصميم البوت بالصور)
@bot.command(name="ايموجي")
@in_allowed_channel()
async def emoji_game(ctx):
    emojis = ["👾", "🦆", "🤡", "⛳", "🥜", "🎻", "🧠", "🦍", "🏓"]
    correct_emoji = random.choice(emojis)
    
    embed = discord.Embed(
        title="لعبة الإيموجي | Central Bank",
        description="سيتم اختيار الايموجي بشكل عشوائي بعد عدة ثوانٍ\nفي حال الفوز سيتم إضافة مبلغ **1500 $** إلى رصيدك\nفي حال الخسارة لن يتم خصم المبلغ من رصيدك",
        color=discord.Color.dark_theme()
    )
    
    # إنشاء أزرار شبكية للإيموجيات
    view = discord.ui.View()
    for emo in emojis:
        button = discord.ui.Button(label=emo, style=discord.ButtonStyle.secondary)
        
        async def button_callback(interaction: discord.Interaction, selected=emo):
            if interaction.user != ctx.author:
                await interaction.response.send_message("هذه اللعبة ليست لك!", ephemeral=True)
                return
            
            if selected == correct_emoji:
                current = get_balance(ctx.author.id)
                set_balance(ctx.author.id, current + 1500)
                await interaction.response.edit_message(content=f"🎉 مبروك فزت! الإيموجي الصحيح كان {correct_emoji}\nتمت إضافة 1500$ إلى رصيدك.", view=None, embed=None)
            else:
                await interaction.response.edit_message(content=f"😴 لقد خسرت...\nالإيموجي الصحيح : {correct_emoji}\nاختيارك : {selected}", view=None, embed=None)
                
        button.callback = button_callback
        view.add_item(button)
        
    await ctx.send(embed=embed, view=view)

# التعامل مع الأخطاء وتجاهل الأوامر خارج الروم
@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.CheckFailure):
        await ctx.message.add_reaction("❌")

bot.run(os.getenv("DISCORD_TOKEN"))
