import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
import discord
from discord.ui import Button, View
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

class RankingView(View):
    def __init__(self, chunks, title):
        super().__init__(timeout=60) # 60초 후 버튼 비활성화
        self.chunks = chunks
        self.title = title
        self.current_page = 0

    def create_embed(self):
        chunk = self.chunks[self.current_page]
        embed = discord.Embed(
            title=f"🏆 {self.title}",
            description="\n".join(chunk),
            color=0x1ABC9C
        )
        # 하단에 "1/2" 같은 페이지 표시 추가
        embed.set_footer(text=f"Page {self.current_page + 1}/{len(self.chunks)}")
        return embed

    @discord.ui.button(label="◀", style=discord.ButtonStyle.gray)
    async def prev_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.current_page > 0:
            self.current_page -= 1
            await interaction.response.edit_message(embed=self.create_embed(), view=self)
        else:
            await interaction.response.send_message("첫 페이지입니다.", ephemeral=True)

    @discord.ui.button(label="▶", style=discord.ButtonStyle.gray)
    async def next_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.current_page < len(self.chunks) - 1:
            self.current_page += 1
            await interaction.response.edit_message(embed=self.create_embed(), view=self)
        else:
            await interaction.response.send_message("마지막 페이지입니다.", ephemeral=True)

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

    # Koyeb 환경 변수에 넣은 프록시 주소 가져오기
    proxy_url = os.environ.get("PROXY_URL")
    proxies = {
        "http": proxy_url,
        "https": proxy_url,
    }

    try:
        # 프록시를 통해 요청 (timeout은 넉넉히 15초)
        res = requests.get(url, headers=headers, proxies=proxies, timeout=15)
        print(f"[API 호출 상태 코드] {res.status_code}")
        
        if res.status_code == 200:
            return res.json().get("items", [])
        else:
            print(f"[API 오류] {res.text}")
            return []
    except Exception as e:
        print(f"프록시 연결 실패: {e}")
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
'''async def send_ranking_in_chunks(channel, players, title, is_clan_channel=False):
    if not players:
        return

    chunk_size = 25
    for i in range(0, len(players), chunk_size):
        chunk = players[i : i + chunk_size]
        
        ranking_lines = []
        for p in chunk:
            player_name = p['name']
            rank_val = p['rank']
            trophy_val = p['trophies']
            clan_name = p.get("clan", {}).get("name", "")
            
            display_text = f"{player_name} ({trophy_val})"
            
            if ("백의" in clan_name):
                line = f"{rank_val}. [**{display_text} (백의)**](https://clashofclans.com)"
            elif ("적의" in clan_name):
                # 적의도 rank_val을 넣어주는 게 줄 맞춤에 좋을 거야!
                line = f"{rank_val}. [**{display_text} (적의)**](https://clashofclans.com)"
            else:
                line = f"{rank_val}. {player_name} ({trophy_val})"
            
            ranking_lines.append(line)

        # ⭐ 핵심: 박스 너비를 강제로 고정하기 위한 투명 가이드라인
        # 일반 공백(' ')은 디스코드가 무시하므로, 특수 공백 문자를 사용해
        width_guide = "_" * 45 # 또는 특수공백 60개
        full_description = "\n".join(ranking_lines) + f"\n{width_guide}"

        embed = discord.Embed(
            title=f"🏆 {title}",
            description=full_description,
            color=0x1ABC9C,
            timestamp=datetime.now()
        )

        await channel.send(embed=embed)
        await asyncio.sleep(0.8)'''

# 랭킹 명령어를 처리하는 함수 수정
async def send_ranking_with_buttons(channel, players, title):
    chunk_size = 25
    all_lines = []
    
    # 1. 일단 모든 플레이어 줄을 생성
    for p in players:
        player_name = p['name']
        rank_val = p['rank']
        trophy_val = p['trophies']
        clan_name = p.get("clan", {}).get("name", "")
        
        display_text = f"{player_name} ({trophy_val})"
            
        if ("백의" in clan_name):
            line = f"{rank_val}. [**{display_text} (백의)**](https://clashofclans.com)"
        elif ("적의" in clan_name):
                # 적의도 rank_val을 넣어주는 게 줄 맞춤에 좋을 거야!
            line = f"{rank_val}. [**{display_text} (적의)**](https://clashofclans.com)"
        else:
            line = f"{rank_val}. {player_name} ({trophy_val})"
            
        all_lines.append(line)

    # 2. 25명씩 묶음(Chunk) 생성
    chunks = [all_lines[i : i + chunk_size] for i in range(0, len(all_lines), chunk_size)]
    
    # 3. 버튼 뷰 생성 및 전송
    view = RankingView(chunks, title)
    await channel.send(embed=view.create_embed(), view=view)

async def daily_task(channel_a, channel_b):
    KST = timezone(timedelta(hours=9))
    while True:
        now_kst = datetime.now(KST)
        target_time = now_kst.replace(hour=10, minute=55, second=0, microsecond=0)

        if now_kst >= target_time:
            target_time += timedelta(days=1)

        wait_seconds = (target_time - now_kst).total_seconds()
        print(f"[예약] 다음 정기 출력까지 {int(wait_seconds)}초 대기")
        await asyncio.sleep(wait_seconds)
        
        players = get_top_players()
        if players:
            await send_ranking_with_buttons(channel_a, players, "Local Ranking 🇰🇷")

        '''clan_members = get_clan_members(CLAN_TAG)
        if clan_members:
            # 클랜원 랭킹은 순위를 1부터 다시 매겨서 전송
            for idx, m in enumerate(clan_members, 1):
                m['rank'] = idx  # 내부 순위로 덮어쓰기
                # 클랜원 랭킹이니까 clan_name은 우리 클랜으로 고정
                m['clan'] = {'name': '백의'} 
                
            await send_ranking_in_chunks(channel_b, clan_members, "백의 클랜원 트로피 순위 ⭐")'''

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

@client.event
async def on_message(message):
    # 봇 자신이 쓴 메시지에는 반응하지 않게 방어
    if message.author == client.user:
        return

    # 채팅창에 !test 라고 치면 실행
    if message.content == "!test":
        print(f"[{message.author}]님이 테스트 명령어를 사용함")
        
        # 전체 로컬 랭킹 상위 10명만 테스트로 출력해보기
        players = get_top_players()
        if players:
            print("조건문 안에 들어옴.")
            # message.channel은 명령어를 친 바로 그 채널을 의미해
            await send_ranking_with_buttons(message.channel, players[:], "랭킹 디자인 테스트")
        
        await message.channel.send("✅ 테스트 출력이 완료되었습니다!")

client.run(TOKEN)