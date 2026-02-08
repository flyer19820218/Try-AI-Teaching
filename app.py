import streamlit as st
import google.generativeai as genai
import os, asyncio, edge_tts, re, base64, io, random
from PIL import Image

# --- 零件檢查 ---
try:
    import fitz # pymupdf
except ImportError:
    st.error("❌ 零件缺失！請確保已安裝 pymupdf 與 edge-tts。")
    st.stop()

# --- 1. 核心視覺規範 ---
st.set_page_config(page_title="臻·極速自然能量域", layout="wide", initial_sidebar_state="expanded")

st.markdown("""
    <style>
    /* 1. 全局視覺鎖定 */
    .stApp, [data-testid="stAppViewContainer"], .stMain, [data-testid="stHeader"] { 
        background-color: #ffffff !important; 
    }
    
    /* 2. 空間壓縮術 */
    div.block-container { padding-top: 1rem !important; padding-bottom: 2rem !important; }
    section[data-testid="stSidebar"] > div { padding-top: 1rem !important; }

    /* 3. 側邊欄與按鈕 */
    [data-testid="stSidebar"] { min-width: 320px !important; max-width: 320px !important; }
    header[data-testid="stHeader"] { background-color: transparent !important; z-index: 1 !important; }
    button[data-testid="stSidebarCollapseButton"] { color: #000000 !important; display: block !important; }

    /* 4. 輸入元件美化 */
    [data-baseweb="input"], [data-baseweb="select"], [data-testid="stNumberInput"] div, [data-testid="stTextInput"] div, [data-testid="stSelectbox"] > div > div {
        background-color: #ffffff !important;
        border: 1px solid #d1d5db !important;
        border-radius: 6px !important;
        box-shadow: 0 1px 2px rgba(0,0,0,0.05) !important;
    }
    [data-baseweb="select"] > div { background-color: #ffffff !important; color: #000000 !important; }
    [data-baseweb="input"] input, [data-baseweb="select"] div { color: #000000 !important; }

    /* 5. 字體規範 */
    html, body, .stMarkdown, p, label, li, h1, h2, h3, .stButton button, a {
        color: #000000 !important;
        font-family: 'HanziPen SC', '翩翩體', sans-serif !important;
    }
    .stButton button { border: 2px solid #000000 !important; background-color: #ffffff !important; font-weight: bold !important; }
    .stMarkdown p { font-size: calc(1rem + 0.3vw) !important; }

    /* 6. 特殊區塊 */
    section[data-testid="stFileUploadDropzone"]::before { content: "📸 拖曳圖片至此或點擊下方按鈕 ➔"; color: #000; font-weight: bold; text-align: center; }
    .guide-box { border: 2px dashed #01579b; padding: 1rem; border-radius: 12px; background-color: #f0f8ff; color: #000; }
    .info-box { border: 1px solid #ddd; padding: 1rem; border-radius: 8px; background-color: #f9f9f9; font-size: 0.9rem; }
    
    /* 逐字稿備用區塊 */
    .transcript-box { background-color: #f8f9fa; border-left: 6px solid #2b2b2b; padding: 15px; margin-top: 10px; margin-bottom: 30px; border-radius: 4px; }
    </style>
""", unsafe_allow_html=True)

st.title("🏃‍♀️ 臻 · 極速自然能量域")
st.markdown("### 🔬 資深理化老師 AI 助教：曉臻老師陪你衝刺科學馬拉松")
st.divider()

# --- 2. 曉臻語音引擎 (VTT 格式修正版) ---
async def generate_audio_and_vtt(text):
    # 1. 文本清洗
    voice_text = text.replace("---PAGE_SEP---", " ")
    corrections = {"補給": "補己", "Ethanol":"75g", "七十五公克": "乙醇", "75%": "百分之七十五"}
    for word, correct in corrections.items():
        voice_text = voice_text.replace(word, correct)
    
    clean_text = voice_text.replace("[[VOICE_START]]", "").replace("[[VOICE_END]]", "")
    clean_text = re.sub(r'[<>#@*_=]', '', clean_text)
    clean_text = clean_text.replace("$", "") 

    communicate = edge_tts.Communicate(clean_text, "zh-TW-HsiaoChenNeural", rate="-2%")
    
    audio_data = b""
    # ⚠️ 關鍵：VTT 檔頭後方必須要有空行
    vtt_lines = ["WEBVTT\n\n"] 
    
    current_sentence = ""
    start_time = 0
    has_word_boundary = False
    
    def format_time(offset_ticks):
        total_seconds = offset_ticks / 10_000_000
        hours = int(total_seconds // 3600)
        minutes = int((total_seconds % 3600) // 60)
        seconds = total_seconds % 60
        return f"{hours:02}:{minutes:02}:{seconds:06.3f}"

    try:
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                audio_data += chunk["data"]
            elif chunk["type"] == "WordBoundary":
                has_word_boundary = True
                word = chunk["text"]
                offset = chunk["offset"]
                duration = chunk["duration"]
                
                if start_time == 0:
                    start_time = offset
                
                current_sentence += word
                
                # 斷句邏輯：遇到標點或過長就切斷
                if word in ["，", "。", "！", "？", "、", "!", "?", ",", "."] or len(current_sentence) > 25:
                    end_time = offset + duration
                    vtt_lines.append(f"{format_time(start_time)} --> {format_time(end_time)}")
                    vtt_lines.append(f"{current_sentence}\n") 
                    vtt_lines.append("\n") # 區塊間空行
                    current_sentence = ""
                    start_time = 0 

        if current_sentence:
             vtt_lines.append(f"{format_time(start_time)} --> {format_time(start_time + 10_000_000)}")
             vtt_lines.append(f"{current_sentence}\n")

        # 保險：若無時間軸，生成一條假字幕
        if not has_word_boundary:
             vtt_lines.append("00:00:00.000 --> 00:20:00.000")
             vtt_lines.append("（正在播放音訊...請開啟 CC 字幕）\n")

        audio_b64 = base64.b64encode(audio_data).decode()
        vtt_content = "".join(vtt_lines) 
        vtt_b64 = base64.b64encode(vtt_content.encode()).decode()
        
        return audio_b64, vtt_b64

    except Exception as e:
        return None, str(e)

# --- 3. 視覺文字淨化 ---
def clean_for_eye(text):
    t = text.replace('\u00a0', ' ').replace("---PAGE_SEP---", "")
    t = re.sub(r'\[\[VOICE_START\]\].*?\[\[VOICE_END\]\]', '', t, flags=re.DOTALL)
    t = t.replace("【顯示稿】", "").replace("【隱藏讀音稿】", "").replace("～～", "")
    return t.strip()

# --- 4. 側邊欄 ---
st.sidebar.title("🚪 打開實驗室大門-金鑰")
st.sidebar.markdown("""
<div class="info-box">
    <b>📢 曉臻老師的叮嚀：</b><br>
    現在是 <b>Podcast 模式</b>！<br>
    畫面上有黑色的字幕機，如果字沒出來，請點一下播放器右下角的「CC」或「三點」圖示。<br>
    <a href="mailto:flyer19820218@gmail.com" style="color: #01579b;">flyer19820218@gmail.com</a>
</div>
<br>
""", unsafe_allow_html=True)
st.sidebar.markdown("""
<div class="guide-box">
    <b>📖 值日生啟動指南：</b><br>
    1. 前往 <a href="https://aistudio.google.com/app/apikey" target="_blank" style="color:#01579b; font-weight:bold;">Google AI Studio</a>。<br>
    2. 貼回下方金鑰區開啟能量域！
</div>
""", unsafe_allow_html=True)
user_key = st.sidebar.text_input("🔑 實驗室啟動金鑰", type="password", key="tower_key")
st.sidebar.divider()
st.sidebar.subheader("💬 曉臻問題箱")
student_q = st.sidebar.text_input("打字問曉臻：", key="science_q")
uploaded_file = st.sidebar.file_uploader("📸 照片區：", type=["jpg", "png", "jpeg"], key="science_f")

# --- 初始化 State ---
if "class_started" not in st.session_state: st.session_state.class_started = False
if "display_images" not in st.session_state: st.session_state.display_images = []
if "raw_parts" not in st.session_state: st.session_state.raw_parts = []
if "audio_b64" not in st.session_state: st.session_state.audio_b64 = None
if "vtt_b64" not in st.session_state: st.session_state.vtt_b64 = None
if "error_msg" not in st.session_state: st.session_state.error_msg = None

# --- 5. 曉臻教學核心指令 ---
SYSTEM_PROMPT = r"""
你是資深自然科學助教曉臻。你現在要進行一場約 20 分鐘的深度講義導讀。

⚠️【格式嚴格要求】：
1. 請務必按照頁面順序導讀。
2. 每一頁的開頭，一定要加上標籤：『---PAGE_SEP---』。
3. 每一頁的內容分為兩部分：
   (A) [[VOICE_START]] 這裡是你要唸出來的口語內容 [[VOICE_END]]
   (B) 這裡是顯示在畫面上的文字稿

⚠️【內容規範】：
- 每一頁的顯示稿必須包含：【曉臻老師上課逐字說明】、【知識點總結】、【常見考點提醒】。
- 總結時必喊：『這就是自然科學 the 真理！』

⚠️【讀音特殊規範】：
- 化學式 n=m/M 讀作 n～～ 等於～～ m～～ 除以～～ M～～
"""

# --- 6. 導航系統 ---
col1, col2, col3 = st.columns([1, 1, 1])
with col1: vol_select = st.selectbox("📚 冊別選擇", ["第一冊", "第二冊", "第三冊", "第四冊", "第五冊", "第六冊"], index=3)
with col2: chap_select = st.selectbox("🧪 章節選擇", ["第一章", "第二章", "第三章", "第四章", "第五章", "第六章"], index=0)
with col3: start_page = st.number_input("🏁 起始頁碼", 1, 200, 1, key="start_pg")

filename = f"{vol_select}_{chap_select}.pdf"
pdf_path = os.path.join("data", filename)

# --- 主畫面邏輯 ---
if not st.session_state.class_started:
    
    # --- 備課模式：顯示大圖 ---
    cover_image_path = None
    for ext in [".jpg", ".png", ".jpeg", ".JPG", ".PNG"]:
        temp_path = os.path.join("data", f"cover{ext}")
        if os.path.exists(temp_path):
            cover_image_path = temp_path
            break
    if cover_image_path:
        st.image(Image.open(cover_image_path), use_container_width=True)
    else:
        st.info("🏃‍♀️ 曉臻老師正在起跑線上準備中...")

    st.divider()

    show_preview = st.checkbox("👀 我想先偷看一下講義內容 (預覽模式)", value=False)
    if show_preview and os.path.exists(pdf_path):
        try:
            doc = fitz.open(pdf_path)
            total_pages = len(doc)
            page = doc.load_page(start_page - 1) 
            pix = page.get_pixmap(matrix=fitz.Matrix(2, 2))
            img = Image.open(io.BytesIO(pix.tobytes()))
            st.image(img, caption=f"📍 預覽：第 {start_page} 頁 (全書共 {total_pages} 頁)", use_container_width=True)
        except: pass

    st.divider()
    # 按鈕區
    if st.button(f"🏃‍♀️ 確認無誤 - 開始今天的 AI 自然課程 (P.{start_page}~P.{start_page+4})", type="primary", use_container_width=True):
        if user_key and os.path.exists(pdf_path):
            with st.status("🏃‍♀️ 曉臻老師正在暖身中...", expanded=True) as status:
                try:
                    st.write("📖 正在翻閱講義圖片...")
                    doc = fitz.open(pdf_path)
                    images_to_process, display_images_list = [], []
                    pages_to_read = range(start_page - 1, min(start_page + 4, len(doc)))
                    
                    if len(pages_to_read) == 0:
                        st.error("⚠️ 已經到最後一頁了，沒有內容可以上課囉！")
                        st.stop()

                    for p in pages_to_read:
                        pix = doc.load_page(p).get_pixmap(matrix=fitz.Matrix(2, 2))
                        img = Image.open(io.BytesIO(pix.tobytes()))
                        images_to_process.append(img)
                        display_images_list.append((p + 1, img))
                    
                    st.write("🧠 正在分析科學概念與考點 (Gemini 2.5 Flash)...")
                    genai.configure(api_key=user_key)
                    MODEL = genai.GenerativeModel('models/gemini-2.5-flash') 
                    
                    res = MODEL.generate_content([f"{SYSTEM_PROMPT}\n導讀P.{start_page}起內容。"] + images_to_process)
                    raw_res = res.text.replace('\u00a0', ' ')
                    
                    # 儲存原始文字 (切分)
                    if "---PAGE_SEP---" in raw_res:
                        raw_parts_split = [p for p in raw_res.split("---PAGE_SEP---") if p.strip()]
                    else:
                        raw_parts_split = [raw_res]
                    st.session_state.raw_parts = raw_parts_split
                    
                    st.write("🎙️ 正在錄製語音與生成字幕 (這一步最久，請稍候)...")
                    voice_matches = re.findall(r'\[\[VOICE_START\]\](.*?)\[\[VOICE_END\]\]', raw_res, re.DOTALL)
                    voice_full_text = " ".join(voice_matches) if voice_matches else clean_for_eye(raw_res)
                    
                    result_audio, result_vtt = asyncio.run(generate_audio_and_vtt(voice_full_text))
                    
                    st.session_state.audio_b64 = result_audio if result_audio else None
                    st.session_state.vtt_b64 = result_vtt if result_audio else None
                    st.session_state.error_msg = result_vtt if not result_audio else None
                        
                    st.session_state.display_images = display_images_list
                    status.update(label="✅ 備課完成！曉臻老師準備好了！", state="complete", expanded=False)
                    st.session_state.class_started = True
                    st.rerun() 
                except Exception as e:
                    st.error(f"❌ 發生錯誤：{e}")
                    status.update(label="❌ 備課失敗", state="error")
        elif not user_key:
            st.warning("🔑 請先輸入實驗室啟動金鑰。")
        else:
            st.error(f"📂 找不到講義文件：{filename}")

else:
    # --- 上課模式：無封面圖，只有播放器+講義 ---
    st.success("🔔
