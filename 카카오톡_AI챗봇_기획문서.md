# 카카오톡 AI 챗봇 기획문서

## chatgpt-on-wechat (CowAgent) 기반 카카오톡 채널 확장

---

## 1. 프로젝트 개요

### 1.1 원본 프로젝트 (chatgpt-on-wechat / CowAgent)

- **GitHub**: https://github.com/zhayujie/chatgpt-on-wechat
- **언어**: Python 3.7~3.12
- **핵심 기능**: LLM 기반 AI 어시스턴트 (자율 태스크 플래닝, 장기 메모리, 멀티모달, 스킬 시스템)
- **지원 채널**: WeChat, Feishu, DingTalk, QQ, WeCom, Web, Terminal
- **아키텍처**: 채널 추상화 레이어를 통해 플랫폼 독립적으로 동작

### 1.2 목표

CowAgent의 채널 추상화 레이어(`channel/`)에 **카카오톡 채널**을 새로 구현하여,
카카오 i 오픈빌더 스킬 서버 방식으로 카카오톡에서 AI 챗봇을 운영한다.

### 1.3 결론부터: 가능한가?

**가능하다. 단, 핵심 제약이 있다.**

| 항목 | WeChat | 카카오톡 (오픈빌더) |
|------|--------|---------------------|
| 통신 방식 | 장시간 폴링 / WebSocket | Webhook POST (스킬 서버) |
| 응답 시간 제한 | 느슨함 | **5초 타임아웃 (고정)** |
| 스트리밍 | 가능 | 불가능 |
| 이미지 수신 | URL 직접 수신 | URL 수신 가능 |
| 파일 수신 | 가능 | 파일명만 전달, URL 없음 |
| 음성 메시지 | 가능 | 제한적 |
| 사용자 식별 | 고유 ID | userRequest.user.id |

**5초 타임아웃** - LLM 응답은 보통 5~30초 소요되지만, **카카오 공식 콜백 API**로 해결 가능.

---

## 2. 기술 아키텍처

### 2.1 전체 구조

```
사용자 (카카오톡)
    │
    ▼
카카오 i 오픈빌더 (봇 시스템)
    │  POST /skill (SkillPayload JSON)
    ▼
┌─────────────────────────────────┐
│  KakaoTalk Channel Adapter      │  ← 새로 개발
│  (Flask/FastAPI 스킬 서버)       │
│                                 │
│  ┌─ 요청 수신 & 파싱           │
│  ├─ 비동기 LLM 호출 디스패치    │
│  ├─ 즉시 "생각중..." 응답 반환  │
│  └─ 결과 콜백 처리              │
└─────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────┐
│  CowAgent Core                  │
│  ├─ Agent Engine (태스크 플래닝)│
│  ├─ Model Layer (GPT/Claude/..)│
│  ├─ Memory System              │
│  └─ Skills System              │
└─────────────────────────────────┘
```

### 2.2 채널 추상화 레이어 분석

CowAgent는 팩토리 패턴으로 채널을 관리:

```
channel/
├── channel.py           # 기본 Channel 추상 클래스
├── channel_factory.py   # 채널 인스턴스 생성 팩토리
├── chat_channel.py      # 채팅 채널 공통 로직
├── chat_message.py      # 메시지 추상화
├── file_cache.py        # 파일 캐시
├── weixin/              # WeChat 구현
├── wechatmp/            # WeChat 공식계정
├── feishu/              # Feishu
├── dingtalk/            # DingTalk
├── qq/                  # QQ
├── web/                 # Web UI
└── terminal/            # CLI
```

새로 추가할 것:
```
channel/
└── kakao/
    ├── __init__.py
    ├── kakao_channel.py       # Channel 추상 클래스 구현
    ├── kakao_message.py       # ChatMessage 구현
    ├── kakao_skill_server.py  # Flask/FastAPI 스킬 서버
    └── kakao_callback_handler.py # 콜백 API + 폴링 폴백 처리
```

---

## 3. 핵심 기술 과제

### 3.1 5초 타임아웃 해결: 카카오 공식 콜백 API

카카오가 AI 챗봇용으로 **공식 콜백(Callback) 기능**을 제공한다.
별도의 우회 해킹이 아니라, 카카오가 인정한 공식 솔루션.

- **공식 문서**: https://kakaobusiness.gitbook.io/main/tool/chatbot/skill_guide/ai_chatbot_callback_guide
- **참고 오픈소스**: [ChatGee](https://woensug-choi.github.io/ChatGee/) (Flask + OpenAI + 콜백 구현)

#### 콜백 API 동작 원리

```
[사용자] "양자역학 설명해줘"
     │
     ▼
[카카오 서버] → POST 요청 (SkillPayload + callbackUrl 포함)
     │
     ▼
[우리 스킬 서버]
  1단계: 즉시 응답 반환 (< 5초)
     {"version":"2.0", "useCallback": true}
     → 사용자에게 "생각중..." 자동 표시
     │
  2단계: 백그라운드에서 LLM 호출 (시간 제한 없음)
     │
  3단계: LLM 응답 완료 → callbackUrl로 POST 전송 (< 1분)
     → 사용자 카카오톡에 답변이 자동 도착!
```

#### 콜백 API 핵심 스펙

- **callbackUrl**: 카카오가 요청마다 생성하는 1회용 URL
- **유효시간**: 1분 (이 안에 결과를 보내야 함)
- **사용 횟수**: 1회 (한 번 보내면 만료)
- **승인 필요**: 오픈빌더 > 설정 > AI 챗봇 관리에서 신청 (1~2영업일)
- **테스트 제한**: 봇 테스트 환경에서 콜백 완전 지원 안 됨 → 실제 채널에서 테스트

#### 콜백 요청/응답 형식

**1단계 - 즉시 응답 (useCallback 활성화):**
```json
{
  "version": "2.0",
  "useCallback": true,
  "data": {
    "text": "생각하고 있어요... 잠시만 기다려주세요!"
  }
}
```

**2단계 - 콜백 전송 (callbackUrl로 POST):**
```json
{
  "version": "2.0",
  "template": {
    "outputs": [
      {
        "simpleText": {
          "text": "AI가 생성한 답변 텍스트"
        }
      }
    ]
  }
}
```

**카카오 콜백 응답 (성공/실패 확인):**
```json
{
  "taskId": "uuid",
  "status": "SUCCESS",
  "message": "정상 처리",
  "timestamp": 1712600000
}
```

#### 콜백 에러 케이스

- `Invalid callback token` — 1분 초과 또는 이미 사용된 URL
- `Invalid json response` — JSON 형식 오류
- `Invalid skill-json format` — SkillResponse 형식 불일치

#### 폴백 전략: 콜백 미승인 시

콜백 승인 전이나, 콜백 실패 시 대비:

```
[사용자 발화]
    → 즉시 응답: "생각중..." + [결과 확인] quickReply 버튼
    → 백그라운드 LLM 호출 → 결과를 Redis/메모리 저장
    → 사용자가 [결과 확인] 버튼 클릭
    → 저장된 결과 반환
```

#### 권장 전략: 하이브리드 (콜백 우선 + 폴링 폴백)

1. **콜백 승인 완료 시**: 모든 요청에 콜백 API 사용 (사용자 경험 최상)
2. **콜백 미승인/실패 시**: 폴링 방식으로 자동 전환
3. **단순 질문**: 5초 내 직접 응답 시도 (콜백 불필요)

### 3.2 메시지 타입 매핑

#### 수신 (사용자 → 봇)

| CowAgent 내부 타입 | 카카오톡 SkillPayload |
|--------------------|-----------------------|
| TEXT | userRequest.utterance |
| IMAGE | 플러그인으로 이미지 URL 수신 |
| VOICE | 지원 제한적 |
| FILE | 파일명만 수신 (URL 없음) — **미지원** |

#### 발신 (봇 → 사용자)

| CowAgent 출력 | 카카오톡 SkillResponse 타입 |
|---------------|---------------------------|
| 텍스트 응답 | simpleText (최대 1000자) |
| 이미지 응답 | simpleImage (URL 필수) |
| 링크 포함 응답 | textCard + webLink 버튼 |
| 리스트 응답 | listCard |
| 리치 응답 | basicCard (썸네일+설명+버튼) |
| 긴 텍스트 | 여러 simpleText로 분할 (최대 3개 output) |
| 초장문 | simpleText + "더보기" webLink 버튼 |

### 3.3 SkillPayload 요청 파싱

카카오 오픈빌더가 보내는 요청 (콜백 활성화 시 `callbackUrl` 포함):

```json
{
  "intent": {
    "id": "블록ID",
    "name": "블록명"
  },
  "userRequest": {
    "callbackUrl": "https://bot-api.kakao.com/callback/...",
    "timezone": "Asia/Seoul",
    "params": { "surface": "Kakaotalk.plusfriend" },
    "block": { "id": "...", "name": "..." },
    "utterance": "사용자가 입력한 텍스트",
    "lang": "ko",
    "user": {
      "id": "유저고유ID",
      "type": "botUserKey",
      "properties": {}
    }
  },
  "bot": { "id": "봇ID", "name": "봇이름" },
  "action": {
    "name": "액션명",
    "clientExtra": {},
    "params": {},
    "id": "액션ID",
    "detailParams": {}
  }
}
```

> **callbackUrl**: 콜백이 활성화된 블록에서만 포함됨. 1회용이며 1분 내 사용해야 함.

### 3.4 SkillResponse 응답 생성

```json
{
  "version": "2.0",
  "template": {
    "outputs": [
      {
        "simpleText": {
          "text": "AI 응답 텍스트 (최대 1000자)"
        }
      }
    ],
    "quickReplies": [
      {
        "label": "다시 질문하기",
        "action": "message",
        "messageText": "다시 질문할게요"
      }
    ]
  }
}
```

---

## 4. 구현 상세

### 4.1 카카오톡 채널 구현 (kakao_channel.py)

```python
# 핵심 구현 골격

class KakaoChannel(ChatChannel):
    """카카오톡 오픈빌더 스킬 서버 채널"""
    
    channel_type = "kakao"
    
    def startup(self):
        """FastAPI 스킬 서버 시작"""
        # POST /skill 엔드포인트 등록
        # 비동기 처리 워커 시작
        
    def handle_skill_request(self, payload: dict):
        """SkillPayload 수신 처리"""
        # 1. userRequest.utterance 추출
        # 2. user.id로 세션 관리
        # 3. ChatMessage 생성
        # 4. 응답 시간 예측
        # 5-a. 빠른 응답 가능 → 동기 처리 (5초 내)
        # 5-b. 느린 응답 예상 → 비동기 디스패치 + "생각중" 반환
        
    def build_skill_response(self, reply_text, reply_type="text"):
        """CowAgent 응답 → SkillResponse JSON 변환"""
        # 텍스트 길이에 따른 분할
        # 이미지/카드 타입 변환
        # quickReplies 생성
```

### 4.2 콜백 핸들러 (kakao_callback_handler.py)

```python
import httpx
import asyncio

class KakaoCallbackHandler:
    """카카오 공식 콜백 API 기반 비동기 응답 처리"""
    
    def __init__(self):
        self.pending_responses = {}  # user_id → 결과 (폴링 폴백용)
    
    async def process_with_callback(self, callback_url: str, user_id: str, message: str):
        """콜백 방식: 백그라운드에서 LLM 호출 후 callbackUrl로 전송"""
        try:
            answer = await call_llm(message)
            
            # 카카오가 준 callbackUrl로 결과 전송
            async with httpx.AsyncClient() as client:
                resp = await client.post(callback_url, json={
                    "version": "2.0",
                    "template": {
                        "outputs": [{"simpleText": {"text": self._truncate(answer)}}]
                    }
                })
                result = resp.json()
                if result.get("status") != "SUCCESS":
                    # 콜백 실패 시 폴링 저장소에 보관
                    self.pending_responses[user_id] = answer
        except Exception:
            self.pending_responses[user_id] = answer
    
    def build_callback_response(self):
        """콜백 활성화 즉시 응답"""
        return {
            "version": "2.0",
            "useCallback": True,
            "data": {"text": "생각하고 있어요... 잠시만 기다려주세요!"}
        }
    
    def build_polling_response(self):
        """폴백: 콜백 미사용 시 폴링 응답"""
        return {
            "version": "2.0",
            "template": {
                "outputs": [{"simpleText": {"text": "생각하고 있어요... 잠시만요!"}}],
                "quickReplies": [{
                    "label": "결과 확인",
                    "action": "block",
                    "blockId": "CHECK_RESULT_BLOCK_ID"
                }]
            }
        }
    
    def get_polling_result(self, user_id) -> Optional[str]:
        """폴링 폴백: 저장된 결과 조회"""
        return self.pending_responses.pop(user_id, None)
    
    def _truncate(self, text: str, limit: int = 1000) -> str:
        if len(text) <= limit:
            return text
        return text[:limit - 20] + "\n\n...(응답이 잘렸습니다)"
```

### 4.3 config.json 설정 추가

```json
{
  "channel_type": "kakao",
  "kakao": {
    "skill_server_port": 8080,
    "skill_server_host": "0.0.0.0",
    "sync_timeout_sec": 4.5,
    "use_callback": true,
    "callback_timeout_sec": 55,
    "polling_result_ttl_sec": 300,
    "max_text_length": 1000,
    "thinking_message": "생각하고 있어요... 잠시만 기다려주세요!",
    "check_result_block_id": "YOUR_BLOCK_ID_HERE"
  }
}
```

### 4.4 channel_factory.py 수정

```python
# 기존 팩토리에 카카오 채널 등록
def create_channel(channel_type):
    ...
    elif channel_type == "kakao":
        from channel.kakao.kakao_channel import KakaoChannel
        return KakaoChannel()
```

---

## 5. 카카오 i 오픈빌더 설정

### 5.1 사전 준비

1. **카카오톡 채널 생성** (https://center-pf.kakao.com)
2. **카카오 i 오픈빌더 접속** (https://i.kakao.com)
3. **개발 권한 신청** (승인까지 5~7일 소요)
4. **봇 생성** → 채널 연결
5. **콜백 API 승인 신청** → 설정 > AI 챗봇 관리 (승인까지 1~2영업일)
   - 사용 목적과 근거를 작성하여 제출
   - 승인 후 블록 상세에서 "콜백 API 설정" 옵션 활성화

### 5.2 블록 구성

```
[폴백 블록] (모든 미매칭 발화 처리)
    ├─ 스킬: main_skill
    │   └─ URL: https://your-server.com/skill
    └─ 콜백 API 설정: 활성화 ← 승인 후 체크

[결과 확인 블록] (콜백 실패 시 폴링 폴백용)
    └─ 스킬: check_result_skill
        └─ URL: https://your-server.com/skill/check
```

### 5.3 스킬 서버 엔드포인트

```
POST /skill           ← 메인 대화 처리
POST /skill/check     ← 비동기 결과 조회
GET  /health          ← 헬스체크
```

---

## 6. 배포 아키텍처

### 6.1 최소 구성 (개인/소규모)

```
[카카오 오픈빌더] → [ngrok/Cloudflare Tunnel] → [로컬 서버]
                                                    └─ CowAgent + KakaoChannel
```

### 6.2 프로덕션 구성

```
[카카오 오픈빌더]
    │
    ▼
[클라우드 서버 (AWS/GCP/NCP)]
    ├─ Nginx (리버스 프록시 + SSL)
    ├─ CowAgent + KakaoChannel (Gunicorn/Uvicorn)
    ├─ Redis (비동기 결과 저장)
    └─ SQLite/PostgreSQL (메모리/세션)
```

### 6.3 Docker 구성

```dockerfile
# 기존 CowAgent Dockerfile 확장
FROM cowagent:latest

# 카카오 채널 추가 의존성
RUN pip install fastapi uvicorn redis

# 스킬 서버 포트
EXPOSE 8080

# 카카오 채널 모드로 시작
ENV CHANNEL_TYPE=kakao
```

---

## 7. 개발 로드맵

### Phase 0: 카카오 사전 준비 (1주, 병렬 진행)

- [ ] 카카오톡 채널 생성
- [ ] 카카오 i 오픈빌더 개발 권한 신청 (5~7일 소요)
- [ ] **콜백 API 승인 신청** (1~2영업일) ← 가장 먼저!
- [ ] 봇 생성 및 채널 연결

### Phase 1: 기본 텍스트 대화 + 콜백 (2~3주)

- [ ] CowAgent 포크 및 로컬 환경 구성
- [ ] `channel/kakao/` 디렉토리 생성
- [ ] KakaoChannel 클래스 구현 (ChatChannel 상속)
- [ ] KakaoMessage 클래스 구현 (ChatMessage 상속)
- [ ] FastAPI 스킬 서버 구현
- [ ] SkillPayload 파싱 → CowAgent 메시지 변환 (callbackUrl 포함)
- [ ] CowAgent 응답 → SkillResponse 변환
- [ ] channel_factory.py에 kakao 등록
- [ ] **콜백 핸들러 구현** (callbackUrl로 비동기 응답 전송)
- [ ] 동기 응답 (단순 질문 4.5초 내 처리) + 콜백 자동 분기
- [ ] 카카오 오픈빌더 블록 설정 & 콜백 활성화 & 테스트

### Phase 2: 폴링 폴백 + 안정화 (1주)

- [ ] 콜백 실패 시 폴링 폴백 (결과 확인 버튼)
- [ ] 결과 확인 블록 & 스킬 엔드포인트
- [ ] 콜백 에러 핸들링 (토큰 만료, JSON 오류 등)
- [ ] 결과 TTL 및 만료 처리 (Redis 또는 인메모리)

### Phase 3: 리치 메시지 & 멀티모달 (1~2주)

- [ ] 이미지 응답 (simpleImage)
- [ ] 카드 응답 (basicCard, textCard)
- [ ] 긴 텍스트 분할 (1000자 제한 대응)
- [ ] 이미지 수신 처리 (플러그인 연동)
- [ ] quickReplies를 활용한 대화 흐름 개선

### Phase 4: 고급 기능 (2~3주)

- [ ] 장기 메모리 연동 (user.id 기반 세션)
- [ ] 스킬 시스템 연동
- [ ] 음성 메시지 처리 (가능한 범위 내)
- [ ] 관리자 명령어 (봇 설정 변경 등)
- [ ] 에러 핸들링 & 모니터링
- [ ] Docker 배포 구성

### Phase 5: 프로덕션 안정화 (1~2주)

- [ ] 부하 테스트 (동시 사용자)
- [ ] Redis 기반 세션 관리
- [ ] 로깅 & 알림 체계
- [ ] 카카오 오픈빌더 봇 배포 (개발 → 운영)
- [ ] 사용자 가이드 문서

---

## 8. 기술적 리스크 & 대응

### 8.1 5초 타임아웃 → 콜백 API로 해결 (Resolved)

- **리스크**: LLM API 호출이 5초를 초과하면 카카오 오픈빌더가 에러 반환
- **해결**: **카카오 공식 콜백 API** 사용 — `useCallback: true`로 즉시 응답 후, callbackUrl로 결과 전송
- **제약**: 콜백 승인 필요 (1~2영업일), callbackUrl 유효시간 1분, 1회 사용
- **폴백**: 콜백 실패 시 폴링 방식 (결과 확인 버튼) 자동 전환
- **추가 최적화**: 단순 질문은 4.5초 내 직접 응답 시도 (콜백 불필요)

### 8.2 파일 수신 불가

- **리스크**: 카카오톡에서 사용자가 보낸 파일(PDF, 문서 등)의 URL을 받을 수 없음
- **대응**: 파일 분석 기능은 미지원으로 안내. 이미지는 가능하므로 이미지 기반 기능에 집중

### 8.3 카카오 정책 변경

- **리스크**: 오픈빌더 API 정책, 요금, 승인 기준 변경 가능
- **대응**: 채널 추상화 덕분에 다른 채널(웹 등)로 즉시 전환 가능

### 8.4 동시 사용자 처리

- **리스크**: 다수 사용자가 동시 요청 시 LLM API 병목
- **대응**: 요청 큐잉, Rate limiting, 사용자별 쿨다운 적용

---

## 9. 비용 구조

### 9.1 카카오 측

- 카카오톡 채널: 무료
- 카카오 i 오픈빌더: 무료 (기본)
- 콜백 API: 무료 (승인만 받으면 추가 비용 없음)

### 9.2 LLM API

- GPT-4o-mini: 입력 $0.15/1M, 출력 $0.6/1M (가장 경제적)
- GPT-4o: 입력 $2.5/1M, 출력 $10/1M
- Claude Sonnet: 입력 $3/1M, 출력 $15/1M
- 월 1만 건 대화 기준: GPT-4o-mini 약 $5~15, GPT-4o 약 $50~150

### 9.3 서버

- 최소: 개인 PC + ngrok (무료)
- 소규모: VPS 1대 (월 $5~20)
- 프로덕션: AWS/NCP (월 $30~100+)

---

## 10. 대안 접근법

만약 CowAgent 포크가 과하다고 느껴지면:

### 10.1 경량 버전: 직접 스킬 서버 구축

CowAgent 없이 순수 FastAPI + LLM API로 카카오 스킬 서버만 구현.
- 장점: 단순, 가벼움
- 단점: 메모리/스킬/멀티모달 직접 구현 필요

### 10.2 LangChain/LangGraph 기반

LangChain Agent + FastAPI 스킬 서버.
- 장점: 한국어 커뮤니티 활발, 유연한 체인 구성
- 단점: CowAgent의 채팅 특화 기능(메모리, 컨텍스트 관리) 재구현 필요

### 10.3 기존 한국 카카오톡 봇 프레임워크 활용

- [PyKakao](https://github.com/WooilJeong/PyKakao) 등 기존 라이브러리와 LLM 결합
- 장점: 카카오 API 래핑 완료
- 단점: AI 에이전트 기능 부족

---

## 11. 결론 및 권장안

### 추천 접근: CowAgent 포크 + 카카오 채널 구현

**이유:**
1. 채널 추상화가 이미 잘 설계되어 있어 카카오 채널 추가가 자연스러움
2. 메모리, 스킬, 멀티모달 등 고급 기능을 처음부터 활용 가능
3. 다른 채널(웹, 터미널)과 동시 운영 가능 — 디버깅에 유리
4. Python 생태계라 한국 개발자에게 친숙

**핵심 결정 포인트:**
- 5초 타임아웃 → **카카오 공식 콜백 API로 해결** (승인만 받으면 됨)
- 콜백 승인을 가장 먼저 신청 (Phase 0에서 병렬 진행)
- 텍스트 위주로 시작, 리치 메시지는 점진적 추가
- MVP는 Phase 0~1 완료 시점 (3~4주)

---

## 부록: 참고 자료

- **원본 프로젝트**: https://github.com/zhayujie/chatgpt-on-wechat
- **카카오 공식 콜백 가이드**: https://kakaobusiness.gitbook.io/main/tool/chatbot/skill_guide/ai_chatbot_callback_guide
- **ChatGee (오픈소스 참고)**: https://woensug-choi.github.io/ChatGee/
- **카카오 i 오픈빌더**: https://i.kakao.com/openbuilder
- **카카오 스킬 응답 JSON 포맷**: https://kakaobusiness.gitbook.io/main/tool/chatbot/skill_guide/answer_json_format

---

*작성일: 2026-04-09*
*최종 수정: 2026-04-09 (콜백 API 반영)*
