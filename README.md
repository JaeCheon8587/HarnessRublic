# HarnessRublic

자사 솔루션 (XLab 등) 의 **문서 표준 준수도** + **AI-Ready 인프라** 를 100점 만점으로 스코어링.

## 실행

```
python scripts/score.py <솔루션 경로> --json out.json
```

UTF-8 환경 (Windows PowerShell): `python -X utf8 scripts/score.py ...`

## 출력

- `out.json` — 다운스트림 AI consumer 입력용 구조화 데이터
- stdout — 마크다운 리포트

## Rubric (v2.5-100pt-team-AB)

| Cat | Name | Pts | Source |
|-----|------|-----|--------|
| A | Solution & App Coverage | 15 | team-template |
| B | Document Structural Compliance | 20 | team-template |
| C | Tribal Knowledge Externalization | 20 | legacy v2 |
| D | Cross-Module Dependency Mapping | 15 | legacy v2 |
| E | Verification & Quality Gates | 15 | legacy v2 |
| F | Freshness & Self-Maintenance | 10 | legacy v2 |
| G | Agent Performance Outcomes | 5 | legacy v2 |

상세: [`references/scoring-rubric.md`](references/scoring-rubric.md)

## JSON 스키마 (v2.5 신규 키)

```jsonc
{
  "meta": {
    "rubric_version": "v2.5-100pt-team-AB",
    "solution_code": "XLAB",              // 신규 — Src/Mirero.<X>.<SOL>/ 패턴 추정
    "apps": [{                            // 신규 — Backend Services Overview ∪ FS
      "system_code": "LOADER",
      "docs_dir": "Docs/LOADER",
      "src_dir": "Src/Mirero.PCC.XLab/App/Loader",
      "has_prd": true, "has_fc": true, "has_arch": true, "has_catalog": true,
      "frd_count": 3, "adr_count": 1
    }]
  },
  "categories": { "A": {...}, "B": {...}, ... "G": {...} },
  "template_compliance": {                // 신규 — doc-type별 진단
    "Docs/LOADER/FRD/LOADER-FRD-001.md": {
      "kind": "app_frd",
      "missing_sections": ["12. 상태 정의"],
      "meta_fields_missing": [],
      "history_present": true,
      "four_stage_markers": {"반드시": 2, "허용": 0, "금지": 1, "절대 금지": 0},
      "na_violations": 3,
      "placeholder_leftover": 0
    }
  },
  "actions": [...]                        // ROI 정렬, A/B 신규 트리거 포함
}
```

## 대상 솔루션 구조

```
<Solution>/
├── CLAUDE.md                          ← SOLUTION_CODE + Backend Services Overview SSOT
├── Docs/
│   ├── ARCHITECTURE.md                ← 솔루션 레이어 모델
│   ├── PRD.md                         ← (선택) 솔루션 PRD
│   ├── DDD_ARCHITECTURE_RULES.md
│   ├── OBJECT_ORIENTED_DESIGN_RULES.md
│   ├── BEHAVIORAL_GUIDELINES_RULES.md
│   ├── DOCUMENT_GUIDE.md
│   └── {App}/                         ← App별 1폴더 (Loader/Master/Client/...)
│       ├── {App}-PRD.md
│       ├── {App}-FC.md
│       ├── {App}-ARCHITECTURE.md
│       ├── {App}-ADR-CATALOG.md
│       ├── FRD/{App}-FRD-{NNN}.md
│       └── ADR/{App}-ADR-{NNN}.md
└── Src/Mirero.<Product>.<X>/App/<App>/  ← Docs/<App>/ 와 1:1 매핑
```

템플릿 SSOT: `C:\Users\cross\OneDrive\Desktop\Docs\Docs\_templates\`
