import discord
from discord.ext import commands
import os
import random
import asyncio
import time

intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)

# روم الـ bank المخصص للأوامر
ALLOWED_CHANNEL_ID = 1544385495310540881

# قواعد بيانات مؤقتة لتخزين البيانات
user_balances = {}
user_properties = {}
salary_cooldowns = {}

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

# 1. أمر المساعدة والأسعار الرئيسي
@bot.command(name="مساعدة", aliases=["اسعار"])
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
    price_button = discord.ui.Button(label="معلومات الاسعار", style=discord.ButtonStyle.secondary)
    
    async def price_cb(interaction: discord.Interaction):
        await interaction.response.send_message("📊 **معلومات الأسعار:** يتم تحديث الأسعار صعوداً وهبوطاً تلقائياً لكل الأصول في السوق.", ephemeral=True)
    price_button.callback = price_cb
    view.add_item(price_button)
    
    await ctx.send(embed=embed, view=view)

# 2. أمر الرصيد وكشف الحساب
@bot.command(name="رصيد", aliases=["كشف"])
@in_allowed_channel()
async def balance_cmd(ctx, member: discord.Member = None):
    target = member or ctx.author
    bal = get_balance(target.id)
    embed = discord.Embed(
        title="حسابك المصرفي | Central Bank",
        description=f"رصيد العضو {target.mention}\nالحالي: **{bal:,} $**",
        color=discord.Color.gold()
    )
    await ctx.send(embed=embed)

# 3. أمر التحويل
@bot.command(name="تحويل")
@in_allowed_channel()
async def transfer_cmd(ctx, member: discord.Member, amount: int):
    if amount <= 0:
        await ctx.send("❌ الرجاء إدخال مبلغ صحيح!")
        return
    
    sender_bal = get_balance(ctx.author.id)
    if sender_bal < amount:
        await ctx.send("❌ رصيدك الحالي لا يكفي لإتمام عملية التحويل.")
        return
    
    set_balance(ctx.author.id, sender_bal - amount)
    receiver_bal = get_balance(member.id)
    set_balance(member.id, receiver_bal + amount)
    
    await ctx.send(f"✅ تم تحويل مبلغ **{amount:,} $** بنجاح إلى العضو {member.mention}")

# 4. أمر الراتب (مع تحدي ترتيب الأرقام السريع)
@bot.command(name="راتب")
@in_allowed_channel()
async def salary_cmd(ctx):
    # توليد 6 أرقام عشوائية لترتيبها تصاعدياً
    nums = random.sample(range(10, 100), 6)
    sorted_nums = sorted(nums)
    
    embed = discord.Embed(
        title="الراتب | Central Bank",
        description=f"يجب عليك ترتيب الأعداد تصاعدياً في 60 ثانية:\n**{'  '.join(map(str, nums))}**\n\nاكتب الأرقام بالترتيب في رسالة واحدة (مفصولة بمسافات).",
        color=discord.Color.blue()
    )
    await ctx.send(embed=embed)
    
    def check(m):
        return m.author == ctx.author and m.channel == ctx.channel

    try:
        msg = await bot.wait_for('message', timeout=60.0, check=check)
        user_input = [int(n) for n in msg.content.split() if n.isdigit()]
        
        if user_input == sorted_nums:
            current = get_balance(ctx.author.id)
            set_balance(ctx.author.id, current + 5000)
            await ctx.send(f"🎉 ممتاز! لقد رتبت الأرقام بشكل صحيح وتم إيداع **5,000 $** راتبك في حسابك.")
        else:
            await ctx.send(f"⚠️ لم تقم بترتيب الاعداد بشكل صحيح 😒\nلن يتم اضافة مبلغ الراتب لحسابك.")
    except asyncio.TimeoutError:
        await ctx.send(f"⏰ انتهى وقت الإنتظار! لم يتم إيداع الراتب.")

# 5. أمر التداول والاستثمار
@bot.command(name="تداول")
@in_allowed_channel()
async def trade_cmd(ctx, amount: int = None):
    if not amount:
        embed = discord.Embed(
            title="تداول | Central Bank",
            description="طريقة الاستخدام :\n`!تداول المبلغ`",
            color=discord.Color.dark_theme()
        )
        await ctx.send(embed=embed)
        return
    
    bal = get_balance(ctx.author.id)
    if bal < amount:
        await ctx.send("❌ رصيدك لا يكفي للتداول بهذا المبلغ.")
        return
    
    profit = random.choice([True, False])
    if profit:
        won_amount = int(amount * 1.5)
        set_balance(ctx.author.id, bal + won_amount)
        await ctx.send(f"📈 ربحت في صفقة التداول وتمت إضافة **{won_amount:,} $** لحسابك!")
    else:
        set_balance(ctx.author.id, bal - amount)
        await ctx.send(f"📉 خسرت في صفقة التداول وتم خصم **{amount:,} $** من رصيدك.")

# 6. لعبة الإيموجي التفاعلية
@bot.command(name="ايموجي")
@in_allowed_channel()
async def emoji_game(ctx):
    emojis = ["👾", "🦆", "🤡", "⛳", "🥜", "🎻", "🧠", "🦍", "🏓"]
    correct_emoji = random.choice(emojis)
    
    embed = discord.Embed(
        title="لعبة الإيموجي | Central Bank",
        description="اختر الإيموجي الصحيح:\nفي حال الفوز سيتم إضافة مبلغ **1500 $** إلى رصيدك.",
        color=discord.Color.dark_theme()
    )
    
    view = discord.ui.View()
    for emo in emojis:
        button = discord.ui.Button(label=emo, style=discord.ButtonStyle.secondary)
        
        async def make_callback(e=emo):
            async def btn_cb(interaction: discord.Interaction):
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
