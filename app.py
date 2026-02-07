import os, re, io, time, base64, asyncio
import streamlit as st
import google.generativeai as genai
import fitz  # pymupdf
from PIL import Image
import edge_tts
from mutagen.mp3 import MP3
from streamlit_autorefresh import st_autorefresh


# =========================
# A) 設定 & 風格
# =========================
st.set_page_config(page_title="臻·極速自然能量域", layout="wide", initial_sidebar_state="expanded")

st.markdown("""
<style>
:root { color-scheme: light !important; }
.stApp, [data-testid="stAppViewContainer"], .stMain, [data-testid="stHeader"] { background:#fff !important; }
[data-testid="stSidebar"] { min-width: 320px !important; max-width: 320px !important; }
[data-testid="stWidgetLabel"] div, [data-testid="stWidgetLabel"] p { background:transparent !important; border:none !important; box-shadow:none !important; padding:0 !important; }
html, body, .stMarkdown, p, label, li, h1, h2, h3, .stButton button, a {
  color:#000 !important; font-family:'HanziPen SC','翩翩體',sans-serif !important;
}
.stButton button { border:2px solid #000 !important; background:#fff !important; font-weight:bold !important; }
.box { border:1px solid #ddd; padding:12px; border-radius:10px; background:#fafafa; }
</style>
""", unsafe_allow_html=True)

st.title("🏃‍♀️ 臻 · 極速自然能量域")
st.markdown("### 🔬 曉臻老師：一次講 5 頁（逐句字幕 + 自動翻頁）")
st.divider()


# =========================
# B) 讀 prompt.txt（避免被截斷）
# =========================
def load_prompt(path="prompt.txt"):
    if not os.path.exists(path):
        st.error(f"❌ 找不到 {path}，請建立 prompt.txt 並貼上你的 SYSTEM_PROMPT")
        st.stop()
    with open(path, "r", encoding="utf-8") as f:
        return f.read().strip()

SYSTEM_PROMPT = load_prompt("prompt.txt")


# =========================
# C) 小工具
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

def split_to_captions(text: str):
    t = re.sub(r"\s+", " ", text.strip())
    parts = re.split(r"(?<=[。！？；…])\s*", t)
    parts = [p.strip() for p in parts if p.strip()]
    return parts if parts else [t]


# =========================
# D) PDF：頁數 & 轉圖（縮小避免 Vision 太慢）
# =========================
@st.cache_data(show_spinner=False)
def pdf_page_count(pdf_path: str) -> int:
    doc = fitz.open(pdf_path)
    return len(doc)

@st.cache_data(show_spinner=False)
def pdf_page_png(pdf_path: str, page_1based: int, zoom: float = 1.0) -> bytes:
    doc = fitz.open(pdf_path)
    idx = page_1based - 1
    if idx < 0 or idx >= len(doc):
        return b""
    pix = doc.load_page(idx).get_pixmap(matrix=fitz.Matrix(zoom, zoom))
    return pix.tobytes("png")

def png_to_pil(png_bytes: bytes) -> Image.Image:
    return Image.open(io.BytesIO(png_bytes))


# =========================
# E) Gemini：產生顯示稿+語音稿（60秒 timeout）
# =========================
def gemini_make_text(api_key: str, page_num: int, page_img: Image.Image):
    genai.configure(api_key=api_key)
    model = genai.GenerativeModel("models/gemini-2.0-flash")  # 先求穩與快

    t0 = time.time()
    res = model.generate_content(
        [f"{SYSTEM_PROMPT}\n導讀P.{page_num}內容。", page_img],
        request_options={"timeout": 60}
    )
    raw = (res.text or "").replace("\u00a0", " ").strip()
    st.caption(f"✅ Gemini 完成（{time.time()-t0:.1f}s）")

    # 語音稿
    voice_matches = re.findall(r"\[\[VOICE_START\]\](.*?)\[\[VOICE_END\]\]", raw, re.DOTALL)
    voice_text = " ".join(m.strip() for m in voice_matches).strip() if voice_matches else raw

    # 顯示稿
    display_text = re.sub(r"\[\[VOICE_START\]\].*?\[\[VOICE_END\]\]", "", raw, flags=re.DOTALL).strip()
    return display_text, voice_text


# =========================
# F) TTS：產 mp3 + 逐句字幕（60秒 timeout）
# =========================
async def tts_make_audio(text: str):
    voice_text = text.replace("---PAGE_SEP---", " ")
    voice_text = voice_text.replace("$", "")
    voice_text = voice_text.replace("[[VOICE_START]]", "").replace("[[VOICE_END]]", "")
    voice_text = re.sub(r"[<>#@*_=]", "", voice_text)

    communicate = edge_tts.Communicate(voice_text, "zh-TW-HsiaoChenNeural", rate="-2%")
    audio_data = b""
    async for chunk in communicate.stream():
        if chunk["type"] == "audio":
            audio_data += chunk["data"]

    dur = MP3(io.BytesIO(audio_data)).info.length
    b64 = base64.b64encode(audio_data).decode()
    audio_html = f"""
    <audio controls autoplay style="width:100%">
      <source src="data:audio/mp3;base64,{b64}" type="audio/mp3">
    </audio>
    """
    captions = split_to_captions(voice_text)
    return audio_html, dur, captions

def make_page_packet(api_key: str, pdf_path: str, page_num: int):
    png = pdf_page_png(pdf_path, page_num, zoom=1.0)  # ✅ 重要：縮小
    if not png:
        return None
    img = png_to_pil(png)

    # 1) Gemini
    display_text, voice_text = gemini_make_text(api_key, page_num, img)

    # 2) TTS（加 60 秒 timeout，避免卡死）
    t0 = time.time()
    try:
        audio_html, dur, captions = run_async(asyncio.wait_for(tts_make_audio(voice_text), timeout=60))
    except Exception as e:
        raise RuntimeError(f"TTS 失敗或超時：{e}")
    st.caption(f"✅ TTS 完成（{time.time()-t0:.1f}s）")

    interval_ms = max(350, int((dur / max(1, len(captions))) * 1000))
    return {
        "page_num": page_num,
        "img": img,
        "display_text": display_text,
        "audio_html": audio_html,
        "captions": captions,
        "interval_ms": interval_ms,
    }


# =========================
# G) Sidebar：選冊/章/頁 → 先預覽，再開始
# =========================
st.sidebar.markdown('<div class="box"><b>流程</b><br>1) 填 API key<br>2) 選冊/章（立刻預覽）<br>3) 選起始頁<br>4) 開始 → 一次講 5 頁</div>', unsafe_allow_html=True)
api_key = st.sidebar.text_input("🔑 Gemini API Key", type="password")

vol = st.sidebar.selectbox("📚 冊別", ["第一冊","第二冊","第三冊","第四冊","第五冊","第六冊"], index=3)
chap = st.sidebar.selectbox("🧪 章節", ["第一章","第二章","第三章","第四章","第五章","第六章"], index=2)

filename = f"{vol}_{chap}.pdf"
pdf_path = os.path.join("data", filename)


# =========================
# H) Session state（只管 5 頁）
# =========================
if "mode" not in st.session_state: st.session_state.mode = "preview"  # preview/teach/break
if "start_page" not in st.session_state: st.session_state.start_page = 1
if "end_page" not in st.session_state: st.session_state.end_page = 5
if "pkt" not in st.session_state: st.session_state.pkt = None
if "cap_i" not in st.session_state: st.session_state.cap_i = 0
if "cached_key" not in st.session_state: st.session_state.cached_key = ""


# =========================
# I) 預覽區：選章節就載入 PDF
# =========================
st.subheader("📄 講義預覽（選章節即載入）")

if not os.path.exists(pdf_path):
    st.error(f"📂 找不到：{filename}（請確認 data/ 內有這份 PDF）")
    st.stop()

total = pdf_page_count(pdf_path)
col1, col2 = st.columns([1, 2])

with col1:
    sp = st.number_input("🏁 起始頁（本段講 5 頁）", 1, max(1, total), st.session_state.start_page)
    st.session_state.start_page = int(sp)
    st.session_state.end_page = min(int(sp) + 4, total)
    st.write(f"📌 範圍：{st.session_state.start_page}～{st.session_state.end_page}")

with col2:
    prev = pdf_page_png(pdf_path, st.session_state.start_page, zoom=1.2)
    if prev:
        st.image(prev, caption=f"預覽：第 {st.session_state.start_page} 頁", use_container_width=True)

st.divider()


# =========================
# J) 開始上課
# =========================
if st.session_state.mode in ["preview", "break"]:
    if st.button("🏃‍♀️ 開始上課（一次講 5 頁）", type="primary", use_container_width=True):
        key_use = api_key.strip() if api_key else st.session_state.cached_key
        if not key_use:
            st.warning("請先輸入 Gemini API Key")
            st.stop()

        st.session_state.cached_key = key_use
        st.session_state.cap_i = 0
        page_now = st.session_state.start_page

        with st.spinner(f"備課中：第 {page_now} 頁（首次會比較久）..."):
            st.session_state.pkt = make_page_packet(key_use, pdf_path, page_now)
            st.session_state.mode = "teach"
            st.rerun()


# =========================
# K) 上課模式：逐句字幕 + 自動翻頁（到第 5 頁停）
# =========================
if st.session_state.mode == "teach":
    pkt = st.session_state.pkt
    if pkt is None:
        st.session_state.mode = "preview"
        st.rerun()

    st.success(f"🔔 上課中：第 {pkt['page_num']} 頁（本段：{st.session_state.start_page}～{st.session_state.end_page}）")
    st.markdown(pkt["audio_html"], unsafe_allow_html=True)
    st.image(pkt["img"], caption=f"🏁 第 {pkt['page_num']} 頁講義", use_container_width=True)

    cap_box = st.empty()
    caps = pkt["captions"]
    i = st.session_state.cap_i
    if caps:
        line = caps[min(i, len(caps)-1)]
        cap_box.markdown(
            f"""<div style="position:sticky;bottom:0;padding:14px 16px;border:2px solid #000;border-radius:14px;background:#fff;font-size:24px;text-align:center;line-height:1.4;margin-top:12px;">{line}</div>""",
            unsafe_allow_html=True
        )

    st_autorefresh(interval=pkt["interval_ms"], key="tick")
    st.session_state.cap_i += 1

    # 本頁結束 → 下一頁 / 或 5 頁結束
    if caps and st.session_state.cap_i >= len(caps):
        next_page = pkt["page_num"] + 1

        if next_page > st.session_state.end_page:
            st.session_state.mode = "break"
            st.session_state.pkt = None
            st.session_state.cap_i = 0
            st.rerun()

        with st.spinner(f"翻頁備課：第 {next_page} 頁..."):
            key_use = st.session_state.cached_key
            st.session_state.pkt = make_page_packet(key_use, pdf_path, next_page)
            st.session_state.cap_i = 0
            st.rerun()

    with st.expander("📜 本頁完整文字稿（顯示稿）"):
        st.markdown(pkt["display_text"])

    if st.button("🏁 直接回預覽", use_container_width=True):
        st.session_state.mode = "preview"
        st.session_state.pkt = None
        st.session_state.cap_i = 0
        st.rerun()


# =========================
# L) 休息模式：下一段 5 頁
# =========================
if st.session_state.mode == "break":
    st.success("✅ 本段 5 頁講完！休息一下～")
    c1, c2 = st.columns(2)

    with c1:
        if st.button("➡️ 下一段 5 頁（繼續）", type="primary", use_container_width=True):
            next_start = st.session_state.end_page + 1
            if next_start > total:
                st.info("已到最後一頁。")
                st.session_state.mode = "preview"
                st.rerun()

            st.session_state.start_page = next_start
            st.session_state.end_page = min(next_start + 4, total)
            st.session_state.cap_i = 0

            with st.spinner(f"備課中：第 {next_start} 頁..."):
                st.session_state.pkt = make_page_packet(st.session_state.cached_key, pdf_path, next_start)
                st.session_state.mode = "teach"
                st.rerun()

    with c2:
        if st.button("🏁 回預覽（重新選頁）", use_container_width=True):
            st.session_state.mode = "preview"
            st.session_state.pkt = None
            st.session_state.cap_i = 0
            st.rerun()
