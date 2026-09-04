# GAME PM Morning Brief Self-Org-gent

게임 사업 PM을 위한 일일 브리핑 자동화 프로젝트입니다. 공식 Market Signal, 공개 Player & Live 반응, PM 의사결정을 세 개의 Skill로 분리하고 근거 추적이 가능한 브리핑을 생성하는 구조를 지향합니다.

## 기본 실행: compact-v1

수집 → 게임별 변경 자료 한 번 요약 → 코드로 보고서 조립 → Notion·Slack 순서입니다.
3 Skill의 역할은 유지하지만 AI 분석을 세 번 반복하지 않습니다. Game Radar는 보류 중입니다.
실제 발송이 꺼져 있어 정기 실행은 수집·유료 API 호출 없이 종료합니다.

[간소화 실행 안내](docs/compact-runtime.md)에서 예산, 테스트, 롤백 방법을 확인할 수 있습니다.
아래의 상세 분석 모드는 명시적으로 선택하는 수동 진단용입니다.

## Detailed components (manual diagnostics)

- Core games: 8
- Schedule target: 매일 08:10 KST (GitHub Actions)
- State target: 전용 `state` 브랜치의 JSON
- Delivery target: 전용 Slack 앱 + Notion
- Implemented: Market Signal 공식 공지/YouTube 수집, 변경 감지, 게임별 bounded batch 분석, One Event + Multiple Evidence 병합, 입력 완전성 검증, state branch 분석 캐시, OpenAI Structured Outputs 기반 Signal 변환
- Player Live source foundation: 8개 게임별 검증 URL과 evidence role을 `config/player_live_sources.json`에 등록했습니다. 공식 YouTube는 `RSS_READY`, 디시인사이드 8개는 `ADAPTER_READY`, 나머지 커뮤니티는 `ADAPTER_PENDING`입니다.
- Implemented Player Live collection: 공식 YouTube RSS를 `OFFICIAL_FACT`, 디시인사이드 게시물을 `PLAYER_CLAIM`으로 분리하는 공통 Evidence 수집 계층, 최근 7일 bounded scan, 작성자 비수집, 변경 해시, 출처별 coverage gap.
- Implemented Player Live analysis: 게임별 bounded OpenAI Structured Outputs 군집화, 입력 완전성 검증, 공식 팩트·이용자 주장 경계 검증, 한국어 출력 검증, PM 지표 의미 검증, 1회 교정 재시도, 게임별 분석 캐시, `PlayerLiveInsight` 생성.
- Implemented PM Decision V1: 두 Scout 결과의 게임별 OpenAI 합성, 입력 완전성 검증, 필수 deep dive 확인, 근거 상속, `P0` 제한, PM 지표·한국어 검증, 1회 교정 재시도, `MorningBrief` 및 Slack·Notion 미리보기 생성.
- Foundation only: 인벤·공식 커뮤니티 수집, Game Radar 자동 탐지, 실제 자동 발송은 아직 활성화되지 않았습니다.

## Skills

- `market-signal`: 공식 출처 수집과 Signal 정규화
- `player-live-watch`: 공개 플레이어 반응 및 라이브 이슈 분석
- `pm-decision-lead`: 교차 검증, 우선순위 결정, Morning Brief 구성

각 역할의 경계와 호출 순서는 `AGENTS.md`, 개별 판단 규칙은 `skills/*/SKILL.md`, 공통 데이터 계약은 `shared/schemas.py`를 따릅니다.

## Safe Signal test

GitHub 저장소의 `Settings > Secrets and variables > Actions`에 다음 값을 등록합니다.

- Secret: `OPENAI_API_KEY`
- Variable: `OPENAI_MODEL`

그다음 `Actions > Game PM Morning Brief > Run workflow`에서 `signal-test`를 선택하면 공식 자료를 수집하고 OpenAI Signal JSON을 artifact로 생성합니다. 이 모드는 Slack과 Notion에 발송하지 않습니다. 결과의 `analysis_metrics`에서 입력 수, 배치 수, 실제 API 호출 수, 캐시 적중 게임, 분석 시간을 확인할 수 있습니다.

Player Live 공통 Evidence 수집과 `PlayerLiveInsight` 생성을 함께 검증하려면 같은 화면에서 `player-live-test`를 선택합니다. 이 모드도 Slack과 Notion에는 발송하지 않으며 결과는 workflow artifact에 저장됩니다.

세 Skill 전체 합성과 최종 메시지 모양까지 검증하려면 `decision-test`를 선택합니다. 이 모드는 `MorningBrief`, Slack 미리보기, Notion 미리보기를 artifact로 생성하지만 실제 전송은 하지 않습니다.

## Security

키, 웹훅, 토큰, 쿠키는 저장소에 커밋하지 않습니다. `.env`, `state/`, `output/`, Python 캐시는 Git 추적에서 제외됩니다. 실제 전송은 전체 품질 게이트를 통과하고 별도로 승인되기 전까지 fail-closed 상태를 유지합니다.

## Runtime

- Python 3.12+
- HTTP 및 파싱: Python 표준 라이브러리 우선
- 외부 dependency: 인프라 연결에 불가피한 경우만 허용
