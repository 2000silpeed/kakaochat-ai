# TODOS — KakaoChat AI

> Eng Review (2026-04-09) 에서 생성. 각 항목은 리뷰 과정에서 식별된 deferred 작업.

---

## T-001: CI/CD 파이프라인 설계 (v1.0)

- **What**: GitHub Actions로 pytest + APK 빌드 + Docker 이미지 빌드/푸시 자동화
- **Why**: 오픈소스 프로젝트에서 CI 없으면 PR 품질 관리 불가. Distribution check에서 CI/CD 부재 확인.
- **Effort**: CC ~30분
- **Blocked by**: 코어 코드 존재 (Phase 1~3 완료 후)
- **Target**: v1.0

## T-002: Accessibility Service fallback 조사

- **What**: Reply Action / 알림 수집률이 부족할 경우 Accessibility Service로 채팅 내역 직접 읽기 가능성 조사
- **Why**: Outside Voice에서 지적된 알림 번들링 문제. 수집률 90% 미달 시 대안 필요.
- **Effort**: 조사 2~4시간, 구현 시 추가
- **Blocked by**: Gate 1 수집률 측정 결과
- **Target**: Gate 1 실패 시 즉시 착수

## T-003: 대화 스레드 자동 생성 (한국어 토픽 클러스터링)

- **What**: 한국어 토픽 클러스터링으로 오픈챗 대화를 자동 스레드화
- **Why**: CEO Review에서 SKIPPED. 한국어 토픽 분류 정확도 불확실.
- **Effort**: M (클러스터링 모델 선택 + 튜닝)
- **Blocked by**: Gate 2 통과 + Mem0 한국어 성능 검증 경험 축적
- **Target**: v0.5 이후 재평가
