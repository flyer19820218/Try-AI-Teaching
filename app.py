import streamlit as st
import google.generativeai as genai
import os, asyncio, edge_tts, re, base64, io, time
from PIL import Image

# --- 零件檢查 ---
try:
    import fitz # pymupdf
except ImportError:
    st.error("❌ 零件缺失！")
    st.stop()

# --- 1. 核心視覺 (延用您的白底黑字規範) ---
st.set_page_config(page_title="臻·極速自然能量域", layout="wide")
st.markdown("<style>.stApp {background-color: #ffffff;}</style>", unsafe_allow_html=True)

# --- 2. 曉臻 2.0 專屬組件：防亂碼打字機 ---
def smart_typewriter(text):
    # 偵測 $$ 標記，確保化學式不亂碼
    tokens = re.split(r'(\$\$.*?\$\$|\$.*?\$)', text, flags=re.DOTALL)
    for token in tokens:
        if not token: continue
        if token.startswith('$'):
            yield token  # 化學式整串跳出
        else:
            for char in token:
                yield char
                time.sleep(0.08) # 逐字配速

# --- 3. 曉臻真聲引擎 (呼叫 HsiaoChen) ---
async def generate_voice_base64(text):
    # 清理標籤，確保曉臻不唸出奇怪代碼
    clean_text = re.sub(r'[^\w\u4e00-\u9fff\d，。！？「」～ ]', '', text.replace("$", ""))
    communicate = edge_tts.Communicate(clean_text, "zh-TW-HsiaoChenNeural", rate="-2%")
    audio_data = b""
    async for chunk in communicate.stream():
        if chunk["type"] == "audio": audio_data += chunk["data"]
    b64 = base64.b64encode(audio_data).decode()
    return f'<audio controls autoplay style="width:100%"><source src="data:audio/mp3;base64,{b64}" type="audio/mp3"></audio>'

# --- 4. 曉臻教學核心 (保留您的原創 SYSTEM_PROMPT) ---
SYSTEM_PROMPT = """妳是資深自然科學助教曉臻... (此處填入您原始的 10 則知識庫設定)"""

st.title("🏃‍♀️ 臻 · 極速自然能量域")
user_key = st.sidebar.text_input("🔑 金鑰", type="password")

# --- 5. 上課邏輯 (音 ➔ 文 ➔ 圖 ➔ 詳) ---
if "class_started" not in st.session_state: st.session_state.class_started = False

if not st.session_state.class_started:
    if st.button("🏃‍♀️ 開始馬拉松課程"):
        # ... (此處保留您原始的 PDF 轉圖片邏輯) ...
        # 假設執行成功後設定以下狀態
        st.session_state.res_text = "模擬導讀內容：運動能促進 BDNF。反應式為 $$2H_{2} + O_{2} \\rightarrow 2H_{2}O$$ ---PAGE_SEP--- 第二頁內容"
        st.session_state.audio_html = asyncio.run(generate_voice_base64(st.session_state.res_text))
        st.session_state.class_started = True
        st.rerun()
else:
    # 1. 聲音播放器 (放在最頂端)
    st.markdown("### 1️⃣ 曉臻老師語音補給")
    st.markdown(st.session_state.audio_html, unsafe_allow_html=True)
    
    st.divider()
    parts = st.session_state.res_text.split("---PAGE_SEP---")

    # 2. 逐頁循環：字幕 ➔ 圖片 ➔ 詳解
    for i in range(len(parts)):
        # 顯示字幕 (打字機效果)
        st.markdown(f"### 💬 曉臻導讀中...")
        st.write_stream(smart_typewriter(parts[i]))
        
        # 顯示講義圖片 (假設您有 display_images)
        # st.image(st.session_state.display_images[i]) 
        
        # 詳細文字內容 (Expander 摺疊)
        with st.expander("📜 詳細文字稿", expanded=True):
            st.write(parts[i])
        st.divider()
