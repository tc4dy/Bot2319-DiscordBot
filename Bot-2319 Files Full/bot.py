import discord
import os
import ipinfo
import requests
import socket
import ssl
import whois
import dns.resolver
import datetime
import random
import asyncio
import re
import hashlib
from discord import ui
from discord.ui import View, Button
import secrets
import json
import aiohttp
import time
from discord.ext import commands
from dotenv import load_dotenv

load_dotenv()

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
IPINFO_TOKEN = os.getenv("IPINFO_TOKEN")
ipinfo_handler = ipinfo.getHandler(IPINFO_TOKEN)

XP_FILE = "xp_data.json"
PUNISHED_FILE = "punished.json"
CONFIG_FILE = "config.json"

_processed_commands = set()
_processed_xp = set()

def _already_processed_cmd(message_id: int) -> bool:
    if message_id in _processed_commands:
        return True
    _processed_commands.add(message_id)
    if len(_processed_commands) > 5000:
        oldest = sorted(_processed_commands)[:2500]
        for x in oldest:
            _processed_commands.discard(x)
    return False

def _already_processed_xp(message_id: int) -> bool:
    if message_id in _processed_xp:
        return True
    _processed_xp.add(message_id)
    if len(_processed_xp) > 5000:
        oldest = sorted(_processed_xp)[:2500]
        for x in oldest:
            _processed_xp.discard(x)
    return False

def load_config():
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except:
            pass
    default = {
        "log_channel_id": None,
        "punished_role_id": None,
        "register_channel_id": None,
        "unregistered_role_id": None,
        "register_staff_role_id": None
    }
    save_config(default)
    return default

def save_config(config):
    tmp = CONFIG_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2, ensure_ascii=False)
    os.replace(tmp, CONFIG_FILE)

config = load_config()

def get_config_value(key, default=None):
    return config.get(key, default)

def update_config(key, value):
    config[key] = value
    save_config(config)

intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.guilds = True
intents.voice_states = True

bot = commands.Bot(command_prefix="!", intents=intents, help_command=None)
bot.remove_command('help')

async def log_message(embed):
    channel_id = get_config_value("log_channel_id")
    if channel_id:
        channel = bot.get_channel(channel_id)
        if channel:
            await channel.send(embed=embed)

def load_xp():
    if os.path.exists(XP_FILE):
        try:
            with open(XP_FILE, "r") as f:
                content = f.read().strip()
                if not content:
                    return {}
                return json.loads(content)
        except:
            return {}
    return {}

def save_xp(data):
    tmp_file = XP_FILE + ".tmp"
    with open(tmp_file, "w") as f:
        json.dump(data, f, indent=2)
    os.replace(tmp_file, XP_FILE)

xp_data = load_xp()

def load_punished():
    if os.path.exists(PUNISHED_FILE):
        try:
            with open(PUNISHED_FILE, "r") as f:
                return json.load(f)
        except:
            return {}
    return {}

def save_punished(data):
    tmp = PUNISHED_FILE + ".tmp"
    with open(tmp, "w") as f:
        json.dump(data, f, indent=2)
    os.replace(tmp, PUNISHED_FILE)

def xp_for_next_level(level):
    return (level + 1) * 800

def get_level(xp):
    level = 0
    remaining = xp
    while remaining >= xp_for_next_level(level):
        remaining -= xp_for_next_level(level)
        level += 1
    return level

def generate_xp_bar(xp, level, bar_length=12):
    remaining = xp
    for i in range(level):
        remaining -= xp_for_next_level(i)
    needed = xp_for_next_level(level)
    current = remaining
    filled = int((current / needed) * bar_length)
    bar = "█" * filled + "░" * (bar_length - filled)
    return bar, current, needed

def get_rank_title(level):
    if level < 5:
        return "🌱 Rookie"
    elif level < 10:
        return "⚽ Player"
    elif level < 20:
        return "🥾 Professional"
    elif level < 35:
        return "⭐ Star"
    elif level < 50:
        return "🔥 Superstar"
    elif level < 65:
        return "💎 Elite"
    elif level < 80:
        return "👑 Captain"
    elif level < 90:
        return "🏆 Champion"
    elif level < 100:
        return "🐐 GOAT"
    else:
        return "🌍 LEGEND"

RANK_ROLES = {}

RANK_INFO = {
    "Rookie": {"level": 0, "emoji": "🌱", "salary": "0 €"},
    "Player": {"level": 5, "emoji": "⚽", "salary": "60K €"},
    "Professional": {"level": 10, "emoji": "🥾", "salary": "100K €"},
    "Star": {"level": 20, "emoji": "⭐", "salary": "240K €"},
    "Superstar": {"level": 35, "emoji": "🔥", "salary": "600K €"},
    "Elite": {"level": 50, "emoji": "💎", "salary": "1M €"},
    "Captain": {"level": 65, "emoji": "👑", "salary": "1.5M €"},
    "Champion": {"level": 80, "emoji": "🏆", "salary": "3M €"},
    "GOAT": {"level": 90, "emoji": "🐐", "salary": "5M €"},
    "LEGEND": {"level": 100, "emoji": "🌍", "salary": "10M €"},
}

guess_sessions = {}

def parse_duration(duration_str):
    match = re.match(r"(\d+)(seconds|second|sec|s|minutes|minute|min|m|hours|hour|hr|h|days|day|d)", duration_str.lower())
    if not match:
        return None, None
    value = int(match.group(1))
    unit = match.group(2)
    seconds_map = {
        "s": 1, "sec": 1, "second": 1, "seconds": 1,
        "m": 60, "min": 60, "minute": 60, "minutes": 60,
        "h": 3600, "hr": 3600, "hour": 3600, "hours": 3600,
        "d": 86400, "day": 86400, "days": 86400
    }
    unit_singular = {
        "s": "second", "sec": "second", "second": "second", "seconds": "second",
        "m": "minute", "min": "minute", "minute": "minute", "minutes": "minute",
        "h": "hour", "hr": "hour", "hour": "hour", "hours": "hour",
        "d": "day", "day": "day", "days": "day"
    }
    unit_plural = {
        "s": "seconds", "sec": "seconds", "second": "seconds", "seconds": "seconds",
        "m": "minutes", "min": "minutes", "minute": "minutes", "minutes": "minutes",
        "h": "hours", "hr": "hours", "hour": "hours", "hours": "hours",
        "d": "days", "day": "days", "days": "days"
    }
    display = unit_singular[unit] if value == 1 else unit_plural[unit]
    return seconds_map[unit] * value, f"{value} {display}"

async def domain_info_async(domain):
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _domain_info_sync, domain)

def _domain_info_sync(domain):
    try:
        ip = socket.gethostbyname(domain)
        try:
            hostname = socket.gethostbyaddr(ip)[0]
        except:
            hostname = "Unknown"
        try:
            whois_info = whois.whois(domain)
            registrar = whois_info.registrar if whois_info.registrar else "Unknown"
            creation_date = whois_info.creation_date if whois_info.creation_date else "Unknown"
            expiration_date = whois_info.expiration_date if whois_info.expiration_date else "Unknown"
        except:
            registrar = creation_date = expiration_date = "Unknown"
        try:
            response = requests.get(f"http://ip-api.com/json/{ip}", timeout=5)
            geo = response.json()
            country = geo.get("country", "Unknown")
            city = geo.get("city", "Unknown")
            isp = geo.get("isp", "Unknown")
        except:
            country = city = isp = "Unknown"
        dns_records = {}
        for rt in ["A", "MX", "NS", "TXT"]:
            try:
                answers = dns.resolver.resolve(domain, rt)
                dns_records[rt] = [str(r) for r in answers]
            except:
                dns_records[rt] = ["Record not found"]
        try:
            ctx = ssl.create_default_context()
            with ctx.wrap_socket(socket.socket(), server_hostname=domain) as s:
                s.settimeout(3)
                s.connect((domain, 443))
                cert = s.getpeercert()
            ssl_issuer = dict(x[0] for x in cert["issuer"]).get("organizationName", "Unknown")
            ssl_expiry = cert.get("notAfter", "Unknown")
        except:
            ssl_issuer = "No SSL or could not be retrieved"
            ssl_expiry = "Unknown"
        open_ports = []
        for port in [80, 443, 22, 21, 25]:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(1)
            if sock.connect_ex((ip, port)) == 0:
                open_ports.append(port)
            sock.close()
        try:
            r = requests.get(f"https://{domain}", timeout=4)
            status_code = r.status_code
            server = r.headers.get("Server", "Unknown")
        except:
            status_code = "Could not connect"
            server = "Unknown"
        return {
            "ip": ip, "hostname": hostname, "country": country, "city": city,
            "isp": isp, "registrar": registrar, "creation_date": creation_date,
            "expiration_date": expiration_date, "dns_records": dns_records,
            "ssl_issuer": ssl_issuer, "ssl_expiry": ssl_expiry,
            "open_ports": open_ports, "status_code": status_code, "server": server
        }
    except Exception as e:
        return {"error": str(e)}

async def translate_text(text, target_lang):
    try:
        url = "https://translate.googleapis.com/translate_a/single"
        params = {
            "client": "gtx",
            "sl": "auto",
            "tl": target_lang,
            "dt": "t",
            "q": text
        }
        async with aiohttp.ClientSession() as session:
            async with session.get(url, params=params, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    translation = ""
                    for item in data[0]:
                        if item[0]:
                            translation += item[0]
                    return translation
                else:
                    return None
    except Exception:
        return None

async def get_coordinates(city):
    url = f"https://geocoding-api.open-meteo.com/v1/search?name={city}&count=1&language=en&format=json"
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as resp:
            if resp.status != 200:
                return None, None
            data = await resp.json()
            if not data.get("results"):
                return None, None
            result = data["results"][0]
            return result["latitude"], result["longitude"]

async def get_weather(lat, lon):
    url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&current_weather=true&timezone=auto&forecast_days=1"
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as resp:
            if resp.status != 200:
                return None
            return await resp.json()

async def _remove_punishment(user_id: int):
    punished = load_punished()
    uid_str = str(user_id)
    if uid_str not in punished:
        return
    data = punished[uid_str]
    roles = data.get("roles", [])

    punished_role_id = get_config_value("punished_role_id")
    guild = None
    if punished_role_id:
        for g in bot.guilds:
            if g.get_role(punished_role_id):
                guild = g
                break
    if not guild:
        del punished[uid_str]
        save_punished(punished)
        return

    member = guild.get_member(user_id)
    if member:
        punished_role = guild.get_role(punished_role_id)
        if punished_role and punished_role in member.roles:
            try:
                await member.remove_roles(punished_role, reason="Punishment expired")
            except:
                pass
        roles_to_add = []
        for rid in roles:
            r = guild.get_role(rid)
            if r and r not in member.roles:
                roles_to_add.append(r)
        if roles_to_add:
            try:
                await member.add_roles(*roles_to_add, reason="Punishment expired, restoring previous roles")
            except:
                pass

    del punished[uid_str]
    save_punished(punished)

    embed = discord.Embed(
        title="Punishment Removed",
        description=f"<@{user_id}>'s punishment has been automatically removed.",
        color=0x57F287,
        timestamp=datetime.datetime.now()
    )
    await log_message(embed)

async def remove_punishment(user_id: int, wait_duration: int):
    await asyncio.sleep(wait_duration)
    punished = load_punished()
    if str(user_id) not in punished:
        return
    await _remove_punishment(user_id)

@bot.event
async def on_ready():
    print(f"{bot.user} is online!")
    await bot.change_presence(activity=discord.Activity(
        type=discord.ActivityType.listening, name="!help"
    ))

    log_channel_id = get_config_value("log_channel_id")
    if log_channel_id:
        log_channel = bot.get_channel(log_channel_id)
        if log_channel:
            print(f"Log channel found: #{log_channel.name}")
        else:
            print(f"Log channel NOT FOUND! ID: {log_channel_id}")
    else:
        print("Log channel not configured!")

    punished = load_punished()
    now = time.time()
    for uid_str, data in list(punished.items()):
        end = data.get("end", 0)
        uid = int(uid_str)
        if end and end <= now:
            await _remove_punishment(uid)
        elif end:
            remaining = end - now
            asyncio.create_task(remove_punishment(uid, remaining))

@bot.event
async def on_message_delete(message):
    if message.author.bot:
        return
    embed = discord.Embed(
        title="Message Deleted",
        description=f"User: {message.author.mention} ({message.author})\nChannel: {message.channel.mention}\nMessage: {message.content[:1000] if message.content else 'Empty message'}",
        color=0xED4245,
        timestamp=datetime.datetime.now()
    )
    await log_message(embed)

@bot.event
async def on_message_edit(before, after):
    if before.author.bot or before.content == after.content:
        return
    embed = discord.Embed(
        title="Message Edited",
        description=f"User: {before.author.mention} ({before.author})\nChannel: {before.channel.mention}\nBefore: {before.content[:500]}\nAfter: {after.content[:500]}",
        color=0xFEE75C,
        timestamp=datetime.datetime.now()
    )
    await log_message(embed)

@bot.event
async def on_member_join(member):
    embed = discord.Embed(
        title="Member Joined",
        description=f"{member.mention} ({member}) joined the server.\nAccount created: {member.created_at.strftime('%d.%m.%Y %H:%M')}",
        color=0x2ECC71,
        timestamp=datetime.datetime.now()
    )
    embed.set_thumbnail(url=member.display_avatar.url)
    await log_message(embed)

@bot.event
async def on_member_remove(member):
    embed = discord.Embed(
        title="Member Left",
        description=f"{member.mention} ({member}) left the server.",
        color=0xED4245,
        timestamp=datetime.datetime.now()
    )
    embed.set_thumbnail(url=member.display_avatar.url)
    await log_message(embed)

@bot.event
async def on_member_update(before, after):
    if before.roles == after.roles:
        return
    added_roles = [r for r in after.roles if r not in before.roles]
    removed_roles = [r for r in before.roles if r not in after.roles]
    embed = discord.Embed(
        title="Roles Updated",
        description=f"User: {after.mention} ({after})",
        color=0x9B59B6,
        timestamp=datetime.datetime.now()
    )
    if added_roles:
        embed.add_field(name="Added Roles", value=", ".join(r.mention for r in added_roles), inline=False)
    if removed_roles:
        embed.add_field(name="Removed Roles", value=", ".join(r.mention for r in removed_roles), inline=False)
    await log_message(embed)

@bot.event
async def on_member_ban(guild, user):
    embed = discord.Embed(
        title="Member Banned",
        description=f"{user.mention} ({user}) was banned.",
        color=0xED4245,
        timestamp=datetime.datetime.now()
    )
    await log_message(embed)

@bot.event
async def on_member_unban(guild, user):
    embed = discord.Embed(
        title="Ban Removed",
        description=f"{user.mention} ({user}) was unbanned.",
        color=0x57F287,
        timestamp=datetime.datetime.now()
    )
    await log_message(embed)

@bot.event
async def on_voice_state_update(member, before, after):
    if before.channel == after.channel:
        return
    if after.channel:
        embed = discord.Embed(
            title="Joined Voice Channel",
            description=f"User: {member.mention} ({member})\nChannel: {after.channel.mention}",
            color=0x2ECC71,
            timestamp=datetime.datetime.now()
        )
    else:
        embed = discord.Embed(
            title="Left Voice Channel",
            description=f"User: {member.mention} ({member})\nChannel: {before.channel.mention}",
            color=0xED4245,
            timestamp=datetime.datetime.now()
        )
    await log_message(embed)

@bot.event
async def on_guild_channel_create(channel):
    embed = discord.Embed(
        title="Channel Created",
        description=f"Channel: {channel.mention}\nName: {channel.name}\nType: {channel.type}",
        color=0x2ECC71,
        timestamp=datetime.datetime.now()
    )
    await log_message(embed)

@bot.event
async def on_guild_channel_delete(channel):
    embed = discord.Embed(
        title="Channel Deleted",
        description=f"Channel: {channel.name}\nType: {channel.type}",
        color=0xED4245,
        timestamp=datetime.datetime.now()
    )
    await log_message(embed)

@bot.event
async def on_guild_channel_update(before, after):
    if before.overwrites == after.overwrites:
        return
    embed = discord.Embed(
        title="Channel Permissions Updated",
        description=f"Channel: {after.mention}\nName: {after.name}",
        color=0x3498DB,
        timestamp=datetime.datetime.now()
    )
    await log_message(embed)

    if before.name != after.name:
        embed = discord.Embed(
            title="Channel Name Changed",
            description=f"Old Name: {before.name}\nNew Name: {after.name}\nChannel: {after.mention}",
            color=0xFEE75C,
            timestamp=datetime.datetime.now()
        )
        await log_message(embed)

@bot.event
async def on_guild_role_create(role):
    embed = discord.Embed(
        title="Role Created",
        description=f"Role: {role.mention}\nName: {role.name}",
        color=0x2ECC71,
        timestamp=datetime.datetime.now()
    )
    await log_message(embed)

@bot.event
async def on_guild_role_delete(role):
    embed = discord.Embed(
        title="Role Deleted",
        description=f"Role: {role.name}",
        color=0xED4245,
        timestamp=datetime.datetime.now()
    )
    await log_message(embed)

@bot.event
async def on_guild_role_update(before, after):
    if before.name != after.name:
        embed = discord.Embed(
            title="Role Name Changed",
            description=f"Old Name: {before.name}\nNew Name: {after.name}",
            color=0xFEE75C,
            timestamp=datetime.datetime.now()
        )
        await log_message(embed)
    if before.color != after.color:
        embed = discord.Embed(
            title="Role Color Changed",
            description=f"Role: {after.mention}\nOld Color: {before.color}\nNew Color: {after.color}",
            color=0xFEE75C,
            timestamp=datetime.datetime.now()
        )
        await log_message(embed)

@bot.event
async def on_message(message):
    if message.author.bot:
        return

    if _already_processed_xp(message.id):
        return

    uid = str(message.author.id)
    current_data = load_xp()
    if uid not in current_data:
        current_data[uid] = {"xp": 0, "level": 0, "messages": 0}

    gained = random.randint(230, 250)
    current_data[uid]["xp"] += gained
    current_data[uid]["messages"] = current_data[uid].get("messages", 0) + 1

    old_level = current_data[uid].get("level", 0)
    new_level = get_level(current_data[uid]["xp"])
    current_data[uid]["level"] = new_level

    xp_data[uid] = current_data[uid]
    save_xp(current_data)

    if new_level > old_level:
        rank = get_rank_title(new_level)
        embed = discord.Embed(
            title="LEVEL UP!",
            description=(
                f"{message.author.mention} reached a new peak!\n\n"
                f"```\n"
                f"  ╔══════════════════════╗\n"
                f"     Level  {old_level}  ->  {new_level}   \n"
                f"  ╚══════════════════════╝\n"
                f"```\n"
                f"Rank: {rank}"
            ),
            color=0xFFD700
        )
        embed.set_thumbnail(url=message.author.display_avatar.url)
        await message.channel.send(embed=embed)

    await bot.process_commands(message)

@bot.command(name="emoji")
@commands.cooldown(1, 3, commands.BucketType.user)
async def emoji(ctx, *, text: str = None):
    if text is None:
        embed = discord.Embed(
            title="Invalid Usage",
            description="Usage: !emoji [text]\nExample: !emoji Hello\n\nSupported: A-Z, 0-9, space",
            color=0xED4245
        )
        await ctx.send(embed=embed)
        return

    emoji_letter = {
        'a': '🇦', 'b': '🇧', 'c': '🇨', 'ç': '🇨', 'd': '🇩', 'e': '🇪',
        'f': '🇫', 'g': '🇬', 'ğ': '🇬', 'h': '🇭', 'ı': '🇮', 'i': '🇮',
        'j': '🇯', 'k': '🇰', 'l': '🇱', 'm': '🇲', 'n': '🇳', 'o': '🇴',
        'ö': '🇴', 'p': '🇵', 'r': '🇷', 's': '🇸', 'ş': '🇸', 't': '🇹',
        'u': '🇺', 'ü': '🇺', 'v': '🇻', 'y': '🇾', 'z': '🇿',
        '0': '0️⃣', '1': '1️⃣', '2': '2️⃣', '3': '3️⃣', '4': '4️⃣',
        '5': '5️⃣', '6': '6️⃣', '7': '7️⃣', '8': '8️⃣', '9': '9️⃣',
        '!': '❗', '?': '❓', ' ': '  '
    }

    result = ""
    for letter in text.lower():
        if letter in emoji_letter:
            result += emoji_letter[letter] + " "
        else:
            result += letter + " "

    embed = discord.Embed(
        title="Text -> Emoji",
        color=0x57F287
    )
    embed.add_field(name="Original", value=f"```{text}```", inline=False)
    embed.add_field(name="Emoji Version", value=f"{result[:1000]}", inline=False)
    embed.set_footer(text=f"By {ctx.author.display_name}")
    embed.timestamp = datetime.datetime.now()
    await ctx.send(embed=embed)

@emoji.error
async def emoji_error(ctx, error):
    if isinstance(error, commands.CommandOnCooldown):
        await ctx.send(f"Wait: {error.retry_after:.1f}s")

@bot.command(name="ping")
@commands.cooldown(1, 3, commands.BucketType.user)
async def ping(ctx):
    latency = round(bot.latency * 1000)
    color = 0x57F287 if latency < 100 else (0xFEE75C if latency < 200 else 0xED4245)
    bar_len = 10
    filled = min(int((latency / 300) * bar_len), bar_len)
    bar = "▓" * filled + "░" * (bar_len - filled)
    embed = discord.Embed(title="Pong!", color=color)
    embed.add_field(name="Latency", value=f"`{bar}` **{latency}ms**", inline=False)
    await ctx.send(embed=embed)

@ping.error
async def ping_error(ctx, error):
    if isinstance(error, commands.CommandOnCooldown):
        await ctx.send(f"Wait: {error.retry_after:.1f}s")

@bot.command(name="avatar")
@commands.cooldown(1, 3, commands.BucketType.user)
async def avatar(ctx, member: discord.Member = None):
    member = member or ctx.author
    embed = discord.Embed(title=f"{member.display_name} - Avatar", color=0x5865F2)
    embed.set_image(url=member.display_avatar.url)
    await ctx.send(embed=embed)

@avatar.error
async def avatar_error(ctx, error):
    if isinstance(error, commands.CommandOnCooldown):
        await ctx.send(f"Wait: {error.retry_after:.1f}s")

@bot.command(name="server")
@commands.cooldown(1, 5, commands.BucketType.guild)
async def server(ctx):
    g = ctx.guild
    embed = discord.Embed(title=f"{g.name}", color=0x5865F2)
    embed.set_thumbnail(url=g.icon.url if g.icon else discord.Embed.Empty)
    embed.add_field(name="Members", value=f"`{g.member_count}`", inline=True)
    embed.add_field(name="Channels", value=f"`{len(g.channels)}`", inline=True)
    embed.add_field(name="Created", value=f"`{g.created_at.strftime('%d.%m.%Y')}`", inline=True)
    embed.add_field(name="Owner", value=g.owner.mention, inline=True)
    embed.add_field(name="ID", value=f"`{g.id}`", inline=True)
    await ctx.send(embed=embed)

@server.error
async def server_error(ctx, error):
    if isinstance(error, commands.CommandOnCooldown):
        await ctx.send(f"Wait: {error.retry_after:.1f}s")

@bot.command(name="random")
@commands.cooldown(1, 2, commands.BucketType.user)
async def random_cmd(ctx):
    n = random.randint(1, 100)
    embed = discord.Embed(description=f"Random number: **{n}**", color=0xEB459E)
    await ctx.send(embed=embed)

@random_cmd.error
async def random_cmd_error(ctx, error):
    if isinstance(error, commands.CommandOnCooldown):
        await ctx.send(f"Wait: {error.retry_after:.1f}s")

@bot.command(name="coinflip")
@commands.cooldown(1, 2, commands.BucketType.user)
async def coinflip(ctx):
    result = random.choice(["Heads", "Tails"])
    embed = discord.Embed(description=f"**{result}**", color=0xFEE75C)
    await ctx.send(embed=embed)

@coinflip.error
async def coinflip_error(ctx, error):
    if isinstance(error, commands.CommandOnCooldown):
        await ctx.send(f"Wait: {error.retry_after:.1f}s")

@bot.command(name="dice")
@commands.cooldown(1, 2, commands.BucketType.user)
async def dice(ctx):
    n = random.randint(1, 6)
    faces = ["", "⚀", "⚁", "⚂", "⚃", "⚄", "⚅"]
    embed = discord.Embed(description=f"{faces[n]} Dice: **{n}**", color=0xEB459E)
    await ctx.send(embed=embed)

@dice.error
async def dice_error(ctx, error):
    if isinstance(error, commands.CommandOnCooldown):
        await ctx.send(f"Wait: {error.retry_after:.1f}s")

@bot.command(name="luckynumber")
@commands.cooldown(1, 3, commands.BucketType.user)
async def luckynumber(ctx):
    n = random.randint(1, 100)
    colors_list = ["Red", "Blue", "Green", "Yellow", "Purple", "Orange"]
    color = random.choice(colors_list)
    embed = discord.Embed(title="Luck Machine", color=0x57F287)
    embed.add_field(name="Lucky Number", value=f"**{n}**", inline=True)
    embed.add_field(name="Lucky Color", value=f"**{color}**", inline=True)
    await ctx.send(embed=embed)

@luckynumber.error
async def luckynumber_error(ctx, error):
    if isinstance(error, commands.CommandOnCooldown):
        await ctx.send(f"Wait: {error.retry_after:.1f}s")

@bot.command(name="word")
@commands.cooldown(1, 2, commands.BucketType.user)
async def word(ctx, letter: str = None):
    if not letter or len(letter) != 1 or not letter.isalpha():
        await ctx.send("Enter a valid letter! !word a")
        return
    words = {
        'a': ['apple', 'ant', 'arm', 'arrow', 'actor', 'anchor', 'artist', 'autumn', 'avenue', 'atom'],
        'b': ['ball', 'book', 'bird', 'bank', 'beach', 'bread', 'bridge', 'bottle', 'butter', 'basket'],
        'c': ['cat', 'car', 'cake', 'cloud', 'chair', 'clock', 'coast', 'coin', 'castle', 'candle'],
        'd': ['dog', 'door', 'desk', 'dream', 'drum', 'duck', 'dance', 'dinner', 'dragon', 'doctor'],
        'e': ['egg', 'ear', 'earth', 'eagle', 'echo', 'ember', 'energy', 'engine', 'envelope', 'evening'],
        'f': ['fish', 'fire', 'forest', 'flower', 'friend', 'farm', 'feather', 'finger', 'future', 'frame'],
        'g': ['game', 'garden', 'glass', 'gold', 'green', 'goat', 'ghost', 'guitar', 'globe', 'grape'],
        'h': ['hat', 'house', 'horse', 'heart', 'hill', 'honey', 'hotel', 'hunter', 'hammer', 'harbor'],
        'i': ['ice', 'island', 'iron', 'image', 'insect', 'ivory', 'idea', 'igloo', 'income', 'ink'],
        'j': ['jar', 'juice', 'jungle', 'jacket', 'jewel', 'journey', 'judge', 'junior', 'jolly', 'jigsaw'],
        'k': ['key', 'king', 'kite', 'kitchen', 'knife', 'knight', 'koala', 'kettle', 'kingdom', 'keyboard'],
        'l': ['lamp', 'lion', 'lake', 'leaf', 'letter', 'ladder', 'lemon', 'light', 'lunch', 'library'],
        'm': ['moon', 'mouse', 'mountain', 'music', 'mirror', 'market', 'medal', 'money', 'morning', 'mother'],
        'n': ['nose', 'nest', 'night', 'number', 'needle', 'nature', 'navy', 'nephew', 'nickel', 'nurse'],
        'o': ['owl', 'ocean', 'orange', 'onion', 'office', 'olive', 'opera', 'orbit', 'oven', 'oyster'],
        'p': ['pen', 'piano', 'pencil', 'pizza', 'planet', 'pocket', 'prince', 'potato', 'pepper', 'pirate'],
        'q': ['queen', 'quilt', 'question', 'quiet', 'quail', 'quarter', 'quartz', 'quest', 'quick', 'quote'],
        'r': ['rain', 'river', 'rabbit', 'rocket', 'radio', 'ribbon', 'ring', 'road', 'room', 'ruler'],
        's': ['sun', 'star', 'snake', 'school', 'silver', 'spring', 'stone', 'sugar', 'summer', 'sword'],
        't': ['tree', 'tiger', 'table', 'teacher', 'thunder', 'ticket', 'tower', 'train', 'travel', 'tunnel'],
        'u': ['umbrella', 'uncle', 'uniform', 'unit', 'universe', 'urban', 'urge', 'useful', 'usual', 'utensil'],
        'v': ['van', 'valley', 'village', 'violin', 'vision', 'voice', 'volume', 'voyage', 'velvet', 'vase'],
        'w': ['water', 'wolf', 'window', 'winter', 'wisdom', 'wonder', 'world', 'writer', 'wagon', 'wallet'],
        'x': ['xylophone', 'xenon', 'xerus', 'xylem', 'xebec', 'x-ray', 'xerox', 'xenial', 'xiphoid', 'xystus'],
        'y': ['yellow', 'yacht', 'yogurt', 'yard', 'year', 'yarn', 'youth', 'yawn', 'yield', 'yolk'],
        'z': ['zebra', 'zero', 'zone', 'zoo', 'zipper', 'zombie', 'zenith', 'zigzag', 'zeppelin', 'zucchini']
    }
    letter = letter.lower()
    if letter not in words:
        await ctx.send(f"No word found for letter `{letter}`.")
        return
    picked = random.choice(words[letter])
    embed = discord.Embed(
        description=f"Starting with **`{letter.upper()}`** -> **{picked}**",
        color=0x5865F2
    )
    await ctx.send(embed=embed)

@word.error
async def word_error(ctx, error):
    if isinstance(error, commands.CommandOnCooldown):
        await ctx.send(f"Wait: {error.retry_after:.1f}s")

@bot.command(name="guess")
@commands.cooldown(1, 2, commands.BucketType.user)
async def guess(ctx, number: int = None):
    uid = ctx.author.id
    if number is None or number < 1 or number > 100:
        await ctx.send("Enter a number between 1-100! !guess 50")
        return
    if uid not in guess_sessions:
        guess_sessions[uid] = {"target": random.randint(1, 100), "attempts": 0}
    session = guess_sessions[uid]
    session["attempts"] += 1
    target = session["target"]
    if number < target:
        embed = discord.Embed(description=f"**{number}** is too small! Try a bigger number. (Attempt: {session['attempts']})", color=0xFEE75C)
        await ctx.send(embed=embed)
    elif number > target:
        embed = discord.Embed(description=f"**{number}** is too big! Try a smaller number. (Attempt: {session['attempts']})", color=0xFEE75C)
        await ctx.send(embed=embed)
    else:
        attempts = session["attempts"]
        del guess_sessions[uid]
        stars = "⭐" * max(1, 6 - attempts)
        embed = discord.Embed(
            title="CORRECT!",
            description=f"The number was **{target}**!\nYou found it in **{attempts}** attempts!\n{stars}",
            color=0x57F287
        )
        await ctx.send(embed=embed)

@guess.error
async def guess_error(ctx, error):
    if isinstance(error, commands.CommandOnCooldown):
        await ctx.send(f"Wait: {error.retry_after:.1f}s")

@bot.command(name="rps")
@commands.cooldown(1, 2, commands.BucketType.user)
async def rps(ctx, choice: str = None):
    if choice is None or choice.lower() not in ["rock", "paper", "scissors"]:
        await ctx.send("!rps rock / !rps paper / !rps scissors")
        return
    bot_choice = random.choice(["rock", "paper", "scissors"])
    choice = choice.lower()
    icons = {"rock": "🪨", "paper": "📄", "scissors": "✂️"}
    if choice == bot_choice:
        result, color = "Tie!", 0xFEE75C
    elif (choice == "rock" and bot_choice == "scissors") or (choice == "paper" and bot_choice == "rock") or (choice == "scissors" and bot_choice == "paper"):
        result, color = "You won!", 0x57F287
    else:
        result, color = "You lost!", 0xED4245
    embed = discord.Embed(title="Rock Paper Scissors", color=color)
    embed.add_field(name="You", value=f"{icons[choice]} {choice.capitalize()}", inline=True)
    embed.add_field(name="Bot", value=f"{icons[bot_choice]} {bot_choice.capitalize()}", inline=True)
    embed.add_field(name="Result", value=result, inline=False)
    await ctx.send(embed=embed)

@rps.error
async def rps_error(ctx, error):
    if isinstance(error, commands.CommandOnCooldown):
        await ctx.send(f"Wait: {error.retry_after:.1f}s")

class PasswordView(View):
    def __init__(self, author, password):
        super().__init__(timeout=60)
        self.author = author
        self.password = password
        self.message = None

    async def interaction_check(self, interaction):
        if interaction.user != self.author:
            await interaction.response.send_message("These buttons are only for the person who ran the command!", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="Send via DM", style=discord.ButtonStyle.success, custom_id="dm")
    async def dm_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            dm_embed = discord.Embed(
                title="Your Secure Password",
                description=(
                    f"Hello {self.author.mention}!\n\n"
                    "Your new password has been created:\n"
                    f"||`{self.password}`||\n\n"
                    "Do not share this password with anyone!"
                ),
                color=0x57F287
            )
            dm_embed.set_footer(text="This message is for you only.")
            await self.author.send(embed=dm_embed)

            await interaction.response.edit_message(
                embed=discord.Embed(
                    title="Password Sent via DM",
                    description="Your password has been sent to your direct messages.",
                    color=0x57F287
                ),
                view=None
            )
            await self.message.edit(view=None)

        except discord.Forbidden:
            await interaction.response.edit_message(
                embed=discord.Embed(
                    title="DM Could Not Be Sent",
                    description="Your direct messages are closed! Please enable DMs and try again.",
                    color=0xED4245
                ),
                view=None
            )
            await self.message.edit(view=None)

    @discord.ui.button(label="Post Here", style=discord.ButtonStyle.danger, custom_id="channel")
    async def channel_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        embed = discord.Embed(
            title="Secure Password Created",
            description=(
                f"User: {self.author.mention}\n"
                f"Password: ||`{self.password}`||\n\n"
                "Do not share this password with anyone!"
            ),
            color=0x57F287
        )
        embed.set_footer(text="Spoiler - click to view.")

        await interaction.response.edit_message(
            embed=embed,
            view=None
        )
        await self.message.edit(view=None)

@bot.command(name="password")
@commands.cooldown(1, 3, commands.BucketType.user)
async def password(ctx):
    chars = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789!@#$%^&*"
    pwd = "".join(secrets.choice(chars) for _ in range(14))

    embed = discord.Embed(
        title="Password Created",
        description=(
            "Your password is ready!\n\n"
            "Send via DM - Your password is sent to you as a private message.\n"
            "Post Here - Your password becomes visible in this channel.\n\n"
            "Choose one of the buttons!"
        ),
        color=0x5865F2
    )
    embed.set_footer(text="Buttons are available for 60 seconds.")

    view = PasswordView(ctx.author, pwd)
    view.message = await ctx.send(embed=embed, view=view)

@password.error
async def password_error(ctx, error):
    if isinstance(error, commands.CommandOnCooldown):
        await ctx.send(f"Wait: {error.retry_after:.1f}s")

@bot.command(name="level")
@commands.cooldown(1, 3, commands.BucketType.user)
async def level(ctx, member: discord.Member = None):
    member = member or ctx.author
    uid = str(member.id)
    current_data = load_xp()
    if uid not in current_data:
        current_data[uid] = {"xp": 0, "level": 0, "messages": 0}
    xp = current_data[uid]["xp"]
    lvl = get_level(xp)
    current_data[uid]["level"] = lvl
    xp_data[uid] = current_data[uid]
    bar, current, needed = generate_xp_bar(xp, lvl)
    rank = get_rank_title(lvl)
    embed = discord.Embed(
        title=f"{member.display_name} - Profile",
        color=0xFFD700
    )
    embed.set_thumbnail(url=member.display_avatar.url)
    embed.add_field(name="Level", value=f"**{lvl}**", inline=True)
    embed.add_field(name="Total XP", value=f"**{xp}**", inline=True)
    embed.add_field(name="Rank", value=rank, inline=True)
    embed.add_field(
        name=f"Progress `{current}/{needed} XP`",
        value=f"`[{bar}]`",
        inline=False
    )
    await ctx.send(embed=embed)

@level.error
async def level_error(ctx, error):
    if isinstance(error, commands.CommandOnCooldown):
        await ctx.send(f"Wait: {error.retry_after:.1f}s")

@bot.command(name="rank")
@commands.cooldown(1, 5, commands.BucketType.user)
async def rank(ctx):
    embed = discord.Embed(
        title="RANK SYSTEM",
        description="Ranks and rewards you earn as you level up:",
        color=0xFFD700
    )

    rank_list = []
    for rank_name, info in RANK_INFO.items():
        lvl = info["level"]
        salary = info["salary"]
        emoji_icon = info["emoji"]
        rank_list.append(f"{emoji_icon} **{rank_name}** - Level `{lvl}` - {salary}")

    embed.add_field(
        name="Rank Table",
        value="\n".join(rank_list),
        inline=False
    )

    embed.set_footer(text="You earn an average of 230-250 XP per message")
    embed.timestamp = datetime.datetime.now()
    await ctx.send(embed=embed)

@rank.error
async def rank_error(ctx, error):
    if isinstance(error, commands.CommandOnCooldown):
        await ctx.send(f"Wait: {error.retry_after:.1f}s")

@bot.command(name="leaderboard")
@commands.cooldown(1, 5, commands.BucketType.guild)
async def leaderboard(ctx):
    current_data = load_xp()
    if not current_data:
        embed = discord.Embed(title="No Data", description="No messages have been sent yet.", color=0xED4245)
        await ctx.send(embed=embed)
        return
    sorted_users = sorted(current_data.items(), key=lambda x: x[1].get("messages", 0), reverse=True)[:5]
    medals = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣"]
    embed = discord.Embed(
        title="Top 5 Users by Messages",
        color=0xFFD700
    )
    embed.set_thumbnail(url=ctx.guild.icon.url if ctx.guild.icon else discord.Embed.Empty)
    if not any(d.get("messages", 0) > 0 for _, d in sorted_users):
        embed.description = "No message data yet. Start chatting!"
        await ctx.send(embed=embed)
        return
    lines = []
    for i, (uid, data) in enumerate(sorted_users):
        member = ctx.guild.get_member(int(uid))
        name = member.display_name if member else f"User#{uid[-4:]}"
        msgs = data.get("messages", 0)
        lvl = get_level(data["xp"])
        rank_title = get_rank_title(lvl)
        lines.append(
            f"{medals[i]} **{name}**\n"
            f"┣ 💬 `{msgs}` messages\n"
            f"┣ ⚡ `{data['xp']}` XP\n"
            f"┗ {rank_title} - Level `{lvl}`"
        )
    embed.description = "\n\n".join(lines)
    embed.set_footer(text=f"Tracking {len(current_data)} users in total")
    embed.timestamp = datetime.datetime.now()
    await ctx.send(embed=embed)

@leaderboard.error
async def leaderboard_error(ctx, error):
    if isinstance(error, commands.CommandOnCooldown):
        await ctx.send(f"Wait: {error.retry_after:.1f}s")

@bot.command(name="date")
async def date(ctx):
    now = datetime.datetime.now()
    embed = discord.Embed(
        description=f"**{now.strftime('%d.%m.%Y')}** - **{now.strftime('%H:%M:%S')}**",
        color=0x5865F2
    )
    await ctx.send(embed=embed)

@bot.command(name="poll")
@commands.cooldown(1, 10, commands.BucketType.user)
async def poll(ctx, *, question_and_options: str = None):
    if question_and_options is None:
        await ctx.send("!poll Question? | Option1 Option2")
        return
    try:
        parts = question_and_options.split("|")
        if len(parts) < 2:
            await ctx.send("Separate the question and options with `|`.")
            return
        question = parts[0].strip()
        options = [s.strip() for s in parts[1].split() if s.strip()]
        if not (2 <= len(options) <= 10):
            await ctx.send("Enter between 2-10 options.")
            return
        emojis = ["1️⃣","2️⃣","3️⃣","4️⃣","5️⃣","6️⃣","7️⃣","8️⃣","9️⃣","🔟"]
        embed = discord.Embed(title=f"{question}", color=0x5865F2)
        embed.description = "\n".join(f"{emojis[i]} {s}" for i, s in enumerate(options))
        embed.set_footer(text=f"Poll created by: {ctx.author.display_name}")
        msg = await ctx.send(embed=embed)
        for i in range(len(options)):
            await msg.add_reaction(emojis[i])
    except:
        await ctx.send("Format: !poll Question? | Option1 Option2")

@poll.error
async def poll_error(ctx, error):
    if isinstance(error, commands.CommandOnCooldown):
        await ctx.send(f"Wait: {error.retry_after:.1f}s")

@bot.command(name="remind")
@commands.cooldown(1, 5, commands.BucketType.user)
async def remind(ctx, duration: str = None, *, message: str = None):
    if duration is None or message is None:
        await ctx.send("!remind 10m meeting")
        return
    seconds, duration_display = parse_duration(duration)
    if seconds is None:
        await ctx.send("Invalid duration. Examples: 10s, 10m, 1h, 2d")
        return
    embed = discord.Embed(
        description=f"I will remind you in **{duration_display}**: *{message}*",
        color=0x57F287
    )
    await ctx.send(embed=embed)
    await asyncio.sleep(seconds)
    remind_embed = discord.Embed(
        title="Reminder!",
        description=f"{ctx.author.mention}\n\n**{message}**",
        color=0xED4245
    )
    await ctx.send(embed=remind_embed)

@remind.error
async def remind_error(ctx, error):
    if isinstance(error, commands.CommandOnCooldown):
        await ctx.send(f"Wait: {error.retry_after:.1f}s")

@bot.command(name="pick")
@commands.cooldown(1, 2, commands.BucketType.user)
async def pick(ctx, *, input_str: str = None):
    if input_str is None:
        embed = discord.Embed(
            title="Invalid Usage",
            description=(
                "Mode 1 - Comma-separated: !pick word,number,word\n"
                "Mode 2 - Space-separated: !pick word number word\n\n"
                "Examples:\n"
                "!pick 1,2,adana,63\n"
                "!pick a,b,c\n"
                "!pick 1 adana 3 yusuf"
            ),
            color=0xED4245
        )
        await ctx.send(embed=embed)
        return

    if "," in input_str:
        options = [s.strip() for s in input_str.split(",") if s.strip()]
    else:
        options = [s.strip() for s in input_str.split() if s.strip()]

    if len(options) < 2:
        embed = discord.Embed(
            title="Not Enough Options",
            description="You must enter at least **2 options**.\n!pick a,b,c or !pick a b c",
            color=0xED4245
        )
        await ctx.send(embed=embed)
        return

    picked = random.choice(options)
    listing = " · ".join(f"`{s}`" for s in options)

    embed = discord.Embed(title="Pick", color=0xEB459E)
    embed.add_field(name="Options", value=listing, inline=False)
    embed.add_field(name="Picked", value=f"**{picked}**", inline=False)
    embed.set_footer(text=f"Randomly picked from {len(options)} options")
    await ctx.send(embed=embed)

@pick.error
async def pick_error(ctx, error):
    if isinstance(error, commands.CommandOnCooldown):
        await ctx.send(f"Wait: {error.retry_after:.1f}s")

@bot.command(name="translate")
@commands.cooldown(1, 5, commands.BucketType.user)
async def translate(ctx, *, text_lang: str = None):
    if text_lang is None:
        embed = discord.Embed(
            title="Invalid Usage",
            description=(
                "Usage 1: !translate text: [text] lang: [lang]\n"
                "Usage 2: !translate [text] lang: [lang]\n\n"
                "Examples:\n"
                "!translate text: The weather is nice today lang: tr\n"
                "!translate The weather is nice today lang: tr\n\n"
                "Supported Languages:\n"
                "en English, tr Turkish, de German\n"
                "fr French, es Spanish, it Italian\n"
                "ru Russian, ar Arabic, ja Japanese"
            ),
            color=0xED4245
        )
        await ctx.send(embed=embed)
        return

    text_match = re.search(r"text:\s*(.+?)(?=\s+lang:|$)", text_lang, re.IGNORECASE)
    lang_match = re.search(r"lang:\s*([a-z]{2})", text_lang, re.IGNORECASE)

    if not lang_match:
        embed = discord.Embed(
            title="Invalid Format",
            description=(
                "Please specify the target language! (lang: en)\n"
                "Example: !translate The weather is nice today lang: tr"
            ),
            color=0xED4245
        )
        await ctx.send(embed=embed)
        return

    target_lang = lang_match.group(1).lower()

    if text_match:
        text = text_match.group(1).strip()
    else:
        text = re.sub(r"\s*lang:\s*[a-z]{2}\s*", "", text_lang, flags=re.IGNORECASE).strip()

    if not text:
        embed = discord.Embed(
            title="Text Not Found",
            description="Please enter the text to translate!",
            color=0xED4245
        )
        await ctx.send(embed=embed)
        return

    translation = await translate_text(text, target_lang)
    if translation is None:
        embed = discord.Embed(
            title="Translation Failed",
            description="Could not connect to the translation API. Please try again later.",
            color=0xED4245
        )
        await ctx.send(embed=embed)
        return

    lang_map = {
        "tr": "Turkish", "en": "English", "de": "German",
        "fr": "French", "es": "Spanish", "it": "Italian",
        "ru": "Russian", "ar": "Arabic", "ja": "Japanese",
        "pt": "Portuguese", "nl": "Dutch", "pl": "Polish"
    }

    target_name = lang_map.get(target_lang, target_lang.upper())

    embed = discord.Embed(title="Translation", color=0x9B59B6)
    embed.add_field(name=f"Original", value=f"```{text}```", inline=False)
    embed.add_field(name=f"Translation ({target_name})", value=f"```{translation}```", inline=False)
    embed.set_footer(text=f"Queried by {ctx.author.display_name}")
    embed.timestamp = datetime.datetime.now()
    await ctx.send(embed=embed)

@translate.error
async def translate_error(ctx, error):
    if isinstance(error, commands.CommandOnCooldown):
        await ctx.send(f"Wait: {error.retry_after:.1f}s")

@bot.command(name="lookup")
@commands.cooldown(1, 10, commands.BucketType.user)
async def lookup(ctx, target: str = None):
    if target is None:
        await ctx.send("!lookup example.com or !lookup 8.8.8.8")
        return
    msg = await ctx.send(f"Querying **{target}**...")
    if re.match(r"^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$", target):
        try:
            try:
                hostname = socket.gethostbyaddr(target)[0]
            except:
                hostname = "Unknown"
            loop = asyncio.get_event_loop()
            def geo_req():
                r = requests.get(f"http://ip-api.com/json/{target}", timeout=5)
                return r.json()
            geo = await loop.run_in_executor(None, geo_req)
            embed = discord.Embed(title=f"IP: {target}", color=0x5865F2)
            embed.add_field(name="Hostname", value=hostname, inline=False)
            embed.add_field(name="Country", value=geo.get("country","?"), inline=True)
            embed.add_field(name="City", value=geo.get("city","?"), inline=True)
            embed.add_field(name="ISP", value=geo.get("isp","?"), inline=True)
            await msg.edit(content=None, embed=embed)
        except Exception as e:
            await msg.edit(content=f"Error: {e}")
    else:
        info = await domain_info_async(target)
        if "error" in info:
            await msg.edit(content=f"{info['error']}")
            return
        embed = discord.Embed(title=f"{target}", color=0x57F287)
        embed.add_field(name="IP", value=f"`{info['ip']}`", inline=True)
        embed.add_field(name="Hostname", value=info["hostname"], inline=True)
        embed.add_field(name="Country", value=info["country"], inline=True)
        embed.add_field(name="City", value=info["city"], inline=True)
        embed.add_field(name="ISP", value=info["isp"], inline=True)
        embed.add_field(name="Registrar", value=info["registrar"], inline=True)
        embed.add_field(name="SSL", value=info["ssl_issuer"], inline=False)
        embed.add_field(name="SSL Expiry", value=str(info["ssl_expiry"]), inline=True)
        embed.add_field(name="HTTP", value=str(info["status_code"]), inline=True)
        embed.add_field(name="Server", value=info["server"], inline=True)
        ports = ", ".join(map(str, info["open_ports"])) if info["open_ports"] else "None"
        embed.add_field(name="Open Ports", value=ports, inline=False)
        dns_str = "\n".join(f"**{k}:** {', '.join(v[:2])}" for k, v in info["dns_records"].items())
        embed.add_field(name="DNS", value=dns_str, inline=False)
        await msg.edit(content=None, embed=embed)

@lookup.error
async def lookup_error(ctx, error):
    if isinstance(error, commands.CommandOnCooldown):
        await ctx.send(f"Wait: {error.retry_after:.1f}s")

@bot.command(name="ipinfo")
@commands.cooldown(1, 5, commands.BucketType.user)
async def ipinfo_cmd(ctx, ip: str = None):
    if ip is None:
        await ctx.send("!ipinfo 8.8.8.8")
        return
    try:
        details = ipinfo_handler.getDetails(ip)
        embed = discord.Embed(title=f"IP: {ip}", color=0x9B59B6)
        embed.add_field(name="Country", value=getattr(details, "country", "?"), inline=True)
        embed.add_field(name="City", value=getattr(details, "city", "?"), inline=True)
        embed.add_field(name="Region", value=getattr(details, "region", "?"), inline=True)
        embed.add_field(name="ISP", value=getattr(details, "org", "?"), inline=False)
        embed.add_field(name="Location", value=getattr(details, "loc", "?"), inline=True)
        embed.add_field(name="Timezone", value=getattr(details, "timezone", "?"), inline=True)
        await ctx.send(embed=embed)
    except Exception as e:
        await ctx.send(f"Query failed: {e}")

@ipinfo_cmd.error
async def ipinfo_cmd_error(ctx, error):
    if isinstance(error, commands.CommandOnCooldown):
        await ctx.send(f"Wait: {error.retry_after:.1f}s")

@bot.command(name="weather")
@commands.cooldown(1, 5, commands.BucketType.user)
async def weather(ctx, *, city: str = None):
    if city is None:
        embed = discord.Embed(
            title="Invalid Usage",
            description="Usage: !weather [city]\nExample: !weather London",
            color=0xED4245
        )
        await ctx.send(embed=embed)
        return

    lat, lon = await get_coordinates(city)
    if lat is None or lon is None:
        await ctx.send(f"**{city}** not found! Please enter a valid city name.")
        return

    data = await get_weather(lat, lon)
    if data is None:
        await ctx.send("Could not retrieve weather data. Please try again later.")
        return

    current = data.get("current_weather")
    if current is None:
        await ctx.send("Weather data could not be retrieved.")
        return

    temperature = current.get("temperature")
    wind = current.get("windspeed")
    wind_direction = current.get("winddirection")
    weather_code = current.get("weathercode")

    weather_map = {
        0: "Clear", 1: "Mostly Clear", 2: "Partly Cloudy",
        3: "Overcast", 45: "Fog", 48: "Dense Fog",
        51: "Light Drizzle", 53: "Moderate Drizzle", 55: "Heavy Drizzle",
        61: "Light Rain", 63: "Moderate Rain", 65: "Heavy Rain",
        71: "Light Snow", 73: "Moderate Snow", 75: "Heavy Snow",
        95: "Thunderstorm", 96: "Hail", 99: "Heavy Hail"
    }
    condition = weather_map.get(weather_code, "Unknown")

    if temperature < 0:
        condition_emoji = "🥶"
    elif temperature < 10:
        condition_emoji = "❄️"
    elif temperature < 20:
        condition_emoji = "🌤️"
    elif temperature < 30:
        condition_emoji = "☀️"
    else:
        condition_emoji = "🔥"

    embed = discord.Embed(
        title=f"{condition_emoji} {city.title()} Weather",
        description=f"**{condition}**",
        color=0x3498db
    )
    embed.add_field(name="Temperature", value=f"**{temperature:.1f}°C**", inline=True)
    embed.add_field(name="Wind", value=f"**{wind:.1f} km/h**", inline=True)
    if wind_direction:
        embed.add_field(name="Wind Direction", value=f"**{wind_direction}°**", inline=True)
    embed.set_footer(text=f"Queried by: {ctx.author.display_name}")
    embed.timestamp = datetime.datetime.now()
    await ctx.send(embed=embed)

@weather.error
async def weather_error(ctx, error):
    if isinstance(error, commands.CommandOnCooldown):
        await ctx.send(f"Wait: {error.retry_after:.1f}s")

@bot.command(name="clear")
@commands.has_permissions(manage_messages=True)
@commands.cooldown(1, 10, commands.BucketType.guild)
async def clear(ctx, amount: str = None):
    if amount is None:
        embed = discord.Embed(
            title="Invalid Usage",
            description=(
                "Usage 1: !clear <number> - Deletes a specific number of messages\n"
                "Usage 2: !clear all - Clears the entire channel\n\n"
                "Examples:\n"
                "!clear 10 - Deletes the last 10 messages\n"
                "!clear all - Clears the entire channel"
            ),
            color=0xED4245
        )
        await ctx.send(embed=embed, delete_after=10)
        return

    if amount.lower() == "all":
        embed = discord.Embed(
            title="Entire Channel Will Be Cleared!",
            description="This action will clear the **entire channel**. Do you confirm?\n\n✅ Confirm\n❌ Cancel",
            color=0xFEE75C
        )
        confirm_msg = await ctx.send(embed=embed)
        await confirm_msg.add_reaction("✅")
        await confirm_msg.add_reaction("❌")

        def check(reaction, user):
            return user == ctx.author and reaction.message.id == confirm_msg.id and str(reaction.emoji) in ["✅", "❌"]

        try:
            reaction, user = await bot.wait_for("reaction_add", timeout=30, check=check)

            if str(reaction.emoji) == "✅":
                try:
                    await confirm_msg.delete()
                except:
                    pass

                wait_msg = await ctx.send("Clearing the channel... Please wait.")

                deleted_count = 0
                while True:
                    messages = [m async for m in ctx.channel.history(limit=100)]
                    if not messages:
                        break
                    deleted = await ctx.channel.purge(limit=100)
                    deleted_count += len(deleted)
                    await asyncio.sleep(1)

                try:
                    await wait_msg.delete()
                except:
                    pass

                embed = discord.Embed(
                    title="Entire Channel Cleared!",
                    description=f"**{deleted_count}** messages deleted.\nChannel: {ctx.channel.mention}",
                    color=0x57F287
                )
                embed.set_footer(text=f"Performed by: {ctx.author.display_name}")
                msg = await ctx.send(embed=embed)
                await asyncio.sleep(5)
                try:
                    await msg.delete()
                except:
                    pass

            else:
                embed = discord.Embed(
                    title="Cancelled",
                    description="The clear operation has been cancelled.",
                    color=0xED4245
                )
                await confirm_msg.edit(embed=embed)
                await asyncio.sleep(3)
                try:
                    await confirm_msg.delete()
                except:
                    pass

        except asyncio.TimeoutError:
            embed = discord.Embed(
                title="Timed Out",
                description="The operation was cancelled because you did not confirm.",
                color=0xED4245
            )
            await confirm_msg.edit(embed=embed)
            await asyncio.sleep(3)
            try:
                await confirm_msg.delete()
            except:
                pass
        return

    if not amount.isdigit():
        embed = discord.Embed(
            title="Invalid Usage",
            description="Please enter a number or **all**!\nExample: !clear 10 or !clear all",
            color=0xED4245
        )
        await ctx.send(embed=embed, delete_after=5)
        return

    amount_int = int(amount)
    if amount_int < 1 or amount_int > 1000:
        embed = discord.Embed(
            title="Invalid Amount",
            description="The number of messages to delete must be between **1 and 1000**.",
            color=0xED4245
        )
        await ctx.send(embed=embed, delete_after=5)
        return

    try:
        await ctx.message.delete()
    except:
        pass

    deleted = await ctx.channel.purge(limit=amount_int)

    embed = discord.Embed(
        title="Cleared!",
        description=f"**{len(deleted)}** messages deleted.\nChannel: {ctx.channel.mention}",
        color=0x57F287
    )
    embed.set_footer(text=f"Performed by: {ctx.author.display_name}")
    msg = await ctx.send(embed=embed)
    await asyncio.sleep(4)
    try:
        await msg.delete()
    except:
        pass

@clear.error
async def clear_error(ctx, error):
    if isinstance(error, commands.MissingPermissions):
        embed = discord.Embed(
            title="Insufficient Permissions",
            description="You need the **Manage Messages** permission to use this command.",
            color=0xED4245
        )
        await ctx.send(embed=embed, delete_after=5)
    elif isinstance(error, commands.CommandOnCooldown):
        await ctx.send(f"Wait: {error.retry_after:.1f}s", delete_after=3)

@bot.command(name="ban")
@commands.has_permissions(ban_members=True)
@commands.cooldown(1, 3, commands.BucketType.user)
async def ban(ctx, member: discord.Member = None, *, reason: str = "No reason provided"):
    if member is None:
        embed = discord.Embed(
            title="Invalid Usage",
            description="Usage: !ban @user [reason]\nExample: !ban @john Broke the rules",
            color=0xED4245
        )
        await ctx.send(embed=embed)
        return
    if member == ctx.author:
        embed = discord.Embed(title="Error", description="You cannot ban yourself!", color=0xED4245)
        await ctx.send(embed=embed)
        return
    if member == ctx.guild.owner:
        embed = discord.Embed(title="Error", description="You cannot ban the server owner!", color=0xED4245)
        await ctx.send(embed=embed)
        return
    if ctx.author.top_role <= member.top_role:
        embed = discord.Embed(title="Insufficient Permissions", description="You cannot ban someone with an equal or higher role than you!", color=0xED4245)
        await ctx.send(embed=embed)
        return
    try:
        try:
            dm_embed = discord.Embed(
                title="You Have Been Banned!",
                description=f"Server: {ctx.guild.name}\nReason: {reason}\nModerator: {ctx.author.display_name}",
                color=0xED4245
            )
            await member.send(embed=dm_embed)
        except:
            pass
        await member.ban(reason=f"By {ctx.author}: {reason}")
        embed = discord.Embed(title="User Banned!", color=0xED4245)
        embed.add_field(name="User", value=f"{member.mention} ({member})", inline=True)
        embed.add_field(name="Moderator", value=ctx.author.mention, inline=True)
        embed.add_field(name="Reason", value=reason, inline=False)
        embed.set_thumbnail(url=member.display_avatar.url)
        embed.timestamp = datetime.datetime.now()
        await ctx.send(embed=embed)
    except discord.Forbidden:
        embed = discord.Embed(title="Error", description="I do not have permission to ban this user!", color=0xED4245)
        await ctx.send(embed=embed)

@ban.error
async def ban_error(ctx, error):
    if isinstance(error, commands.MissingPermissions):
        embed = discord.Embed(title="Insufficient Permissions", description="You need the **Ban Members** permission to use this command.", color=0xED4245)
        await ctx.send(embed=embed)
    elif isinstance(error, commands.MemberNotFound):
        embed = discord.Embed(title="User Not Found", description="Mention a valid user! Example: !ban @player", color=0xED4245)
        await ctx.send(embed=embed)
    elif isinstance(error, commands.CommandOnCooldown):
        await ctx.send(f"Wait: {error.retry_after:.1f}s")

@bot.command(name="unban")
@commands.has_permissions(ban_members=True)
@commands.cooldown(1, 3, commands.BucketType.user)
async def unban(ctx, user_id: int = None, *, reason: str = "No reason provided"):
    if user_id is None:
        embed = discord.Embed(
            title="Invalid Usage",
            description="Usage: !unban <user_id> [reason]\nExample: !unban 123456789",
            color=0xED4245
        )
        await ctx.send(embed=embed)
        return
    try:
        user = await bot.fetch_user(user_id)
        await ctx.guild.unban(user, reason=f"By {ctx.author}: {reason}")
        embed = discord.Embed(title="Ban Removed!", color=0x57F287)
        embed.add_field(name="User", value=f"{user} (`{user.id}`)", inline=True)
        embed.add_field(name="Moderator", value=ctx.author.mention, inline=True)
        embed.add_field(name="Reason", value=reason, inline=False)
        embed.timestamp = datetime.datetime.now()
        await ctx.send(embed=embed)
    except discord.NotFound:
        embed = discord.Embed(title="Error", description="No banned user found with that ID!", color=0xED4245)
        await ctx.send(embed=embed)
    except discord.Forbidden:
        embed = discord.Embed(title="Error", description="I do not have permission to unban this user!", color=0xED4245)
        await ctx.send(embed=embed)

@unban.error
async def unban_error(ctx, error):
    if isinstance(error, commands.MissingPermissions):
        embed = discord.Embed(title="Insufficient Permissions", description="You need the **Ban Members** permission to use this command.", color=0xED4245)
        await ctx.send(embed=embed)
    elif isinstance(error, commands.BadArgument):
        embed = discord.Embed(title="Invalid Usage", description="Enter a valid user ID! Example: !unban 123456789", color=0xED4245)
        await ctx.send(embed=embed)
    elif isinstance(error, commands.CommandOnCooldown):
        await ctx.send(f"Wait: {error.retry_after:.1f}s")

@bot.command(name="kick")
@commands.has_permissions(kick_members=True)
@commands.cooldown(1, 3, commands.BucketType.user)
async def kick(ctx, member: discord.Member = None, *, reason: str = "No reason provided"):
    if member is None:
        embed = discord.Embed(
            title="Invalid Usage",
            description="Usage: !kick @user [reason]\nExample: !kick @john Broke the rules",
            color=0xED4245
        )
        await ctx.send(embed=embed)
        return
    if member == ctx.author:
        embed = discord.Embed(title="Error", description="You cannot kick yourself!", color=0xED4245)
        await ctx.send(embed=embed)
        return
    if member == ctx.guild.owner:
        embed = discord.Embed(title="Error", description="You cannot kick the server owner!", color=0xED4245)
        await ctx.send(embed=embed)
        return
    if ctx.author.top_role <= member.top_role:
        embed = discord.Embed(title="Insufficient Permissions", description="You cannot kick someone with an equal or higher role than you!", color=0xED4245)
        await ctx.send(embed=embed)
        return
    try:
        try:
            dm_embed = discord.Embed(
                title="You Have Been Kicked!",
                description=f"Server: {ctx.guild.name}\nReason: {reason}\nModerator: {ctx.author.display_name}",
                color=0xFEE75C
            )
            await member.send(embed=dm_embed)
        except:
            pass
        await member.kick(reason=f"By {ctx.author}: {reason}")
        embed = discord.Embed(title="User Kicked!", color=0xFEE75C)
        embed.add_field(name="User", value=f"{member.mention} ({member})", inline=True)
        embed.add_field(name="Moderator", value=ctx.author.mention, inline=True)
        embed.add_field(name="Reason", value=reason, inline=False)
        embed.set_thumbnail(url=member.display_avatar.url)
        embed.timestamp = datetime.datetime.now()
        await ctx.send(embed=embed)
    except discord.Forbidden:
        embed = discord.Embed(title="Error", description="I do not have permission to kick this user!", color=0xED4245)
        await ctx.send(embed=embed)

@kick.error
async def kick_error(ctx, error):
    if isinstance(error, commands.MissingPermissions):
        embed = discord.Embed(title="Insufficient Permissions", description="You need the **Kick Members** permission to use this command.", color=0xED4245)
        await ctx.send(embed=embed)
    elif isinstance(error, commands.MemberNotFound):
        embed = discord.Embed(title="User Not Found", description="Mention a valid user! Example: !kick @john", color=0xED4245)
        await ctx.send(embed=embed)
    elif isinstance(error, commands.CommandOnCooldown):
        await ctx.send(f"Wait: {error.retry_after:.1f}s")

@bot.command(name="ship")
@commands.cooldown(1, 5, commands.BucketType.user)
async def ship(ctx, member1: discord.Member = None, member2: discord.Member = None):
    if member1 is None or member2 is None:
        embed = discord.Embed(
            title="Invalid Usage",
            description="Usage: !ship @user1 @user2\nExample: !ship @john @jane",
            color=0xED4245
        )
        await ctx.send(embed=embed)
        return
    if member1 == member2:
        embed = discord.Embed(
            title="Did You Ship Yourself?",
            description=f"{member1.mention} is trying to ship with themselves... Narcissist vibes 🪞",
            color=0xED4245
        )
        await ctx.send(embed=embed)
        return
    rate = random.randint(0, 100)
    filled = int(rate / 10)
    empty = 10 - filled
    bar = "❤️" * filled + "🖤" * empty
    if rate <= 20:
        message = "👫 Stay friends, love hasn't helped anyone 😅"
        color = 0x95a5a6
        emoji_title = "💀 No Love Here"
        status = "Friendship > Love"
    elif rate <= 40:
        message = "🚫 Stop trying, love doesn't fill the stomach, friendship is the answer 😬"
        color = 0xe74c3c
        emoji_title = "😬 Forced Love"
        status = "Fate Doesn't Want This"
    elif rate <= 60:
        message = "😐 There's no great love here, force a marriage if you want 💍"
        color = 0xe67e22
        emoji_title = "😐 Average Spark"
        status = "Maybe, Maybe Not"
    elif rate <= 80:
        message = "🔥 Put in a little more effort and it'll happen, good luck 😍"
        color = 0xf1c40f
        emoji_title = "🔥 There's Hope!"
        status = "Love Is Knocking"
    else:
        results = [
            "THIS IS TRUE LOVE, I SEE MARRIAGE, IS YOUR RING READY? 💍👰🤵",
            "I SEE LOVE, I SEE MARRIAGE, IS THE GROOM READY? 💒💍😍",
            "THIS IS TRUE LOVE, PREPARE THE RINGS, BOOK THE WEDDING HALL 💍🎊👑"
        ]
        message = random.choice(results)
        color = 0xFF69B4
        emoji_title = "😍❤️‍🔥 TRUE LOVE!"
        status = "Fate United Them"
    ship_name = member1.display_name[:len(member1.display_name)//2] + member2.display_name[len(member2.display_name)//2:]
    embed = discord.Embed(title=f"{emoji_title}", color=color)
    embed.add_field(name="💞 Ship Name", value=f"**{ship_name}**", inline=False)
    embed.add_field(name="👫 Couple", value=f"{member1.mention} 💘 {member2.mention}", inline=False)
    embed.add_field(name=f"💝 Compatibility - **{rate}%**", value=f"{bar}", inline=False)
    embed.add_field(name="🏷️ Status", value=f"*{status}*", inline=True)
    embed.add_field(name="💬 Comment", value=message, inline=False)
    embed.set_footer(text=f"💌 Ship test • {ctx.guild.name}")
    embed.timestamp = datetime.datetime.now()
    await ctx.send(embed=embed)

@ship.error
async def ship_error(ctx, error):
    if isinstance(error, commands.CommandOnCooldown):
        await ctx.send(f"Wait: {error.retry_after:.1f}s")
    elif isinstance(error, commands.MemberNotFound):
        embed = discord.Embed(title="User Not Found", description="Mention valid users! Example: !ship @john @jane", color=0xED4245)
        await ctx.send(embed=embed)

@bot.command(name="reverse")
@commands.cooldown(1, 3, commands.BucketType.user)
async def reverse(ctx, *, text: str = None):
    if text is None:
        embed = discord.Embed(
            title="Invalid Usage",
            description="Usage: !reverse [text]\nExample: !reverse Hello world",
            color=0xED4245
        )
        await ctx.send(embed=embed)
        return

    reversed_text = text[::-1]

    embed = discord.Embed(
        title="Reversed",
        color=0x5865F2
    )
    embed.add_field(name="Original", value=f"```{text}```", inline=False)
    embed.add_field(name="Reversed", value=f"```{reversed_text}```", inline=False)
    embed.set_footer(text=f"By {ctx.author.display_name}")
    embed.timestamp = datetime.datetime.now()
    await ctx.send(embed=embed)

@reverse.error
async def reverse_error(ctx, error):
    if isinstance(error, commands.CommandOnCooldown):
        await ctx.send(f"Wait: {error.retry_after:.1f}s")

class HelpView(discord.ui.View):
    def __init__(self, ctx):
        super().__init__(timeout=120)
        self.ctx = ctx
        self.page = 0
        self.total_pages = 3
        self.embed = None
        self.message = None

    async def update_embed(self, interaction: discord.Interaction = None):
        embed = discord.Embed(title="📚 Command List", color=0x5865F2)
        embed.set_footer(text=f"Page {self.page+1}/{self.total_pages} • Bot-2319")
        embed.timestamp = datetime.datetime.now()

        if self.page == 0:
            embed.description = "**General Commands** - Fun, games, info and tools"
            embed.add_field(
                name="🎮 Games & Fun",
                value=(
                    "`!coinflip` - Flip a coin\n"
                    "`!dice` - Roll a dice\n"
                    "`!random` - Random number 1-100\n"
                    "`!luckynumber` - Lucky number and color\n"
                    "`!word [letter]` - Random word starting with letter\n"
                    "`!guess [number]` - Guess a number 1-100\n"
                    "`!rps [rock/paper/scissors]` - Rock paper scissors\n"
                    "`!ship @user1 @user2` - Ship rate\n"
                    "`!reverse [text]` - Reverse text\n"
                    "`!emoji [text]` - Convert text to emoji"
                ),
                inline=False
            )
            embed.add_field(
                name="🌐 Lookup & Info",
                value=(
                    "`!lookup [domain/ip]` - Detailed site/IP analysis\n"
                    "`!ipinfo [ip]` - IP info (ipinfo)\n"
                    "`!weather [city]` - Weather\n"
                    "`!translate [text] lang:[lang]` - Translate text\n"
                    "`!qr [text/link]` - Generate QR code\n"
                    "`!ping` - Bot latency\n"
                    "`!avatar [@user]` - Show avatar\n"
                    "`!server` - Server info\n"
                    "`!date` - Date and time"
                ),
                inline=False
            )
            embed.add_field(
                name="⏰ Other",
                value=(
                    "`!remind [duration] [message]` - Set a reminder\n"
                    "`!poll Question? | Option1 Option2` - Create a poll\n"
                    "`!pick a,b,c` - Random selection\n"
                    "`!password` - Generate a secure password"
                ),
                inline=False
            )

        elif self.page == 1:
            embed.description = "**🛡️ Moderation Commands** - Staff commands (permanent if no duration is given)"
            embed.add_field(
                name="👮 User Management",
                value=(
                    "`!ban @user [reason]` - Ban a user\n"
                    "`!unban <id>` - Remove a ban\n"
                    "`!kick @user [reason]` - Kick a user\n"
                    "`!mute @user [duration] [reason]` - Mute (permanent if no duration)\n"
                    "`!unmute @user [reason]` - Remove mute\n"
                    "`!punish @user [duration] [reason]` - Punish (permanent if no duration)\n"
                    "`!unpunish @user` - Remove punishment"
                ),
                inline=False
            )
            embed.add_field(
                name="📝 Channel & Message Management",
                value=(
                    "`!clear [number/all]` - Delete messages (all clears the entire channel)\n"
                    "`!lock` - Lock the channel\n"
                    "`!unlock` - Unlock the channel"
                ),
                inline=False
            )
            embed.add_field(
                name="⏱️ Duration Formats",
                value=(
                    "`10s`, `10m`, `1h`, `2d`\n"
                    "You can also use full names: `10 minutes`, `1 hour`\n"
                    "If no duration is given, it will be **permanent**."
                ),
                inline=False
            )

        else:
            embed.description = "**⚙️ Setup System** - Configure the bot settings"
            embed.add_field(
                name="📌 Basic Settings",
                value=(
                    "`!setup logchannel #channel` - Log channel\n"
                    "`!setup punishedrole @role` - Punished role\n"
                    "`!setup registerchannel #channel` - Register channel\n"
                    "`!setup unregisteredrole @role` - Unregistered role\n"
                    "`!setup staffrole @role` - Register staff role"
                ),
                inline=False
            )
            embed.add_field(
                name="🗑️ Removal & Viewing",
                value=(
                    "`!setup remove <setting>` - Remove a setting\n"
                    "`!setup show` - Show all settings"
                ),
                inline=False
            )

        if interaction:
            await interaction.response.edit_message(embed=embed, view=self)
        else:
            self.embed = embed
            self.message = await self.ctx.send(embed=embed, view=self)

    @discord.ui.button(label="◀️ Back", style=discord.ButtonStyle.secondary, custom_id="back")
    async def back_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.page > 0:
            self.page -= 1
            await self.update_embed(interaction)

    @discord.ui.button(label="🏠 Home", style=discord.ButtonStyle.primary, custom_id="home")
    async def home_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.page = 0
        await self.update_embed(interaction)

    @discord.ui.button(label="▶️ Next", style=discord.ButtonStyle.secondary, custom_id="next")
    async def next_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.page < self.total_pages - 1:
            self.page += 1
            await self.update_embed(interaction)

    async def on_timeout(self):
        for child in self.children:
            child.disabled = True
        if self.message:
            await self.message.edit(view=self)

@bot.command(name="help")
async def help(ctx):
    view = HelpView(ctx)
    await view.update_embed()

@bot.command(name="qr")
@commands.cooldown(1, 5, commands.BucketType.user)
async def qr(ctx, *, text: str = None):
    if text is None:
        embed = discord.Embed(
            title="Invalid Usage",
            description=(
                "Usage: !qr [text/link]\n"
                "Examples:\n"
                "!qr Hello world\n"
                "!qr https://google.com"
            ),
            color=0xED4245
        )
        await ctx.send(embed=embed)
        return

    await ctx.send("Generating QR code...")

    url = f"https://api.qrserver.com/v1/create-qr-code/?size=300x300&data={text}"

    embed = discord.Embed(
        title="QR Code Generated",
        description=f"Content: `{text}`",
        color=0x57F287
    )
    embed.set_image(url=url)
    embed.set_footer(text=f"Created by {ctx.author.display_name}")
    embed.timestamp = datetime.datetime.now()

    await ctx.send(embed=embed)

@qr.error
async def qr_error(ctx, error):
    if isinstance(error, commands.CommandOnCooldown):
        await ctx.send(f"Wait: {error.retry_after:.1f}s")

@bot.command(name="punish")
@commands.has_permissions(manage_messages=True)
@commands.cooldown(1, 5, commands.BucketType.user)
async def punish(ctx, member: discord.Member = None, duration: str = None, *, reason: str = "No reason provided"):
    if member is None:
        embed = discord.Embed(
            title="Invalid Usage",
            description="Usage: !punish @user [duration] [reason]\nExample: !punish @john 10m Spamming\n\nIf no duration is given, the punishment will be permanent.",
            color=0xED4245
        )
        await ctx.send(embed=embed)
        return

    if member == ctx.author:
        await ctx.send("You cannot punish yourself!")
        return
    if member.guild_permissions.administrator:
        await ctx.send("This user cannot be punished because they are an administrator!")
        return

    seconds = None
    duration_display = "Permanent"
    if duration:
        seconds, duration_display = parse_duration(duration)
        if seconds is None:
            await ctx.send("Invalid duration format! Examples: 10m, 1h, 2d, 12 days, 1 hour")
            return
        if seconds > 2592000:
            await ctx.send("Maximum punishment duration is 30 days!")
            return

    punished = load_punished()
    if str(member.id) in punished:
        await ctx.send("This user is already punished!")
        return

    punished_role_id = get_config_value("punished_role_id")
    roles = [r.id for r in member.roles if r.id != punished_role_id and not r.is_default()]

    end_time = time.time() + seconds if seconds else None

    punished[str(member.id)] = {
        "roles": roles,
        "end": end_time,
        "reason": reason,
        "staff": ctx.author.id,
        "duration_display": duration_display
    }
    save_punished(punished)

    roles_to_remove = [r for r in member.roles if not r.is_default() and r.id != punished_role_id]
    if roles_to_remove:
        try:
            await member.remove_roles(*roles_to_remove, reason=f"Punishment: {reason}")
        except:
            pass

    punished_role = ctx.guild.get_role(punished_role_id) if punished_role_id else None
    if punished_role:
        try:
            await member.add_roles(punished_role, reason=f"Punishment: {reason}")
        except:
            pass

    duration_text = duration_display if seconds else "Permanent (until removed)"
    embed = discord.Embed(
        title="Punishment Applied",
        description=f"{member.mention} has been punished.\nDuration: {duration_text}\nReason: {reason}\nModerator: {ctx.author.mention}",
        color=0xED4245,
        timestamp=datetime.datetime.now()
    )
    await ctx.send(embed=embed)

    if seconds:
        asyncio.create_task(remove_punishment(member.id, seconds))

@punish.error
async def punish_error(ctx, error):
    if isinstance(error, commands.MissingPermissions):
        await ctx.send("You do not have permission to use this command!")
    elif isinstance(error, commands.CommandOnCooldown):
        await ctx.send(f"Wait: {error.retry_after:.1f}s")

@bot.command(name="unpunish")
@commands.has_permissions(manage_messages=True)
@commands.cooldown(1, 5, commands.BucketType.user)
async def unpunish(ctx, member: discord.Member = None):
    if member is None:
        embed = discord.Embed(
            title="Invalid Usage",
            description="Usage: !unpunish @user\nExample: !unpunish @john",
            color=0xED4245
        )
        await ctx.send(embed=embed)
        return

    punished = load_punished()
    if str(member.id) not in punished:
        await ctx.send("This user is not punished!")
        return

    await _remove_punishment(member.id)

    embed = discord.Embed(
        title="Punishment Removed",
        description=f"{member.mention}'s punishment has been removed by {ctx.author.mention}.",
        color=0x57F287,
        timestamp=datetime.datetime.now()
    )
    await ctx.send(embed=embed)

@unpunish.error
async def unpunish_error(ctx, error):
    if isinstance(error, commands.MissingPermissions):
        await ctx.send("You do not have permission to use this command!")
    elif isinstance(error, commands.CommandOnCooldown):
        await ctx.send(f"Wait: {error.retry_after:.1f}s")

@bot.command(name="mute")
@commands.has_permissions(moderate_members=True)
@commands.cooldown(1, 3, commands.BucketType.user)
async def mute(ctx, member: discord.Member = None, duration: str = None, *, reason: str = "No reason provided"):
    if member is None:
        embed = discord.Embed(
            title="Invalid Usage",
            description="Usage: !mute @user [duration] [reason]\nExample: !mute @john 10m Spamming\n\nIf no duration is given, the mute will be permanent.",
            color=0xED4245
        )
        await ctx.send(embed=embed)
        return

    if member == ctx.author:
        await ctx.send("You cannot mute yourself!")
        return
    if member == ctx.guild.owner:
        await ctx.send("You cannot mute the server owner!")
        return
    if ctx.author.top_role <= member.top_role:
        await ctx.send("You cannot mute someone with an equal or higher role than you!")
        return

    if duration:
        seconds, duration_display = parse_duration(duration)
        if seconds is None:
            await ctx.send("Invalid duration format! Examples: 10m, 1h, 2d, 12 days, 1 hour")
            return
        if seconds > 2419200:
            await ctx.send("Maximum mute duration is 28 days!")
            return
        if seconds < 1:
            await ctx.send("Minimum mute duration is 1 second!")
            return
    else:
        seconds = None
        duration_display = "Permanent"

    try:
        if seconds:
            end = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(seconds=seconds)
            await member.timeout(end, reason=f"By {ctx.author}: {reason}")
        else:
            await member.timeout(datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=28), reason=f"By {ctx.author}: {reason} (Permanent)")
            duration_display = "Permanent (28 days maximum)"

        try:
            dm_embed = discord.Embed(
                title="You Have Been Muted!",
                description=f"Server: {ctx.guild.name}\nDuration: {duration_display}\nReason: {reason}\nModerator: {ctx.author.display_name}",
                color=0xED4245
            )
            await member.send(embed=dm_embed)
        except:
            pass

        embed = discord.Embed(
            title="User Muted!",
            color=0xED4245
        )
        embed.add_field(name="User", value=f"{member.mention} ({member})", inline=True)
        embed.add_field(name="Moderator", value=ctx.author.mention, inline=True)
        embed.add_field(name="Duration", value=duration_display, inline=True)
        embed.add_field(name="Reason", value=reason, inline=False)
        embed.set_thumbnail(url=member.display_avatar.url)
        embed.timestamp = datetime.datetime.now()
        await ctx.send(embed=embed)

    except discord.Forbidden:
        await ctx.send("I do not have permission to mute this user!")

@mute.error
async def mute_error(ctx, error):
    if isinstance(error, commands.MissingPermissions):
        await ctx.send("You need the Moderate Members permission to use this command!")
    elif isinstance(error, commands.MemberNotFound):
        await ctx.send("Mention a valid user! Example: !mute @john 10m")
    elif isinstance(error, commands.CommandOnCooldown):
        await ctx.send(f"Wait: {error.retry_after:.1f}s")

@bot.command(name="unmute")
@commands.has_permissions(moderate_members=True)
@commands.cooldown(1, 3, commands.BucketType.user)
async def unmute(ctx, member: discord.Member = None, *, reason: str = "No reason provided"):
    if member is None:
        embed = discord.Embed(
            title="Invalid Usage",
            description="Usage: !unmute @user [reason]\nExample: !unmute @john Punishment over",
            color=0xED4245
        )
        await ctx.send(embed=embed)
        return

    if member.timed_out_until is None:
        await ctx.send(f"{member.mention} is not muted!")
        return

    try:
        await member.timeout(None, reason=f"By {ctx.author}: {reason}")

        try:
            dm_embed = discord.Embed(
                title="Your Mute Has Been Removed!",
                description=f"Server: {ctx.guild.name}\nReason: {reason}\nModerator: {ctx.author.display_name}",
                color=0x57F287
            )
            await member.send(embed=dm_embed)
        except:
            pass

        embed = discord.Embed(
            title="Mute Removed!",
            color=0x57F287
        )
        embed.add_field(name="User", value=f"{member.mention} ({member})", inline=True)
        embed.add_field(name="Moderator", value=ctx.author.mention, inline=True)
        embed.add_field(name="Reason", value=reason, inline=False)
        embed.set_thumbnail(url=member.display_avatar.url)
        embed.timestamp = datetime.datetime.now()
        await ctx.send(embed=embed)

    except discord.Forbidden:
        await ctx.send("I do not have permission to remove this user's mute!")

@unmute.error
async def unmute_error(ctx, error):
    if isinstance(error, commands.MissingPermissions):
        await ctx.send("You need the Moderate Members permission to use this command!")
    elif isinstance(error, commands.MemberNotFound):
        await ctx.send("Mention a valid user! Example: !unmute @john")
    elif isinstance(error, commands.CommandOnCooldown):
        await ctx.send(f"Wait: {error.retry_after:.1f}s")

@bot.command(name="lock")
@commands.has_permissions(manage_channels=True)
@commands.cooldown(1, 5, commands.BucketType.guild)
async def lock(ctx):
    channel = ctx.channel
    overwrite = channel.overwrites_for(ctx.guild.default_role)
    overwrite.send_messages = False
    await channel.set_permissions(ctx.guild.default_role, overwrite=overwrite)

    embed = discord.Embed(
        title="🔒 Channel Locked",
        description=f"**{channel.mention}** has been locked by {ctx.author.mention}!\n\nOnly administrators can send messages.",
        color=0xED4245,
        timestamp=datetime.datetime.now()
    )
    embed.set_footer(text="Bot-2319 - Lock System")
    await ctx.send(embed=embed)

@lock.error
async def lock_error(ctx, error):
    if isinstance(error, commands.MissingPermissions):
        embed = discord.Embed(
            title="Insufficient Permissions",
            description="You need the **Manage Channels** permission to use this command.",
            color=0xED4245
        )
        await ctx.send(embed=embed, delete_after=5)
    elif isinstance(error, commands.CommandOnCooldown):
        await ctx.send(f"Wait: {error.retry_after:.1f}s")

@bot.command(name="unlock")
@commands.has_permissions(manage_channels=True)
@commands.cooldown(1, 5, commands.BucketType.guild)
async def unlock(ctx):
    channel = ctx.channel
    overwrite = channel.overwrites_for(ctx.guild.default_role)
    overwrite.send_messages = None
    await channel.set_permissions(ctx.guild.default_role, overwrite=overwrite)

    embed = discord.Embed(
        title="🔓 Channel Unlocked",
        description=f"**{channel.mention}** has been unlocked by {ctx.author.mention}!\nEveryone can now send messages.",
        color=0x57F287,
        timestamp=datetime.datetime.now()
    )
    embed.set_footer(text="Bot-2319 - Lock System")
    await ctx.send(embed=embed)

@unlock.error
async def unlock_error(ctx, error):
    if isinstance(error, commands.MissingPermissions):
        embed = discord.Embed(
            title="Insufficient Permissions",
            description="You need the **Manage Channels** permission to use this command.",
            color=0xED4245
        )
        await ctx.send(embed=embed, delete_after=5)
    elif isinstance(error, commands.CommandOnCooldown):
        await ctx.send(f"Wait: {error.retry_after:.1f}s")

@bot.command(name="setup")
@commands.has_permissions(administrator=True)
@commands.cooldown(1, 3, commands.BucketType.guild)
async def setup(ctx, *, setting: str = None):
    if setting is None:
        embed = discord.Embed(
            title="Setup System",
            description="Used to configure the bot settings.",
            color=0x5865F2
        )
        embed.add_field(
            name="Usage",
            value=(
                "To set: !setup <setting> <value>\n"
                "To remove: !setup remove <setting>\n"
                "To show: !setup show\n\n"
                "Available Settings:\n"
                "logchannel, punishedrole, registerchannel, unregisteredrole, staffrole"
            ),
            inline=False
        )
        embed.add_field(
            name="Examples",
            value=(
                "!setup logchannel #log\n"
                "!setup punishedrole @Punished\n"
                "!setup remove unregisteredrole\n"
                "!setup show"
            ),
            inline=False
        )
        await ctx.send(embed=embed)
        return

    if setting.lower() in ["show", "list", "display"]:
        config_data = load_config()
        embed = discord.Embed(
            title="Current Settings",
            color=0x5865F2,
            timestamp=datetime.datetime.now()
        )

        channel_settings = {
            "Log Channel": config_data.get("log_channel_id"),
            "Punished Role": config_data.get("punished_role_id"),
            "Register Channel": config_data.get("register_channel_id"),
            "Unregistered Role": config_data.get("unregistered_role_id"),
            "Register Staff Role": config_data.get("register_staff_role_id")
        }

        text = ""
        for name, value in channel_settings.items():
            if value:
                if "channel" in name.lower() or "log" in name.lower():
                    channel = ctx.guild.get_channel(value)
                    if channel:
                        text += f"**{name}:** {channel.mention}\n"
                    else:
                        text += f"**{name}:** `{value}` (Invalid ID)\n"
                else:
                    role = ctx.guild.get_role(value)
                    if role:
                        text += f"**{name}:** {role.mention}\n"
                    else:
                        text += f"**{name}:** `{value}` (Invalid ID)\n"
            else:
                text += f"**{name}:** `Not set`\n"
        embed.add_field(name="Basic Settings", value=text, inline=False)

        await ctx.send(embed=embed)
        return

    if setting.lower().startswith(("remove", "delete")):
        parts = setting.split(maxsplit=1)
        if len(parts) < 2:
            await ctx.send("Specify which setting to remove! Example: !setup remove unregisteredrole")
            return

        setting_name = parts[1].strip().lower()

        aliases = {
            "logchannel": "log_channel_id",
            "log": "log_channel_id",
            "punishedrole": "punished_role_id",
            "punished": "punished_role_id",
            "registerchannel": "register_channel_id",
            "register": "register_channel_id",
            "unregisteredrole": "unregistered_role_id",
            "unregistered": "unregistered_role_id",
            "staffrole": "register_staff_role_id",
            "staff": "register_staff_role_id"
        }

        if setting_name in aliases:
            key = aliases[setting_name]
            update_config(key, None)
            await ctx.send(f"{setting_name} removed successfully!")
            return

        await ctx.send(f"{setting_name} is not a valid setting! Type !setup to see available settings.")
        return

    parts = setting.split()
    if not parts:
        await ctx.send("Invalid format. Example: !setup logchannel #channel")
        return

    key_part = parts[0]
    value = " ".join(parts[1:]) if len(parts) > 1 else ""

    setting_parts = setting.split(maxsplit=1)
    if len(setting_parts) != 2:
        await ctx.send("Invalid format. Example: !setup logchannel #channel")
        return
    command = setting_parts[0].lower()
    value = setting_parts[1].strip()

    aliases_map = {
        "logchannel": "log_channel_id",
        "log": "log_channel_id",
        "punishedrole": "punished_role_id",
        "punished": "punished_role_id",
        "registerchannel": "register_channel_id",
        "register": "register_channel_id",
        "unregisteredrole": "unregistered_role_id",
        "unregistered": "unregistered_role_id",
        "staffrole": "register_staff_role_id",
        "staff": "register_staff_role_id"
    }

    if command not in aliases_map:
        await ctx.send("Invalid setting. Available: logchannel, punishedrole, registerchannel, unregisteredrole, staffrole")
        return

    key = aliases_map[command]

    if "channel" in command or "log" in command:
        channel = None
        if value.startswith("<#") and value.endswith(">"):
            channel_id = int(value.strip("<#>"))
            channel = ctx.guild.get_channel(channel_id)
        elif value.isdigit():
            channel_id = int(value)
            channel = ctx.guild.get_channel(channel_id)
        else:
            for ch in ctx.guild.channels:
                if value.lower() in ch.name.lower():
                    channel = ch
                    break

        if not channel:
            await ctx.send("No valid channel found! Please enter #channel, channel ID or channel name.")
            return

        update_config(key, channel.id)
        await ctx.send(f"{command} set to {channel.mention}!")
    else:
        role = None
        if value.startswith("<@&") and value.endswith(">"):
            role_id = int(value.strip("<@&>"))
            role = ctx.guild.get_role(role_id)
        elif value.isdigit():
            role_id = int(value)
            role = ctx.guild.get_role(role_id)
        else:
            for r in ctx.guild.roles:
                if value.lower() in r.name.lower():
                    role = r
                    break

        if not role:
            await ctx.send("No valid role found! Please enter @role, role ID or role name.")
            return

        update_config(key, role.id)
        await ctx.send(f"{command} set to {role.mention}!")

@setup.error
async def setup_error(ctx, error):
    if isinstance(error, commands.MissingPermissions):
        await ctx.send("You need Administrator permission to use this command!")
    elif isinstance(error, commands.CommandOnCooldown):
        await ctx.send(f"Wait: {error.retry_after:.1f}s")

bot.run(DISCORD_TOKEN)
