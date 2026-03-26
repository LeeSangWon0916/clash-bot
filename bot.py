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
    
    def do_HEAD(self):
        self.send_response(200)
        self.end_headers()

def run_server():
    server = HTTPServer(('0.0.0.0', 8000), Handler)
    server.serve_forever()

threading.Thread(target=run_server).start()

load_dotenv()
TOKEN = os.environ["DISCORD_TOKEN"]
API_KEY = os.environ["CLASH_API_KEY"]
CHANNEL_ID_A = int(os.environ["CHANNEL_ID_A"]) # 전체 로컬 랭킹용
CHANNEL_ID_B = int(os.environ["CHANNEL_ID_B"]) # 클랜 전용 랭킹용
CLAN_TAG = os.environ["CLAN_TAG"]

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
    
def get_clan_members(clan_tag):
    # 태그에 #이 있으면 URL 인코딩(%23)으로 바꿔줘야 해
    safe_tag = clan_tag.replace("#", "%23")
    url = f"https://api.clashofclans.com/v1/clans/{safe_tag}/members"
    headers = {"Authorization": f"Bearer {API_KEY}"}
    
    try:
        res = requests.get(url, headers=headers)
        if res.status_code == 200:
            # 트로피 순으로 정렬해서 반환
            members = res.json().get("items", [])
            return sorted(members, key=lambda x: x['trophies'], reverse=True)
        return []
    except Exception as e:
        print(f"클랜 API 오류: {e}")
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
                field_name = f"⭐ **{player_name}**"
                field_value = f"```fix\n{rank_str}   {trophy_str}\n```" # [clan_name] 삭제
            else:
                # 일반 스타일
                field_name = f"🔹 `{rank_str}` `{trophy_str}` {player_name}"
                field_value = "\u200b"

            embed.add_field(name=field_name, value=field_value, inline=False)

        embed.set_footer(text="Clash of Clans Ranking System", icon_url=client.user.avatar.url if client.user.avatar else None)
        
        await channel.send(embed=embed)
        await asyncio.sleep(0.8) # 속도 제한 방지

async def daily_task(channel_a, channel_b):
    KST = timezone(timedelta(hours=9))
    while True:
        now_kst = datetime.now(KST)
        target_time = now_kst.replace(hour=22, minute=57, second=0, microsecond=0)

        if now_kst >= target_time:
            target_time += timedelta(days=1)

        wait_seconds = (target_time - now_kst).total_seconds()
        print(f"[예약] 다음 정기 출력까지 {int(wait_seconds)}초 대기")
        await asyncio.sleep(wait_seconds)
        
        players = get_top_players()
        if players:
            await send_ranking_in_chunks(channel_a, players, "Local Ranking 🇰🇷")

        clan_members = get_clan_members(CLAN_TAG)
        if clan_members:
            # 클랜원 랭킹은 순위를 1부터 다시 매겨서 전송
            for idx, m in enumerate(clan_members, 1):
                m['rank'] = idx  # 내부 순위로 덮어쓰기
                # 클랜원 랭킹이니까 clan_name은 우리 클랜으로 고정
                m['clan'] = {'name': '백의'} 
                
            await send_ranking_in_chunks(channel_b, clan_members, "백의 클랜원 트로피 순위 ⭐")

        print(f"[{datetime.now(KST).strftime('%Y-%m-%d %H:%M:%S')}] 모든 랭킹 전송 완료!")
        await asyncio.sleep(60)

@client.event
async def on_ready():
    print(f"Logged in as {client.user}")
    
    try:
        # 두 개의 채널 객체를 각각 가져오기
        channel_a = await client.fetch_channel(CHANNEL_ID_A)
        channel_b = await client.fetch_channel(CHANNEL_ID_B)
        
        print(f"채널 연결 성공: {channel_a.name}, {channel_b.name}")
        
        # daily_task에 두 채널을 모두 전달
        asyncio.create_task(daily_task(channel_a, channel_b))
        
        print("모든 자동화 작업(멀티 채널)이 시작되었습니다.")
        
    except discord.errors.Forbidden:
        print("❌ 권한 오류: 봇이 채널 중 하나에 접근할 권한이 없습니다.")
    except Exception as e:
        print(f"❌ 오류 발생: {e}")

client.run(TOKEN)