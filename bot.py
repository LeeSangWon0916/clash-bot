import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
import discord
from discord.ui import Button, View
import requests
import asyncio
import aiohttp
import os
import io
from dotenv import load_dotenv
from datetime import datetime, timedelta, timezone
import pandas as pd
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import json
from gspread_formatting import set_column_width as g_set_width

# --- 서버 설정 (Koyeb 유지용) ---
class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"OK")
    
    def do_HEAD(self):
        self.send_response(200)
        self.end_headers()

# 1. 구글 시트 버튼 (링크 연결형)
class GoogleSheetButton(discord.ui.Button):
    def __init__(self, players_data):
        super().__init__(label="Google Sheet", style=discord.ButtonStyle.success)
        self.players_data = players_data

    async def callback(self, interaction: discord.Interaction):

        try:
            await interaction.response.defer(ephemeral=True)
        except discord.errors.NotFound:
            # 이미 만료된 상호작용이라면 무시하거나 로그만 남김
            print("상호작용이 만료되어 defer를 할 수 없습니다.")
            return
        
        status_msg = await interaction.followup.send(
            "⏳ 구글 스프레드시트를 생성 중입니다. 잠시만 기다려 주세요...", 
            ephemeral=True
        )
        
        try:
            # 환경 변수 및 인증 로직
            creds_json_str = os.environ.get("CREDENTIALS_JSON")
            creds_info = json.loads(creds_json_str)
            if "private_key" in creds_info:
                creds_info["private_key"] = creds_info["private_key"].replace("\\n", "\n")
            
            scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
            creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_info, scope)
            client = gspread.authorize(creds)

            # 시트 열기 (URL 방식이 가장 확실해)
            sheet_url = "https://docs.google.com/spreadsheets/d/1ZXTm4gkUCoHlpsyk42h58bbGRaicRMwVPaa-90IKAYg/edit?hl=ko"
            doc = client.open_by_url(sheet_url)
            sheet = doc.get_worksheet(0)

            # 2. 헤더 설정 (순서 변경: Ranking -> Trophies)
            headers = ["Name", "Tag", "Clan", "Clan Tag", "Global Ranking", "Trophies"]
            rows = [headers]

            # 💡 [대체] 이미 players_data에 담겨있는 값을 꺼내 쓰기만 함
            for p in self.players_data:
                rows.append([
                    p['name'], 
                    p['tag'], 
                    p.get('clan', {}).get('name', 'N/A'),
                    p.get('clan_tag', 'N/A'),
                    p.get('global_rank', '0'), # 미리 수집된 값 사용
                    p['trophies']
                ])

            # 출력할 시트 주소
            sheet_url = "https://docs.google.com/spreadsheets/d/1ZXTm4gkUCoHlpsyk42h58bbGRaicRMwVPaa-90IKAYg"

            # ---------------------------------------------------------
            # 🔄 디자인 유지형 데이터 업데이트
            # ---------------------------------------------------------
            
            # 1. 기존 데이터 "값"만 지우기 (디자인은 보존됨)
            # A1부터 F열의 아주 먼 곳(예: 500행)까지 값만 삭제
            sheet.batch_clear(["A1:F500"]) 

            # 2. 새 데이터 넣기
            # 'RAW' 모드로 넣어야 수식이나 서식이 깨지지 않고 값만 들어감
            sheet.update('A1', rows, value_input_option='RAW')

            await status_msg.edit(
                content=f"📗 구글 스프레드시트 최신화가 완료되었습니다!\n🔗 [실시간 랭킹 확인하기]({sheet_url})"
            )

        except Exception as e:
            # ❗ 가장 바깥쪽 예외 처리: 인증 실패, 시트 접근 불가 등 대비
            print(f"❌ Google Sheet Error: {e}")
            await interaction.followup.send(f"❌ 시트 업데이트 중 오류 발생: {e}", ephemeral=True)


# 2. 엑셀 다운로드 버튼 (본인만 볼 수 있게 전송)
class DownloadButton(discord.ui.Button):
    def __init__(self, players_data):
        super().__init__(label="Download", style=discord.ButtonStyle.secondary)
        self.players_data = players_data

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        excel_file = await self.generate_excel() 
        await interaction.followup.send(
            "✨ 엑셀 리포트 생성이 완료되었습니다.", 
            file=excel_file, 
            ephemeral=True
        )

    async def generate_excel(self):
        # 1. 헤더 순서 변경 (Global Ranking을 Trophies 앞으로)
        headers_list = ["Name", "Tag", "Clan", "Clan Tag", "Global Ranking", "Trophies"]
        rows = []
        api_headers = {"Authorization": f"Bearer {API_KEY}"}
        proxy_url = os.environ.get("PROXY_URL")

        async with aiohttp.ClientSession() as session:
            for p in self.players_data:
                player_tag = p['tag']
                safe_p_tag = player_tag.replace("#", "%23")
                player_url = f"https://api.clashofclans.com/v1/players/{safe_p_tag}"
                
                global_rank = "N/A"
                try:
                    async with session.get(player_url, headers=api_headers, proxy=proxy_url, timeout=10) as res:
                        if res.status == 200:
                            data = await res.json()
                            legend_stats = data.get("legendStatistics", {})
                            global_rank = legend_stats.get("currentSeason", {}).get("rank", "N/A")
                except: pass

                # 2. 데이터 행 추가 순서 변경 (global_rank를 trophies 앞으로)
                rows.append([
                    p['name'], p['tag'], 
                    p.get('clan', {}).get('name', 'N/A'),
                    p.get('clan_tag', 'N/A'),
                    global_rank, p['trophies']
                ])
                await asyncio.sleep(0.01)

        df = pd.DataFrame(rows, columns=headers_list)
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, index=False, sheet_name='Ranking')
            workbook = writer.book
            worksheet = writer.sheets['Ranking']

            header_fill = PatternFill(start_color="366092", end_color="366092", fill_type="solid")
            header_font = Font(color="FFFFFF", bold=True, size=12)
            odd_fill = PatternFill(start_color="FFFFFF", end_color="FFFFFF", fill_type="solid")
            even_fill = PatternFill(start_color="F2F2F2", end_color="F2F2F2", fill_type="solid")
            thin_border = Border(left=Side(style='thin'), right=Side(style='thin'), 
                                top=Side(style='thin'), bottom=Side(style='thin'))

            for col_num, value in enumerate(df.columns, 1):
                cell = worksheet.cell(row=1, column=col_num)
                cell.fill = header_fill
                cell.font = header_font
                cell.alignment = Alignment(horizontal='center')
                cell.border = thin_border

            for row_num in range(2, len(rows) + 2):
                row_fill = even_fill if row_num % 2 == 1 else odd_fill
                for col_num in range(1, len(headers_list) + 1):
                    cell = worksheet.cell(row=row_num, column=col_num)
                    cell.fill = row_fill
                    cell.border = thin_border
                    # 3. 정렬 수정: 4열(Clan Tag)까지는 왼쪽 정렬, 5열(Global Rank)부터는 중앙 정렬
                    cell.alignment = Alignment(horizontal='left' if col_num <= 4 else 'center')

            # 4. 열 너비 최적화 (순서 변경에 맞춰 조정)
            # Name(20), Tag(15), Clan(15), Clan Tag(15), Global Rank(18), Trophies(12)
            column_widths = [20, 15, 15, 15, 18, 12]
            for i, width in enumerate(column_widths, 1):
                worksheet.column_dimensions[worksheet.cell(row=1, column=i).column_letter].width = width

        output.seek(0)
        return discord.File(output, filename=f"Clan_Ranking_Report_{datetime.now().strftime('%m%d')}.xlsx")


    
class RankingView(View):
    def __init__(self, players_data, title, fetch_func):
        super().__init__(timeout=None)

        # 💡 중복 제거 로직: 태그를 기준으로 가장 먼저 발견된 데이터만 유지
        seen = set()
        unique_players = []
        for p in players_data:
            if p['tag'] not in seen:
                unique_players.append(p)
                seen.add(p['tag'])

        self.players_data = unique_players #players_data
        self.title = title
        self.fetch_func = fetch_func
        self.current_page = 0
        self.chunk_size = 100
        self.update_chunks()

        # 페이지가 1개 이하일 경우 네비게이션 버튼 제거
        if len(self.chunks) <= 1:
            self.remove_item(self.prev_button)
            self.remove_item(self.next_button)
        
        # 채널 B(연합 랭킹)일 때만 구글 시트와 다운로드 버튼 추가
        if "Korea Ranking" not in self.title:
            self.add_item(GoogleSheetButton(self.players_data))
            # self.add_item(DownloadButton(self.players_data))

    def update_chunks(self):
        all_lines = []
        is_korea_ranking = "Korea Ranking" in self.title

        for idx, p in enumerate(self.players_data, 1):
            player_name = p['name']
            rank_val = p.get('rank', idx)
            trophy_val = p['trophies']
            clan_info = p.get("clan")
            clan_name = clan_info.get("name", "") if clan_info else ""
            
            if is_korea_ranking:
                display_text = f"{player_name} ({trophy_val})"
                if "백의" in clan_name:
                    line = f"{rank_val}. [**{display_text} (백의)**](https://clashofclans.com)"
                elif "적의" in clan_name:
                    line = f"{rank_val}. [**{display_text} (적의)**](https://clashofclans.com)"
                elif ("신의" in clan_name):
                    # 적의도 rank_val을 넣어주는 게 줄 맞춤에 좋을 거야!
                    line = f"{rank_val}. [**{display_text} (신의)**](https://clashofclans.com)"
                elif ("KoreaClan" in clan_name):
                    # 적의도 rank_val을 넣어주는 게 줄 맞춤에 좋을 거야!
                    line = f"{rank_val}. [**{display_text} (KoreaClan)**](https://clashofclans.com)"
                elif ("Onda2" in clan_name):
                    # 적의도 rank_val을 넣어주는 게 줄 맞춤에 좋을 거야!
                    line = f"{rank_val}. [**{display_text} (Onda2)**](https://clashofclans.com)"
                elif ("On다" in clan_name):
                    # 적의도 rank_val을 넣어주는 게 줄 맞춤에 좋을 거야!
                    line = f"{rank_val}. [**{display_text} (On다)**](https://clashofclans.com)"
                elif ("백의CWL" in clan_name):
                    # 적의도 rank_val을 넣어주는 게 줄 맞춤에 좋을 거야!
                    line = f"{rank_val}. [**{display_text} (백의CWL)**](https://clashofclans.com)"
                else:
                    line = f"{rank_val}. {player_name} ({trophy_val})"
            else:
                rank_str = f"{rank_val:>2}"
                trophy_str = f"{trophy_val:>4}"
                # 정렬된 파란색 랭킹 링크 스타일
                line = f"[`{rank_str}`](https://clashofclans.com) `{trophy_str}` {player_name} | {clan_name}"

            all_lines.append(line)
        
        self.chunks = [all_lines[i : i + self.chunk_size] for i in range(0, len(all_lines), self.chunk_size)]

    def create_embed(self):
        embed = discord.Embed(
            title=self.title,
            description="\n".join(self.chunks[self.current_page]),
            color=0x1ABC9C,
        )
        # 푸터 날짜 고정 또는 datetime.now().strftime('%Y-%m-%d %H:%M') 사용 가능
        embed.set_footer(text=f"Page {self.current_page + 1}/{len(self.chunks)} • 오늘 오후 14:00")
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
# CLAN_TAG = os.environ["CLAN_TAG"]

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
    # 1. 태그 정규화 (# 제거 후 %23 부착)
    clean_tag = clan_tag.strip().replace("#", "")
    url = f"https://api.clashofclans.com/v1/clans/%23{clean_tag}/members"
    headers = {"Authorization": f"Bearer {API_KEY}"}
    
    # 2. 프록시 설정 (Koyeb 환경 변수에서 가져오기)
    proxy_url = os.environ.get("PROXY_URL")
    proxies = {
        "http": proxy_url,
        "https": proxy_url,
    }

    try:
        # 3. 프록시와 타임아웃을 포함하여 요청
        res = requests.get(url, headers=headers, proxies=proxies, timeout=15)
        
        if res.status_code == 200:
            data = res.json()
            members = data.get("items", [])
            # 트로피 순으로 정렬해서 반환
            return sorted(members, key=lambda x: int(x.get('trophies', 0)), reverse=True)
        else:
            print(f"[클랜 API 에러] 상태 코드: {res.status_code}")
            return []
            
    except Exception as e:
        print(f"[클랜 API 예외 발생] {e}")
        return []

# 국내 랭킹 명령어를 처리하는 함수
async def send_ranking_with_buttons(channel, players, title, fetch_func):

    # 1. 채널 B(연합 랭킹)일 때만 미리 상세 데이터(Global Rank) 수집
    if "Korea Ranking" not in title:
        api_headers = {"Authorization": f"Bearer {API_KEY}"}
        proxy_url = os.environ.get("PROXY_URL")
        
        async with aiohttp.ClientSession() as session:
            for p in players:
                safe_tag = p['tag'].replace("#", "%23")
                try:
                    async with session.get(f"https://api.clashofclans.com/v1/players/{safe_tag}", 
                                           headers=api_headers, proxy=proxy_url, timeout=5) as res:
                        if res.status == 200:
                            data = await res.json()
                            p['global_rank'] = data.get("legendStatistics", {}).get("currentSeason", {}).get("rank", "0")
                except:
                    p['global_rank'] = "N/A"
                await asyncio.sleep(0.01)
    
    # 3. 버튼 뷰 생성 및 전송
    view = RankingView(players, title, fetch_func)
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
        date_str = now_kst.strftime("%m/%d-%-I %p")
        
        players = get_top_players()
        if players:
            await send_ranking_with_buttons(channel_a, players, f"Korea Ranking ({date_str})", fetch_func=get_top_players)

        # 2. 채널 B (통합 클랜 랭킹: 백의, 적의, 신의)
        # 환경 변수에서 3개 클랜 태그를 각각 가져옴
        clan_info_list = [
            {"name": "백의", "tag": os.environ.get("CLAN_TAG_WHITE")},
            {"name": "적의", "tag": os.environ.get("CLAN_TAG_RED")},
            {"name": "신의", "tag": os.environ.get("CLAN_TAG_GOD")},
            {"name": "백의종군", "tag": os.environ.get("CLAN_TAG_BJ")},
            {"name": "Onda2", "tag": os.environ.get("CLAN_TAG_ONDA2")},
            {"name": "On다", "tag": os.environ.get("CLAN_TAG_ONDA")},
            {"name": "KoreaClan", "tag": os.environ.get("CLAN_TAG_KOREA")},
            {"name": "백의CWL", "tag": os.environ.get("CLAN_TAG_KOREA")}
        ]

        all_combined_members = []

        for info in clan_info_list:
            tag = info["tag"]
            if not tag: continue # 태그가 설정 안 되어 있으면 패스
            
            members = get_clan_members(tag)
            if members:
                for m in members:
                    league_tier = m.get("leagueTier", {})
                    if league_tier and league_tier.get("name") == "Legend League":
                        m['clan'] = {'name': info["name"]}
                        m['clan_tag'] = tag
                        all_combined_members.append(m)

        if all_combined_members:
            # 1. 전체 인원을 트로피 순으로 정렬
            all_combined_members.sort(key=lambda x: int(x.get('trophies', 0)), reverse=True)
            
            # 2. 상위 50명만 컷
            top_50_combined = all_combined_members[:100]
            
            # 3. 1등부터 순위 새로 매기기
            for idx, m in enumerate(top_50_combined, 1):
                m['rank'] = idx
            
            # 4. 채널 B에 전송
            # 제목에 "Korea"가 안 들어가니까 아까 설정한 대로 파란색 링크 없이 출력될 거야
            await send_ranking_with_buttons(
                channel_b, 
                top_50_combined, 
                f"Clan Ranking ({date_str})",
                fetch_func=None # 통합 데이터는 새로고침 로직이 복잡하니 일단 제외
            )

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