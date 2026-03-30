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
    def __init__(self, players_data, title, fetch_func):
        super().__init__(timeout=None)
        self.players_data = players_data # 현재 데이터
        self.title = title
        self.fetch_func = fetch_func     # 데이터를 새로 가져올 함수
        self.current_page = 0
        self.chunk_size = 100
        self.update_chunks()

    def update_chunks(self):
        # 플레이어 데이터를 100명씩 나누는 작업
        all_lines = []
        for p in self.players_data:
            player_name = p['name']
            rank_val = p['rank']
            trophy_val = p['trophies']
            clan_name = p.get("clan", {}).get("name", "")
            
            display_text = f"{player_name} ({trophy_val})"
            
            if "백의" in clan_name:
                line = f"{rank_val}. [**{display_text} (백의)**](https://clashofclans.com)"
            elif "적의" in clan_name:
                line = f"{rank_val}. [**{display_text} (적의)**](https://clashofclans.com)"
            else:
                line = f"{rank_val}. {player_name} ({trophy_val})"
            all_lines.append(line)
        
        self.chunks = [all_lines[i : i + self.chunk_size] for i in range(0, len(all_lines), self.chunk_size)]

    def create_embed(self):
        chunk = self.chunks[self.current_page]

        embed = discord.Embed(
            title=self.title,
            description="\n".join(chunk),
            color=0x1ABC9C,
            timestamp=datetime.now()
        )
        embed.set_footer(text=f"Page {self.current_page + 1}/{len(self.chunks)}")
        return embed

    @discord.ui.button(label="◀", style=discord.ButtonStyle.primary)
    async def prev_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.current_page = (self.current_page - 1) % len(self.chunks)
        await interaction.response.edit_message(embed=self.create_embed(), view=self)

    @discord.ui.button(label="▶", style=discord.ButtonStyle.primary)
    async def next_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.current_page = (self.current_page + 1) % len(self.chunks)
        await interaction.response.edit_message(embed=self.create_embed(), view=self)

    # 🔄 새로고침 버튼 추가 (초록색)
    '''@discord.ui.button(label="🔄", style=discord.ButtonStyle.secondary)
    async def refresh_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            # 1. 상호작용 지연 처리 (3초 타임아웃 방지)
            # 'defer_update'가 아니라 'defer'야!
            await interaction.response.defer()
            
            # 2. 데이터 새로 가져오기
            # 만약 fetch_func가 일반 함수(def)라면 아래처럼 실행
            # 만약 비동기 함수(async def)라면 그냥 await self.fetch_func()
            if asyncio.iscoroutinefunction(self.fetch_func):
                new_players = await self.fetch_func()
            else:
                loop = asyncio.get_event_loop()
                new_players = await loop.run_in_executor(None, self.fetch_func)
            
            if new_players:
                self.players_data = new_players
                self.update_chunks() # 데이터 다시 쪼개기
                
                # 3. 메시지 업데이트
                await interaction.edit_original_response(embed=self.create_embed(), view=self)
            else:
                await interaction.followup.send("데이터를 가져오는 데 실패했습니다.", ephemeral=True)
                
        except Exception as e:
            print(f"새로고침 중 에러 발생: {e}")
            # 에러 발생 시 사용자에게 알림
            await interaction.followup.send("새로고침 중 문제가 발생했습니다.", ephemeral=True)'''

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

# 국내 랭킹 명령어를 처리하는 함수
async def send_ranking_with_buttons(channel, players, title):
    chunk_size = 100
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
    
    # 3. 버튼 뷰 생성 및 전송
    view = RankingView(players, title, get_top_players)
    await channel.send(embed=view.create_embed(), view=view)

async def daily_task(channel_a, channel_b):
    KST = timezone(timedelta(hours=9))

    while True:
        now_kst = datetime.now(KST)
        target_time = now_kst.replace(hour=14, minute=0, second=0, microsecond=0)

        if now_kst >= target_time:
            target_time += timedelta(days=1)

        wait_seconds = (target_time - now_kst).total_seconds()
        print(f"[예약] 다음 정기 출력까지 {int(wait_seconds)}초 대기")
        await asyncio.sleep(wait_seconds)

        now_kst = datetime.now(KST)
        date_str = now_kst.strftime("%y.%m.%d")
        
        players = get_top_players()
        if players:
            await send_ranking_with_buttons(channel_a, players, f"Korea Ranking ({date_str})")

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
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
        players = get_top_players()
        if players:
            # message.channel은 명령어를 친 바로 그 채널을 의미해
            await send_ranking_with_buttons(
                message.channel, 
                players[:], 
                f"랭킹 디자인 테스트 ({now_str})"
            )
        
        await message.channel.send("✅ 테스트 출력이 완료되었습니다!")

client.run(TOKEN)