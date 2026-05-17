"""Team-template helpers for Harness_Rublic (A·B 카테고리 범위).

자사 솔루션 문서 표준 (`Docs/_templates/`) 준수도 검사용 상수·정규식·파서·validator.
score.py 에서 import. C/D/E/F/G 는 기존 score.py 로직 그대로 사용.

Doc kinds (A·B 범위):
  root_claude / sol_arch / sol_prd / ddd / oop / behavior / guide
  app_prd / app_fc / app_arch / app_catalog / app_frd / app_adr
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable


# ----------------------------------------------------------------------------
# 상수 — 필수 문서 / 디렉터리
# ----------------------------------------------------------------------------
REQUIRED_ROOT_DOCS = ("CLAUDE.md",)
REQUIRED_DOCS_ROOT = (
    "ARCHITECTURE.md",
    "DDD_ARCHITECTURE_RULES.md",
    "OBJECT_ORIENTED_DESIGN_RULES.md",
    "BEHAVIORAL_GUIDELINES_RULES.md",
    "DOCUMENT_GUIDE.md",
)
APP_REQUIRED_DOC_SUFFIXES = ("-PRD.md", "-FC.md", "-ARCHITECTURE.md", "-ADR-CATALOG.md")
APP_SUBDIRS = ("FRD", "ADR")

DOCS_ROOTS = ("Docs", "docs")


# ----------------------------------------------------------------------------
# 핵심 섹션 헤딩 (전 섹션 강제 X — 핵심만)
# ----------------------------------------------------------------------------
FRD_CORE_HEADINGS = [
    "1. 작업 지시 요약",
    "2. 구현 범위",
    "6. 기본 흐름",
    "8. 예외 흐름",
    "9. 상세 기능 요구사항",
    "20. 수용 기준",
    "21. 테스트 기준",
]
SOLUTION_ARCH_HEADINGS = ["2. 솔루션 아키텍처", "4. 레이어별 책임", "6. 레이어 참조 방향"]
SOLUTION_PRD_HEADINGS = ["1. 제품 배경", "3. 목표", "7. 제품 범위", "부록 B", "부록 D", "부록 E"]
APP_PRD_HEADINGS = ["1. 배경", "3. 목표", "7. 주요 기능", "10. Feature Catalog"]
APP_ARCH_HEADINGS = ["1. App 개요", "2. 핵심 책임", "5. 솔루션 SSOT 인용"]
APP_CATALOG_HEADINGS = ["Accepted", "Proposed"]
ADR_HEADINGS = ["상태", "컨텍스트", "결정", "결과"]
ROOT_CLAUDE_HEADINGS = ["설계 문서 인덱스", "Backend Services Overview"]

# kind → 핵심 헤딩 리스트 매핑
KIND_HEADINGS: dict[str, list[str]] = {
    "root_claude": ROOT_CLAUDE_HEADINGS,
    "sol_arch": SOLUTION_ARCH_HEADINGS,
    "sol_prd": SOLUTION_PRD_HEADINGS,
    "app_prd": APP_PRD_HEADINGS,
    "app_arch": APP_ARCH_HEADINGS,
    "app_catalog": APP_CATALOG_HEADINGS,
    "app_frd": FRD_CORE_HEADINGS,
    "app_adr": ADR_HEADINGS,
}


# ----------------------------------------------------------------------------
# 정규식
# ----------------------------------------------------------------------------
RE_META_TABLE_HEADER = re.compile(r"\|\s*항목\s*\|\s*값\s*\|", re.I)
RE_HISTORY_HEADING = re.compile(r"^##\s*변경\s*이력", re.M)
RE_4STAGE = re.compile(r"(반드시|허용|금지|절대\s*금지)")
RE_BACKEND_OV = re.compile(r"^#{1,4}\s*.*Backend Services Overview", re.M | re.I)
RE_FORBID_MATRIX = re.compile(r"6\.1[^\n]*절대\s*금지\s*매트릭스", re.I)
RE_FRD_FILE = re.compile(r"^([A-Z][A-Z0-9_]*)-FRD-(\d{3})\.md$")
RE_ADR_FILE = re.compile(r"^([A-Z][A-Z0-9_]*)-ADR-(\d{3})\.md$")
RE_NA_CELL = re.compile(r"^\s*(N/A|n/a|\-|TBD|tbd)\s*$", re.M)
RE_MISJAKSUNG = re.compile(r"(미작성|추후)")
RE_PLACEHOLDER = re.compile(r"\{(App|SYSTEM_CODE|APP_CODE|SOLUTION_CODE|NNN|프로젝트명|이름)\}")
RE_MERMAID = re.compile(r"```mermaid", re.I)

META_REQUIRED_FIELDS = ("문서 ID", "버전", "작성 가정", "관련 문서")

# kind별 메타 필수 필드 (템플릿 차이 반영)
META_FIELDS_BY_KIND: dict[str, tuple[str, ...]] = {
    "app_frd": ("문서 ID", "기능 ID", "작성 가정", "관련 문서"),
    "app_catalog": ("문서 ID", "작성 가정", "관련 문서"),
    "app_adr": (),  # ADR narrative — 메타 표 선택
}


# ----------------------------------------------------------------------------
# Data classes
# ----------------------------------------------------------------------------
@dataclass
class App:
    name: str
    docs_dir: Path
    src_dir: Path | None = None
    prd: Path | None = None
    fc: Path | None = None
    arch: Path | None = None
    catalog: Path | None = None
    frd_files: list[Path] = field(default_factory=list)
    adr_files: list[Path] = field(default_factory=list)

    @property
    def has_prd(self) -> bool: return self.prd is not None
    @property
    def has_fc(self) -> bool: return self.fc is not None
    @property
    def has_arch(self) -> bool: return self.arch is not None
    @property
    def has_catalog(self) -> bool: return self.catalog is not None
    @property
    def has_context(self) -> bool:
        return self.has_prd or self.has_fc


@dataclass
class DocTypeReport:
    kind: str
    path: str
    missing_sections: list[str] = field(default_factory=list)
    meta_fields_missing: list[str] = field(default_factory=list)
    history_present: bool = False
    four_stage_markers: dict[str, int] = field(default_factory=dict)
    na_violations: int = 0
    placeholder_leftover: int = 0


# ----------------------------------------------------------------------------
# IO
# ----------------------------------------------------------------------------
def _read(p: Path) -> str:
    try:
        return p.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return ""


def _find_docs_dir(repo: Path) -> Path | None:
    for name in DOCS_ROOTS:
        d = repo / name
        if d.is_dir():
            return d
    return None


# ----------------------------------------------------------------------------
# Doc kind detection
# ----------------------------------------------------------------------------
def detect_doc_kind(path: Path, repo: Path) -> str:
    """파일 경로로부터 doc kind 추정. unknown 시 빈 문자열."""
    try:
        rel = path.relative_to(repo)
    except ValueError:
        return ""
    parts = rel.parts
    name = path.name

    # repo 루트 CLAUDE.md
    if len(parts) == 1 and name == "CLAUDE.md":
        return "root_claude"

    # Docs/ 하위
    if not parts or parts[0].lower() not in {r.lower() for r in DOCS_ROOTS}:
        return ""

    if len(parts) == 2:
        # Docs/<file>
        n = name
        if n == "ARCHITECTURE.md":
            return "sol_arch"
        if n == "PRD.md":
            return "sol_prd"
        if n == "DDD_ARCHITECTURE_RULES.md":
            return "ddd"
        if n == "OBJECT_ORIENTED_DESIGN_RULES.md":
            return "oop"
        if n == "BEHAVIORAL_GUIDELINES_RULES.md":
            return "behavior"
        if n == "DOCUMENT_GUIDE.md":
            return "guide"
        return ""

    # Docs/<App>/ 하위
    if len(parts) >= 3:
        # App 폴더 식별 (placeholder _templates 제외)
        app_seg = parts[1]
        if app_seg.startswith("_") or app_seg.startswith("."):
            return ""

        # Docs/<App>/<file>
        if len(parts) == 3:
            n = name
            if n.endswith("-PRD.md"):
                return "app_prd"
            if n.endswith("-FC.md"):
                return "app_fc"
            if n.endswith("-ARCHITECTURE.md"):
                return "app_arch"
            if n.endswith("-ADR-CATALOG.md"):
                return "app_catalog"
            return ""

        # Docs/<App>/FRD/<file>  또는 Docs/<App>/ADR/<file>
        if len(parts) == 4:
            sub = parts[2]
            if sub == "FRD" and RE_FRD_FILE.match(name):
                return "app_frd"
            if sub == "ADR" and RE_ADR_FILE.match(name):
                return "app_adr"
            return ""

    return ""


# ----------------------------------------------------------------------------
# Meta-table / history / markers / FRD validators
# ----------------------------------------------------------------------------
def parse_meta_table(text: str) -> set[str]:
    """문서 상단 메타 표(`| 항목 | 값 |` 패턴)에서 발견된 필드명 집합."""
    found: set[str] = set()
    m = RE_META_TABLE_HEADER.search(text)
    if not m:
        # alt: 첫 라인 셀이 '문서 ID' 류로 시작하는 표 — header line 없이 첫 행이 필드명
        for f in META_REQUIRED_FIELDS:
            if re.search(rf"\|\s*{re.escape(f)}\s*\|", text):
                found.add(f)
        return found
    # 헤더 발견 — 이후 표 영역 내 필드명 검색
    start = m.end()
    region = text[start : start + 1500]  # 메타 표 길이 cap
    for f in META_REQUIRED_FIELDS:
        if re.search(rf"\|\s*{re.escape(f)}\s*\|", region):
            found.add(f)
    return found


def missing_meta_fields(text: str, kind: str | None = None) -> list[str]:
    required = META_FIELDS_BY_KIND.get(kind or "", META_REQUIRED_FIELDS)
    if not required:
        return []
    # parse_meta_table 은 META_REQUIRED_FIELDS 만 검색 → kind별 재검사
    found: set[str] = set()
    for f in required:
        if re.search(rf"\|\s*{re.escape(f)}\s*\|", text):
            found.add(f)
    return [f for f in required if f not in found]


def has_history_table(text: str) -> bool:
    return bool(RE_HISTORY_HEADING.search(text))


def validate_section_headings(text: str, expected_prefixes: Iterable[str]) -> list[str]:
    """heading 본문이 expected_prefix 로 시작하는지 loose 매칭. missing 반환."""
    missing: list[str] = []
    for prefix in expected_prefixes:
        pat = re.compile(rf"^#{{1,6}}\s*{re.escape(prefix)}", re.M)
        if not pat.search(text):
            missing.append(prefix)
    return missing


def count_4stage_markers(text: str) -> dict[str, int]:
    out = {"반드시": 0, "허용": 0, "금지": 0, "절대 금지": 0}
    for m in RE_4STAGE.finditer(text):
        token = m.group(1).replace(" ", "")
        if token == "절대금지":
            out["절대 금지"] += 1
        elif token in out:
            out[token] += 1
    return out


def all_four_stages_present(text: str) -> bool:
    c = count_4stage_markers(text)
    return all(v > 0 for v in c.values())


def count_placeholder_leftover(text: str) -> int:
    return len(RE_PLACEHOLDER.findall(text))


def validate_frd(text: str) -> dict:
    """FRD 핵심 7절 검사 + 빈칸/N/A/placeholder 카운트."""
    missing = validate_section_headings(text, FRD_CORE_HEADINGS)
    na = len(RE_NA_CELL.findall(text)) + len(RE_MISJAKSUNG.findall(text))
    placeholders = count_placeholder_leftover(text)
    return {
        "missing_sections": missing,
        "na_violations": na,
        "placeholder_leftover": placeholders,
    }


# ----------------------------------------------------------------------------
# Backend Services Overview parser
# ----------------------------------------------------------------------------
RE_TABLE_ROW = re.compile(r"^\|[^\n]+\|\s*$", re.M)
RE_TABLE_SEP = re.compile(r"^\|[\s\-:|]+\|\s*$", re.M)


def parse_backend_overview(root_claude_text: str) -> list[str]:
    """root CLAUDE.md 의 Backend Services Overview 표에서 SYSTEM_CODE(App 코드) 컬럼 추출."""
    m = RE_BACKEND_OV.search(root_claude_text)
    if not m:
        return []
    # 헤딩 이후 첫 마크다운 표 블록만 파싱
    tail = root_claude_text[m.end() :]
    # 다음 ## heading 직전까지로 cap
    next_h = re.search(r"^#{1,3}\s", tail, re.M)
    block = tail[: next_h.start()] if next_h else tail

    rows = RE_TABLE_ROW.findall(block)
    if len(rows) < 2:
        return []

    # row[0] = header, row[1] = separator, row[2..] = data
    header_cells = [c.strip() for c in rows[0].strip("|").split("|")]
    # SYSTEM_CODE / App 코드 / SYSTEM 컬럼 식별
    target_idx = None
    for i, h in enumerate(header_cells):
        h_low = h.replace(" ", "").lower()
        if "systemcode" in h_low or "appcode" in h_low or h_low in ("app", "system"):
            target_idx = i
            break
    if target_idx is None:
        # fallback: 1번째 컬럼
        target_idx = 0

    apps: list[str] = []
    data_rows = rows[2:] if RE_TABLE_SEP.match(rows[1]) else rows[1:]
    for r in data_rows:
        cells = [c.strip() for c in r.strip("|").split("|")]
        if target_idx >= len(cells):
            continue
        val = cells[target_idx]
        # placeholder 행 / 빈 행 제외
        if not val or RE_PLACEHOLDER.search(val) or val in {"-", "—"}:
            continue
        # 백틱 제거
        val = val.strip("`").strip()
        if not val:
            continue
        # 영문 대문자 코드만 — 한국어 설명 행 제외
        if re.match(r"^[A-Z][A-Z0-9_]*$", val):
            apps.append(val)
    # dedupe preserving order
    seen: set[str] = set()
    out: list[str] = []
    for a in apps:
        if a not in seen:
            seen.add(a)
            out.append(a)
    return out


# ----------------------------------------------------------------------------
# Solution / App discovery
# ----------------------------------------------------------------------------
RE_SRC_APP_DIR = re.compile(r"^Src[\\/](Mirero[^\\/]+)[\\/]App[\\/]([^\\/]+)$")


def _find_src_apps(repo: Path) -> dict[str, Path]:
    """`Src/Mirero.*/App/<App>/` 폴더 매핑 — key=upper(App folder name) → 경로."""
    out: dict[str, Path] = {}
    src = repo / "Src"
    if not src.is_dir():
        src = repo / "src"
        if not src.is_dir():
            return out
    for product in src.iterdir():
        if not product.is_dir() or not product.name.lower().startswith("mirero"):
            continue
        app_root = product / "App"
        if not app_root.is_dir():
            continue
        for app in app_root.iterdir():
            if not app.is_dir():
                continue
            # 패키지 같은 폴더명 (예: Mirero.PCC.XLab.App.MapOverview.FabView) 제외
            if "." in app.name or app.name.lower().startswith("mirero"):
                continue
            out[app.name.upper()] = app
    return out


def _find_docs_apps(docs_dir: Path) -> dict[str, Path]:
    """`Docs/<App>/` 폴더 매핑 (placeholder `_templates`, supporting docs 제외)."""
    out: dict[str, Path] = {}
    for child in docs_dir.iterdir():
        if not child.is_dir():
            continue
        if child.name.startswith("_") or child.name.startswith("."):
            continue
        out[child.name.upper()] = child
    return out


def _collect_app_files(app: App) -> None:
    d = app.docs_dir
    # 메인 4종 (suffix 매칭 — App 폴더명 대소문자 무시)
    for f in d.iterdir():
        if not f.is_file() or not f.name.endswith(".md"):
            continue
        name = f.name
        if name.endswith("-PRD.md") and app.prd is None:
            app.prd = f
        elif name.endswith("-FC.md") and app.fc is None:
            app.fc = f
        elif name.endswith("-ARCHITECTURE.md") and app.arch is None:
            app.arch = f
        elif name.endswith("-ADR-CATALOG.md") and app.catalog is None:
            app.catalog = f
    # FRD/
    frd_dir = d / "FRD"
    if frd_dir.is_dir():
        for f in sorted(frd_dir.iterdir()):
            if f.is_file() and RE_FRD_FILE.match(f.name):
                app.frd_files.append(f)
    # ADR/
    adr_dir = d / "ADR"
    if adr_dir.is_dir():
        for f in sorted(adr_dir.iterdir()):
            if f.is_file() and RE_ADR_FILE.match(f.name):
                app.adr_files.append(f)


def discover_apps(repo: Path) -> tuple[Path | None, Path | None, list[App], list[str]]:
    """root CLAUDE.md, docs_dir, apps (fs 기준), overview_apps (Backend Services Overview)."""
    root_claude = repo / "CLAUDE.md"
    root_claude_path: Path | None = root_claude if root_claude.exists() else None

    docs_dir = _find_docs_dir(repo)

    overview_apps: list[str] = []
    if root_claude_path is not None:
        overview_apps = parse_backend_overview(_read(root_claude_path))

    apps: list[App] = []
    if docs_dir is not None:
        docs_apps = _find_docs_apps(docs_dir)
        src_apps = _find_src_apps(repo)
        # union — Docs/<App>/ 와 Src App 합집합
        all_keys = sorted(set(docs_apps) | set(src_apps))
        for key in all_keys:
            d = docs_apps.get(key)
            if d is None:
                # Src 만 있고 Docs 없는 케이스 — 가상의 App 등록 (coverage = 0)
                # docs_dir/<key> 가상 경로
                d = docs_dir / key
            app = App(name=key, docs_dir=d, src_dir=src_apps.get(key))
            if d.exists():
                _collect_app_files(app)
            apps.append(app)

    return root_claude_path, docs_dir, apps, overview_apps


# ----------------------------------------------------------------------------
# Per-doc compliance report
# ----------------------------------------------------------------------------
def build_doc_report(path: Path, repo: Path, kind: str | None = None) -> DocTypeReport | None:
    k = kind or detect_doc_kind(path, repo)
    if not k:
        return None
    text = _read(path)
    rep = DocTypeReport(
        kind=k,
        path=str(path.relative_to(repo).as_posix()) if path.is_absolute() and repo in path.parents or path == repo else str(path),
        history_present=has_history_table(text),
        four_stage_markers=count_4stage_markers(text),
        placeholder_leftover=count_placeholder_leftover(text),
    )
    # 메타 필드 — root_claude/rule 류는 표 없을 수 있음
    if k not in ("root_claude", "behavior", "guide", "ddd", "oop"):
        rep.meta_fields_missing = missing_meta_fields(text, k)
    # 핵심 헤딩
    expected = KIND_HEADINGS.get(k)
    if expected:
        rep.missing_sections = validate_section_headings(text, expected)
    # FRD 빈칸/NA
    if k == "app_frd":
        v = validate_frd(text)
        rep.missing_sections = v["missing_sections"]
        rep.na_violations = v["na_violations"]
        rep.placeholder_leftover = v["placeholder_leftover"]
    return rep


# ----------------------------------------------------------------------------
# 4-stage marker rule pool
# ----------------------------------------------------------------------------
def collect_rule_pool(repo: Path, docs_dir: Path | None, apps: list[App]) -> list[Path]:
    """4단계 마커 검사 대상 풀: DDD/OOP 룰 + 솔루션 ARCHITECTURE + 각 App-ARCHITECTURE."""
    pool: list[Path] = []
    if docs_dir is None:
        return pool
    for name in ("DDD_ARCHITECTURE_RULES.md", "OBJECT_ORIENTED_DESIGN_RULES.md", "ARCHITECTURE.md"):
        p = docs_dir / name
        if p.exists():
            pool.append(p)
    for app in apps:
        if app.arch is not None:
            pool.append(app.arch)
    return pool


# ----------------------------------------------------------------------------
# Self-test
# ----------------------------------------------------------------------------
if __name__ == "__main__":
    import sys

    # Quick smoke test
    sample_meta = """| 항목 | 값 |
|---|---|
| 문서 ID | XLAB-PRD |
| 버전 | 0.1 |
| 작성 가정 | sample |
| 관련 문서 | [CLAUDE](../CLAUDE.md) |

## 변경 이력
| 버전 | 일자 | 변경 요약 | 작성자 |
|---|---|---|---|
| 0.1 | 2026-05-16 | 초안 | tester |

## 1. 제품 배경
content
## 3. 목표
content
"""
    assert parse_meta_table(sample_meta) == {"문서 ID", "버전", "작성 가정", "관련 문서"}
    assert has_history_table(sample_meta)
    assert missing_meta_fields(sample_meta) == []
    assert "1. 제품 배경" not in validate_section_headings(sample_meta, ["1. 제품 배경", "3. 목표"])
    assert validate_section_headings(sample_meta, ["1. 제품 배경", "3. 목표"]) == []

    sample_4 = "반드시 X. 허용 Y. 금지 Z. 절대 금지 W."
    c = count_4stage_markers(sample_4)
    assert c == {"반드시": 1, "허용": 1, "금지": 1, "절대 금지": 1}, c
    assert all_four_stages_present(sample_4)

    sample_overview = """## Backend Services Overview

| App | TFM | 설명 |
|---|---|---|
| `LOADER` | net8.0 | 로더 |
| `MASTER` | net8.0 | 마스터 |
| `{SYSTEM_CODE}` | - | placeholder |
"""
    assert parse_backend_overview(sample_overview) == ["LOADER", "MASTER"], parse_backend_overview(sample_overview)

    print("team_template.py self-test OK", file=sys.stderr)
