# 유튜브 악플 탐지기

유튜브 영상 주소를 넣으면 댓글을 가져와 사전과 Smilegate AI(`smilegate-ai/kor_unsmile`)로 악플을 찾아줍니다.

## 실행
```
pip install -r requirements.txt
streamlit run app.py
```
API 키는 `.streamlit/secrets.toml`(Git에 올라가지 않음) 또는 환경변수 `YOUTUBE_API_KEY`로 설정합니다.
예시는 `.streamlit/secrets.toml.example` 참고.

## 배포 (Streamlit Community Cloud)
share.streamlit.io → Create app → 이 저장소, `app.py` 선택 → Advanced settings → Secrets에 `YOUTUBE_API_KEY = "..."` 입력.
AI 모델이 메모리 문제로 안 올라가면 `requirements.txt`에서 `transformers`, `torch`를 지우면 사전 전용으로 동작합니다.
