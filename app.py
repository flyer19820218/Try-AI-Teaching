import streamlit as st
import google.generativeai as genai
import os, re, base64, io, asyncio
from PIL import Image

import fitz  # pymupdf
import edge_tts
from mutagen.mp3 import MP3
from streamlit_autorefresh import st_autorefresh


# =========================
# 0) 讀取 prompt.txt（避免程式被截斷）
# =========================
def load_system_prompt(path="prompt.txt"):
    if not os.path.exists(path):
        st.error(f"❌ 找不到 {path}，請建立 prompt.txt 並貼上你的 SYSTEM_PROMPT")
        st.stop()
    with open(path, "r", encoding="utf-8") as f:
        return f.read().strip()


SYSTEM_PROMPT = load_system_prompt("prompt.txt")


# =========================
# 1) Streamlit 設定 & 風格
# =========================
st.set_page_config(page_title="臻·極速自然能量域", layout="wide", initial_sidebar_state="expanded")

st.markdown("""
<style>
:root { color-scheme: light !important; }
.stApp, [data-testid="stAppViewContainer"], .stMain, [data-testid="stHeader"] { 
    background-color: #ffffff !important; 
}
div.block-container { padding-top: 1rem !important; padding-bottom: 2rem !important; }
section[data-testid="stSidebar"] > div { padding-top: 1rem !important; }
[data-testid="stSidebar"] { min-width: 320px !important; max-width: 320px !important; }
header[data-testid="stHeader"] { background-color: transparent !important; z-index: 1 !important; }
button[data-testid="stSidebarCollapseButton"] { color: #000000 !important; display: block !important; }

[data-testid="stWidgetLabel"] div, [data-testid="stWidgetLabel"] p {
    background-color: transparent !important;
    border: none !important;
    box-shadow: none !important;
    padding: 0 !important;
}

html, body, .stMarkdown, p, label, li, h1, h2, h3, .stButton button, a {
    color: #000000 !important;
    font-family: 'HanziPen SC', '翩翩體', sans-serif !important;
}
.stButton button {
    border: 2px solid #000000 !important;
    background-color: #ffffff !important;
    font-weight: bold !important;
}
.info-box { border: 1px solid #ddd; padding: 1rem; border-radius: 8px; background-color: #f9f9f9; font-size: 0.9rem; color: #000; }
.guide-box { border: 2px dashed #01579b; padding: 1rem; border-radius: 12px; background-color: #f0f8ff; color: #000; }
</style>
""", unsafe_allow_html=True)

st.title("🏃‍♀️ 臻 · 極速自然能量域")
st.markdown("### 🔬 資深理化老師 AI 助教：曉臻老師陪你衝刺科學馬拉松")
st.divider()


# =========================
# 2) Async helper
# =========================
def run_async(coro):
    try:
        return asyncio.run(coro)
    except RuntimeError:
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(coro)
        finally:
            loop.close()


# =========================
# 3) 字幕切句
# =========================
def split_to_captions(text: str):
    t = text.strip()
    t = re.sub(r"\s+", " ", t)
    chunks = re.split(r"(?<=[。！？；…])\s*", t)
    chunks = [c.strip() for c in chunks if c.strip()]
    return chunks if chunks else [t]


# =========================
# 4) TTS：產生音檔 + duration + captions
# =========================
async def generate_voice_and_meta(text: str):
    voice_text = text.replace("---PAGE_SEP---", " ")

    corrections = {"補給": "補己", "Ethanol": "75g", "七十五公克": "乙醇", "75%": "百分之七十五"}
    for word, correct in corrections.items():
        voice_text = voice_text.replace(word, correct)

    clean_text = voice_text.replace("$", "")
    clean_text = clean_text.replace("[[VOICE_START]]", "").replace("[[VOICE_END]]", "")
    clean_text = re.sub(r"[<>#@*_=]", "", clean_text)

    communicate = edge_tts.Communicate(clean_text, "zh-TW-HsiaoChenNeural", rate="-2%")
    audio_data = b""
    async for chunk in communicate.stream():
        if chunk["type"] == "audio":
            audio_data += chunk["data"]

    duration_sec = MP3(io.BytesIO(audio_data)).info.length

    b64 = base64.b64encode(audio_data).decode()
    audio_html = f"""
    <audio controls autoplay style="width:100%">
      <source src="data:audio/mp3;base64,{b64}" type="audio/mp3">
    </audio>
    """

    captions = split_to_captions(clean_text)
    return audio_html, duration_sec, captions


# =========================
# 5) PDF：讀取單頁
# =========================
def load_pdf_page_image(pdf_path: str, page_1based: int):
    doc = fitz.open(pdf_path)
    idx = page_1based - 1
    total = len(doc)
    if idx < 0 or idx >= total:
        return None, total
    pix = doc.load_page(idx).get_pixmap(matrix=fitz.Matrix(2, 2))
    img = Image.open(io.BytesIO(pix.tobytes()))
    return img, total


# =========================
# 6) Gemini：產生顯示稿 + 讀音稿
# =========================
def gemini_generate_page(api_key: str, page_num: int, page_img: Image.Image):
    genai.configure(api_key=api_key)
    model = genai.GenerativeModel("models/gemini-2.5-flash")

    res = model.generate_content([f"{SYSTEM_PROMPT}\n導讀P.{page_num}內容。", page_img])
    raw = (res.text or "").replace("\u00a0", " ").strip()

    voice_matches = re.findall(r"\[\[VOICE_START\]\](.*?)\[\[VOICE_END\]\]", raw, re.DOTALL)
    voice_full_text = " ".join(m.strip() for m in voice_matches).strip() if voice_matches else raw

    display_text = re.sub(r"\[\[VOICE_START\]\].*?\[\[VOICE_END\]\]", "", raw, flags=re.DOTALL).strip()
    return display_text, voice_full_text


# =========================
# 7) 準備本頁：PDF + Gemini + TTS + 字幕節奏
# =========================
def prepare_page_packet(api_key: str, pdf_path: str, page_num: int):
    img, total_pages = load_pdf_page_image(pdf_path, page_num)
    if img is None:
        return None

    display_text, voice_text = gemini_generate_page(api_key, page_num, img)
    audio_html, duration_sec, captions = run_async(generate_voice_and_meta(voice_text))

    n = max(1, len(captions))
    cap_interval_ms = max(250, int((duration_sec / n) * 1000))  # 最少 0.25s

    return {
        "page_num": page_num,
        "total_pages": total_pages,
        "img": img,
        "display_text": display_text,
        "audio_html": audio_html,
        "captions": captions,
        "cap_interval_ms": cap_interval_ms,
    }


# =========================
# 8) Sidebar：金鑰 & 選單
# =========================
st.sidebar.title("打開實驗室大門-金鑰")

st.sidebar.markdown("""
<div class="info-box">
<b>📢 版本說明</b><br>
✅ 每次只講 1 頁<br>
✅ 逐句字幕 + 自動翻頁<br>
</div>
""", unsafe_allow_html=True)

api_key = st.sidebar.text_input("🔑 實驗室啟動金鑰（Gemini API Key）", type="password")

vol_select = st.sidebar.selectbox("📚 冊別選擇", ["第一冊", "第二冊", "第三冊", "第四冊", "第五冊", "第六冊"], index=3)
chap_select = st.sidebar.selectbox("🧪 章節選擇", ["第一章", "第二章", "第三章", "第四章", "第五章", "第六章"], index=2)
start_page = st.sidebar.number_input("🏁 起始頁碼", 1, 500, 1)

filename = f"{vol_select}_{chap_select}.pdf"
pdf_path = os.path.join("data", filename)


# =========================
# 9) Session state
# =========================
if "class_started" not in st.session_state:
    st.session_state.class_started = False
if "packet" not in st.session_state:
    st.session_state.packet = None
if "cap_idx" not in st.session_state:
    st.session_state.cap_idx = 0


# =========================
# 10) 首頁：開始
# =========================
if not st.session_state.class_started:
    st.markdown("### ✅ 字幕模式：一句一句跳，播完自動翻頁")
    st.divider()

    if st.button("🏃‍♀️ 開始上課", type="primary", use_container_width=True):
        if not api_key:
            st.warning("請先輸入 Gemini API Key")
        elif not os.path.exists(pdf_path):
            st.error(f"📂 找不到講義文件：{filename}（請確認 data/ 內有該檔案）")
        else:
            with st.spinner("曉臻正在備課中..."):
                pkt = prepare_page_packet(api_key, pdf_path, int(start_page))
                if pkt is None:
                    st.error("❌ 起始頁超出 PDF 範圍")
                else:
                    st.session_state.packet = pkt
                    st.session_state.cap_idx = 0
                    st.session_state.class_started = True
                    st.rerun()

else:
    # =========================
    # 11) 上課中：字幕 + 自動翻頁
    # =========================
    pkt = st.session_state.packet
    if pkt is None:
        st.session_state.class_started = False
        st.rerun()

    st.success(f"🔔 上課中：第 {pkt['page_num']} / {pkt['total_pages']} 頁")

    st.markdown(pkt["audio_html"], unsafe_allow_html=True)
    st.image(pkt["img"], caption=f"🏁 第 {pkt['page_num']} 頁講義", use_container_width=True)

    # 字幕
    cap_box = st.empty()
    captions = pkt["captions"]
    idx = st.session_state.cap_idx

    if captions:
        line = captions[min(idx, len(captions) - 1)]
        cap_box.markdown(
            f"""
            <div style="
                position: sticky; bottom: 0;
                padding: 14px 16px;
                border: 2px solid #000;
                border-radius: 14px;
                background: #fff;
                font-size: 24px;
                text-align: center;
                line-height: 1.4;
                margin-top: 12px;
            ">{line}</div>
            """,
            unsafe_allow_html=True
        )

    # 每隔 cap_interval_ms 刷新一次
    st_autorefresh(interval=pkt["cap_interval_ms"], key="caption_tick")
    st.session_state.cap_idx += 1

    # 本頁字幕播完 -> 下一頁
    if captions and st.session_state.cap_idx >= len(captions):
        next_page = pkt["page_num"] + 1
        if next_page > pkt["total_pages"]:
            st.success("✅ 全部頁面講完了！這就是自然科學 the 真理！")
            st.session_state.class_started = False
            st.session_state.packet = None
            st.session_state.cap_idx = 0
            st.stop()

        with st.spinner(f"翻頁中...準備第 {next_page} 頁"):
            new_pkt = prepare_page_packet(api_key, pdf_path, next_page)
            if new_pkt is None:
                st.error("❌ 下一頁讀取失敗")
                st.session_state.class_started = False
                st.session_state.packet = None
                st.session_state.cap_idx = 0
                st.stop()
            else:
                st.session_state.packet = new_pkt
                st.session_state.cap_idx = 0
                st.rerun()

    with st.expander("📜 本頁完整文字稿（顯示稿 / 含 LaTeX）"):
        st.markdown(pkt["display_text"])

    if st.button("🏁 下課休息（回到首頁）", use_container_width=True):
        st.session_state.class_started = False
        st.session_state.packet = None
        st.session_state.cap_idx = 0
        st.rerun()
