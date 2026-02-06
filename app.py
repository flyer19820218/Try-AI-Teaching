import streamlit as st
import google.generativeai as genai
import os, asyncio, edge_tts, re, base64, io, time
from PIL import Image

# --- 零件檢查 ---
try:
    import fitz # pymupdf
except ImportError:
    st.error("❌ 零件缺失！請確保環境中安裝了 pymupdf。")
    st.stop()

# --- 1. 核心視覺規範 (全白、翩翩體感、黑字) ---
st.set_page_config(page_title="臻·極速自然能量域", layout="wide", initial_sidebar_state="expanded")

st.markdown("""
    <style>
    .stApp, [data-testid="stAppViewContainer"], .stMain, [data-testid="stHeader"] { 
        background-color: #ffffff !important; 
    }
    div.block-container { padding-top: 1rem !important; }
    html, body, .stMarkdown, p, label, li, h1, h2, h3, .stButton button {
        color: #000000 !important;
        font-family: 'HanziPen SC', '翩翩體', sans-serif !important;
    }
    .stButton button {
        border: 2px solid #000000 !important;
        background-color: #ffffff !important;
        font-weight: bold !important;
    }
    .transcript-box { background-color: #fdfdfd; border-left: 5px solid #000; padding: 15px; margin-bottom: 25px; line-height: 1.6; }
    </style>
""", unsafe_allow_html=True)

# --- 💡 核心外掛：智能打字機邏輯 (防 LaTeX 亂碼) ---
def smart_typewriter(text):
    # 使用正則表達式切開 LaTeX ($$ 或 $) 與 普通文字
    tokens = re.split(r'(\$\$.*?\$\$|\$.*?\$)', text, flags=re.DOTALL)
    for token in tokens:
        if not token: continue
        if token.startswith('$'):
            # 化學式不准拆開跑，整串直接閃現！
            yield token
        else:
            # 普通文字逐字跑，配速 0.08s
            for char in token:
                yield char
                time.sleep(0.08)

# --- 2. 曉臻語音引擎 (zh-TW-HsiaoChenNeural) ---
async def generate_voice_base64(text):
    voice_text = text.replace("---PAGE_SEP---", " ")
    corrections = {"補給": "補己", "Ethanol": "乙醇", "75%": "百分之七十五", "%": "趴"}
    for word, correct in corrections.items():
        voice_text = voice_text.replace(word, correct)
    clean_text = voice_text.replace("$", "")
    clean_text = re.sub(r'[^\w\u4e00-\u9fff\d，。！？「」～ ]', '', clean_text)
    
    communicate = edge_tts.Communicate(clean_text, "zh-TW-HsiaoChenNeural", rate="-2%")
    audio_data = b""
    async for chunk in communicate.stream():
        if chunk["type"] == "audio": audio_data += chunk["data"]
    b64 = base64.b64encode(audio_data).decode()
    return f'<audio controls autoplay style="width:100%"><source src="data:audio/mp3;base64,{b64}" type="audio/mp3"></audio>'

def clean_for_eye(text):
    t = text.replace("---PAGE_SEP---", "")
    t = re.sub(r'([a-zA-Z0-9])～～\s*', r'\1', t) 
    t = t.replace("～～", "")
    return t

# --- 3. 曉臻教學核心指令 (保留 10 則科學人知識) ---
SYSTEM_PROMPT = """
你是資深自然科學助教曉臻，馬拉松選手 (PB 92分)。妳現在要導讀講義。請遵守規範：
1. 【科學人開場】：僅限從下方知識庫選取一則分享。結尾必含：『熱身一下下課老師就要去跑步了』。
2. 【翻頁】：解說完當頁內容才唸『翻到第 X 頁』。每頁最開頭加上標籤『---PAGE_SEP---』。
3. 【偵測】：僅當圖片明確出現「練習」二字才啟動題目模式。
4. 【轉譯規範】：化學式字母後方加「～～」。範例：氧氣 ➔ $$O_{2}$$ (O～～ two～～ 也就是氧氣)。
5. 【結尾】：必喊『這就是自然科學 the 真理！』。
# --- 曉臻科學小知識庫 ---
1. BDNF：記憶的神經肥料。 2. 鳶尾素：保護神經元。 3. 海馬迴：增加記憶空間。 
4. 前額葉：提升專注。 5. 神經遞質：緩解焦慮。 6. 線粒體：提供思考能量。
7. 突觸塑性：學習更快。 8. 內啡肽：提升耐受度。 9. 晝夜節律：固化記憶。 10. 鏡像神經元：提升合作。
"""

# --- 4. 側邊欄與導航 ---
st.title("🏃‍♀️ 臻 · 極速自然能量域")
st.sidebar.title("🔑 實驗室門禁")
user_key = st.sidebar.text_input("輸入 API Key", type="password")

col1, col2, col3 = st.columns([1, 1, 1])
with col1: vol = st.selectbox("冊別", ["第一冊", "第二冊", "第三冊", "第四冊", "第五冊", "第六冊"], index=3)
with col2: chap = st.selectbox("章節", ["第一章", "第二章", "第三章", "第四章", "第五章", "第六章"], index=2)
with col3: start_pg = st.number_input("起始頁碼", 1, 100, 1)

pdf_path = os.path.join("data", f"{vol}_{chap}.pdf")

if "class_started" not in st.session_state: st.session_state.class_started = False

# --- 5. 主程式流程 ---
if not st.session_state.class_started:
    cover_path = os.path.join("data", "cover.jpg")
    if os.path.exists(cover_path): st.image(cover_path, use_container_width=True)
    
    if st.button("🏃‍♀️ 開始馬拉松課程", use_container_width=True, type="primary"):
        if user_key and os.path.exists(pdf_path):
            with st.spinner("曉臻正在開嗓並翻閱講義..."):
                try:
                    doc = fitz.open(pdf_path)
                    imgs, disp_imgs = [], []
                    pages = range(start_pg - 1, min(start_pg + 4, len(doc)))
                    for p in pages:
                        pix = doc.load_page(p).get_pixmap(matrix=fitz.Matrix(2, 2))
                        img = Image.open(io.BytesIO(pix.tobytes()))
                        imgs.append(img)
                        disp_imgs.append((p + 1, img))
                    
                    genai.configure(api_key=user_key)
                    model = genai.GenerativeModel('gemini-2.0-flash')
                    res = model.generate_content([f"{SYSTEM_PROMPT}\n導讀P.{start_pg}起。"] + imgs)
                    
                    st.session_state.res_text = res.text
                    st.session_state.audio_html = asyncio.run(generate_voice_base64(res.text))
                    st.session_state.display_images = disp_imgs
                    st.session_state.class_started = True
                    st.rerun()
                except Exception as e:
                    st.error(f"❌ 錯誤：{e}")
else:
    # 🏃‍♀️ 順序：1.音 2.文 3.圖 4.詳
    if "audio_html" in st.session_state:
        st.markdown("### 1️⃣ 曉臻老師語音補給")
        st.markdown(st.session_state.audio_html, unsafe_allow_html=True)
    
    st.divider()
    parts = st.session_state.res_text.split("---PAGE_SEP---")

    if len(parts) > 0:
        st.markdown("### 💬 曉臻老師開場...")
        st.write_stream(smart_typewriter(clean_for_eye(parts[0])))
        st.divider()

    for i, (p_num, img) in enumerate(st.session_state.display_images):
        if (i + 1) < len(parts):
            st.markdown(f"### 💬 曉臻導讀 P.{p_num}...")
            st.write_stream(smart_typewriter(clean_for_eye(parts[i+1])))
            st.image(img, caption=f"🏁 第 {p_num} 頁講義", use_container_width=True)
            with st.expander(f"📜 P.{p_num} 詳細文字稿", expanded=True):
                st.markdown(f'<div class="transcript-box">{clean_for_eye(parts[i+1])}</div>', unsafe_allow_html=True)
            st.divider()

    if st.button("🏁 下課休息"):
        st.session_state.class_started = False
        st.rerun()
