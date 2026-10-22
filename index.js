const { Client, GatewayIntentBits, REST, Routes, SlashCommandBuilder } = require('discord.js');
require('dotenv').config();

// إنشاء عميل البوت مع الصلاحيات المطلوبة (Intents)
const client = new Client({
    intents: [
        GatewayIntentBits.Guilds,
        GatewayIntentBits.GuildMessages,
        GatewayIntentBits.MessageContent,
    ],
});

// تعريف الأوامر (Slash Commands)
const commands = [
    new SlashCommandBuilder()
        .setName('ping')
        .setDescription('للتحقق من سرعة استجابة البوت'),
    
    new SlashCommandBuilder()
        .setName('say')
        .setDescription('يجعل البوت يكرر ما تقوله')
        .addStringOption(option =>
            option.setName('message')
                .setDescription('الرسالة المراد تكرارها')
                .setRequired(true)),
].map(command => command.toJSON());

// حدث الاشتغال وتثبيت الأوامر
client.once('ready', async () => {
    console.log(`تم تسجيل الدخول بنجاح باسم: ${client.user.tag}`);

    const rest = new REST({ version: '10' }).setToken(process.env.DISCORD_TOKEN);

    try {
        console.log('جاري تحديث الأوامر (Slash Commands)...');
        await rest.put(
            Routes.applicationCommands(client.user.id),
            { body: commands },
        );
        console.log('تم تحديث الأوامر بنجاح!');
    } catch (error) {
        console.error(error);
    }
});

// التعامل مع تنفيذ الأوامر
client.on('interactionCreate', async interaction => {
    if (!interaction.isChatInputCommand()) return;

    const { commandName } = interaction;

    if (commandName === 'ping') {
        const ping = client.ws.ping;
        await interaction.reply(`🏓 Pong! سرعة الاستجابة: **${ping}ms**`);
    } 
    
    else if (commandName === 'say') {
        const messageText = interaction.options.getString('message');
        await interaction.reply({ content: `تم الإرسال: ${messageText}` });
    }
});

// تشغيل البوت باستخدام التوكن من ملف .env
client.login(process.env.DISCORD_TOKEN);
