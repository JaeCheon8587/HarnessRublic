# Team-Template Rubric · v2.5 (100 pt · 7 categories, A·B = team-template, C–G = legacy AI-Ready)

이 문서는 `scripts/score.py` 의 단일 진실 기준입니다. **A·B 카테고리는 자사 솔루션 문서 표준 (`Docs/_templates/`) 준수도** 를 측정하고, C–G 는 기존 AI-Ready rubric (v2.1) 을 그대로 유지합니다. 후속 단계에서 C/D/E 도 team-template 으로 확장 예정.

| Cat | Name | Points | Source |
|-----|------|--------|--------|
| A | Solution & App Coverage | 15 | team-template |
| B | Document Structural Compliance | 20 | team-template |
| C | Tribal Knowledge Externalization | 20 | legacy v2 |
| D | Cross-Module Dependency & Data Flow Mapping | 15 | legacy v2 |
| E | Verification & Quality Gates | 15 | legacy v2 |
| F | Freshness & Self-Maintenance | 10 | legacy v2 |
| G | Agent Performance Outcomes | 5 | legacy v2 |

**Total = 100**

참조: [`Docs/_templates/DOCUMENT_GUIDE.md`](../../../Docs/Docs/_templates/DOCUMENT_GUIDE.md) — 문서 작성 SSOT.

---

## A. Solution & App Coverage · /15 *(team-template)*

> 솔루션 내 모든 App 이 진입 문서 + Backend Services Overview 등재로 navigation 가능한가.

**Measurement** *(Auto)*

```
Coverage = (진입 문서 보유 App 수) / (파일시스템 App 총수)
점수    = round(Coverage × 15)
         − 5 (root CLAUDE.md 부재)
         − 2 × (Backend Services Overview 등재됐으나 폴더 없는 App 수)
```

- **App 식별**: `Docs/<App>/` 폴더명 ∪ `Src/Mirero.<Product>.<X>/App/<App>/` 폴더명 (대문자 정규화).
- **진입 문서**: `{App}-PRD.md` OR `{App}-FC.md` 존재.
- **Backend Services Overview**: root `CLAUDE.md` 의 `## Backend Services Overview` 마크다운 표 SYSTEM_CODE 컬럼 파싱. placeholder (`{SYSTEM_CODE}`) 행 제외.

**Findings**:
- 진입 문서 미보유 App 목록
- Overview 등재 ↔ 파일시스템 mismatch
- Src↔Docs 폴더 매핑 불일치

---

## B. Document Structural Compliance · /20 *(team-template)*

> 각 doc-type 이 템플릿 핵심 구조 (메타 표, 변경 이력, 핵심 섹션, 4단계 마커, 빈칸 금지) 를 따르는가.

| Sub | Item | Points | Full-Score Criteria |
|-----|------|--------|---------------------|
| B1 | RouterCompleteness *(Auto)*    | 4 | root `CLAUDE.md` 핵심 섹션 (설계 문서 인덱스 / Backend Services Overview) 모두 존재 |
| B2 | MetaTable & History *(Auto)*   | 4 | 모든 content/supporting 문서에 메타 표 필수 필드 (문서 ID·버전·작성 가정·관련 문서) + 변경 이력 표 존재 |
| B3 | FourStageMarkers *(Auto)*      | 4 | 룰 풀 (DDD·OOP 룰 + 솔루션 ARCHITECTURE + 각 App-ARCHITECTURE) 에 반드시·허용·금지·절대 금지 4개 마커 모두 등장 |
| B4 | SectionCompliance *(Auto)*     | 4 | doc-type 별 **핵심 섹션** 모두 등장 (전 섹션 강제 X — 부록 표 참조) |
| B5 | NoBlankViolations *(Auto)*     | 4 | FRD 본문 빈칸 / N/A / placeholder (`{App}`, `{NNN}` 등) 잔존 0건 |

각 sub-item 4점 만점 → 풀 통과율 × 4 (round).

**Per-kind 메타 필수 필드** (B2):
- 일반 (PRD/FC/ARCHITECTURE/CATALOG): 문서 ID, 버전, 작성 가정, 관련 문서
- FRD: 문서 ID, 기능 ID, 작성 가정, 관련 문서
- ADR-CATALOG: 문서 ID, 작성 가정, 관련 문서
- ADR (개별): 메타 표 선택

**평가 풀**:
- B1: root CLAUDE.md
- B2: content + supporting (Docs/ 루트 룰 5종 제외)
- B3: DDD/OOP/ARCH 룰 + 각 App-ARCH
- B4: doc-type 식별 가능한 모든 문서 (kind별 핵심 헤딩 매칭)
- B5: 각 App의 FRD 파일

---

---

## C. Tribal Knowledge Externalization · /20

> 숨은 규칙, 실패 패턴, human-only knowledge가 구조화되었는가.

### Five-Question Framework *(Heuristic + Manual)*

각 핵심 module에 대해 다음 5개 질문에 답할 수 있으면 4점씩, 총 20점:

1. **What does this module configure / own?** — `## Purpose`, "configures", "owns" 표현
2. **What are common modification patterns?** — `## Patterns`, "common changes", "## How to"
3. **What non-obvious patterns cause failures?** — `Why:`, `Note:`, `Gotcha`, `Don't`
4. **What are the cross-module dependencies?** — "depends on", "imports", `## Cross-module`
5. **What tribal knowledge is hidden in comments / history / human memory?** — `MEMORY.md` / `ADR` / `docs/decisions` 존재

### Score band

| Score | Criteria |
|-------|----------|
| 0     | senior engineer / Slack / 과거 PR에만 지식 존재 |
| 5     | 일부 gotcha가 README / comment에 흩어짐 |
| 10    | 반복 작업의 암묵지 일부 문서화 |
| 15    | compatibility rule / naming / generated code rule / deprecated-but-required rule 정리 |
| 20    | 식별된 tribal knowledge 대부분이 context file / checklist / playbook에 반영 + AI가 질의로 회수 가능 |

자동 점수 = (5질문 통과 평균 × 20). 실제 깊이는 사람이 검증.

---

## D. Cross-Module Dependency & Data Flow Mapping · /15

> 변경 영향 범위를 AI가 추적할 수 있는가.

| Score | Criteria |
|-------|----------|
| 0     | 변경 영향을 사람이 수동으로 추적 |
| 5     | 일부 architecture diagram 또는 dependency note |
| 10    | 주요 module 간 dependency / ownership 문서화 |
| 15    | "What depends on X?" 에 graph / index / map으로 답 가능. repo / service / test / data flow ripple 추적 가능 |

**Auto checks:**
- `docs/architecture.md`, `ARCHITECTURE.md`, `docs/dependency-graph*` 존재
- `mermaid` / `graphviz` 다이어그램 fence 존재 (CLAUDE/AGENTS/ARCHITECTURE/ADR 등 확장 context 풀 검사)
- 확장 context 풀 안에 `## Dependencies` / `Cross-module` 섹션
- monorepo 의 `pnpm-workspace.yaml` / `turbo.json` / `nx.json` 으로 graph 도출 가능 여부

**Why important.** 한 field change가 6개 subsystem에 ripple 되는 대규모 codebase에서 결정적. 이게 약하면 D를 깎는 것이 옳음.

---

## E. Verification & Quality Gates · /15

> AI-generated context와 code change를 검증하는 체계가 있는가.

| Sub | Item | Points | Full-Score Criteria |
|-----|------|--------|---------------------|
| E1 | Reference Accuracy *(Auto)*        | 5 | CLAUDE.md / context file이 언급한 file path · API · command 의 hallucination 0건 |
| E2 | Independent Critic Review *(Manual)* | 4 | 최소 2-3 round 독립 review 또는 checklist (CODEOWNERS / review template / agent critic) |
| E3 | Task Validation *(Auto)*           | 4 | 변경 유형별 build / test / lint / typecheck / e2e 검증 명령 제공 + 실제 실행 가능 |
| E4 | Prompt / Workflow Tests *(Heuristic)* | 2 | 대표 AI task query를 실제 테스트 (`evals/`, agent test) |

**E1 자동 채점 알고리즘:**
1. 모든 context file (`router + content + supporting`) 에서 `[A-Za-z0-9_./-]+\.(py|ts|tsx|js|md|sql|json|yaml|yml|toml)` 후보를 추출
2. 각 후보를 repo 루트 기준으로 존재 검증
3. `valid / total` 비율 → `round(ratio × 5)`

> Meta 표현으로 "zero hallucinated paths"가 5점의 조건. 이것이 AI-ready의 핵심 — 검증되지 않은 context는 없는 것보다 **위험하다**.

---

## F. Freshness & Self-Maintenance · /10

> Context가 stale 해지지 않도록 자동 유지되는가.

| Score | Criteria |
|-------|----------|
| 0     | 수동 관리 + stale 여부 불명 |
| 3     | owner 있음 + 가끔 update |
| 6     | CI / script로 broken path / reference 일부 검출 |
| 10    | 주기적 file path validation, coverage gap detection, critic review, stale reference repair 자동 실행 |

**Auto checks:**
- 각 CLAUDE.md mtime vs 같은 module 내부 코드 파일 latest mtime 비교 — drift 비율
- `.github/workflows/*` 에 context / docs validation step 존재
- pre-commit / husky 에 path validation hook 존재
- `MEMORY.md` Session Notes 의 가장 최근 entry 날짜

**왜 강조되는가.** Stale context는 hallucination을 augmented retrieval로 정당화한다. 없는 것보다 **나쁘다**.

---

## G. Agent Performance Outcomes · /5

> 실제 AI task 성공률 / 효율 개선이 측정되는가.

| Score | Criteria |
|-------|----------|
| 0     | AI 성능 측정 없음 |
| 2     | 정성적으로 "도움 된다" 수준 |
| 3     | 대표 task success rate 또는 human intervention rate 측정 |
| 5     | tool calls, token usage, task completion time, correctness, prompt pass rate를 before / after로 측정 |

**Tracked metrics (예시):**
- AI task pass rate
- 평균 tool calls per task
- 평균 tokens per task
- human clarification count
- failed PR / rework rate
- hallucinated file path count
- time-to-first-correct-change

**Auto checks:**
- `evals/`, `benchmarks/`, `agent-metrics/` 디렉터리 존재
- `.skill-eval.json`, `agent-results.json` 같은 결과 파일
- AI usage telemetry 설정 (Claude Code session log, OpenTelemetry)

---

## Final Grade

| Score | Level | Meaning | Badge color |
|-------|-------|---------|-------------|
| 90-100 | **AI-Native / Agentic-Ready** | Agent가 대부분 반복 작업을 자율 수행 + context layer self-maintaining | green |
| 75-89  | **AI-Ready** | 대부분 작업에서 AI가 안정적으로 navigation, edit, verify | green |
| 60-74  | **AI-Assisted** | AI 유용하지만 complex / domain task에는 human context 필요 | amber |
| 40-59  | **AI-Fragile** | 단순 task는 가능, hidden rule / dependency로 오류 위험 높음 | amber |
| < 40   | **AI-Hostile** | tribal knowledge 의존도 높음 + AI는 추측 기반 | red |

---

## ROI Heuristics for Recommendations

각 갭에 대해 다음 형식으로 액션을 제시:

```
Effort: S (<1h) / M (1-4h) / L (4h+)
Impact: time saved per AI task × estimated tasks/period
Priority = Impact / Effort
```

대표 액션 ROI 표:

| Action | Effort | Impact (typical) |
|--------|--------|------------------|
| 핵심 module에 CLAUDE.md 추가 | S (30-60 min) | task당 2-5 min × 주 N task |
| god file (>500 lines) 분할 | M (1-3 hr/file) | 토큰 30-50% 절감 + 정확도 ↑ |
| `## Cross-module deps` 섹션 추가 | S (30 min) | cascade bug 방지 |
| MEMORY.md / ADR 도입 | M (2-4 hr 초기) | tribal knowledge 보존 (외부화) |
| path validation CI 추가 | S (1 hr) | stale reference 자동 차단 |
| agent eval test 추가 | L (4-8 hr) | AI 회귀 catch |
| naming refactor | M-L | 일관성 향상 (낮은 우선순위) |

상위 5개를 Priority 내림차순으로 정렬해 제시.

---

## 부록 A · doc-type ↔ 핵심 섹션 매핑 (B4 검사 기준)

전 섹션 강제 X — **핵심만** 검사. 누락 시 finding 발생, 점수는 풀 통과율로 환산.

| Kind | 파일 패턴 | 핵심 섹션 |
|------|----------|-----------|
| `root_claude` | `/CLAUDE.md` | 설계 문서 인덱스, Backend Services Overview |
| `sol_arch` | `Docs/ARCHITECTURE.md` | 2. 솔루션 아키텍처 / 4. 레이어별 책임 / 6. 레이어 참조 방향 |
| `sol_prd` | `Docs/PRD.md` | 1. 제품 배경 / 3. 목표 / 7. 제품 범위 / 부록 B / 부록 D / 부록 E |
| `app_prd` | `Docs/<App>/<App>-PRD.md` | 1. 배경 / 3. 목표 / 7. 주요 기능 / 10. Feature Catalog |
| `app_arch` | `Docs/<App>/<App>-ARCHITECTURE.md` | 1. App 개요 / 2. 핵심 책임 / 5. 솔루션 SSOT 인용 |
| `app_catalog` | `Docs/<App>/<App>-ADR-CATALOG.md` | Accepted / Proposed |
| `app_frd` | `Docs/<App>/FRD/<App>-FRD-{NNN}.md` | 1. 작업 지시 요약 / 2. 구현 범위 / 6. 기본 흐름 / 8. 예외 흐름 / 9. 상세 기능 요구사항 / 20. 수용 기준 / 21. 테스트 기준 |
| `app_adr` | `Docs/<App>/ADR/<App>-ADR-{NNN}.md` | 상태 / 컨텍스트 / 결정 / 결과 |
| `ddd` `oop` `behavior` `guide` | `Docs/{룰 파일}.md` | (B3 4단계 마커 검사만, 핵심 섹션 강제 X) |

---

## 부록 B · 식별자 정규식

| 종류 | 패턴 | 예시 |
|------|------|------|
| FRD 파일명 | `^([A-Z][A-Z0-9_]*)-FRD-(\d{3})\.md$` | `LOADER-FRD-001.md` |
| ADR 파일명 | `^([A-Z][A-Z0-9_]*)-ADR-(\d{3})\.md$` | `LOADER-ADR-001.md` |
| Feature ID | `\bF\d{3}\b` | F001 / F099 (정식), F101+ (Backlog) |
| 수용 기준 | `\bAC-F?\d{3}-\d{3}\b` | `AC-F001-001` |
| 테스트 기준 | `\bTC-F?\d{3}-\d{3}\b` | `TC-F001-001` |
| 미확인 사항 | `\bQ-F?\d{3}-\d{3}\b` | `Q-F001-001` |
| placeholder 잔존 | `\{(App\|SYSTEM_CODE\|APP_CODE\|SOLUTION_CODE\|NNN\|프로젝트명)\}` | `{App}` `{NNN}` |

---

## 부록 C · 자사 템플릿 SSOT

- 작성 가이드: [`Docs/_templates/DOCUMENT_GUIDE.md`](../../../Docs/Docs/_templates/DOCUMENT_GUIDE.md)
- 라우터 템플릿: `_templates/CLAUDE-TEMPLATE.md`
- 솔루션 ARCHITECTURE: `_templates/ARCHITECTURE-TEMPLATE.md`
- 솔루션 PRD: `_templates/PRD-TEMPLATE.md`
- App 4종: `_templates/App/APP-{PRD,FC,ARCHITECTURE,ADR-CATALOG}-TEMPLATE.md`
- App FRD/ADR: `_templates/App/FRD/APP-FRD-001-TEMPLATE.md`, `_templates/App/ADR/APP-ADR-001-TEMPLATE.md`
- 룰 4종: `_templates/{DDD_ARCHITECTURE_RULES,OBJECT_ORIENTED_DESIGN_RULES,BEHAVIORAL_GUIDELINES_RULES,DOCUMENT_GUIDE}.md`

**용어**:
- `SOLUTION_CODE` — 솔루션 식별자 (예 `XLAB`)
- `SYSTEM_CODE` ≡ `APP_CODE` ≡ `{App}` — App 식별자 (예 `LOADER`). SSOT = root CLAUDE.md `## Backend Services Overview` 표.

**ADR 명칭**: 결과 파일도 `ADR` prefix 유지 (DOCUMENT_GUIDE 0.2 의 ARD rename 룰은 오기, 무시).

