import asyncio
import discord
from discord import app_commands
from discord.ext import commands
import yt_dlp

# Configuración de intents
intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)

queues = {}

YTDL_OPTIONS = {
    'format': 'bestaudio/best',
    'extractaudio': True,
    'audioformat': 'mp3',
    'outtmpl': '%(extractor)s-%(id)s-%(title)s.%(ext)s',
    'restrictfilenames': True,
    'noplaylist': True,
    'nocheckcertificate': True,
    'ignoreerrors': False,
    'logtostderr': False,
    'quiet': True,
    'no_warnings': True,
    'default_search': 'ytsearch',
    'source_address': '0.0.0.0',
}

FFMPEG_OPTIONS = {
    'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
    'options': '-vn',
}

ytdl = yt_dlp.YoutubeDL(YTDL_OPTIONS)

class YTDLSource(discord.PCMVolumeTransformer):
    def __init__(self, source, *, data, volume=0.5):
        super().__init__(source, volume)
        self.data = data
        self.title = data.get('title')
        self.url = data.get('url')

    @classmethod
    async def create_source(cls, search: str, *, loop=None):
        loop = loop or asyncio.get_event_loop()
        
        # Ejecuta la extracción de datos sin bloquear el event loop
        data = await loop.run_in_executor(None, lambda: ytdl.extract_info(search, download=False))

        if not data:
            raise ValueError("No se encontraron resultados para la búsqueda.")

        if 'entries' in data:
            if not data['entries']:
                raise ValueError("No se encontraron resultados en YouTube.")
            data = data['entries'][0]

        audio_url = data.get('url')
        if not audio_url:
            raise ValueError("No se pudo obtener el stream de audio.")

        return cls(discord.FFmpegPCMAudio(audio_url, **FFMPEG_OPTIONS), data=data)

def play_next(interaction: discord.Interaction):
    guild_id = interaction.guild_id
    if guild_id in queues and len(queues[guild_id]) > 0:
        next_song = queues[guild_id].pop(0)
        coro = play_song(interaction, next_song['search'])
        asyncio.run_coroutine_threadsafe(coro, bot.loop)
    else:
        if guild_id in queues:
            queues.pop(guild_id)

async def play_song(interaction: discord.Interaction, search: str):
    try:
        player = await YTDLSource.create_source(search, loop=bot.loop)
        vc = interaction.guild.voice_client
        if vc and vc.is_connected():
            vc.play(player, after=lambda e: play_next(interaction))
            await interaction.channel.send(f"🎶 Reproduciendo ahora: **{player.title}**")
    except Exception as e:
        await interaction.channel.send(f"⚠️ Error al reproducir: `{e}`")
        play_next(interaction)

@bot.event
async def on_ready():
    # Sincronización de comandos
    await bot.tree.sync()
    print(f"Bot conectado como {bot.user} y comandos slash sincronizados.")

# --- COMANDOS SLASH ---

@bot.tree.command(name="play", description="Reproduce una canción por nombre o URL directa")
@app_commands.describe(cancion="Pega un enlace de YouTube/Spotify o escribe el nombre de la pista")
async def slash_play(interaction: discord.Interaction, cancion: str):
    if not interaction.user.voice:
        return await interaction.response.send_message("❌ ¡Debes estar en un canal de voz!", ephemeral=True)

    # Defer da hasta 15 minutos para procesar sin timeout
    await interaction.response.defer()

    voice_channel = interaction.user.voice.channel
    vc = interaction.guild.voice_client

    if vc is None:
        vc = await voice_channel.connect()
    elif vc.channel != voice_channel:
        await vc.move_to(voice_channel)

    guild_id = interaction.guild_id

    try:
        if vc.is_playing() or vc.is_paused():
            if guild_id not in queues:
                queues[guild_id] = []

            # Obtener título preliminar
            info = await bot.loop.run_in_executor(None, lambda: ytdl.extract_info(cancion, download=False, process=False))
            title = cancion
            if info:
                if 'entries' in info and info['entries']:
                    title = info['entries'][0].get('title', cancion)
                else:
                    title = info.get('title', cancion)

            queues[guild_id].append({'search': cancion, 'title': title})
            await interaction.followup.send(f"📋 Añadida a la cola (Posición #{len(queues[guild_id])}): **{title}**")
        else:
            player = await YTDLSource.create_source(cancion, loop=bot.loop)
            vc.play(player, after=lambda e: play_next(interaction))
            await interaction.followup.send(f"🎶 Reproduciendo ahora: **{player.title}**")
    except Exception as e:
        await interaction.followup.send(f"⚠️ Error al procesar la canción: `{e}`")

@bot.tree.command(name="skip", description="Salta la canción actual")
async def slash_skip(interaction: discord.Interaction):
    vc = interaction.guild.voice_client
    if vc and vc.is_playing():
        vc.stop()
        await interaction.response.send_message("⏭️ Canción saltada.")
    else:
        await interaction.response.send_message("❌ No hay nada reproduciéndose.", ephemeral=True)

@bot.tree.command(name="queue", description="Muestra la lista de reproducción en espera")
async def slash_queue(interaction: discord.Interaction):
    guild_id = interaction.guild_id
    if guild_id not in queues or len(queues[guild_id]) == 0:
        return await interaction.response.send_message("📭 La cola de reproducción está vacía.", ephemeral=True)

    msg = "**📜 Cola de reproducción actual:**\n"
    for idx, song in enumerate(queues[guild_id], start=1):
        msg += f"`{idx}.` {song['title']}\n"
    
    await interaction.response.send_message(msg)

@bot.tree.command(name="stop", description="Detiene la música, vacía la cola y sale del canal")
async def slash_stop(interaction: discord.Interaction):
    guild_id = interaction.guild_id
    if guild_id in queues:
        queues[guild_id].clear()
    
    vc = interaction.guild.voice_client
    if vc:
        await vc.disconnect()
        await interaction.response.send_message("⏹️ Bot desconectado y cola vaciada.")
    else:
        await interaction.response.send_message("❌ El bot no está en un canal de voz.", ephemeral=True)

# Reemplaza con tu token de Discord Developer Portal
bot.run("MTU0MjkyNDY1OTU1MTUwMjM2Ng.G4YvR7.Y4Qy4TTlAZwYQ3djYEFp7SARcokWmJjTk3w2T0")