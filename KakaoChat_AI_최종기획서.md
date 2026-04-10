# KakaoChat AI — 최종 통합 기획서

> 카카오톡 오픈챗 집단지성 에이전트
> 작성일: 2026-04-09
> 산출물 통합: 기획문서 + 디자인문서 + CEO Plan + 리뷰 결과

---

## 1. 프로젝트 개요

### 한 줄 요약
카카오톡 오픈챗방에 상주하면서 모든 대화를 기억하고, 질문에 답하고, 좋은 지식을 큐레이션하는 AI 에이전트. 오픈소스.

### 문제
카카오톡 오픈챗방은 한국 최대의 비공식 지식 공유 공간이지만, 대화가 흘러가면 사라진다. 검색 안 되고, 스레드 없고, 북마크 공유도 안 된다. "어제 누가 올린 그 링크 뭐였지?" — 아무도 답하지 못한다.

### 비전 (10x)
"한국 개발자 커뮤니티의 집단 두뇌" — 수백 개 오픈챗방의 지식이 연결되고, Weekly Digest가 자동 발행되고, 크로스챗 인텔리전스가 동작하는 미래.

### 타겟
한국 AI 오픈챗방 커뮤니티. 첫 사용자 그룹이 이미 존재.

---

## 2. 기술 아키텍처

### 하이브리드 구조 (Approach C)

```
[카카오톡 앱 (안드로이드)]
    |  알림 발생
    v
[Android Bridge App] (경량, Kotlin)
    |  NotificationListenerService → JSON 파싱
    |  WebSocket 전송
    v
[AI Server] (Python, Mac/Win/Linux/Cloud)
    ├── Message Pipeline
    |   ├── 수신 → 파싱 → 정규화
    |   ├── URL 감지 → LinkArchiver
    |   └── 비동기 큐 (asyncio.Queue, 배치 처리)
    |
    ├── Mem0 Memory Engine (Group Chat 네이티브 지원)
    |   ├── Short-term: 최근 대화 컨텍스트
    |   ├── Long-term: 큐레이션된 지식 (ChromaDB)
    |   └── Entity Memory: 누가 뭘 말했는지
    |
    ├── Knowledge Curator
    |   ├── 시그널 필터: URL 포함, 100자+, 코드블록, 기술키워드
    |   ├── 노이즈 필터: ㅋㅋ만, 이모티콘만, 인사말
    |   ├── TIL 추출: "TIL", "오 몰랐네", "신기하다" 시그널
    |   └── 장기 승격: 시그널 점수 초과 시 Long-term 저장
    |
    ├── Participation Engine
    |   ├── @멘션 → 즉시 응답
    |   ├── 질문 감지 (? + "뭐였지", "누가") → 메모리 검색 응답
    |   ├── 중복 질문 감지 (cosine > 0.9) → 과거 답변 소환
    |   ├── 전문가 추천 → 주제별 적임자 태깅
    |   ├── 관련 대화 감지 (cosine > 0.85) → 자발적 참여
    |   └── 빈도 제한: 분당 1회, 연속 3회 후 5분 쿨다운
    |
    ├── Weekly Digest Generator
    |   └── 매주 월요일 08:00 KST, LLM 요약 → 자동 포스팅
    |
    ├── LLM Agent (GPT-4o-mini 기본, config에서 교체 가능)
    |
    └── response_mode: active / passive / off
        ├── active: 수집 + 응답 (Reply Action)
        ├── passive: 수집 + 메모리만 (CLI/웹에서 질의)
        └── off: 중지
    |
    v  응답 명령 (active 모드 시)
[Android Bridge App] → Reply Action → 카카오톡 오픈챗
```

### 기술 스택

- **메모리 엔진**: Mem0 (Group Chat 네이티브 지원, $24M Series A)
- **벡터 DB**: ChromaDB (MVP), 추후 Qdrant
- **임베딩**: intfloat/multilingual-e5-large 또는 jhgan/ko-sroberta-multitask
- **LLM**: OpenAI GPT-4o-mini (비용 효율), config에서 교체 가능
- **서버**: FastAPI (Python 3.11+)
- **브릿지**: Kotlin Android (NotificationListenerService + Foreground Service)
- **통신**: WebSocket (localhost 기본, 외부 노출 시 Bearer token)
- **스케줄러**: APScheduler (Weekly Digest 등)

---

## 3. 핵심 기능

### 코어 (검증 게이트 전)
1. **대화 수집**: 오픈챗방 모든 메시지를 벡터DB에 저장
2. **메모리 검색**: "그 얘기 누가 했어?" → 정확한 답변
3. **자연스러운 참여**: @멘션, 질문 감지 시 맥락 기반 응답
4. **지식 큐레이션**: 필터링으로 시그널/노이즈 분리, 좋은 콘텐츠 장기 저장
5. **수집 전용 모드**: Reply Action 없이도 수집+CLI 질의 가능

### 확장 (검증 게이트 통과 후)
6. **링크 자동 아카이브**: 공유 URL 자동 스크랩 + 요약 + 목록
7. **중복 질문 감지**: "이 질문 2주 전에도 나왔어요, 그때 답변은..."
8. **Weekly Digest**: 매주 월요일 핵심 논의 요약 자동 포스팅
9. **전문가 태깅**: 주제별 전문가 식별 + 질문 시 추천
10. **TIL 자동 추출**: "오 몰랐네" 시그널 → 지식 카드 생성

### 검증 게이트
- **Gate 1**: Reply Action이 카카오톡 오픈챗에서 동작하는지 확인
- **Gate 2**: Mem0 한국어 테스트 10개 케이스 통과
- Gate 미통과 시: 확장 기능 착수하지 않음, passive 모드로 피벗

---

## 4. 제약 사항

- 카카오톡 오픈채팅 공식 API 없음 — 비공식 접근 (NotificationListenerService)
- 카카오 TOS 위반 리스크 (메신저봇R이 수년간 운영, 실질적 위험 낮음)
- 안드로이드 기기 1대 상시 가동 필요 (구형 폰 OK)
- 카톡 업데이트 시 알림 포맷 변경 가능 → 파싱 로직 업데이트 필요
- Android Doze/배터리 최적화 → Foreground Service + 배터리 예외 설정 필수
- 그룹 알림 묶임 ("3개의 새 메시지") → 개별 파싱 불가, skip 처리
- Mac + Windows 크로스 플랫폼 필요 (서버 컴포넌트)

---

## 5. 에러 핸들링

### Error & Rescue Registry

```
EXCEPTION              | RESCUED | ACTION                      | USER SEES
-----------------------|---------|-----------------------------|-----------
ParseError             | Y       | raw 알림 로그, skip         | Nothing
ConnectionError        | Y       | exponential backoff 재연결   | Nothing (큐잉)
SerializeError         | Y       | 로그 + skip                 | Nothing
MemoryError            | Y       | 로그 + 침묵                 | Nothing
DBConnectionError      | Y       | 큐잉 + 재연결 대기 + 알림   | 지연
TimeoutError           | Y       | 3회 재시도                   | 침묵
RateLimitError         | Y       | backoff + 재시도             | 침묵
LLMParseError          | Y       | raw 응답 로그 + 침묵        | Nothing
RefusalError           | Y       | 로그 + "어려운 질문" 응답    | 안내 메시지
ScrapeError            | Y       | URL만 저장, 요약 없이        | "링크 저장됨"
ScrapeTimeoutError     | Y       | URL만 저장                   | "링크 저장됨"
ReplyError             | Y       | pending 저장 + 재시도        | 지연
DigestSendError        | Y       | 로그 + 다음 주기 재시도      | Digest 지연
InsufficientDataError  | Y       | "데이터 부족" 응답           | 안내 메시지
```

### 브릿지 연결 관리
- WebSocket 끊김: exponential backoff 재연결 (최대 5분)
- 연결 중 메시지: 브릿지 앱 SQLite 로컬 버퍼에 저장, 복구 후 replay
- 서버 재시작: 브릿지가 자동 재연결, 큐잉된 메시지 전송

---

## 6. 로드맵 & 태스크

### Phase 0: 환경 준비 (Day 0)
- [ ] 안드로이드 기기 준비 (구형 폰 OK, Android 8.0+)
- [ ] Python 3.11+ 환경 구성
- [ ] Mem0 + ChromaDB 설치 테스트

### Phase 1: 코어 검증 (Day 1, 토요일)

**Step 0: Reply Action 검증 (최우선)**
- [ ] 최소 Android 앱 생성 (NotificationListenerService)
- [ ] 카카오톡 오픈챗 알림 캡처 확인
- [ ] Reply Action으로 오픈챗에 메시지 전송 테스트
- [ ] **결과**: 성공 → active 모드 진행 / 실패 → passive 모드로 피벗
- **Done**: Reply Action 동작 여부 확정

**Step 1: Android Bridge**
- [ ] NotificationListenerService + Foreground Service 구현
- [ ] 알림 파싱: sender, text, room, timestamp(수신 시각)
- [ ] WebSocket으로 로컬 Python 서버 전송
- [ ] 배터리 최적화 예외 설정 가이드
- **Done**: `{"room":"AI스터디","sender":"철수","text":"RAG 써봤는데...","ts":1712600000}` 출력

**Step 2: AI Server 기본**
- [ ] FastAPI 서버 뼈대 (`POST /ws`, `GET /health`)
- [ ] WebSocket 수신 핸들러
- [ ] config.yaml: response_mode, llm_model, llm_api_key 등
- **Done**: 브릿지 → 서버 메시지 수신 확인

### Phase 2: 메모리 엔진 (Day 2, 일요일 오전)

**Step 3: Mem0 연동**
- [ ] Mem0 Group Chat 모드 설정
- [ ] 수신 메시지 자동 임베딩 저장
- [ ] **한국어 테스트 10개 케이스** (Gate 2)
  - "RAG 얘기 누가 했어?" → 정확한 결과
  - "어제 공유된 링크 뭐였지?" → URL 포함 응답
  - "ㅋㅋㅋ" → 노이즈로 처리 (검색 결과에 안 나옴)
  - 줄임말/이모티콘 포함 메시지 처리
  - 등등
- [ ] CLI 질의 도구: `python query.py "검색어"`
- **Done**: CLI에서 한국어 질의 → 정확한 답변 (10/10 통과)

### Phase 3: 참여 엔진 (Day 2, 일요일 오후)

**Step 4: 기본 참여 로직**
- [ ] @멘션 감지 → LLM 호출 → Reply Action 답장
- [ ] 질문 감지 (? + 패턴 매칭) → 메모리 검색 → 응답
- [ ] 빈도 제한 (분당 1회, 연속 3회 후 5분 쿨다운)
- [ ] 에러 시 침묵 (오류를 챗방에 보내지 않음)
- **Done**: 카톡 오픈챗에서 @멘션 → AI 응답 수신

**Step 5: 데모 영상**
- [ ] 30초 데모 영상 촬영 ("3일 전 대화 물어보니 AI가 답함")
- [ ] GitHub repo 생성 + README + 데모 GIF
- **Done**: MVP 공개 가능 상태

### Phase 4: 확장 기능 (Gate 통과 후)

**v0.2: 지식 큐레이션 강화**
- [ ] 시그널/노이즈 필터링 엔진
- [ ] 장기 지식 승격 로직
- [ ] TIL 자동 추출
- [ ] 링크 자동 아카이브 (URL 스크래핑 + 요약)

**v0.3: 소셜 기능**
- [ ] 중복 질문 감지
- [ ] "이 방의 전문가" 태깅
- [ ] 전문가 추천 로직

**v0.4: Weekly Digest**
- [ ] DigestGenerator (LLM 요약)
- [ ] 전송 메커니즘 구현 (Accessibility Service 또는 대안)
- [ ] 스케줄러 (매주 월요일 08:00 KST)

**v0.5: 다중 채팅방**
- [ ] 하나의 서버에서 여러 오픈챗방 동시 모니터링
- [ ] 방별 config (참여 수준, 큐레이션 규칙)

**v0.6: 멀티 메신저**
- [ ] Telegram adapter 추가
- [ ] Messenger Adapter 인터페이스 정의

**v1.0: 프로덕션**
- [ ] 안정화 + 버그 수정
- [ ] 문서화 (설치 가이드, API 문서)
- [ ] Docker Compose 배포
- [ ] 커뮤니티 피드백 반영

---

## 7. 비용 구조

### LLM API (월 기준, 1개 방 500~2000 메시지/일)
- **Mem0 메모리 추출**: 메시지당 ~100 토큰 → 월 ~$3~12 (GPT-4o-mini)
- **질의 응답**: 일 10~50회 → 월 ~$1~5
- **Weekly Digest**: 월 4회 → ~$0.5
- **링크 요약**: 일 5~20개 → 월 ~$1~4
- **합계**: 월 약 $5~25 (GPT-4o-mini 기준)

### 서버
- 최소: 개인 PC + 구형 안드로이드 (무료)
- 소규모: VPS 1대 (월 $5~20)
- Docker: 서버 + ChromaDB 원클릭

### 카카오
- 무료 (공식 API 사용 안 함)

---

## 8. 배포 & 오픈소스

- **라이선스**: MIT 또는 Apache 2.0
- **서버**: `git clone` + `pip install -r requirements.txt`
- **브릿지**: GitHub Releases APK (Play Store 비추, TOS 리스크)
- **Docker**: `docker-compose up` (서버 + ChromaDB)
- **데모**: README 상단 30초 GIF + 유튜브 풀 데모

### README 필수 섹션
- 데모 영상/GIF
- 원클릭 설치 가이드 (30분 내 구동 목표)
- config.yaml 설명
- 프라이버시 권장: "방장이 직접 설치하는 것을 전제로 하며, 참여자에게 봇 존재를 고지하는 것을 권장합니다"
- 기여 가이드
- 알려진 제약사항

---

## 9. 리스크 & 대응

### Reply Action 미검증 (CRITICAL → 대응 완료)
- **리스크**: 오픈챗 알림에서 Reply Action이 안 될 수 있음
- **대응**: Day 1 Step 0에서 최우선 검증. 실패 시 passive 모드로 피벗 (수집 전용 + CLI/웹 질의)

### Mem0 한국어 성능 (HIGH → 대응 완료)
- **리스크**: 한국어 줄임말, 이모티콘, ㅋㅋ 등에서 메모리 추출 품질 저하
- **대응**: 한국어 특화 임베딩 모델 사용 + Day 2에 10개 테스트 케이스 검증

### 카카오톡 업데이트 (MEDIUM)
- **리스크**: 카톡 업데이트 시 알림 포맷 변경 → 파싱 깨짐
- **대응**: 파싱 실패 시 raw 알림 로그 기록. 커뮤니티 PR로 빠르게 대응.

### Android 백그라운드 Kill (MEDIUM)
- **리스크**: Doze/배터리 최적화로 서비스 종료
- **대응**: Foreground Service + persistent notification + 배터리 예외 설정 가이드

### 동시 사용자/다중 방 (LOW, 후순위)
- **리스크**: 메시지 볼륨 증가 시 처리 병목
- **대응**: 비동기 큐 + 배치 처리. v0.5에서 다중 방 아키텍처 설계.

---

## 10. 차별점 (기존 프로젝트 vs KakaoChat AI)

- **CowAgent (chatgpt-on-wechat)**: 중국 메신저 전용, 1:1 챗봇, 그룹챗 기억 없음
- **ChatGee**: 카카오 전용이지만 단순 GPT 래퍼, 1:1 전용
- **메신저봇R**: 안드로이드 JS 스크립팅, AI 에이전트/메모리 기능 없음
- **PyKakao**: API 래핑만, 오픈챗 미지원
- **Mem0**: 메모리 엔진은 있지만 카카오톡 통합 없음

**KakaoChat AI = 카카오톡 오픈챗 통합 + Mem0 메모리 + 한국어 지식 큐레이션**
→ 이 조합은 아무도 안 만들었음.

---

## 11. 리뷰 현황

```
+====================================================================+
|                    REVIEW STATUS                                    |
+====================================================================+
| Review          | Status    | Key Findings                         |
|-----------------|-----------|--------------------------------------|
| Office Hours    | DONE      | Builder mode, Approach C 선택        |
|                 |           | Mem0 코어 추천 (세컨드 오피니언)     |
| CEO Review      | DONE      | SCOPE EXPANSION, 5개 확장 수락       |
|                 |           | 수집 전용 모드 + 검증 게이트 추가    |
|                 |           | Outside voice: 8개 이슈, 3개 대응    |
| Eng Review      | DONE      | 12개 이슈, 전부 해결                  |
|                 |           | Outside voice: 5개 이슈, 4개 대응    |
| Design Review   | SKIPPED   | UI 없음                              |
+====================================================================+
```

---

## 12. 참고 자료

- **Mem0 (메모리 엔진)**: https://github.com/mem0ai/mem0
- **Mem0 Group Chat 문서**: https://docs.mem0.ai/platform/features/group-chat
- **ChatGee (참고 오픈소스)**: https://woensug-choi.github.io/ChatGee/
- **카카오톡 봇 제작법**: https://namu.wiki/w/카카오톡%20봇/제작법
- **채팅 자동응답 봇 API**: https://darktornado.github.io/KakaoTalkBot/docs/api/list/
- **카카오 AI 챗봇 콜백 가이드**: https://kakaobusiness.gitbook.io/main/tool/chatbot/skill_guide/ai_chatbot_callback_guide

---

*최종 수정: 2026-04-09*
*Office Hours + CEO Review + Eng Review 결과 통합*
*다음 단계: 코딩 시작*

---

## 13. Eng Review 결과 요약 (2026-04-09)

### Architecture (5개 이슈 → 전부 A)
- pending_responses 큐 + TTL (응답 유실 방지)
- Digest 전송 후보 3가지 + 검증 기준 명시
- Mem0 OSS 명시 + Gate 2에서 오픈소스 Group Chat 검증
- API key는 환경변수 기반 (config.yaml에 넣지 않음)
- target_rooms 화이트리스트 코어에 포함

### Code Quality (3개 이슈 → 전부 A)
- SimilarityMatcher 통합 (중복감지 + 관련대화 = 1개 서비스)
- Pipeline 순서 명시: Parser → Curator(분류) → Engine(액션)
- config.yaml 전체 스키마 사전 정의

### Test (1개 이슈 → A)
- 47개 코드 경로 식별, Phase별 테스트 전략 추가
- pytest + pytest-asyncio (Python), JUnit (Kotlin)

### Performance (3개 이슈 → A,A,B)
- Curator 필터링 후 선택적 임베딩 (noise는 임베딩 스킵)
- question 분류 메시지에만 유사도 검색
- 메모리 pruning은 MVP에서 스킵

### Outside Voice (5개 지적 → 4개 대응)
- Gate 1에 "알림 수집률 측정" 추가 (목표 90%+)
- README에 비공식 API 경고 추가, 오픈소스 유지
- Gate 2에 "실제 API 비용 측정" 추가
- 단일 기기 테스트 + README에 테스트 환경 명시

### 추가 안전장치
- 모든 raw 메시지를 텍스트 로그로 보관 (Curator 오분류 복구용)

### Worktree 병렬화
- Sequential implementation (코어가 한 모듈에 집중되므로 병렬화 불필요)
- Phase 4 확장 기능은 Gate 통과 후 독립적으로 병렬 가능
