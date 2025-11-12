import os
import asyncio
import logging
from typing import Dict, Optional, List

import requests
from bs4 import BeautifulSoup

import aiohttp
import discord
from discord.ext import commands, tasks
from dotenv import load_dotenv

# ----------------- Setup -----------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)

load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")

# ONE channel id only
CHANNEL_ID = 1153263160556531762 

# Discord bot (one instance only)
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

# OpenRouter config
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1/chat/completions"
OPENROUTER_MODEL = "mistralai/mistral-7b-instruct"

# HTTP stuff
USER_AGENT = "Mozilla/5.0 (DiscordBot; subreddit watcher by @you)"
BROWSER_HEADERS = {"User-Agent": USER_AGENT}

# aiohttp session holder
session: Optional[aiohttp.ClientSession] = None

# ----------------- Fun commands -----------------
@bot.command()
async def ping(ctx): await ctx.send("Boop!")

@bot.command()
async def copper(ctx): await ctx.send("haha get scammed!")

@bot.command()
async def sus(ctx): await ctx.send("your a sussy baka and you know that!")

@bot.command()
async def name(ctx): await ctx.send("hyperion!")

@bot.command()
async def Language(ctx):
    await ctx.send("Beginner's Latin Book: https://archive.org/details/beginnerslatinb01collgoog/page/n48/mode/2up?view=theater")

@bot.command()
async def hf(ctx): await ctx.send("Click here to go the Hypixel Forums: https://hypixel.net/")

@bot.command()
async def Latin(ctx):
    await ctx.send("Latin Dictionary Online: https://web.archive.org/web/20231211013956/https://personal.math.ubc.ca/~cass/frivs/latin/latin-dict-full.html")

@bot.command()
async def t(ctx): await ctx.send("https://docs.python.org/3.13/tutorial/")

# ----------------- Cuneiform / CipherB -----------------
cuneiform_map = {
    "a":"𒀀","b":"𒁀","c":"𒅝","d":"𒁲","e":"𒂊","f":"𒈿","g":"𒈀","h":"𒈩","i":"𒈿",
    "j":"𐥎","k":"𒋒","l":"𒉻","m":"𒊬","n":"𒋁","o":"Ω","p":"𒁉","q":"𐥒","r":"𒊑",
    "s":"𒊓","t":"𒌾","u":"𒌋","v":"𒇙","w":"𒈿","x":"X","y":"𒇆","z":"ξ"
}
def translate_to_cuneiform(text): return ''.join(cuneiform_map.get(ch, ch) for ch in text.lower())
@bot.command()
async def cuneiform(ctx, *, text): await ctx.send(translate_to_cuneiform(text))

cipherB_map = {
    "a":"B","b":"V","c":"G","d":"Q","e":"C","f":"E","g":"A","h":"Z","i":"N","j":"O",
    "k":"M","l":"X","m":"R","n":"L","o":"P","p":"J","q":"U","r":"H","s":"K","t":"F",
    "u":"W","v":"I","w":"D","x":"X","y":"T","z":"Y"
}
def translate_to_cipherB(text): return ''.join(cipherB_map.get(ch, ch) for ch in text.lower())
@bot.command()
async def cipherB(ctx, *, text): await ctx.send(translate_to_cipherB(text))

# ----------------- OpenRouter ask -----------------
@bot.command()
async def ask(ctx, *, question):
    await ctx.typing()
    try:
        headers = {
            "Authorization": f"Bearer {OPENROUTER_API_KEY}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://mydiscordbot.local",
            "X-Title": "Discord Bot Example",
        }
        data = {"model": OPENROUTER_MODEL, "messages": [{"role": "user", "content": question}]}
        resp = requests.post(OPENROUTER_BASE_URL, headers=headers, json=data, timeout=30)
        resp.raise_for_status()
        result = resp.json()
        message = result["choices"][0]["message"]["content"]
        await ctx.send(message[:1997] + "..." if len(message) > 2000 else message)
    except Exception as e:
        await ctx.send(f"Error: {e}")


SUBREDDITS: List[str] = ["AncientCivilizations", "fountainpens","Asmongold","eu4","DoomerCircleJerk"]
CHECK_INTERVAL_MIN = 30
last_seen_by_sub: Dict[str, Optional[str]] = {sr: None for sr in SUBREDDITS}

async def fetch_latest_post(subreddit: str) -> Optional[dict]:
    """Return newest post (dict) or None."""
    assert session is not None, "HTTP session not initialized"
    url = f"https://www.reddit.com/r/{subreddit}/new.json"
    params = {"limit": 1}
    try:
        async with session.get(url, headers=BROWSER_HEADERS, params=params, timeout=20) as resp:
            if resp.status == 429:
                retry = int(resp.headers.get("Retry-After", "5"))
                logging.warning(f"[{subreddit}] 429; sleeping {retry}s")
                await asyncio.sleep(retry)
                return None
            resp.raise_for_status()
            data = await resp.json()
            kids = data.get("data", {}).get("children", [])
            if not kids:
                return None
            return kids[0]["data"]
    except Exception as e:
        logging.error(f"[{subreddit}] fetch error: {e}")
        return None

def format_post(subreddit: str, post: dict) -> str:
    title = post.get("title", "(no title)")
    permalink = post.get("permalink", "")
    url = f"https://www.reddit.com{permalink}" if permalink.startswith("/") else permalink
    author = post.get("author", "unknown")
    return f"🔔 **r/{subreddit}** — **{title}**\n👤 u/{author}\n🔗 {url}"

@tasks.loop(minutes=CHECK_INTERVAL_MIN)
async def reddit_loop():
    channel = bot.get_channel(CHANNEL_ID)
    if channel is None:
        logging.error(f"Channel {CHANNEL_ID} not found.")
        return
    for i, sr in enumerate(SUBREDDITS):
        if i:  # polite stagger
            await asyncio.sleep(1.5)
        post = await fetch_latest_post(sr)
        if not post:
            continue
        pid = post.get("id")
        if not pid:
            continue
        if last_seen_by_sub.get(sr) != pid:
            await channel.send(format_post(sr, post))
            last_seen_by_sub[sr] = pid


hypixel_url = "https://hypixel.net/forums/off-topic.2/"
last_hypixel_thread: Optional[str] = None

def _sync_fetch_latest_hypixel() -> Optional[tuple[str, str]]:
    r = requests.get(hypixel_url, headers=BROWSER_HEADERS, timeout=20)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")
    a = soup.select_one("div.structItem-title a")
    if not a:
        return None
    title = a.text.strip()
    link = f"https://hypixel.net{a['href']}"
    return (title, link)

async def fetch_latest_hypixel() -> Optional[str]:
    try:
        result = await asyncio.to_thread(_sync_fetch_latest_hypixel)
        if not result:
            return None
        title, link = result
        return f"{title}\n{link}"
    except Exception as e:
        logging.error(f"Hypixel scrape error: {e}")
        return None

@tasks.loop(hours=1)
async def hypixel_loop():
    global last_hypixel_thread
    channel = bot.get_channel(CHANNEL_ID)
    if channel is None:
        logging.error(f"Channel {CHANNEL_ID} not found.")
        return
    latest = await fetch_latest_hypixel()
    if not latest:
        return
    if latest != last_hypixel_thread:
        await channel.send(f"💬 **New Off Topic Thread on Hypixel:** {latest}")
        last_hypixel_thread = latest


@bot.event
async def on_ready():
    global session
    logging.info(f"✅ Logged in as {bot.user}")
    session = aiohttp.ClientSession()
    reddit_loop.start()
    hypixel_loop.start()
    logging.info("🔄 Background loops started.")


@bot.event
async def on_disconnect():
    if session and not session.closed:
        await session.close()


bot.run(TOKEN)




