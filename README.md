# KakaoChat AI

카카오톡 오픈챗방에 상주하면서 모든 대화를 기억하고, 질문에 답하고, 좋은 지식을 큐레이션하는 AI 에이전트.

## 문제

카카오톡 오픈챗방은 한국 최대의 비공식 지식 공유 공간이지만, 대화가 흘러가면 사라진다. 검색 안 되고, 스레드 없고, 북마크 공유도 안 된다.

> "어제 누가 올린 그 링크 뭐였지?" — 아무도 답하지 못한다.

KakaoChat AI는 이 문제를 해결한다.

## 기능

- **대화 수집 + 메모리**: 모든 메시지를 벡터DB에 저장, "그 얘기 누가 했어?" 검색
- **지식 큐레이션**: 시그널/노이즈 자동 분류, TIL 추출, URL 감지
- **자연스러운 참여**: @멘션, 질문 감지 시 맥락 기반 응답
- **중복 질문 감지**: 유사 질문 발견 시 과거 답변 자동 소환
- **전문가 태깅**: 주제별 전문가 추적 + 질문 시 추천
- **Weekly Digest**: 매주 월요일 주간 핵심 논의 LLM 요약 자동 포스팅
- **수집 전용 모드**: 응답 없이 수집만 하는 passive 모드 지원

## 아키텍처

```
[카카오톡 앱 (안드로이드)]
    |  알림 발생
    v
[Android Bridge App] (Kotlin)
    |  NotificationListenerService → JSON 파싱 → WebSocket 전송
    v
[AI Server] (Python/FastAPI)
    ├── Message Pipeline (수신 → 큐레이터 분류 → Mem0 저장 → 전문가 추적 → 시그널 수집)
    ├── Mem0 Memory Engine (ChromaDB + HuggingFace 임베딩)
    ├── Knowledge Curator (시그널/노이즈 분류, TIL 추출, URL 감지)
    ├── Participation Engine (멘션/질문 감지, 중복감지, 전문가추천, LLM 응답)
    ├── Weekly Digest (APScheduler → LLM 요약 → 자동 포스팅)
    └── response_mode: active / passive / off
```

## 기술 스택

- **서버**: FastAPI (Python 3.11+)
- **메모리 엔진**: Mem0
- **벡터 DB**: ChromaDB
- **임베딩**: intfloat/multilingual-e5-large
- **LLM**: Gemini 2.0 Flash (config에서 교체 가능)
- **스케줄러**: APScheduler
- **브릿지**: Kotlin Android (NotificationListenerService)
- **통신**: WebSocket

## 빠른 시작

### 1. 설치

```bash
git clone https://github.com/YOUR_USERNAME/kakaochat-ai.git
cd kakaochat-ai

python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

cd server
pip install -r requirements.txt
```

### 2. 환경변수 설정

```bash
# Gemini 사용 시
export GEMINI_API_KEY="your-api-key"

# OpenAI 사용 시 (config.yaml에서 LLM 모델 변경 필요)
export OPENAI_API_KEY="your-api-key"
```

### 3. 설정

`server/config.yaml`에서 설정을 조정한다:

```yaml
response_mode: "passive"  # active: 수집+응답 / passive: 수집만 / off: 중지

llm:
  model: "gemini/gemini-2.0-flash"  # 또는 "openai/gpt-4o-mini"

target_rooms: []  # 특정 방만 모니터링 (비어있으면 모든 방)

digest:
  enabled: true
  schedule: "0 8 * * 1"  # 매주 월요일 08:00 KST
```

### 4. 서버 실행

```bash
cd server
python run.py
```

서버가 `ws://0.0.0.0:8765/ws`에서 WebSocket 연결을 대기한다.

### 5. CLI 메모리 검색

```bash
# 검색
python query.py "RAG 얘기 누가 했어?"

# 특정 사용자 필터
python query.py --user 철수 "링크"

# 특정 방 필터
python query.py --room AI스터디 "RAG"

# 전체 메모리 조회
python query.py --all
```

## 운영 모드

| 모드 | 설명 |
|------|------|
| `active` | 수집 + 메모리 + 응답 (Reply Action으로 오픈챗에 전송) |
| `passive` | 수집 + 메모리만 (CLI/API로 질의) |
| `off` | 서버 중지 |

## API 엔드포인트

- `GET /health` — 서버 상태 확인
- `POST /digest/{room}` — 수동 다이제스트 트리거
- `WS /ws` — Android 브릿지 WebSocket 연결

## 메시지 파이프라인

```
메시지 수신
  → Raw 로그 (logs/raw_messages.jsonl)
  → 큐레이터 분류 (NOISE / NORMAL / SIGNAL / TIL)
  → Mem0 저장 (노이즈 제외)
  → 전문가 트래커 (SIGNAL/TIL → 주제별 기여 기록)
  → 시그널 수집 (다이제스트용 signals.jsonl)
  → 참여 엔진 (active 모드일 때)
       ├── 중복 질문 감지 (cosine > 0.9 → 과거 답변 소환)
       ├── 전문가 추천 (주제 매칭)
       └── LLM 응답 생성
```

## 테스트

```bash
cd server
python -m pytest tests/ -v
```

92개 테스트 전체 통과:
- `test_memory_korean.py` — Mem0 한국어 메모리 (10)
- `test_participation.py` — 참여 엔진 (19)
- `test_curator.py` — 지식 큐레이터 (21)
- `test_duplicate.py` — 중복 감지 (10)
- `test_expert.py` — 전문가 태깅 (10)
- `test_digest.py` — Weekly Digest (12)

## 프로젝트 구조

```
server/
├── app/
│   ├── main.py          # 메시지 파이프라인 + 스케줄러
│   ├── memory.py        # Mem0 메모리 엔진
│   ├── curator.py       # 시그널/노이즈 분류
│   ├── participation.py # 참여 엔진 (응답 생성)
│   ├── duplicate.py     # 중복 질문 감지
│   ├── expert.py        # 전문가 추적/추천
│   ├── digest.py        # Weekly Digest 생성
│   ├── models.py        # Pydantic 모델
│   └── config.py        # 설정 로더
├── tests/               # 테스트 (92개)
├── config.yaml          # 서버 설정
├── run.py               # 서버 엔트리포인트
├── query.py             # CLI 메모리 검색
└── requirements.txt     # 의존성
```

## 비용

월 약 $5~25 (Gemini Flash 기준, 1개 방 500~2000 메시지/일)

- 메모리 추출: ~$3~12
- 질의 응답: ~$1~5
- Weekly Digest: ~$0.5
- 서버: 개인 PC + 구형 안드로이드 (무료)

## 로드맵

- [x] v0.1: 서버 뼈대 + 메모리 엔진
- [x] v0.2: 지식 큐레이션 (시그널/노이즈, TIL, URL)
- [x] v0.3: 소셜 기능 (중복 감지, 전문가 태깅)
- [x] v0.4: Weekly Digest
- [ ] v0.5: 다중 채팅방
- [ ] v1.0: 프로덕션 릴리즈

## 라이센스

MIT License
