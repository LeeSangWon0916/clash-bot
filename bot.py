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
async def daily_task(channel):
    """매일 13시 58분에 실행되는 작업"""
    KST = timezone(timedelta(hours=9))
    while True:
        now_kst = datetime.now(KST)
        target_time = now_kst.replace(hour=12, minute=5, second=0, microsecond=0)

        if now_kst >= target_time:
            target_time += timedelta(days=1)

        wait_seconds = (target_time - now_kst).total_seconds()
        print(f"[예약] 다음 13:58 출력까지 {int(wait_seconds)}초 대기")
        
        await asyncio.sleep(wait_seconds)
        
        try:
            msg = get_top_players()
            await channel.send(f"🔔 **정기 랭킹 알림 (13:58)**\n{msg}")
            print("13:58 정기 전송 완료")
        except Exception as e:
            print(f"정기 전송 오류: {e}")
        
        await asyncio.sleep(60) # 중복 실행 방지

async def minute_task(channel):
    """1분마다 실행되는 체크용 작업"""
    while True:
        try:
            msg = get_top_players()
            now_str = datetime.now().strftime('%H:%M:%S')
            await channel.send(f"⏱️ **1분 단위 체크 ({now_str})**\n{msg}")
            print(f"{now_str} 1분 체크 전송 완료")
        except Exception as e:
            print(f"1분 체크 오류: {e}")
            
        await asyncio.sleep(60)

@client.event
async def on_ready():
    print(f"Logged in as {client.user}")
    channel = await client.fetch_channel(CHANNEL_ID)

    # 두 개의 작업을 동시에 시작
    asyncio.create_task(daily_task(channel))
    asyncio.create_task(minute_task(channel))
    print("모든 자동화 작업이 시작되었습니다.")

client.run(TOKEN)