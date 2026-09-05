# 간소화 운영 방식

2026-09-04 사용자 승인 변경. 목적은 고정 8게임 일일 보고서의 비용과 실패 범위를 줄이는 것이다.

## 변경과 한계

보완: 공식 공지/공식 YouTube HTTP는 대기 20초, 일시적 오류 재시도 1회로 분리했다.
커뮤니티 HTTP는 10초/재시도 0회, 유료 AI 재시도는 여전히 0회다.
공지 링크 추출 실패(LISTING_NO_LINKS), 최근 공지 없음(NO_RECENT_NOTICES),
HTTP 상태, 시간초과, XML 파싱 실패를 구분한다. 빈 HTML을 받는 문제는 재시도 복원만으로
해결됐다고 간주하지 않는다. 출력 상한은 요청 1회 기준 4,000토큰이며 일일 계정 한도가 아니다.
AI 보고서에는 OUTPUT_TOKEN_LIMIT/NETWORK_TIMEOUT/INVALID_JSON/SUMMARY_VALIDATION_FAILED
등과 응답에 포함된 추론 토큰 수를 기록한다. 이전 실행의 원인은 소급 확정할 수 없다.

- 기존 어댑터와 3 Skill 역할은 유지하고 기본 분석을 `app/daily.py`로 통합했다.
- 공식 본문 최대 8건, 커뮤니티 본문 최대 5건/게임, 목록 최대 2페이지.
- 공식 YouTube 중복 수집 제거. 최근 7일 내 새 글·수정 글만 분석.
- 게임당 하루 1회, 총 최대 8회 요청. 요청당 입력 13건 × 본문 1,800자와 제목,
  추론 수준 `low`, 출력 최대 4,000토큰. 자동 유료 재시도 0회. 모델은 기존 OPENAI_MODEL 그대로 사용.
- 호출 수·응답에 포함된 사용 토큰·분석 시간은 daily_report.json에 기록한다.
  타임아웃 등 사용량 응답이 없는 요청은 청구될 수 있어 정확한 비용은 별도 확인해야 한다.
- 정교한 감정/추세/심각도, AI 재판단, 자동 실행 권고, KPI 질문 생성은 기본 경로에서 생략.
  pm_metric_context는 빈 값이다. 공식 내용 P2, 반응만 있으면 P3: 긴급 탐지 서비스가 아니다.
- 분류 category/BM taxonomy와 문장별 근거 ID는 daily_report.json에 남긴다.
- Game Radar는 보류. 수집 상한·본문 잘림으로 일부 정보가 누락될 수 있으므로 완전한 시장 조사가 아니다.
- 실패는 게임별 공백으로 표시하고 다른 게임 결과는 유지한다. 일정은 08:10 KST 실행 요청이며
  GitHub 대기와 수집 시간이 더해지므로 08:10 정각 도착을 보장하지 않는다.

## 실행과 검증

```powershell
python -m unittest discover -s tests
# 아래 두 모드는 실제 API를 사용할 수 있으나 Slack/Notion을 전송하지 않는다.
python -m app.run --mode daily --games mabinogi-mobile --state-dir state --output-dir output
python -m app.run --mode daily-saved --collection-file output/daily_collection.json --state-dir state --output-dir output
```

daily-saved는 재수집하지 않으며 daily와 같은 일일 호출 예산을 공유한다.
로컬 단위 테스트는 가짜 API 응답을 사용하므로 외부 호출/비용이 없다.
부분 게임 검증에서는 나머지 게임을 '변경 없음'이 아니라 '미조사'로 표시한다.

산출물: daily_collection.json, daily_report.json, morning_brief.json,
slack_preview.json, notion_preview.json. 수집 원문은 제한된 CI artifact로만 보관한다.
Notion은 접기 블록에 게임별 사실·주장·해석·공백·출처를 보존한다.

## 전송 및 상태

live_delivery_enabled=false 유지. automatic은 이 상태에서 수집/API 호출 없이 종료한다.
실발송 활성화는 별도 승인 및 1회 통합 검증 후 진행한다. 스위치를 켜면 실제 compact
보고서가 사용되며 미리보기 보고서는 발송하지 않는다.

새 상태 namespace daily/는 기존 detailed 분석 캐시와 독립적이다.
analyzed: 성공한 내용 지문, attempts: 날짜별 호출 예산, summaries: 당일 검증된
요약과 근거 메타데이터(본문 제외). 실패한 자료는 다음 날 다시 시도할 수 있다.
전송 키는 날짜+대상이다. pending 체크포인트는 성공 확인 후 해제한다. 응답을 잃으면
대상에서 실제 게시 여부를 사람이 확인한 후 상태를 복구해야 한다. 무조건 재실행하지 않는다.
부분 실패에도 상태 브랜치에 체크포인트를 저장하고 latest_success와 분리한다.

## 변경 범위와 롤백

소유 계층: app 실행·조립, 두 수집 어댑터 재사용, shared 전송 포맷과 API 한도,
config 예산, root/Skill 실행 계약. 기존 MorningBrief/PMDecisionItem 필드는 호환 유지.
compact summary는 내부 새 계약이며 기존 Signal/Insight JSON 변환을 강제하지 않는다.

기존 collect/signal-test/player-live-test/decision-test/pm-decision 모드는 보존했다.
롤백 시 live_delivery_enabled=false를 유지하고 이 변경을 Git revert한 뒤 기존 수동
진단 모드를 사용한다. daily/ 상태는 무시 가능하며 기존 상태를 지우거나 변환할 필요 없다.
스케줄·URL·비밀키 이름·8게임 목록은 변경하지 않았다.

남은 승인 사항: 실제 발송 활성화. 향후 Radar 재개와 긴급 분석 재도입은 별도 변경이다.
