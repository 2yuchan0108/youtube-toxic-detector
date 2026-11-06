import csv
import io
import os
import re

import pandas as pd
import requests
import streamlit as st

from detector import LEVEL_NAME, detect

st.set_page_config(page_title="유튜브 악플 탐지기", page_icon="🛡️", layout="wide")

MODEL_NAME = "smilegate-ai/kor_unsmile"
DICT_SCORE = {3: 0.95, 2: 0.80, 1: 0.60}


def get_key() -> str:
    try:
        if "YOUTUBE_API_KEY" in st.secrets:
            return st.secrets["YOUTUBE_API_KEY"]
    except Exception:
        pass
    return os.environ.get("YOUTUBE_API_KEY", "")


@st.cache_resource(show_spinner="AI 모델(Smilegate UnSmile) 불러오는 중... 처음에는 몇 분 걸립니다")
def load_model():
    """모델을 못 불러오면(메모리 부족 등) None을 돌려주고 사전 탐지만 씁니다."""
    try:
        from transformers import AutoModelForSequenceClassification, AutoTokenizer, TextClassificationPipeline
        tok = AutoTokenizer.from_pretrained(MODEL_NAME)
        mdl = AutoModelForSequenceClassification.from_pretrained(MODEL_NAME)
        return TextClassificationPipeline(model=mdl, tokenizer=tok, top_k=None,
                                          function_to_apply="sigmoid", truncation=True, max_length=300)
    except Exception as e:  # noqa: BLE001
        st.session_state["model_error"] = str(e)[:200]
        return None


def video_id(u: str):
    u = u.strip()
    m = re.search(r"(?:v=|/shorts/|youtu\.be/|/embed/|/live/)([A-Za-z0-9_-]{11})", u) or re.fullmatch(r"([A-Za-z0-9_-]{11})", u)
    return m.group(1) if m else None


def yt(path: str, **params):
    d = requests.get(f"https://www.googleapis.com/youtube/v3/{path}", params=params, timeout=20).json()
    if "error" in d:
        reason = (d["error"].get("errors") or [{}])[0].get("reason", "")
        msg = {"commentsDisabled": "이 영상은 댓글이 꺼져 있습니다.",
               "quotaExceeded": "오늘 YouTube API 사용량을 모두 썼습니다. 내일 다시 시도해 주세요.",
               "keyInvalid": "API 키가 올바르지 않습니다."}.get(reason, f"YouTube API 오류: {d['error'].get('message', reason)}")
        raise RuntimeError(msg)
    return d


def fetch_comments(vid, key, limit, progress):
    out, token = [], None
    while len(out) < limit:
        p = dict(part="snippet,replies", videoId=vid, maxResults=100, textFormat="plainText", order="relevance", key=key)
        if token:
            p["pageToken"] = token
        d = yt("commentThreads", **p)
        for it in d.get("items", []):
            t = it["snippet"]["topLevelComment"]["snippet"]
            out.append({"작성자": t["authorDisplayName"], "댓글": t["textDisplay"], "좋아요": t.get("likeCount", 0), "구분": "댓글"})
            for r in it.get("replies", {}).get("comments", []):
                s = r["snippet"]
                out.append({"작성자": s["authorDisplayName"], "댓글": s["textDisplay"], "좋아요": s.get("likeCount", 0), "구분": "답글"})
        progress(min(len(out), limit) / limit)
        token = d.get("nextPageToken")
        if not token:
            break
    return out[:limit]


def analyze(comments, use_model):
    """사전으로 먼저 거르고, 확실하지 않은 댓글만 모델로 판별합니다."""
    rows = [dict(c, 점수=0.0, 강도="", 유형="", 근거="") for c in comments]
    for r in rows:
        d = detect(r["댓글"])
        if d:
            r.update(점수=DICT_SCORE[d["level"]], 강도=LEVEL_NAME[d["level"]], 유형=", ".join(d["cats"]), 근거="사전: " + ", ".join(d["words"]))
    pipe = load_model() if use_model else None
    if pipe:
        todo = [r for r in rows if r["점수"] < 0.95]
        for i in range(0, len(todo), 32):
            batch = todo[i:i + 32]
            for r, scores in zip(batch, pipe([b["댓글"] for b in batch])):
                bad = sorted((s for s in scores if s["label"] != "clean"), key=lambda s: -s["score"])
                if bad and bad[0]["score"] > r["점수"]:
                    s = round(bad[0]["score"], 2)
                    r.update(점수=s, 강도="강" if s >= .9 else "중" if s >= .75 else "약" if s >= .6 else "",
                             유형=", ".join(x["label"] for x in bad if x["score"] >= .5) or bad[0]["label"],
                             근거=(r["근거"] + " / " if r["근거"] else "") + f"AI: {bad[0]['label']} {s}")
    return pd.DataFrame(rows), pipe is not None


# ───────── 화면 ─────────
st.title("🛡️ 유튜브 악플 탐지기")
st.caption("영상 주소를 넣으면 댓글에서 욕설·비하·혐오·위협 표현을 찾아줍니다. 사전 + Smilegate AI 결합 방식")

key = get_key()
if not key:
    st.error("API 키가 설정되지 않았습니다. Streamlit의 Secrets에 YOUTUBE_API_KEY를 추가하세요.")
    st.stop()

with st.form("f"):
    url = st.text_input("유튜브 영상 주소", placeholder="https://www.youtube.com/watch?v=...")
    c1, c2, c3 = st.columns(3)
    limit = c1.select_slider("가져올 댓글 수", [100, 300, 500, 1000], value=300)
    min_level = c2.selectbox("최소 악플 강도", ["약 이상 (민감)", "중 이상", "강 이상 (확실한 것만)"], index=1)
    use_model = c3.checkbox("AI 모델도 사용", value=True, help="끄면 사전만 사용해 더 빠릅니다")
    go = st.form_submit_button("분석하기", type="primary")

if go:
    vid = video_id(url or "")
    if not vid:
        st.error("올바른 유튜브 주소를 입력해 주세요.")
        st.stop()
    try:
        v = yt("videos", part="snippet", id=vid, key=key)
        if not v["items"]:
            st.error("영상을 찾을 수 없습니다.")
            st.stop()
        bar = st.progress(0.0, text="댓글 가져오는 중...")
        comments = fetch_comments(vid, key, limit, lambda x: bar.progress(x, text="댓글 가져오는 중..."))
        bar.empty()
        if not comments:
            st.info("댓글이 없습니다.")
            st.stop()
        with st.spinner(f"댓글 {len(comments)}개 분석 중..."):
            df, model_used = analyze(comments, use_model)
        st.session_state["res"] = (v["items"][0]["snippet"]["title"], df, model_used)
    except RuntimeError as e:
        st.error(str(e))
        st.stop()

if "res" in st.session_state:
    title, df, model_used = st.session_state["res"]
    th = {"약 이상 (민감)": 0.6, "중 이상": 0.75, "강 이상 (확실한 것만)": 0.9}[min_level]
    bad = df[df["점수"] >= th].sort_values(["점수", "좋아요"], ascending=False)
    st.subheader(f"🎬 {title}")
    if use_model and not model_used:
        st.warning("AI 모델을 불러오지 못해 사전 탐지만 사용했습니다.")
    m = st.columns(4)
    m[0].metric("분석한 댓글", len(df))
    m[1].metric("악플로 의심", len(bad))
    m[2].metric("악플 비율", f"{len(bad) / len(df) * 100:.1f}%")
    m[3].metric("강도 '강'", int((bad["강도"] == "강").sum()))
    if len(bad):
        cats = bad["유형"].str.split(", ").explode().value_counts()
        st.bar_chart(cats)
        pick = st.multiselect("유형 필터", list(cats.index))
        view = bad[bad["유형"].apply(lambda s: not pick or any(p in s.split(", ") for p in pick))]
        st.dataframe(view[["강도", "점수", "유형", "댓글", "근거", "작성자", "좋아요", "구분"]], use_container_width=True, hide_index=True)
        buf = io.StringIO()
        view.to_csv(buf, index=False, quoting=csv.QUOTE_ALL)
        st.download_button("CSV 저장", "﻿" + buf.getvalue(), "toxic-comments.csv", "text/csv")
    else:
        st.success("기준에 맞는 악플이 없습니다.")
st.caption("자동 탐지는 참고용입니다. 비꼬는 말은 놓칠 수 있고 일반 대화가 잘못 잡힐 수도 있습니다.")
