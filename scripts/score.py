#!/usr/bin/env python3
"""AI-Readiness Cartography — repo scorer (v2 rubric, 100 points, 7 categories).

Audits a repository against the 7-category AI-Ready rubric and emits structured
findings, ROI-ranked actions, and a JSON scorecard suitable for the dashboard
template at assets/template.html.

Usage:
    python score.py [repo_path]                # default: .
    python score.py /path/to/repo --json out.json
    python score.py . --markdown               # human-readable to stdout (default)

Pure stdlib — no external dependencies.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import team_template as tt

# ----------------------------------------------------------------------------
# Constants
# ----------------------------------------------------------------------------
IGNORE_DIRS = {
    "node_modules", ".venv", "venv", ".git", ".next", "dist", "build",
    "__pycache__", ".turbo", ".ruff_cache", ".pytest_cache", ".mypy_cache",
    "target", "out", "coverage", ".cache", ".idea", ".vscode",
}
CODE_EXTS = {".py", ".ts", ".tsx", ".js", ".jsx", ".go", ".rs", ".java", ".kt", ".rb", ".php", ".sql", ".swift", ".cs"}
CONTEXT_FILES = ("CLAUDE.md", "AGENTS.md")
SUPPORTING_DOCS = ("ARCHITECTURE.md", "ADR.md", "ADR-CATALOG.md", "DOCUMENT_GUIDE.md")

# Module discovery patterns (glob, relative to repo root)
MONOREPO_PATTERNS: tuple[str, ...] = (
    "apps/*",
    "packages/*",
    "services/*",
    "Src/*/App/*",   # .NET pattern — Src/<Product>/App/<Module>
    "src/*/App/*",   # lowercase variant
)

# External docs root candidates (directory names tried in order)
DOCS_ROOTS: tuple[str, ...] = ("Docs", "docs")

# Heuristic regex
RE_PATH_REF = re.compile(
    r"(?<![A-Za-z0-9_/])"
    r"((?:\./|[A-Za-z0-9_]+/)[A-Za-z0-9_./-]+\.(?:py|ts|tsx|js|jsx|md|sql|json|yaml|yml|toml|html|css|sh|go|rs|java|kt|rb|php|cs|csproj|sln|xaml))"
)
RE_BASH_FENCE = re.compile(r"```(?:bash|sh|shell|zsh|console)\s*\n([\s\S]*?)```", re.IGNORECASE)
RE_NON_OBVIOUS = re.compile(
    r"(Why:|Note:|Gotcha|Warning|Don't|Caveat|Important:|"
    r"반드시|허용|금지|절대\s*금지|주의)",
    re.IGNORECASE,
)
RE_REL_LINK = re.compile(r"\[[^\]]+\]\((?!https?://)([^)]+)\)")
RE_DEPS_HEADING = re.compile(r"^#+\s.*(depend|cross[- ]module|imports?|see also|related)", re.IGNORECASE | re.MULTILINE)
RE_PURPOSE_HEADING = re.compile(r"^#+\s.*(purpose|owns?|configures?|overview)", re.IGNORECASE | re.MULTILINE)
RE_PATTERN_HEADING = re.compile(r"^#+\s.*(pattern|how to|common change|workflow|recipe)", re.IGNORECASE | re.MULTILINE)
RE_MERMAID = re.compile(r"```mermaid", re.IGNORECASE)


# ----------------------------------------------------------------------------
# Data classes
# ----------------------------------------------------------------------------
@dataclass
class Module:
    path: Path
    rel: str
    code_files: int
    has_context: bool
    context_file: Path | None = None
    context_kind: str = ""  # "CLAUDE.md" | "AGENTS.md" | "PRD-*.md" | "FC-*.md" | "FRD-*.md" | ""


@dataclass
class CategoryScore:
    name: str
    score: int
    max: int
    evidence: dict[str, Any] = field(default_factory=dict)
    sub_scores: dict[str, int] = field(default_factory=dict)
    findings: list[str] = field(default_factory=list)


@dataclass
class Action:
    title: str
    category: str
    effort: str            # S / M / L
    effort_hours: float
    impact: str            # human-readable
    impact_score: int      # 1-10
    priority: float        # impact / effort_hours


@dataclass
class Report:
    meta: dict[str, Any]
    total: int
    grade: str
    grade_color: str
    categories: dict[str, CategoryScore]
    insights: list[str]
    actions: list[Action]
    extras: dict[str, Any]
    template_compliance: dict[str, Any] = field(default_factory=dict)


# ----------------------------------------------------------------------------
# Discovery
# ----------------------------------------------------------------------------
def walk_files(root: Path) -> list[Path]:
    out: list[Path] = []
    for r, dirs, files in os.walk(root):
        dirs[:] = [d for d in dirs if d not in IGNORE_DIRS and not d.startswith(".")]
        for f in files:
            out.append(Path(r) / f)
    return out


def find_core_modules(repo: Path) -> list[Module]:
    """Top-level + glob-matched (MONOREPO_PATTERNS) code-bearing dirs.

    Resolves parents of glob hits to drop ancestor dirs from top-level enumeration,
    preventing duplicate counting (e.g. Src vs Src/Foo/App/Bar)."""
    candidates: set[Path] = set()
    glob_parents: set[Path] = set()
    repo_resolved = repo.resolve()

    # 1) Glob-matched candidates
    for pattern in MONOREPO_PATTERNS:
        for match in repo.glob(pattern):
            if not match.is_dir():
                continue
            if match.name in IGNORE_DIRS or match.name.startswith("."):
                continue
            resolved = match.resolve()
            candidates.add(resolved)
            cur = resolved.parent
            while True:
                if cur == repo_resolved:
                    glob_parents.add(cur)
                    break
                if repo_resolved not in cur.parents:
                    break
                glob_parents.add(cur)
                cur = cur.parent

    # 2) Top-level dirs (보강용)
    for d in sorted(repo.iterdir()):
        if not d.is_dir():
            continue
        if d.name in IGNORE_DIRS or d.name.startswith(".") or d.name.startswith("_"):
            continue
        resolved = d.resolve()
        if resolved in glob_parents:
            continue
        candidates.add(resolved)

    modules: list[Module] = []
    for d in sorted(candidates):
        code_count = 0
        for r, dirs, files in os.walk(d):
            dirs[:] = [x for x in dirs if x not in IGNORE_DIRS and not x.startswith(".")]
            for f in files:
                if Path(f).suffix in CODE_EXTS:
                    code_count += 1
        if code_count == 0:
            continue
        ctx_file, ctx_kind = pick_context_file(d, repo)
        modules.append(Module(
            path=d,
            rel=d.relative_to(repo_resolved).as_posix(),
            code_files=code_count,
            has_context=ctx_file is not None,
            context_file=ctx_file,
            context_kind=ctx_kind,
        ))
    return modules


def find_docs_dir(repo: Path, module_name: str) -> Path | None:
    """Locate repo/<DOCS_ROOTS>/<module_name>-equivalent (case-insensitive). None if missing."""
    target = module_name.lower()
    for root_name in DOCS_ROOTS:
        root = repo / root_name
        if not root.is_dir():
            continue
        for child in root.iterdir():
            if not child.is_dir():
                continue
            if child.name in IGNORE_DIRS or child.name.startswith("."):
                continue
            if child.name.lower() == target:
                return child
    return None


def pick_context_file(d: Path, repo: Path) -> tuple[Path | None, str]:
    """1st: module-local CLAUDE/AGENTS. 2nd: external Docs/<module>/ (PRD/FC/FRD)."""
    # 1순위: 모듈 폴더 내부
    for name in CONTEXT_FILES:
        p = d / name
        if p.exists():
            return p, name
    # 2순위: 외부 Docs/<모듈명>/ — PRD > FC > ARCHITECTURE > FRD-첫번째
    docs_dir = find_docs_dir(repo, d.name)
    if docs_dir is not None:
        for prefix in ("PRD-", "FC-"):
            matches = sorted(docs_dir.glob(f"{prefix}*.md"))
            if matches:
                return matches[0], f"{prefix}*.md"
        arch = docs_dir / "ARCHITECTURE.md"
        if arch.exists():
            return arch, "ARCHITECTURE.md"
        frd_dir = docs_dir / "FRD"
        if frd_dir.is_dir():
            frd_files = sorted(frd_dir.glob("FRD-*.md"))
            if frd_files:
                return frd_files[0], "FRD-*.md"
    return None, ""


def find_all_context_files(repo: Path) -> list[Path]:
    out: list[Path] = []
    for r, dirs, files in os.walk(repo):
        dirs[:] = [d for d in dirs if d not in IGNORE_DIRS and not d.startswith(".")]
        for f in files:
            if f in CONTEXT_FILES:
                out.append(Path(r) / f)
    return out


def find_extended_context_files(repo: Path) -> list[Path]:
    """CLAUDE/AGENTS + Docs/<Mod>/{PRD-*, FC-*, FRD/FRD-*}.md. score_b 전용.
    템플릿/감사용 (_templates, _audit) 폴더는 제외.
    Windows NTFS case-insensitive — DOCS_ROOTS 중 동일 폴더 가리키면 1회만 처리."""
    out: list[Path] = list(find_all_context_files(repo))
    seen: set[Path] = set()
    seen_roots: set[Path] = set()
    for docs_root_name in DOCS_ROOTS:
        docs_root = repo / docs_root_name
        if not docs_root.is_dir():
            continue
        try:
            resolved_root = docs_root.resolve()
        except OSError:
            resolved_root = docs_root
        if resolved_root in seen_roots:
            continue
        seen_roots.add(resolved_root)
        # Docs/ 직속 supporting docs (ARCHITECTURE/ADR/ADR-CATALOG/DOCUMENT_GUIDE)
        for name in SUPPORTING_DOCS:
            p = docs_root / name
            if p.exists():
                rp = p.resolve()
                if rp not in seen:
                    seen.add(rp)
                    out.append(p)
        for child in docs_root.iterdir():
            if not child.is_dir():
                continue
            if child.name in IGNORE_DIRS:
                continue
            if child.name.startswith(".") or child.name.startswith("_"):
                continue
            for prefix in ("PRD-", "FC-"):
                for p in sorted(child.glob(f"{prefix}*.md")):
                    rp = p.resolve()
                    if rp not in seen:
                        seen.add(rp)
                        out.append(p)
            # App 폴더 ARCHITECTURE
            arch = child / "ARCHITECTURE.md"
            if arch.exists():
                rp = arch.resolve()
                if rp not in seen:
                    seen.add(rp)
                    out.append(arch)
            frd_dir = child / "FRD"
            if frd_dir.is_dir():
                for p in sorted(frd_dir.glob("FRD-*.md")):
                    rp = p.resolve()
                    if rp not in seen:
                        seen.add(rp)
                        out.append(p)
    return out


def classify_context_file(p: Path) -> str:
    """router | content | supporting | other"""
    name = p.name
    if name in ("CLAUDE.md", "AGENTS.md"):
        return "router"
    if name.startswith(("PRD-", "FC-", "FRD-")) and name.endswith(".md"):
        return "content"
    if name in SUPPORTING_DOCS:
        return "supporting"
    return "other"


def find_root_claude(repo: Path) -> Path | None:
    p = repo / "CLAUDE.md"
    return p if p.exists() else None


def count_lines(p: Path) -> int:
    try:
        return len(p.read_text(errors="ignore").splitlines())
    except Exception:
        return 0


def read_text(p: Path) -> str:
    try:
        return p.read_text(errors="ignore")
    except Exception:
        return ""


def file_mtime(p: Path) -> float:
    try:
        return p.stat().st_mtime
    except Exception:
        return 0.0


# ----------------------------------------------------------------------------
# A. Solution & App Coverage (team-template)
# ----------------------------------------------------------------------------
def score_a(apps: list[tt.App], root_claude: Path | None, overview_apps: list[str]) -> CategoryScore:
    """팀 템플릿 기준 — App별 진입 문서(PRD or FC) 보유 + Backend Services Overview 정합."""
    total = len(apps)
    covered = sum(1 for a in apps if a.has_context)
    coverage = (covered / total) if total else 0.0
    pts = round(coverage * 15)

    findings: list[str] = []

    # root CLAUDE.md 페널티
    if root_claude is None:
        pts = max(0, pts - 5)
        findings.append("root CLAUDE.md 부재 — solution router/Backend Services Overview SSOT 없음")

    # Backend Services Overview gap: overview에 등재됐지만 파일시스템 App 없음
    fs_names = {a.name.upper() for a in apps}
    overview_set = {x.upper() for x in overview_apps}
    overview_only = sorted(overview_set - fs_names)
    fs_only = sorted(fs_names - overview_set)
    if overview_only:
        pts = max(0, pts - 2 * len(overview_only))
        findings.append(
            f"Backend Services Overview 등재 App {len(overview_only)}개에 대응하는 Docs/<App>/ 폴더 없음: {', '.join(overview_only[:5])}"
        )
    if fs_only and root_claude is not None:
        findings.append(
            f"Docs/<App>/ 또는 Src App 존재하나 Backend Services Overview 미등재 {len(fs_only)}개: {', '.join(fs_only[:5])}"
        )

    # Src ↔ Docs mismatch
    src_docs_mismatch = [a.name for a in apps if a.src_dir is None or not (a.docs_dir.exists())]
    if src_docs_mismatch:
        findings.append(
            f"Src↔Docs 매핑 불일치 {len(src_docs_mismatch)}개 (Docs 또는 Src 폴더 누락): {', '.join(src_docs_mismatch[:5])}"
        )

    # 미커버 App
    uncovered = [a.name for a in apps if not a.has_context]
    if uncovered:
        findings.append(
            f"진입 문서(PRD/FC) 미보유 App {len(uncovered)}개: {', '.join(uncovered[:5])}"
        )

    pts = max(0, min(15, pts))

    return CategoryScore(
        name="Solution & App Coverage",
        score=pts,
        max=15,
        evidence={
            "apps_total": len(apps),
            "apps_with_context": covered,
            "coverage_ratio": round(coverage, 3),
            "root_claude": str(root_claude.name) if root_claude else None,
            "overview_apps": sorted(overview_set),
            "fs_apps": sorted(fs_names),
            "overview_only": overview_only,
            "fs_only": fs_only,
        },
        findings=findings,
    )


# ----------------------------------------------------------------------------
# B. Document Structural Compliance (team-template)
# ----------------------------------------------------------------------------
def score_b(
    repo: Path,
    root_claude: Path | None,
    docs_dir: Path | None,
    apps: list[tt.App],
    template_compliance: dict[str, Any],
) -> CategoryScore:
    """팀 템플릿 구조 준수도. B1 Router / B2 Meta&History / B3 4Stage / B4 SectionCompliance / B5 NoBlank."""
    sub: dict[str, int] = {}
    findings: list[str] = []

    # ---- 검사 대상 doc 풀 수집 ----
    # content/supporting 풀 (B2 메타·이력 대상)
    content_supporting: list[Path] = []
    if docs_dir is not None:
        for name in tt.REQUIRED_DOCS_ROOT:
            p = docs_dir / name
            if p.exists():
                content_supporting.append(p)
        # 솔루션 PRD (선택)
        sol_prd = docs_dir / "PRD.md"
        if sol_prd.exists():
            content_supporting.append(sol_prd)
    # App 콘텐츠
    for app in apps:
        for p in (app.prd, app.fc, app.arch, app.catalog):
            if p is not None:
                content_supporting.append(p)
        content_supporting.extend(app.frd_files)
        content_supporting.extend(app.adr_files)

    # FRD 풀
    frd_files: list[Path] = [f for a in apps for f in a.frd_files]

    # 룰 풀 (4단계 마커)
    rule_pool = tt.collect_rule_pool(repo, docs_dir, apps)

    # ---- B1 RouterCompleteness (4) ----
    if root_claude is None:
        sub["B1_RouterCompleteness"] = 0
        findings.append("root CLAUDE.md 부재 — 라우터 검사 불가")
    else:
        text = tt._read(root_claude)
        missing = tt.validate_section_headings(text, tt.ROOT_CLAUDE_HEADINGS)
        ratio = 1.0 - (len(missing) / max(1, len(tt.ROOT_CLAUDE_HEADINGS)))
        sub["B1_RouterCompleteness"] = round(4 * ratio)
        if missing:
            findings.append(f"root CLAUDE.md 누락 핵심 섹션: {', '.join(missing)}")
        # template_compliance 등재
        rep = tt.build_doc_report(root_claude, repo, "root_claude")
        if rep:
            template_compliance[rep.path] = asdict(rep)

    # ---- B2 MetaTable & History (4) ----
    meta_pool: list[tuple[Path, str]] = []
    for p in content_supporting:
        k = tt.detect_doc_kind(p, repo)
        if k and k not in ("ddd", "oop", "behavior", "guide", "app_adr"):
            meta_pool.append((p, k))
    if meta_pool:
        meta_pass = 0
        history_pass = 0
        for p, k in meta_pool:
            text = tt._read(p)
            if not tt.missing_meta_fields(text, k):
                meta_pass += 1
            if tt.has_history_table(text):
                history_pass += 1
        meta_ratio = meta_pass / len(meta_pool)
        history_ratio = history_pass / len(meta_pool)
        sub["B2_MetaHistory"] = round(4 * (meta_ratio + history_ratio) / 2)
        meta_gap = len(meta_pool) - meta_pass
        history_gap = len(meta_pool) - history_pass
        if meta_gap:
            findings.append(f"메타 표 필수 필드 누락 문서 {meta_gap}건 (문서 ID/버전/작성 가정/관련 문서)")
        if history_gap:
            findings.append(f"변경 이력 표 누락 문서 {history_gap}건")
    else:
        sub["B2_MetaHistory"] = 0
        findings.append("content/supporting 문서 자체 없음 — 메타/이력 검사 불가")

    # ---- B3 FourStageMarkers (4) ----
    if rule_pool:
        passed = sum(1 for p in rule_pool if tt.all_four_stages_present(tt._read(p)))
        ratio = passed / len(rule_pool)
        sub["B3_FourStageMarkers"] = round(4 * ratio)
        gap = len(rule_pool) - passed
        if gap:
            missing_files = [str(p.relative_to(repo).as_posix()) for p in rule_pool if not tt.all_four_stages_present(tt._read(p))]
            findings.append(f"4단계 마커(반드시/허용/금지/절대 금지) 일부 누락 {gap}건: {', '.join(missing_files[:3])}")
    else:
        sub["B3_FourStageMarkers"] = 0
        findings.append("룰 문서(DDD/OOP/ARCH) 없음 — 4단계 마커 검사 불가")

    # ---- B4 SectionCompliance (4) ----
    if content_supporting:
        section_pass = 0
        section_total = 0
        for p in content_supporting:
            kind = tt.detect_doc_kind(p, repo)
            if not kind or kind not in tt.KIND_HEADINGS:
                continue
            section_total += 1
            text = tt._read(p)
            missing = tt.validate_section_headings(text, tt.KIND_HEADINGS[kind])
            rep = tt.build_doc_report(p, repo, kind)
            if rep:
                template_compliance[rep.path] = asdict(rep)
            if not missing:
                section_pass += 1
        if section_total:
            sub["B4_SectionCompliance"] = round(4 * section_pass / section_total)
            gap = section_total - section_pass
            if gap:
                findings.append(f"핵심 섹션 누락 문서 {gap}/{section_total}건 — template_compliance 참조")
        else:
            sub["B4_SectionCompliance"] = 0
            findings.append("doc-kind 식별 가능한 문서 없음 — 섹션 검사 불가")
    else:
        sub["B4_SectionCompliance"] = 0

    # ---- B5 NoBlankViolations (4) ----
    if frd_files:
        clean = 0
        for p in frd_files:
            text = tt._read(p)
            v = tt.validate_frd(text)
            if v["na_violations"] == 0 and v["placeholder_leftover"] == 0:
                clean += 1
        ratio = clean / len(frd_files)
        sub["B5_NoBlankViolations"] = round(4 * ratio)
        gap = len(frd_files) - clean
        if gap:
            findings.append(f"FRD 빈칸/N/A 또는 placeholder 잔존 {gap}/{len(frd_files)}건 — '없음' 명기로 치환 필요")
    else:
        sub["B5_NoBlankViolations"] = 0

    pts = sum(sub.values())
    pts = max(0, min(20, pts))

    return CategoryScore(
        name="Document Structural Compliance",
        score=pts,
        max=20,
        evidence={
            "content_supporting_total": len(content_supporting),
            "frd_total": len(frd_files),
            "rule_pool_total": len(rule_pool),
        },
        sub_scores=sub,
        findings=findings,
    )


# ----------------------------------------------------------------------------
# C. Tribal Knowledge Externalization (Five-Question Framework)
# ----------------------------------------------------------------------------
def score_c(modules: list[Module], repo: Path) -> CategoryScore:
    if not modules:
        return CategoryScore(name="Tribal Knowledge Externalization", score=0, max=20)

    # Detect MEMORY.md / ADR / decisions
    has_memory = (repo / "MEMORY.md").exists()
    # Check Claude Code memory dir for project
    claude_mem_dir_hits = list(repo.glob(".claude/memory*"))
    adr_dirs = [
        repo / "docs" / "adr",
        repo / "docs" / "decisions",
        repo / "adr",
    ]
    has_adr = any(d.exists() for d in adr_dirs)
    has_tribal_store = has_memory or has_adr or bool(claude_mem_dir_hits)

    # Per-module Q1-Q4 from context file content
    q_pass = [0, 0, 0, 0, 0]  # Q1..Q5
    n = max(1, len(modules))
    for m in modules:
        if not m.context_file:
            continue
        text = read_text(m.context_file)
        if RE_PURPOSE_HEADING.search(text) or "owns" in text.lower() or "configures" in text.lower():
            q_pass[0] += 1
        if RE_PATTERN_HEADING.search(text):
            q_pass[1] += 1
        if RE_NON_OBVIOUS.search(text):
            q_pass[2] += 1
        if RE_DEPS_HEADING.search(text) or "depends on" in text.lower():
            q_pass[3] += 1

    # Q5: tribal store presence (binary, project-wide)
    q5_score = 4 if has_tribal_store else 0

    # Sum: each Q is 4 points max. Q1-Q4 = 4 * avg pass rate
    sub = {
        "C_Q1_Owns": round(4 * q_pass[0] / n),
        "C_Q2_Patterns": round(4 * q_pass[1] / n),
        "C_Q3_NonObvious": round(4 * q_pass[2] / n),
        "C_Q4_Dependencies": round(4 * q_pass[3] / n),
        "C_Q5_TribalStore": q5_score,
    }
    pts = sum(sub.values())
    pts = max(0, min(20, pts))

    findings: list[str] = []
    if not has_tribal_store:
        findings.append("MEMORY.md / ADR / docs/decisions 부재 — tribal knowledge 외부화 store 없음")
    if q_pass[3] < n / 2:
        findings.append("Cross-module dependencies 섹션이 절반 이상 module에서 누락")
    if q_pass[1] < n / 2:
        findings.append("Common modification patterns 섹션 누락")

    return CategoryScore(
        name="Tribal Knowledge Externalization",
        score=pts,
        max=20,
        evidence={
            "memory_md": has_memory,
            "adr": has_adr,
            "modules_total": n,
            "q1_owns": q_pass[0],
            "q2_patterns": q_pass[1],
            "q3_nonobvious": q_pass[2],
            "q4_deps": q_pass[3],
        },
        sub_scores=sub,
        findings=findings,
    )


# ----------------------------------------------------------------------------
# D. Cross-Module Dependency & Data Flow Mapping
# ----------------------------------------------------------------------------
def score_d(repo: Path, context_files: list[Path]) -> CategoryScore:
    has_arch = any((repo / p).exists() for p in (
        "ARCHITECTURE.md", "docs/architecture.md", "docs/ARCHITECTURE.md",
        "docs/dependency-graph.md", "docs/data-flow.md",
    ))
    # App별 ARCHITECTURE 존재도 인정
    if not has_arch:
        for docs_root_name in DOCS_ROOTS:
            docs_root = repo / docs_root_name
            if not docs_root.is_dir():
                continue
            for child in docs_root.iterdir():
                if child.is_dir() and not child.name.startswith(("_", ".")):
                    if (child / "ARCHITECTURE.md").exists():
                        has_arch = True
                        break
            if has_arch:
                break
    has_mermaid = any(RE_MERMAID.search(read_text(p)) for p in context_files)
    has_deps_section = sum(1 for p in context_files if RE_DEPS_HEADING.search(read_text(p)))
    has_workspace = any((repo / f).exists() for f in (
        "turbo.json", "nx.json", "pnpm-workspace.yaml", "lerna.json",
    ))

    pts = 0
    if has_arch:
        pts += 6
    if has_mermaid:
        pts += 3
    if has_deps_section >= max(1, len(context_files) // 2):
        pts += 4
    elif has_deps_section >= 1:
        pts += 2
    if has_workspace:
        pts += 2  # graph derivable
    pts = max(0, min(15, pts))

    findings: list[str] = []
    if not has_arch:
        findings.append("ARCHITECTURE.md / dependency map 부재")
    if not has_mermaid:
        findings.append("mermaid 다이어그램 없음 — 시각적 의존도 표현 부재")
    if has_deps_section == 0:
        findings.append("어떤 context file에도 cross-module dependency 섹션 없음")

    return CategoryScore(
        name="Cross-Module Dependency Mapping",
        score=pts,
        max=15,
        evidence={
            "architecture_doc": has_arch,
            "mermaid_diagrams": has_mermaid,
            "context_with_deps_section": has_deps_section,
            "monorepo_workspace": has_workspace,
        },
        findings=findings,
    )


# ----------------------------------------------------------------------------
# E. Verification & Quality Gates
# ----------------------------------------------------------------------------
def score_e(repo: Path, context_files: list[Path]) -> CategoryScore:
    sub: dict[str, int] = {}

    # E1 Reference accuracy: parse all path-like refs from context, verify existence
    total_refs = 0
    bad_refs: list[tuple[Path, str]] = []
    for p in context_files:
        text = read_text(p)
        for ref in set(RE_PATH_REF.findall(text)):
            total_refs += 1
            # try repo-relative and context-file-relative
            candidates = [repo / ref, p.parent / ref]
            if not any(c.exists() for c in candidates):
                bad_refs.append((p, ref))
    if total_refs == 0:
        sub["E1_RefAccuracy"] = 2  # neutral — nothing to verify
    else:
        accuracy = (total_refs - len(bad_refs)) / total_refs
        sub["E1_RefAccuracy"] = round(5 * accuracy)

    # E2 Critic / review infra
    has_codeowners = any((repo / p).exists() for p in (".github/CODEOWNERS", "CODEOWNERS", "docs/CODEOWNERS"))
    has_pr_template = any((repo / p).exists() for p in (
        ".github/pull_request_template.md", ".github/PULL_REQUEST_TEMPLATE.md",
    ))
    e2 = 0
    if has_codeowners:
        e2 += 2
    if has_pr_template:
        e2 += 2
    sub["E2_CriticReview"] = e2

    # E3 Task validation commands actually exist
    have_pkg_json = (repo / "package.json").exists()
    have_pyproject = (repo / "pyproject.toml").exists() or (repo / "apps/api/pyproject.toml").exists() or any(repo.glob("**/pyproject.toml"))
    have_make = (repo / "Makefile").exists()
    have_husky = (repo / ".husky").exists() or (repo / ".husky").is_dir()
    have_workflows = (repo / ".github" / "workflows").exists()
    e3 = 0
    if have_pkg_json or have_pyproject or have_make:
        e3 += 2
    if have_husky:
        e3 += 1
    if have_workflows:
        e3 += 1
    sub["E3_TaskValidation"] = min(4, e3)

    # E4 Prompt / agent eval tests
    has_evals = any((repo / p).exists() for p in ("evals", "benchmarks", "agent-evals", "prompts/test", "tests/agent"))
    sub["E4_PromptTests"] = 2 if has_evals else 0

    pts = sum(sub.values())
    pts = max(0, min(15, pts))

    findings: list[str] = []
    if bad_refs:
        sample = ", ".join(f"{p.relative_to(repo)}: {ref}" for p, ref in bad_refs[:4])
        findings.append(f"hallucinated path {len(bad_refs)}건 (총 {total_refs} 참조 중) — 예: {sample}")
    if not has_codeowners and not has_pr_template:
        findings.append("CODEOWNERS / PR template 없음 — independent critic infra 부재")
    if not has_evals:
        findings.append("agent eval / prompt test 디렉터리 없음 — AI 회귀 catch 없음")

    return CategoryScore(
        name="Verification & Quality Gates",
        score=pts,
        max=15,
        evidence={
            "ref_total": total_refs,
            "ref_broken": len(bad_refs),
            "codeowners": has_codeowners,
            "pr_template": has_pr_template,
            "ci_workflows": have_workflows,
            "husky": have_husky,
            "evals_dir": has_evals,
        },
        sub_scores=sub,
        findings=findings,
    )


# ----------------------------------------------------------------------------
# F. Freshness & Self-Maintenance
# ----------------------------------------------------------------------------
def latest_code_mtime(d: Path) -> float:
    latest = 0.0
    for r, dirs, files in os.walk(d):
        dirs[:] = [x for x in dirs if x not in IGNORE_DIRS and not x.startswith(".")]
        for f in files:
            if Path(f).suffix in CODE_EXTS:
                latest = max(latest, file_mtime(Path(r) / f))
    return latest


def score_f(modules: list[Module], repo: Path) -> CategoryScore:
    # Drift: how many modules' context is older than their newest code file
    drifted = 0
    measurable = 0
    for m in modules:
        if not m.context_file:
            continue
        ctx_mtime = file_mtime(m.context_file)
        code_mtime = latest_code_mtime(m.path)
        if code_mtime == 0:
            continue
        measurable += 1
        # 30-day staleness window
        if ctx_mtime + 30 * 86400 < code_mtime:
            drifted += 1
    drift_ratio = (drifted / measurable) if measurable else 0.0

    # CI / hook validators
    workflows = list((repo / ".github" / "workflows").glob("*.yml")) + list((repo / ".github" / "workflows").glob("*.yaml")) if (repo / ".github" / "workflows").exists() else []
    ctx_validation_workflow = any(
        re.search(r"context|docs|claude|adr|reference", read_text(w), re.IGNORECASE)
        for w in workflows
    )
    hook_validates_paths = (repo / ".husky" / "pre-commit").exists() or (repo / ".husky" / "pre-push").exists()

    pts = 0
    if measurable:
        # up to 6 pts for low drift
        pts += round(6 * (1 - drift_ratio))
    if ctx_validation_workflow:
        pts += 2
    if hook_validates_paths:
        pts += 2
    pts = max(0, min(10, pts))

    findings: list[str] = []
    if drifted:
        findings.append(f"{drifted}/{measurable} module의 context가 코드 변경 후 30일 이상 미갱신")
    if not ctx_validation_workflow:
        findings.append("CI에 context / docs validation step 없음")
    if not hook_validates_paths:
        findings.append("pre-commit / pre-push hook에 path 검증 없음")

    return CategoryScore(
        name="Freshness & Self-Maintenance",
        score=pts,
        max=10,
        evidence={
            "drifted_modules": drifted,
            "measurable_modules": measurable,
            "drift_ratio": round(drift_ratio, 3),
            "ctx_validation_workflow": ctx_validation_workflow,
            "hook_validates_paths": hook_validates_paths,
        },
        findings=findings,
    )


# ----------------------------------------------------------------------------
# G. Agent Performance Outcomes
# ----------------------------------------------------------------------------
def score_g(repo: Path) -> CategoryScore:
    eval_dirs = [p for p in ("evals", "benchmarks", "agent-evals", "agent-metrics") if (repo / p).exists()]
    metric_files = list(repo.glob("**/agent-results.json")) + list(repo.glob("**/.skill-eval.json"))
    metric_files = [m for m in metric_files if not any(seg in m.parts for seg in IGNORE_DIRS)]
    has_telemetry_hint = any(
        re.search(r"telemetry|opentelemetry|claude.*session|agent.*log",
                  read_text(p), re.IGNORECASE)
        for p in (repo / "CLAUDE.md", repo / "AGENTS.md")
        if p.exists()
    )

    pts = 0
    if eval_dirs:
        pts += 3
    if metric_files:
        pts += 1
    if has_telemetry_hint:
        pts += 1
    pts = max(0, min(5, pts))

    findings: list[str] = []
    if not eval_dirs and not metric_files:
        findings.append("agent eval / benchmark 디렉터리·결과 파일 부재 — 성능 측정 인프라 없음")
    if not has_telemetry_hint:
        findings.append("AI usage telemetry 단서 없음 (session log / OpenTelemetry)")

    return CategoryScore(
        name="Agent Performance Outcomes",
        score=pts,
        max=5,
        evidence={
            "eval_dirs": eval_dirs,
            "metric_files": [str(p.relative_to(repo)) for p in metric_files],
            "telemetry_hint": has_telemetry_hint,
        },
        findings=findings,
    )


# ----------------------------------------------------------------------------
# Bonus / extras: large files, naming hints
# ----------------------------------------------------------------------------
def find_large_files(repo: Path, threshold: int = 300) -> list[tuple[Path, int]]:
    out: list[tuple[Path, int]] = []
    for p in walk_files(repo):
        if p.suffix not in CODE_EXTS:
            continue
        ln = count_lines(p)
        if ln > threshold:
            out.append((p, ln))
    out.sort(key=lambda x: -x[1])
    return out


# ----------------------------------------------------------------------------
# Grade & ROI
# ----------------------------------------------------------------------------
def grade_label(total: int) -> tuple[str, str]:
    if total >= 90:
        return "AI-Native", "green"
    if total >= 75:
        return "AI-Ready", "green"
    if total >= 60:
        return "AI-Assisted", "amber"
    if total >= 40:
        return "AI-Fragile", "amber"
    return "AI-Hostile", "red"


def derive_actions(report_partial: dict[str, CategoryScore], modules: list[Module],
                    large_files: list[tuple[Path, int]], repo: Path,
                    apps: list[tt.App] | None = None) -> list[Action]:
    actions: list[Action] = []
    A, B, C, D, E, F, G = (report_partial[k] for k in "ABCDEFG")
    apps = apps or []

    # A — App 진입 문서 미보유
    uncovered = [a.name for a in apps if not a.has_context]
    if uncovered:
        actions.append(Action(
            title=f"{len(uncovered)}개 App에 {{App}}-PRD.md 또는 {{App}}-FC.md 신설 ({', '.join(uncovered[:3])}{'…' if len(uncovered) > 3 else ''})",
            category="A",
            effort="S", effort_hours=1.0 * len(uncovered),
            impact="App별 진입 문서 확보 — AI navigation 1-hop 도달",
            impact_score=9,
            priority=9 / max(1.0, 1.0 * len(uncovered)),
        ))

    # A — Backend Services Overview gap
    overview_only = A.evidence.get("overview_only", [])
    fs_only = A.evidence.get("fs_only", [])
    if overview_only or fs_only:
        gap = sorted(set(overview_only) | set(fs_only))
        actions.append(Action(
            title=f"root CLAUDE.md Backend Services Overview 표 정합 ({', '.join(gap[:4])}{'…' if len(gap) > 4 else ''})",
            category="A",
            effort="S", effort_hours=0.5,
            impact="SYSTEM_CODE SSOT 확정 — App 식별자 단일 출처",
            impact_score=8,
            priority=8 / 0.5,
        ))

    # A — Src↔Docs mismatch
    mismatch = [a.name for a in apps if a.src_dir is None or not a.docs_dir.exists()]
    if mismatch:
        actions.append(Action(
            title=f"Src↔Docs 폴더 매핑 정합 {len(mismatch)}건 ({', '.join(mismatch[:3])})",
            category="A",
            effort="S", effort_hours=1.0,
            impact="코드↔문서 1:1 매핑 — AI cross-reference 정확도 ↑",
            impact_score=7,
            priority=7 / 1.0,
        ))

    # B1 — router 미흡
    if B.sub_scores.get("B1_RouterCompleteness", 0) < 3:
        actions.append(Action(
            title="root CLAUDE.md 핵심 섹션 보강 (설계 문서 인덱스 / Backend Services Overview)",
            category="B",
            effort="S", effort_hours=1.0,
            impact="라우터 진입점 완성 — AI가 1-hop으로 모든 문서 도달",
            impact_score=8,
            priority=8 / 1.0,
        ))

    # B2 — 메타 / 변경이력 누락
    if B.sub_scores.get("B2_MetaHistory", 0) < 3:
        actions.append(Action(
            title="content/supporting 문서에 메타 표 + 변경 이력 표 일괄 추가",
            category="B",
            effort="M", effort_hours=2.0,
            impact="SSOT 추적 + 문서 버저닝 가시화",
            impact_score=7,
            priority=7 / 2.0,
        ))

    # B3 — 4단계 마커 누락
    if B.sub_scores.get("B3_FourStageMarkers", 0) < 3:
        actions.append(Action(
            title="DDD/OOP 룰 + ARCHITECTURE §4–6 + App-ARCH §2 에 4단계 마커(반드시/허용/금지/절대 금지) 보강",
            category="B",
            effort="S", effort_hours=1.0,
            impact="AI가 hidden rule 식별 — 레이어 위반·코드 스타일 사고 차단",
            impact_score=8,
            priority=8 / 1.0,
        ))

    # B4 — 핵심 섹션 누락
    if B.sub_scores.get("B4_SectionCompliance", 0) < 3:
        actions.append(Action(
            title="FRD/PRD/ARCHITECTURE 핵심 섹션 채우기 (template_compliance.missing_sections 참조)",
            category="B",
            effort="M", effort_hours=3.0,
            impact="작업 지시 완결성 — AI가 빠진 컨텍스트 추측하지 않음",
            impact_score=7,
            priority=7 / 3.0,
        ))

    # B5 — FRD 빈칸/placeholder
    if B.sub_scores.get("B5_NoBlankViolations", 0) < 3:
        actions.append(Action(
            title="FRD 23절 빈칸/N/A → '없음' 일괄 치환 + placeholder ({App}, {NNN}) 제거",
            category="B",
            effort="S", effort_hours=0.5,
            impact="AI hallucination 방지 — 빈칸은 자유 추측 유발",
            impact_score=9,
            priority=9 / 0.5,
        ))

    # C — no MEMORY/ADR
    if not C.evidence.get("memory_md") and not C.evidence.get("adr"):
        actions.append(Action(
            title="MEMORY.md 또는 docs/adr/ 도입으로 tribal knowledge 외부화",
            category="C",
            effort="M", effort_hours=3.0,
            impact="senior 의존 의사결정 외부화 → 신규 agent run 시 오류 ↓",
            impact_score=8,
            priority=8 / 3.0,
        ))

    # D — no architecture doc
    if not D.evidence.get("architecture_doc"):
        actions.append(Action(
            title="ARCHITECTURE.md 또는 mermaid dependency 다이어그램 추가",
            category="D",
            effort="M", effort_hours=2.5,
            impact="cross-module ripple 추적 → 변경 영향 분석 시간 절반",
            impact_score=7,
            priority=7 / 2.5,
        ))

    # E1 — broken refs
    if E.evidence.get("ref_broken", 0) > 0:
        actions.append(Action(
            title=f"context의 hallucinated path {E.evidence['ref_broken']}건 수정 (referential trust)",
            category="E",
            effort="S", effort_hours=0.5,
            impact="agent의 잘못된 path-following 방지 — stale = worse than missing",
            impact_score=10,
            priority=10 / 0.5,
        ))

    # E — no path validation in CI
    if not F.evidence.get("ctx_validation_workflow") and not F.evidence.get("hook_validates_paths"):
        actions.append(Action(
            title="CI 또는 pre-push hook에 context path 검증 추가",
            category="F",
            effort="S", effort_hours=1.0,
            impact="stale reference를 코드 머지 시점에 차단 — 회귀 방지",
            impact_score=8,
            priority=8 / 1.0,
        ))

    # 7 (large files) — included in B/C symptom but suggested separately
    huge = [(p, ln) for p, ln in large_files if ln > 500]
    if huge:
        sample = ", ".join(f"{p.relative_to(repo).as_posix()} ({ln})" for p, ln in huge[:3])
        actions.append(Action(
            title=f"god file {len(huge)}개 분할 (>500 lines): {sample}",
            category="B",
            effort="L", effort_hours=2.5 * len(huge),
            impact=f"파일당 ~5K-10K token 절감 + 편집 정확도 ↑",
            impact_score=6,
            priority=6 / max(2.5, 2.5 * len(huge)),
        ))

    # G — no eval infra
    if G.score < 3:
        actions.append(Action(
            title="evals/ 디렉터리 + 대표 task pass-rate 측정 도입",
            category="G",
            effort="L", effort_hours=6.0,
            impact="AI 회귀 측정 가능 — 개선 ROI 자체를 정량화",
            impact_score=6,
            priority=6 / 6.0,
        ))

    actions.sort(key=lambda a: -a.priority)
    return actions


# ----------------------------------------------------------------------------
# Generate insights
# ----------------------------------------------------------------------------
def generate_insights(cats: dict[str, CategoryScore], total: int) -> list[str]:
    out: list[str] = []
    grade, _ = grade_label(total)
    out.append(f"총점 {total}/100 · 등급 {grade}")

    # weakest categories
    norm = sorted(cats.items(), key=lambda kv: kv[1].score / kv[1].max)
    weakest = norm[:2]
    for k, c in weakest:
        out.append(f"가장 낮은 카테고리: {k} {c.name} {c.score}/{c.max}")

    # E1 hallucination is special
    e = cats.get("E")
    if e and e.evidence.get("ref_broken", 0) > 0:
        out.append(
            f"⚠️  context에 hallucinated path {e.evidence['ref_broken']}건 — Meta 기준으로는 0이어야 함"
        )

    # F freshness
    f = cats.get("F")
    if f and f.evidence.get("drift_ratio", 0) > 0.3:
        out.append(f"context drift 높음 ({f.evidence['drift_ratio']:.0%}) — stale 위험")

    return out


# ----------------------------------------------------------------------------
# Main
# ----------------------------------------------------------------------------
def git_branch(repo: Path) -> str:
    try:
        r = subprocess.run(
            ["git", "-C", str(repo), "rev-parse", "--abbrev-ref", "HEAD"],
            capture_output=True, text=True, timeout=5,
        )
        return r.stdout.strip() or "unknown"
    except Exception:
        return "unknown"


def _solution_code_from_path(repo: Path, apps: list[tt.App]) -> str:
    """SOLUTION_CODE 추정: Src/Mirero.<X>.<Y>/ 패턴 중 App/ 서브폴더 보유한 것의 마지막 segment."""
    src = repo / "Src"
    candidates: list[str] = []
    if src.is_dir():
        for child in src.iterdir():
            if not child.is_dir() or not child.name.lower().startswith("mirero"):
                continue
            # `App/` 서브폴더 보유한 것만 — 실제 솔루션 루트
            if not (child / "App").is_dir():
                continue
            parts = child.name.split(".")
            if len(parts) >= 2:
                candidates.append(parts[-1].upper())
    if not candidates:
        # fallback — App/ 없어도 Mirero.* 첫 번째
        if src.is_dir():
            for child in src.iterdir():
                if child.is_dir() and child.name.lower().startswith("mirero"):
                    parts = child.name.split(".")
                    if len(parts) >= 2:
                        return parts[-1].upper()
        return repo.name.upper()
    # repo 폴더명과 매칭되는 것 우선
    repo_low = repo.name.lower()
    for c in candidates:
        if c.lower() in repo_low:
            return c
    # 짧은 segment 우선 (XLab vs UpdateHub — XLab 이 root 솔루션)
    return min(candidates, key=len)


def build_report(repo: Path) -> Report:
    # team-template discovery (A·B 도메인)
    root_claude_tt, docs_dir, apps, overview_apps = tt.discover_apps(repo)

    # 기존 discovery (C/D/E/F 도메인 — 무변경)
    modules = find_core_modules(repo)
    context_files = find_all_context_files(repo)             # score_c/f 용
    ext_context_files = find_extended_context_files(repo)    # score_d/e 용
    root_claude = find_root_claude(repo)
    large_files = find_large_files(repo, 300)

    template_compliance: dict[str, Any] = {}

    cats = {
        "A": score_a(apps, root_claude_tt, overview_apps),
        "B": score_b(repo, root_claude_tt, docs_dir, apps, template_compliance),
        "C": score_c(modules, repo),
        "D": score_d(repo, ext_context_files),
        "E": score_e(repo, ext_context_files),
        "F": score_f(modules, repo),
        "G": score_g(repo),
    }
    total = sum(c.score for c in cats.values())
    grade, color = grade_label(total)
    actions = derive_actions(cats, modules, large_files, repo, apps=apps)
    insights = generate_insights(cats, total)

    solution_code = _solution_code_from_path(repo, apps)

    return Report(
        meta={
            "repo": repo.name,
            "path": str(repo.resolve()),
            "scored_at": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
            "git_branch": git_branch(repo),
            "rubric_version": "v2.5-100pt-team-AB",
            "solution_code": solution_code,
            "apps": [
                {
                    "system_code": a.name,
                    "docs_dir": str(a.docs_dir.relative_to(repo).as_posix()) if a.docs_dir.is_absolute() and repo in a.docs_dir.parents else str(a.docs_dir),
                    "src_dir": str(a.src_dir.relative_to(repo).as_posix()) if a.src_dir and repo in a.src_dir.parents else None,
                    "has_prd": a.has_prd,
                    "has_fc": a.has_fc,
                    "has_arch": a.has_arch,
                    "has_catalog": a.has_catalog,
                    "frd_count": len(a.frd_files),
                    "adr_count": len(a.adr_files),
                }
                for a in apps
            ],
            "modules_total": len(modules),
            "context_files_total": len(context_files),
            "extended_context_total": len(ext_context_files),
            "large_files_300plus": len(large_files),
        },
        template_compliance=template_compliance,
        total=total,
        grade=grade,
        grade_color=color,
        categories=cats,
        insights=insights,
        actions=actions,
        extras={
            "modules": [asdict(m) | {"path": str(m.path), "context_file": str(m.context_file) if m.context_file else None} for m in modules],
            "large_files": [
                {"path": str(p.relative_to(repo).as_posix()), "lines": ln}
                for p, ln in large_files[:30]
            ],
        },
    )


def serialize(report: Report) -> dict[str, Any]:
    cats = {k: asdict(c) for k, c in report.categories.items()}
    return {
        "meta": report.meta,
        "total": report.total,
        "grade": report.grade,
        "grade_color": report.grade_color,
        "categories": cats,
        "insights": report.insights,
        "actions": [asdict(a) for a in report.actions],
        "extras": report.extras,
        "template_compliance": report.template_compliance,
    }


def render_markdown(report: Report) -> str:
    lines = []
    lines.append(f"# Team-Template Rubric Audit · {report.meta['repo']}")
    lines.append("")
    lines.append(f"**Score:** {report.total}/100 · **Grade:** {report.grade}")
    lines.append(f"**Branch:** `{report.meta['git_branch']}` · **Scored:** {report.meta['scored_at']}")
    lines.append(
        f"**Modules:** {report.meta['modules_total']} · "
        f"**Context (CLAUDE/AGENTS):** {report.meta['context_files_total']} · "
        f"**Extended (PRD/FC/FRD 포함):** {report.meta.get('extended_context_total', '-')} · "
        f"**Large files (>300 ln):** {report.meta['large_files_300plus']}"
    )
    lines.append("")

    lines.append("## Category Scores")
    lines.append("")
    lines.append("| Cat | Name | Score |")
    lines.append("|-----|------|-------|")
    for k, c in report.categories.items():
        lines.append(f"| {k} | {c.name} | **{c.score}/{c.max}** |")
    lines.append("")

    lines.append("## Insights")
    for ins in report.insights:
        lines.append(f"- {ins}")
    lines.append("")

    lines.append("## Findings (per category)")
    for k, c in report.categories.items():
        if not c.findings:
            continue
        lines.append(f"### {k}. {c.name}  ({c.score}/{c.max})")
        for f in c.findings:
            lines.append(f"- {f}")
    lines.append("")

    lines.append("## Top Actions (ranked by ROI)")
    lines.append("")
    lines.append("| # | Effort | Action | Impact |")
    lines.append("|---|--------|--------|--------|")
    for i, a in enumerate(report.actions[:8], 1):
        lines.append(f"| {i} | {a.effort} ({a.effort_hours:.1f} hr) | [{a.category}] {a.title} | {a.impact} |")
    lines.append("")

    if report.extras["large_files"]:
        lines.append("## Large Files (>300 lines)")
        for lf in report.extras["large_files"][:10]:
            lines.append(f"- {lf['path']} — **{lf['lines']}** lines")
        lines.append("")

    return "\n".join(lines)


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("repo", nargs="?", default=".", help="repo path (default: cwd)")
    p.add_argument("--json", dest="json_out", help="write JSON report to this path")
    p.add_argument("--markdown", action="store_true", help="emit markdown to stdout (default)")
    p.add_argument("--quiet", action="store_true", help="suppress stdout output")
    args = p.parse_args()

    repo = Path(args.repo).resolve()
    if not repo.exists():
        print(f"error: repo path not found: {repo}", file=sys.stderr)
        return 2

    report = build_report(repo)
    payload = serialize(report)

    if args.json_out:
        Path(args.json_out).write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")

    if not args.quiet:
        if args.json_out and not args.markdown:
            # default: when writing json, also print summary
            print(render_markdown(report))
        elif args.markdown or not args.json_out:
            print(render_markdown(report))

    return 0


if __name__ == "__main__":
    sys.exit(main())
