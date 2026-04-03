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
        await interaction.response.defer(ephemeral=True)
        
        try:
            creds_json_str = os.environ.get("CREDENTIALS_JSON")
            creds_info = json.loads(creds_json_str)
            if "private_key" in creds_info:
                creds_info["private_key"] = creds_info["private_key"].replace("\\n", "\n")
            
            scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
            creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_info, scope)
            client = gspread.authorize(creds)

            sheet_url = "https://docs.google.com" # 본인 주소 사용
            doc = client.open_by_url(sheet_url)
            sheet = doc.get_worksheet(0)

            # 1. 데이터 구성
            headers = ["Name", "Tag", "Clan", "Clan Tag", "Global Ranking", "Trophies"]
            rows = [headers]
            for p in self.players_data:
                rows.append([
                    p.get('name', 'N/A'), p.get('tag', 'N/A'),
                    p.get('clan_name', 'N/A'), p.get('clan_tag', 'N/A'),
                    p.get('global_rank', 'N/A'), p.get('trophies', 0)
                ])

            # 2. 데이터 쓰기 (기존 내용 삭제 후 업데이트)
            sheet.clear()
            sheet.update('A1', rows)

            # ---------------------------------------------------------
            # 🎨 디자인 적용 (엑셀 스타일 동기화)
            # ---------------------------------------------------------
            last_row = len(rows)
            last_col_letter = "F" # A부터 F열까지
            full_range = f"A1:{last_col_letter}{last_row}"

            # 3. 헤더 스타일 (남색 배경 #366092, 흰색 굵은 글씨, 중앙 정렬)
            sheet.format("A1:F1", {
                "backgroundColor": {"red": 54/255, "green": 96/255, "blue": 146/255},
                "textFormat": {"foregroundColor": {"red": 1.0, "green": 1.0, "blue": 1.0}, "bold": True, "fontSize": 11},
                "horizontalAlignment": "CENTER"
            })

            # 4. 본문 스타일 (줄무늬 효과 및 테두리)
            # 짝수 행에 연한 회색 배경 적용 (#F2F2F2)
            for i in range(2, last_row + 1):
                if i % 2 == 1: # 엑셀의 even_fill (여기는 데이터상 짝수행이 홀수 인덱스일 수 있음)
                    row_range = f"A{i}:F{i}"
                    sheet.format(row_range, {"backgroundColor": {"red": 242/255, "green": 242/255, "blue": 242/255}})

            # 5. 정렬 및 테두리 설정
            # 전체 범위 기본 왼쪽 정렬 + 테두리
            sheet.format(full_range, {
                "horizontalAlignment": "LEFT",
                "verticalAlignment": "MIDDLE"
            })
            
            # 랭킹과 트로피(E, F열)만 중앙 정렬
            sheet.format(f"E2:F{last_row}", {"horizontalAlignment": "CENTER"})

            # 6. 열 너비 조정 (이건 시트의 상태에 따라 수동 조절이 필요할 수 있어)
            # gspread에서는 특정 열 너비를 숫자로 지정 가능
            set_column_width(sheet, 'A', 200) # Name
            set_column_width(sheet, 'B:D', 150) # Tags, Clan
            set_column_width(sheet, 'E', 180) # Global Rank
            set_column_width(sheet, 'F', 120) # Trophies

            await interaction.followup.send(
                f"🎨 디자인까지 완벽하게 동기화된 시트를 확인하세요!\n🔗 [실시간 랭킹 확인하기]({sheet_url})", 
                ephemeral=True
            )

        except Exception as e:
            print(f"Google Sheet Error: {e}")
            await interaction.followup.send(f"❌ 시트 업데이트 중 오류 발생: {e}", ephemeral=True)

# 💡 열 너비 조절을 위한 간단한 헬퍼 함수
def set_column_width(worksheet, column_range, width):
    try:
        g_set_width(worksheet, column_range, width)
    except Exception as e:
        print(f"⚠️ 열 너비 조정 중 오류: {e}")

# 2. 엑셀 다운로드 버튼 (본인만 볼 수 있게 전송)
class DownloadButton(discord.ui.Button):
    def __init__(self, players_data):
        # secondary 스타일은 회색 버튼이야
        super().__init__(label="Download", style=discord.ButtonStyle.secondary)
        self.players_data = players_data

    async def callback(self, interaction: discord.Interaction):
        # 1. 클릭 시 사용자에게만 보이는 대기 메시지
        await interaction.response.defer(ephemeral=True)
        
        try:
            # 2. 고정된 데이터를 바탕으로 엑셀 파일 생성 (내부 함수 호출)
            excel_file = await self.generate_excel() 
            
            # 3. 파일 전송 (ephemeral=True로 본인만 확인 가능)
            await interaction.followup.send(
                "✨ 14시 기준 엑셀 리포트 생성이 완료되었습니다.", 
                file=excel_file, 
                ephemeral=True
            )
        except Exception as e:
            print(f"Excel Generation Error: {e}")
            await interaction.followup.send(f"❌ 엑셀 생성 중 오류 발생: {e}", ephemeral=True)

    async def generate_excel(self):
        # 헤더 순서: Name, Tag, Clan, Clan Tag, Global Ranking, Trophies
        headers_list = ["Name", "Tag", "Clan", "Clan Tag", "Global Ranking", "Trophies"]
        rows = []

        # ⭐ 이미 14시에 수집된 데이터를 그대로 사용 (추가 API 호출 없음)
        for p in self.players_data:
            rows.append([
                p.get('name', 'N/A'),
                p.get('tag', 'N/A'),
                p.get('clan_name', 'N/A'),
                p.get('clan_tag', 'N/A'),
                p.get('global_rank', 'N/A'), # 고정된 랭킹 정보
                p.get('trophies', 0)
            ])

        # 데이터프레임 생성
        df = pd.DataFrame(rows, columns=headers_list)
        
        # 메모리 내에서 엑셀 파일 생성 (BytesIO 사용)
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, index=False, sheet_name='Ranking')
            workbook = writer.book
            worksheet = writer.sheets['Ranking']

            # 디자인 설정 (헤더: 남색 배경 + 흰색 글씨)
            header_fill = PatternFill(start_color="366092", end_color="366092", fill_type="solid")
            header_font = Font(color="FFFFFF", bold=True, size=12)
            odd_fill = PatternFill(start_color="FFFFFF", end_color="FFFFFF", fill_type="solid")
            even_fill = PatternFill(start_color="F2F2F2", end_color="F2F2F2", fill_type="solid")
            thin_border = Border(left=Side(style='thin'), right=Side(style='thin'), 
                                top=Side(style='thin'), bottom=Side(style='thin'))

            # 헤더 스타일 적용
            for col_num, value in enumerate(df.columns, 1):
                cell = worksheet.cell(row=1, column=col_num)
                cell.fill = header_fill
                cell.font = header_font
                cell.alignment = Alignment(horizontal='center')
                cell.border = thin_border

            # 본문 스타일 적용 (줄무늬 효과 및 테두리)
            for row_num in range(2, len(rows) + 2):
                row_fill = even_fill if row_num % 2 == 1 else odd_fill
                for col_num in range(1, len(headers_list) + 1):
                    cell = worksheet.cell(row=row_num, column=col_num)
                    cell.fill = row_fill
                    cell.border = thin_border
                    # 4열(Clan Tag)까지는 왼쪽 정렬, 5열(Global Rank)부터는 중앙 정렬
                    cell.alignment = Alignment(horizontal='left' if col_num <= 4 else 'center')

            # 열 너비 최적화 (Global Ranking은 18로 넉넉하게)
            column_widths = [20, 15, 15, 15, 18, 12]
            for i, width in enumerate(column_widths, 1):
                worksheet.column_dimensions[worksheet.cell(row=1, column=i).column_letter].width = width

        output.seek(0)
        # 파일명에 현재 날짜 포함 (예: Clan_Ranking_Report_0403.xlsx)
        return discord.File(output, filename=f"Clan_Ranking_Report_{datetime.now().strftime('%m%d')}.xlsx")
    
class RankingView(View):
    def __init__(self, players_data, title, fetch_func, all_lines):
        super().__init__(timeout=None)
        self.players_data = players_data
        self.title = title
        self.fetch_func = fetch_func
        self.all_lines = all_lines # 저장
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
            self.add_item(DownloadButton(self.players_data))

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

        description = "\n".join(self.all_lines)
        chunk = self.chunks[self.current_page]
        embed = discord.Embed(
            title=self.title,
            description=description,
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
    """
    14시 정각에 호출되어 데이터를 수집하고, 고정된 데이터를 포함한 버튼 뷰를 전송함.
    """
    # 1. 14시 시점의 상세 데이터(Global Rank) 미리 수집 (스냅샷 생성)
    enriched_players = []
    api_headers = {"Authorization": f"Bearer {API_KEY}"}
    proxy_url = os.environ.get("PROXY_URL")

    # 진행 상황을 알기 위한 로그 (선택 사항)
    print(f"[{title}] 상세 데이터 수집 시작... (총 {len(players)}명)")

    async with aiohttp.ClientSession() as session:
        for idx, p in enumerate(players, 1):
            player_tag = p['tag']
            safe_p_tag = player_tag.replace("#", "%23")
            
            global_rank = "N/A"
            try:
                # 14시 시점의 API 정보를 한 번만 가져옴
                async with session.get(
                    f"https://api.clashofclans.com/v1/players/{safe_p_tag}", 
                    headers=api_headers, 
                    proxy=proxy_url, 
                    timeout=5
                ) as res:
                    if res.status == 200:
                        data = await res.json()
                        legend_stats = data.get("legendStatistics", {})
                        # 현재 시즌의 글로벌 랭크 추출
                        global_rank = legend_stats.get("currentSeason", {}).get("rank", "N/A")
            except Exception as e:
                print(f"⚠️ {p['name']} 상세 정보 수집 중 에러: {e}")

            # 💡 기존 플레이어 데이터에 global_rank 정보를 추가 (고정값)
            p['global_rank'] = global_rank
            
            # 클랜 태그 정보가 없는 경우를 대비해 안전하게 처리
            if 'clan' in p and p['clan']:
                p['clan_name'] = p['clan'].get('name', 'N/A')
                p['clan_tag'] = p['clan'].get('tag', 'N/A')
            else:
                p['clan_name'] = 'N/A'
                p['clan_tag'] = 'N/A'

            enriched_players.append(p)
            # API 과부하 방지 (초당 50회 미만 권장)
            await asyncio.sleep(0.01)

    # 2. 디스코드 메시지용 텍스트 생성 (enriched_players 사용)
    all_lines = []
    for idx, p in enumerate(enriched_players, 1):
        player_name = p['name']
        rank_val = p.get('rank', idx) 
        trophy_val = p['trophies']
        clan_name = p.get('clan_name', "")
        
        display_text = f"{player_name} ({trophy_val})"
        
        # 특정 클랜 강조 로직 (백의, 적의, 신의 등)
        if any(keyword in clan_name for keyword in ["백의", "적의", "신의", "KoreaClan", "Onda2", "On다"]):
            # 강조하고 싶은 클랜은 볼드체와 링크 적용
            line = f"{rank_val}. [**{display_text}**](https://clashofclans.com)"
        else:
            line = f"{rank_val}. {player_name} ({trophy_val})"
            
        all_lines.append(line)

    # 3. 버튼 뷰 생성 및 전송
    # 여기서 enriched_players를 넘겨주면, 내부 버튼들이 이 데이터를 그대로 사용함.
    view = RankingView(enriched_players, title, fetch_func, all_lines)
    
    # 임베드 생성 시 all_lines를 활용하도록 RankingView가 설계되어 있어야 함
    embed = view.create_embed() # RankingView 내부에서 all_lines를 기반으로 빌드하도록 수정 필요
    
    await channel.send(embed=embed, view=view)
    print(f"[{title}] 전송 완료.")

async def daily_task(channel_a, channel_b):
    KST = timezone(timedelta(hours=9))

    while True:
        now_kst = datetime.now(KST)
        target_time = now_kst.replace(hour=12, minute=54, second=0, microsecond=0)

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
            {"name": "KoreaClan", "tag": os.environ.get("CLAN_TAG_KOREA")}
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

        print(f"📊 총합 멤버 수: {len(all_combined_members)}명")

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

'''@client.event
async def on_message(message):
    # 봇 자신이 쓴 메시지에는 반응하지 않게 방어
    if message.author == client.user:
        return

    # 채팅창에 !test 라고 치면 실행
    if message.content == "!test":
        print(f"[{message.author}]님이 테스트 명령어를 사용함")
        
        # 전체 로컬 랭킹 상위 10명만 테스트로 출력해보기
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
        players = get_clan_members(CLAN_TAG)
        print(f"가져온 플레이어 수: {len(players) if players else 0}") # 확인용 2
        if players:
            # message.channel은 명령어를 친 바로 그 채널을 의미해
            await send_ranking_with_buttons(
                message.channel, 
                players[:], 
                f"클랜 랭킹 디자인 테스트 ({now_str})",
                fetch_func=lambda: get_clan_members(CLAN_TAG)
            )
        
        await message.channel.send("✅ 테스트 출력이 완료되었습니다!")'''

client.run(TOKEN)