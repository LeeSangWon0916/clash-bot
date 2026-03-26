import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
import discord
import requests
import asyncio
import os
from dotenv import load_dotenv
from datetime import datetime, timedelta, timezone

# --- 서버 설정 (Koyeb 유지용) ---
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

def get_top_players():
    url = "https://api.clashofclans.com/v1/locations/32000216/rankings/players"
    headers = {"Authorization": f"Bearer {API_KEY}"}
    try:
        res = requests.get(url, headers=headers)
        if res.status_code == 200:
            return res.json().get("items", [])
        return []
    except Exception as e:
        print(f"API 오류: {e}")
        return []

# --- 임베드 및 하이라이트 적용 함수 ---
async def send_ranking_in_chunks(channel, players, title):
    if not players:
        return

    # 한 카드(Embed)당 10명씩 담는 것이 가장 깔끔함
    chunk_size = 25
    for i in range(0, len(players), chunk_size):
        chunk = players[i : i + chunk_size]
        
        embed = discord.Embed(
            title=f"🏆 {title}",
            description=f"순위 {i+1}위 ~ {i+len(chunk)}위",
            color=0x1ABC9C, # 청록색 테두리
            timestamp=datetime.now()
        )

        for p in chunk:
            clan_name = p.get("clan", {}).get("name", "N/A")
            player_name = p['name']
            rank_str = f"{p['rank']:03d}"
            trophy_str = f"{p['trophies']}"
            
            if "백의" in clan_name:
                # 노란색 형광펜 스타일 (fix 문법)
                # 이름은 위에 굵게 표시하고, 아래 정보를 노란색 박스에 넣음
                field_name = f"⭐ **{player_name} (백의)**"
                field_value = f"```fix\n{rank_str}  {trophy_str}  [{clan_name}]\n```"
            else:
                # 일반 스타일
                field_name = f"🔹 `{rank_str}` `{trophy_str}` {player_name}"
                field_value = f"┕ `[{clan_name}]`"

            embed.add_field(name=field_name, value=field_value, inline=False)

        embed.set_footer(text="Clash of Clans Ranking System", icon_url=client.user.avatar.url if client.user.avatar else None)
        
        await channel.send(embed=embed)
        await asyncio.sleep(0.8) # 속도 제한 방지

async def daily_task(channel):
    KST = timezone(timedelta(hours=9))
    while True:
        now_kst = datetime.now(KST)
        target_time = now_kst.replace(hour=14, minute=13, second=0, microsecond=0)

        if now_kst >= target_time:
            target_time += timedelta(days=1)

        wait_seconds = (target_time - now_kst).total_seconds()
        print(f"[예약] 다음 정기 출력까지 {int(wait_seconds)}초 대기")
        await asyncio.sleep(wait_seconds)
        
        players = get_top_players()
        if players:
            await send_ranking_in_chunks(channel, players, "Local Ranking 🇰🇷")

        print(f"[{datetime.now(KST).strftime('%Y-%m-%d %H:%M:%S')}] 모든 랭킹 전송 완료!")
        await asyncio.sleep(60)

'''async def minute_task(channel):
    while True:
        try:
            players = get_top_players()
            if players:
                # 테스트 시 상위 10명만 카드로 전송
                await send_ranking_in_chunks(channel, players[:10], "1분 단위 체크")
        except Exception as e:
            print(f"1분 체크 오류: {e}")
        await asyncio.sleep(60)'''

@client.event
async def on_ready():
    print(f"Logged in as {client.user}")
    channel = await client.fetch_channel(CHANNEL_ID)
    asyncio.create_task(daily_task(channel))
    # asyncio.create_task(minute_task(channel))
    print("모든 자동화 작업이 시작되었습니다.")

client.run(TOKEN)