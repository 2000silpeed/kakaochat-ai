# KakaoChat AI

카카오톡 오픈챗방에 상주하면서 모든 대화를 기억하고, 질문에 답하고, 좋은 지식을 큐레이션하는 AI 에이전트. 오픈소스.

## 문제

카카오톡 오픈챗방은 한국 최대의 비공식 지식 공유 공간이지만, 대화가 흘러가면 사라진다. 검색 안 되고, 스레드 없고, 북마크 공유도 안 된다.

> "어제 누가 올린 그 링크 뭐였지?" — 아무도 답하지 못한다.

KakaoChat AI는 이 문제를 해결한다.

## 기능

- **대화 수집 + 메모리**: 모든 메시지를 벡터DB에 저장, "그 얘기 누가 했어?" 검색
- **지식 큐레이션**: 시그널/노이즈 자동 분류, TIL 추출, URL 감지
- **링크 아카이브**: 공유된 URL 자동 스크래핑 + LLM 요약 + 방별 저장/검색
- **자연스러운 참여**: @멘션, 질문 감지 시 맥락 기반 응답
- **중복 질문 감지**: 유사 질문 발견 시 과거 답변 자동 소환
- **전문가 태깅**: 주제별 전문가 추적 + 질문 시 추천
- **Weekly Digest**: 매주 월요일 주간 핵심 논의 LLM 요약 자동 포스팅
- **다중 채팅방**: 하나의 서버에서 여러 방 동시 관리, 방별 설정/통계
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
    ├── Link Archiver (URL 스크래핑 + LLM 요약)
    ├── Participation Engine (멘션/질문 감지, 중복감지, 전문가추천, LLM 응답)
    ├── Room Registry (다중 채팅방 관리, per-room 설정/통계)
    ├── Weekly Digest (APScheduler → LLM 요약 → 자동 포스팅)
    └── response_mode: active / passive / off
```

## 기술 스택

- **서버**: FastAPI (Python 3.12+)
- **메모리 엔진**: Mem0
- **벡터 DB**: ChromaDB
- **임베딩**: intfloat/multilingual-e5-large
- **LLM**: OpenRouter Gemma 4 31B (무료) / Gemini / OpenAI / Claude Code 세션
- **스케줄러**: APScheduler
- **브릿지**: Kotlin Android (NotificationListenerService)
- **통신**: WebSocket

## 빠른 시작

### Docker (추천)

```bash
git clone https://github.com/2000silpeed/kakaochat-ai.git
cd kakaochat-ai

# 환경변수 설정
cp .env.example .env
# .env 파일에서 API 키 설정

# 실행
docker compose up -d
```

### 수동 설치

```bash
git clone https://github.com/2000silpeed/kakaochat-ai.git
cd kakaochat-ai

python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

cd server
pip install -r requirements.txt
```

### 환경변수

```bash
# OpenRouter (무료 모델 사용 가능, 추천)
export OPENROUTER_API_KEY="sk-or-your-key"

# Gemini (Mem0 내부 LLM용)
export GEMINI_API_KEY="your-key"

# OpenAI (선택)
export OPENAI_API_KEY="your-key"
```

### 설정

`server/config.yaml`:

```yaml
response_mode: "passive"  # active: 수집+응답 / passive: 수집만 / off: 중지

llm:
  model: "openrouter/google/gemma-4-31b-it:free"  # 무료

target_rooms: []  # 특정 방만 모니터링 (비어있으면 모든 방)

# 방별 설정 오버라이드
rooms:
  "AI스터디":
    response_mode: "active"
    llm_model: "claude/session"
```

### 서버 실행

```bash
cd server

# 프로덕션
python run.py

# 개발 (hot reload)
python run.py --dev
```

서버가 `ws://0.0.0.0:8765/ws`에서 WebSocket 연결을 대기한다.

## API 엔드포인트

### 서버

- `GET /health` — 서버 상태 + 활성 방 수
- `WS /ws?token=xxx` — Android 브릿지 WebSocket 연결

### 방 관리

- `GET /rooms` — 활성 방 목록 + 통계
- `GET /rooms/{room}` — 개별 방 상태 + effective config
- `PATCH /rooms/{room}` — 방별 설정 오버라이드 (response_mode, llm_model)

### 링크 아카이브

- `GET /links/{room}?q=keyword&days=7` — 아카이브된 링크 조회

### 다이제스트

- `POST /digest/{room}` — 수동 다이제스트 트리거

### Claude 세션

- `GET /sessions` — Claude 세션 상태 조회
- `POST /clear/{room}` — 세션 초기화

### 인증 (Claude OAuth)

- `POST /auth/register` — 방에 OAuth 토큰 등록
- `DELETE /auth/{room}` — 토큰 삭제
- `GET /auth/rooms` — 등록된 방 목록

## CLI 메모리 검색

```bash
python query.py "RAG 얘기 누가 했어?"
python query.py --user 철수 "링크"
python query.py --room AI스터디 "RAG"
python query.py --all
```

## 메시지 파이프라인

```
메시지 수신
  → Raw 로그 (logs/raw_messages.jsonl)
  → 큐레이터 분류 (NOISE / NORMAL / SIGNAL / TIL)
  → Mem0 저장 (노이즈 제외)
  → 링크 아카이브 (URL 포함 시 → 스크래핑 + 요약)
  → 전문가 트래커 (SIGNAL/TIL → 주제별 기여 기록)
  → 시그널 수집 (다이제스트용 signals.jsonl)
  → 참여 엔진 (active 모드일 때)
       ├── 중복 질문 감지 (cosine > 0.9 → 과거 답변 소환)
       ├── 링크 검색 (관련 아카이브 링크 컨텍스트)
       ├── 전문가 추천 (주제 매칭)
       └── LLM 응답 생성
```

## 테스트

```bash
cd server
python -m pytest tests/ -v
```

150개 테스트 전체 통과.

## 프로젝트 구조

```
kakaochat-ai/
├── docker-compose.yml
├── .env.example
├── README.md
├── LICENSE
└── server/
    ├── Dockerfile
    ├── app/
    │   ├── main.py            # 메시지 파이프라인 + 스케줄러 + REST API
    │   ├── memory.py          # Mem0 메모리 엔진
    │   ├── curator.py         # 시그널/노이즈 분류
    │   ├── participation.py   # 참여 엔진 (응답 생성)
    │   ├── link_archive.py    # URL 스크래핑 + LLM 요약
    │   ├── room_registry.py   # 다중 채팅방 관리
    │   ├── duplicate.py       # 중복 질문 감지
    │   ├── expert.py          # 전문가 추적/추천
    │   ├── digest.py          # Weekly Digest 생성
    │   ├── claude_session.py  # Claude Code 세션 관리
    │   ├── auth.py            # OAuth 토큰 관리
    │   ├── models.py          # Pydantic 모델
    │   └── config.py          # 설정 로더
    ├── tests/                 # 테스트 (150개)
    ├── config.yaml            # 서버 설정
    ├── run.py                 # 서버 엔트리포인트
    ├── query.py               # CLI 메모리 검색
    └── requirements.txt
```

## 비용

OpenRouter 무료 모델 사용 시 **$0/월** (Gemma 4 31B, 분당 20요청 제한).

Gemini Flash 사용 시 월 약 $5~25 (1개 방 500~2000 메시지/일).

## 로드맵

- [x] v0.1: 서버 뼈대 + 메모리 엔진
- [x] v0.2: 지식 큐레이션 (시그널/노이즈, TIL, URL)
- [x] v0.3: 소셜 기능 (중복 감지, 전문가 태깅)
- [x] v0.4: Weekly Digest
- [x] v0.5: 다중 채팅방 + per-room 설정
- [x] 링크 아카이브
- [x] OpenRouter 무료 모델 지원
- [x] Claude Code 세션 연동
- [x] Docker 배포
- [ ] v0.6: 멀티 메신저 (Telegram adapter)
- [ ] v1.0: 안정화 + 커뮤니티 피드백

## 라이센스

MIT License
