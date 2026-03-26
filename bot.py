import threading
from http.server import HTTPServer, BaseHTTPRequestHandler

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"OK")

def run_server():
    server = HTTPServer(('0.0.0.0', 8000), Handler)
    server.serve_forever()

# 🔥 이 줄 추가
threading.Thread(target=run_server).start()

import discord
import requests
import asyncio
import os
from dotenv import load_dotenv
from datetime import datetime, timedelta, timezone

load_dotenv()

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

    players = data["items"][:]
    
    msg = "🔥 Top 10 Players 🔥\n"
    
    for p in players:
        msg += f'{p["rank"]}. {p["name"]} - {p["trophies"]}🏆\n'
    
    return msg


@client.event
async def on_ready():
    print(f"Logged in as {client.user}")
    channel = await client.fetch_channel(CHANNEL_ID)

    # 한국 시간대 정의 (UTC+9)
    KST = timezone(timedelta(hours=9))

    while True:
        # 현재 한국 시간 가져오기
        now_kst = datetime.now(KST)
        
        # 오늘 오후 1시 58분(KST) 설정
        target_time = now_kst.replace(hour=12, minute=0, second=0, microsecond=0)

        # 이미 지났으면 내일로 설정
        if now_kst >= target_time:
            target_time += timedelta(days=1)

        wait_seconds = (target_time - now_kst).total_seconds()
        print(f"다음 출력까지 {int(wait_seconds)}초 대기 (목표: {target_time.strftime('%Y-%m-%d %H:%M:%S')} KST)")

        await asyncio.sleep(wait_seconds)

client.run(TOKEN)