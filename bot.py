import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
import discord
import requests
import asyncio
import os
from dotenv import load_dotenv
from datetime import datetime, timedelta, timezone

# --- 서버 및 설정 부분 (동일) ---
class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"OK")

def run_server():
    server = HTTPServer(('0.0.0.0', 8000), Handler)
    server.serve_forever()

threading.Thread(target=run_server).start()

load_dotenv()
TOKEN = os.environ["DISCORD_TOKEN"]
API_KEY = os.environ["CLASH_API_KEY"]
CHANNEL_ID = int(os.environ["CHANNEL_ID"])

intents = discord.Intents.default()
intents.message_content = True
client = discord.Client(intents=intents)

# --- 1. get_top_players: '글자'가 아니라 '리스트'를 반환하도록 수정 ---
def get_top_players():
    url = "https://api.clashofclans.com/v1/locations/32000216/rankings/players"
    headers = {"Authorization": f"Bearer {API_KEY}"}
    
    try:
        res = requests.get(url, headers=headers)
        if res.status_code != 200:
            print("API 실패:", res.text)
            return []  # 에러 시 빈 리스트 반환
        
        data = res.json()
        return data.get("items", [])  # 순수 리스트만 반환
    except Exception as e:
        print(f"네트워크 오류: {e}")
        return []

# --- 2. send_ranking_in_chunks: @client.event 데코레이터 삭제 (일반 함수임) ---
async def send_ranking_in_chunks(channel, players, title):
    if not players:
        return
    
    chunk_size = 50
    for i in range(0, len(players), chunk_size):
        chunk = players[i : i + chunk_size]
        msg = f"📊 **{title} ({i+1}~{i+len(chunk)})**\n"
        
        for p in chunk:
            line = f'{p["rank"]}. {p["name"]} - {p["trophies"]}🏆\n'
            if len(msg) + len(line) > 1950:
                await channel.send(msg)
                msg = "" 
            msg += line
        
        if msg:
            await channel.send(msg)
        await asyncio.sleep(1)

# --- 3. Task 함수들 수정 ---
async def daily_task(channel):
    KST = timezone(timedelta(hours=9))
    while True:
        now_kst = datetime.now(KST)
        # 시간 설정을 다시 13:58로 맞추거나 테스트용 시간으로 유지
        target_time = now_kst.replace(hour=12, minute=20, second=0, microsecond=0)

        if now_kst >= target_time:
            target_time += timedelta(days=1)

        wait_seconds = (target_time - now_kst).total_seconds()
        print(f"[예약] 다음 정기 출력까지 {int(wait_seconds)}초 대기")
        
        await asyncio.sleep(wait_seconds)
        
        players = get_top_players()
        if players:
            await send_ranking_in_chunks(channel, players, "정기 랭킹 알림 (13:58)")
            print("정기 전송 완료")
        
        await asyncio.sleep(60)

async def minute_task(channel):
    while True:
        try:
            players = get_top_players()
            if players:
                now_str = datetime.now().strftime('%H:%M:%S')
                # 테스트용이니 상위 10명만 보내려면 [:10]
                await send_ranking_in_chunks(channel, players[:10], "1분 단위 체크")
                print(f"{now_str} 1분 체크 전송 완료")
        except Exception as e:
            print(f"1분 체크 오류: {e}")
            
        await asyncio.sleep(60)

@client.event
async def on_ready():
    print(f"Logged in as {client.user}")
    channel = await client.fetch_channel(CHANNEL_ID)
    asyncio.create_task(daily_task(channel))
    asyncio.create_task(minute_task(channel))
    print("모든 자동화 작업이 시작되었습니다.")

client.run(TOKEN)