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
from datetime import datetime, timedelta

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

    while True:
        now = datetime.now()
        # 목표 시간 설정 (오늘 13시 58분 00초)
        target_time = now.replace(hour=11, minute=57, second=0, microsecond=0)

        # 만약 이미 오늘 13시 58분이 지났다면, 내일 13시 58분으로 설정
        if now >= target_time:
            target_time += timedelta(days=1)

        # 다음 목표 시간까지 대기해야 할 초(seconds) 계산
        wait_seconds = (target_time - now).total_seconds()
        print(f"다음 출력 시간까지 {wait_seconds}초 대기합니다. (목표: {target_time})")

        # 목표 시간까지 대기
        await asyncio.sleep(wait_seconds)

        # 랭킹 출력 실행
        try:
            msg = get_top_players()
            await channel.send(msg)
            print(f"[{datetime.now()}] 랭킹 정보 전송 완료")
        except Exception as e:
            print("전송 중 오류 발생:", e)

        # 전송 후 바로 다시 루프가 돌면 1초 차이로 중복 전송될 수 있으니 잠시 대기
        await asyncio.sleep(60)

client.run(TOKEN)