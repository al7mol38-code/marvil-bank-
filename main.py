import discord
from discord.ext import commands
import os
import random
import asyncio

intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)

# روم الـ bank المخصص للأوامر
ALLOWED_CHANNEL_ID = 1544385495310540881

# قاعدة بيانات مؤقتة للأرصدة
user_balances = {}

def get_balance(user_id):
    return user_balances.get(user_id, 1000)

def set_balance(user_id, amount):
    user_balances[user_id] = amount

@bot.event
async def on_ready():
    print(f"تم تسجيل الدخول بنجاح باسم {bot.user}")

def in_allowed_channel():
    async def predicate(ctx):
        if ctx.channel.id != ALLOWED_CHANNEL_ID:
            return False
        return True
    return commands.check(predicate)

# لوحة المساعدة والأسعار المطابقة للصورة تماماً
@bot.command(name="مساعدة")
@in_allowed_channel()
async def help_cmd(ctx):
    embed = discord.Embed(
        title="الأسعار و الأوامر | Central Bank",
        description="سيتم تحديث الاسعار بعد : 05:32.8",
        color=discord.Color.dark_theme()
    )
    embed.add_field(name="🚗 سيارات", value="📈 111,110 $", inline=False)
    embed.add_field(name="📊 أسهم", value="📉 38,853 $", inline=False)
    embed.add_field(name="🏙️ أراضي", value="📈 391,193 $", inline=False)
    embed.add_field(name="🚆 قطارات", value="📈 886,324 $", inline=False)
    embed.add_field(name="✈️ طائرات", value="📉 152,344 $", inline=False)
    embed.add_field(name="🏟️ ملاعب", value="📉 3,819,391 $", inline=False)
    
    view = discord.ui.View()
    
    # زر معلومات الأسعار مع تفاعل آمن لمنع خطأ عدم الاستجابة
    price_button = discord.ui.Button(label="معلومات الاسعار", style=discord.ButtonStyle.secondary)
    
    async def button_callback(interaction: discord.Interaction):
        # الاستجابة الفورية لتجنب مشكلة The application didn't respond
        await interaction.response.send_message("📊 **معلومات الأسعار:** يتم تحديث الأسعار صعوداً وهبوطاً تلقائياً كل 5 دقائق بناءً على حركة السوق والتداول في البنك.", ephemeral=True)

    price_button.callback = button_callback
    view.add_item(price_button)
    
    await ctx.send(embed=embed, view=view)

# أمر الرصيد
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

# لعبة الإيموجي السريعة والمنسقة للأزرار
@bot.command(name="ايموجي")
@in_allowed_channel()
async def emoji_game(ctx):
    emojis = ["👾", "🦆", "🤡", "⛳", "🥜", "🎻", "🧠", "🦍", "🏓"]
    correct_emoji = random.choice(emojis)
    
    embed = discord.Embed(
        title="لعبة الإيموجي | Central Bank",
        description="اختر الإيموجي الصحيح من الأسفل:\nفي حال الفوز سيتم إضافة مبلغ **1500 $** إلى رصيدك.",
        color=discord.Color.dark_theme()
    )
    
    view = discord.ui.View()
    for emo in emojis:
        button = discord.ui.Button(label=emo, style=discord.ButtonStyle.secondary)
        
        async def make_callback(e=emo):
            async def btn_cb(interaction: discord.Interaction):
                # تأكيد الاستجابة السريعة لمنع خطأ المهلة
                if interaction.user != ctx.author:
                    await interaction.response.send_message("هذه اللعبة ليست لك!", ephemeral=True)
                    return
                
                if e == correct_emoji:
                    current = get_balance(ctx.author.id)
                    set_balance(ctx.author.id, current + 1500)
                    await interaction.response.edit_message(content=f"🎉 مبروك فزت! الإيموجي الصحيح كان {correct_emoji}\nتمت إضافة 1500$ إلى رصيدك.", view=None, embed=None)
                else:
                    await interaction.response.edit_message(content=f"😴 لقد خسرت...\nالإيموجي الصحيح : {correct_emoji}\nاختيارك : {e}", view=None, embed=None)
            return btn_cb

        button.callback = await make_callback(emo)
        view.add_item(button)
        
    await ctx.send(embed=embed, view=view)

@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.CheckFailure):
        await ctx.message.add_reaction("❌")

bot.run(os.getenv("DISCORD_TOKEN"))
