# GAME PM Morning Brief Self-Org-gent

게임 사업 PM을 위한 일일 브리핑 자동화 프로젝트입니다. 공식 Market Signal, 공개 Player & Live 반응, PM 의사결정을 세 개의 Skill로 분리하고 근거 추적이 가능한 브리핑을 생성하는 구조를 지향합니다.

## Current status

- Core games: 8
- Schedule target: 매일 08:10 KST (GitHub Actions)
- State target: 전용 `state` 브랜치의 JSON
- Delivery target: 전용 Slack 앱 + Notion
- Implemented: Market Signal 공식 공지/YouTube 수집, 변경 감지, 게임별 bounded batch 분석, One Event + Multiple Evidence 병합, 입력 완전성 검증, state branch 분석 캐시, OpenAI Structured Outputs 기반 Signal 변환
- Foundation only: Player & Live 실제 수집, PM Decision 전체 파이프라인, 자동 발송은 아직 활성화되지 않았습니다.

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

## Security

키, 웹훅, 토큰, 쿠키는 저장소에 커밋하지 않습니다. `.env`, `state/`, `output/`, Python 캐시는 Git 추적에서 제외됩니다. 실제 전송은 전체 품질 게이트를 통과하고 별도로 승인되기 전까지 fail-closed 상태를 유지합니다.

## Runtime

- Python 3.12+
- HTTP 및 파싱: Python 표준 라이브러리 우선
- 외부 dependency: 인프라 연결에 불가피한 경우만 허용
