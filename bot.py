import discord
import requests
import asyncio
import os

TOKEN = os.environ["DISCORD_TOKEN"]
API_KEY = os.environ["CLASH_API_KEY"]
CHANNEL_ID = int(os.environ["CHANNEL_ID"])

intents = discord.Intents.default()
intents.message_content = True

client = discord.Client(intents=intents)

def get_top_players():
    url = "https://api.clashofclans.com/v1/locations/32000216/rankings/players"
    
    headers = {
        "Authorization": f"Bearer {API_KEY}"
    }
    
    res = requests.get(url, headers=headers)

    if res.status_code != 200:
        print("API 실패:", res.text)
        return "API 호출 실패"

    data = res.json()

    if "items" not in data:
        print("응답 이상:", data)
        return "데이터 없음"

    players = data["items"][:10]
    
    msg = "🔥 Top 10 Players 🔥\n"
    
    for p in players:
        msg += f'{p["rank"]}. {p["name"]} - {p["trophies"]}🏆\n'
    
    return msg


@client.event
async def on_ready():
    print(f"Logged in as {client.user}")

    channel = await client.fetch_channel(CHANNEL_ID)

    while True:
        try:
            msg = get_top_players()
            await channel.send(msg)
        except Exception as e:
            print("Error:", e)
        
        await asyncio.sleep(3600)


client.run(TOKEN)