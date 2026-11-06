"""사전 기반 한국어/영어 악플 탐지 + (선택) Smilegate UnSmile 모델."""
import re
import unicodedata

# ───────── 사전: (단어, 강도 1약~3강, 유형) ─────────
DICT = []


def _add(cat, lvl, words):
    DICT.extend((w, lvl, cat) for w in words.split())


_add("욕설", 3, "씨발 시발 씨팔 시팔 씨빨 시빨 씨벌 시벌 쉬발 슈발 씨바 씹새 씹년 씹놈 씹팔 좆 좇같 개새끼 개새 개세끼 개색 엠창 앰창 지랄 염병 육시랄")
_add("욕설", 2, "병신 븅신 빙신 존나 존내 졸라 미친놈 미친년 미친새끼 꺼져 닥쳐 아가리 닥치")
_add("욕설", 1, "새끼 쓰레기 시끄러 꺼지")
_add("비하·인신공격", 2, "찐따 정신병자 인간말종 호로 호로새끼 한심 돌대가리 대가리 머저리 등신 또라이 쓰렉 병맛 버러지 기생충 모지리 애자 거지새끼 못생")
_add("비하·인신공격", 3, "걸레 창녀 창년 화냥 느금마 니애미 느그애미 애미뒤 니엄마 느검마")
_add("혐오표현", 3, "한남충 김치녀 된장녀 맘충 틀딱 급식충 짱깨 쪽바리 쪽발이 똥남아 전라디언 경상디언 페미년 메갈년 장애인새끼 똥꼬충 게이새끼 호모새끼 흑형 홍어택배 노인충 개독 한녀 한남")
_add("혐오표현", 2, "일베 메갈 페미나치 급식 틀니 장애")
_add("위협", 3, "죽어버려 죽어라 죽어야 뒤져라 뒤져버려 뒤질래 죽여버 죽이고싶 죽여주 죽일거 칼로찔 패죽 밟아버 자살해 자살이나 뒤지고싶 목매")
_add("성적표현", 3, "섹스하 따먹 빨아줘 야동 벗어봐 몸매평가 가슴 성폭행 강간 걸레같")
_add("성적표현", 2, "섹시 변태 발정 음란")
_add("욕설", 3, "fuck shit bitch asshole bastard cunt motherfucker")
_add("혐오표현", 3, "nigger faggot retard tranny")
_add("위협", 3, "kys killyourself")
_add("욕설", 2, "stfu wtf dumbass idiot moron")

JAMO = [("ㅅㅂ", 3, "욕설"), ("ㅆㅂ", 3, "욕설"), ("ㅅㅍ", 3, "욕설"), ("ㅂㅅ", 3, "욕설"), ("ㅄ", 3, "욕설"),
        ("ㅈㄹ", 2, "욕설"), ("ㅁㅊ", 2, "욕설"), ("ㅅㄲ", 2, "욕설"), ("ㄲㅈ", 2, "욕설"), ("ㄷㅊ", 2, "욕설"),
        ("ㅈㄴ", 2, "욕설"), ("ㄴㄱㅁ", 3, "비하·인신공격"), ("ㅇㅁㅊ", 3, "욕설"), ("ㅂㅈ", 3, "성적표현")]

ALLOW = ("시발점 시발역 시발택시 시발행 시바견 시바이누 시바스 시바타 시바사키 새끼고양이 새끼강아지 새끼손가락 "
         "새끼줄 새끼오리 새끼새 새끼곰 새끼돼지 새끼호랑이 새끼사자 새끼양 새끼토끼 새끼발가락 새끼고래 병신년 존나다 대가리큰 집대가리").split()
ALLOW_RE = re.compile("|".join(ALLOW))
NOBOUND = {"fuck", "shit", "bitch"}  # bullshit 처럼 앞에 글자가 붙어도 잡는 영어 단어
_EN_RE = {w: re.compile(r"(?<![a-z])" + w) for w, _, _ in DICT if re.fullmatch(r"[a-z]+", w) and w not in NOBOUND}

LEVEL_NAME = {3: "강", 2: "중", 1: "약"}


def normalize(s: str) -> str:
    s = unicodedata.normalize("NFKC", s).lower()
    s = re.sub(r"(?<=[가-힣])[0-9](?=[가-힣])", "", s)                    # 시1발 → 시발
    s = re.sub(r"(?<=[가-힣a-z])[^\w\s](?=[가-힣a-z])", "", s)            # 시.발 → 시발
    s = re.sub(r"(^|\s)((?:[가-힣]\s)+[가-힣])(?=\s|$)", lambda m: m.group(1) + re.sub(r"\s", "", m.group(2)), s)  # 씨 발 놈
    s = re.sub(r"(.)\1{3,}", r"\1\1", s)                                  # 과한 반복 축소
    return s


def detect(text: str):
    """사전 탐지. 없으면 None, 있으면 {level, words, cats}."""
    n = normalize(text)
    n = re.sub(r"(?<![a-z])(?:[a-z]\s){3,}[a-z](?![a-z])", lambda m: re.sub(r"\s", "", m.group(0)), n)  # f u c k
    n = ALLOW_RE.sub(" ", n)
    hits = {}
    for w, lvl, cat in DICT:
        if w in hits:
            continue
        if w in _EN_RE:
            ok = bool(_EN_RE[w].search(n))
        else:
            ok = w in n
        if ok:
            hits[w] = (lvl, cat)
    # 자음 표기(ㅅㅂ 등)는 NFKC 전에 원문에서 검사 (정규화하면 자음 모양이 바뀜)
    runs = re.findall(r"[ㄱ-ㅎㅏ-ㅣ]+", re.sub(r"[^\w\s]", "", text.lower()))
    for p, lvl, cat in JAMO:
        if any(p in r for r in runs):
            hits[p] = (lvl, cat)
    if not hits:
        return None
    return {"level": max(l for l, _ in hits.values()), "words": list(hits), "cats": sorted({c for _, c in hits.values()})}
