import streamlit as st
import google.generativeai as genai
import os, re, base64, io, asyncio
from PIL import Image

# PDF
import fitz  # pymupdf

# TTS
import edge_tts
from mutagen.mp3 import MP3

# Auto refresh
from streamlit_autorefresh import st_autorefresh


# =========================
# 0) Streamlit 基本設定 & 風格
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
# 1) 你的 SYSTEM PROMPT（原樣保留）
# =========================
SYSTEM_PROMPT = r"""
你是資深自然科學助教曉臻。你現在要進行一場約 20 分鐘的深度講義導讀。
每一頁「顯示稿」中，必須明確包含以下三個段落標題，且順序固定：
【曉臻老師上課逐字說明】
【知識點總結】
【常見考點提醒】

⚠️【曉臻老師上課逐字說明】必須是口語、白話、像真的老師在講課
⚠️ 不得放入 [[VOICE_START]] 標籤

1. 【深度解說與擴充】：
   - ⚠️ 每一頁解說必須超過 250 字，包含實驗細節、圖表數值解析與觀念推導。
   - 每一頁內容解說完畢後，必須進行該頁的「知識點總結」與「常見考點提醒」。

2. ⚠️【顯示稿規範】：
