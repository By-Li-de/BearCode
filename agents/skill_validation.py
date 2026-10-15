"""Stage skill changes, compare prompt-only cases, and publish or roll back exact versions."""
from __future__ import annotations

import difflib
import hashlib
import json
import re
import uuid
from pathlib import Path
from typing import Awaitable, Callable

from .frontmatter import format_frontmatter, parse_frontmatter
from .skill_evolution import (
    _bump_patch, _normalize_allowed_tools, _normalize_context, _parse_int, _safe_skill_slug,
    _utc_now, _write_json, _write_text_atomic,
    get_evolution_dir, resolve_skill_file,
)


def _record_path(candidate_id: str) -> Path:
    if not re.fullmatch(r"[0-9a-f]{12}", candidate_id):
        raise ValueError("Invalid candidate ID")
    return get_evolution_dir() / "candidates" / f"{candidate_id}.json"


def _fingerprint(record: dict) -> str:
    content = {key: record[key] for key in ("skill", "action", "file", "baseline", "proposed")}
    return hashlib.sha256(json.dumps(content, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def candidate_file(record: dict) -> Path:
    path = Path(record["file"])
    roots = [(Path.cwd() / ".bear/skills").resolve(), (Path.home() / ".bear/skills").resolve()]
    if (not path.is_absolute() or path != path.resolve() or path.name != "SKILL.md"
            or not any(path.is_relative_to(root) for root in roots)):
        raise ValueError("Candidate destination is outside the skill roots or has changed")
    return path


def load_candidate(candidate_id: str) -> dict:
    record = json.loads(_record_path(candidate_id).read_text(encoding="utf-8"))
    if (not isinstance(record, dict)
            or any(not isinstance(record.get(key), str) for key in ("skill", "action", "status", "file", "proposed", "created_at", "fingerprint"))
            or "baseline" not in record or (record["baseline"] is not None and not isinstance(record["baseline"], str))
            or record["status"] not in {"pending", "validated", "accepted", "rolled_back", "rejected"}
            or record["action"] not in {"add", "merge"}
            or ("evaluation" in record and not isinstance(record["evaluation"], dict))):
        raise ValueError("Malformed candidate record")
    if record.get("id") != candidate_id or record.get("fingerprint") != _fingerprint(record):
        raise ValueError("Candidate content changed; stage it again before evaluation")
    candidate_file(record)
    return record


def stage_candidate(*, action: str, name: str, description: str, instructions: str,
                    when_to_use: str = "", target: str = "project", reason: str = "",
                    evidence: str = "", tags: list[str] | None = None, context: str = "inline",
                    user_invocable: bool = False, allowed_tools: object = None) -> dict:
    if (action not in {"add", "merge"} or target not in {"active", "project", "user"}
            or (action == "add" and target == "active")):
        raise ValueError("Expected add/merge and a supported target")
    name = re.sub(r"\s+", " ", name).strip()
    if not name or not description.strip() or not instructions.strip():
        raise ValueError("Candidate name, description, and instructions are required")
    from .skills import get_skill_by_name
    skill = get_skill_by_name(name)
    existing = resolve_skill_file(name, target=target, active_dir=skill.skill_dir if skill else "")
    if action == "add" and resolve_skill_file(name):
        raise ValueError("Skill already exists; stage a merge instead")
    if action == "merge" and not existing:
        raise ValueError("Cannot merge a missing skill")
    root = Path.home() if target == "user" else Path.cwd()
    file = (existing if existing else root / ".bear/skills" / _safe_skill_slug(name) / "SKILL.md").resolve()
    if action == "add" and file.exists():
        raise ValueError("Candidate destination already exists")
    baseline = file.read_bytes().decode("utf-8") if existing else None
    meta = dict(parse_frontmatter(baseline).meta) if baseline is not None else {
        "name": name, "version": "0.1.0", "created-at": _utc_now(),
        "context": _normalize_context(context), "user-invocable": "true" if user_invocable else "false",
    }
    if baseline is None and _normalize_allowed_tools(allowed_tools):
        meta["allowed-tools"] = _normalize_allowed_tools(allowed_tools)
    if baseline is not None:
        meta["version"] = _bump_patch(meta.get("version"))
        meta["last-evolved"] = _utc_now()
        meta["evolution-count"] = str(_parse_int(meta.get("evolution-count")) + 1)
    meta["description"] = re.sub(r"\s+", " ", description).strip()
    if when_to_use:
        meta.pop("when_to_use", None)
        meta["when-to-use"] = re.sub(r"\s+", " ", when_to_use).strip()
    if tags:
        previous = [part for part in meta.get("tags", "").split(",") if part]
        meta["tags"] = ",".join(dict.fromkeys(previous + [re.sub(r"\s+", "-", tag.strip()) for tag in tags]))
    meta = {key: re.sub(r"\s+", " ", str(value)).strip() for key, value in meta.items()}
    record = {
        "id": uuid.uuid4().hex[:12], "status": "pending", "created_at": _utc_now(),
        "skill": name, "action": action, "file": str(file), "baseline": baseline,
        "proposed": format_frontmatter(meta, instructions.strip() + "\n"),
        "reason": reason, "evidence": evidence,
    }
    candidate_file(record)
    record["fingerprint"] = _fingerprint(record)
    _write_json(_record_path(record["id"]), record)
    return {"ok": True, "action": "staged", "skill": name, "candidate_id": record["id"],
            "file": str(file), "candidate_version": meta["version"]}


def list_candidates() -> str:
    paths = sorted((get_evolution_dir() / "candidates").glob("*.json"), reverse=True)
    if not paths:
        return "No skill candidates."
    records, invalid = [], []
    for path in paths:
        try:
            records.append(load_candidate(path.stem))
        except (OSError, ValueError, KeyError, TypeError):
            invalid.append(f"{path.stem}  invalid (review the local record before retrying)")
    records.sort(key=lambda item: item["created_at"], reverse=True)
    lines = []
    for record in records[:30]:
        report = record.get("evaluation") or {}
        score = f" baseline={report['baseline_score']} candidate={report['candidate_score']}/{report['total']}" if report.get("completed") else ""
        lines.append(f"{record['id']}  {record['status']}  {record['action']} {record['skill']}{score}")
    return "\n".join(lines + invalid[:30])


def candidate_diff(candidate_id: str) -> str:
    record = load_candidate(candidate_id)
    diff = "".join(difflib.unified_diff((record["baseline"] or "").splitlines(True),
                                         record["proposed"].splitlines(True),
                                         fromfile="recorded baseline", tofile="candidate"))
    report = record.get("evaluation") or {}
    summary = (f"Model: {report['model']}; passed={report['passed']}; "
               f"baseline={report['baseline_score']}/{report['total']}; "
               f"candidate={report['candidate_score']}/{report['total']}\n") if report.get("completed") else "Not evaluated\n"
    return f"{record['id']} ({record['status']})\n{record['file']}\n{summary}{diff}"


def _load_cases(path: Path) -> list[dict]:
    return _validate_cases(json.loads(path.read_text(encoding="utf-8")))


def _validate_cases(cases: object) -> list[dict]:
    if not isinstance(cases, list) or not 1 <= len(cases) <= 20:
        raise ValueError("Evaluation needs 1–20 cases")
    for case in cases:
        if not isinstance(case, dict) or not isinstance(case.get("prompt"), str) or not case["prompt"].strip():
            raise ValueError("Every case needs a non-empty prompt")
        for key in ("must_include", "must_not_include"):
            values = case.get(key, [])
            if not isinstance(values, list) or any(not isinstance(v, str) or not v.strip() for v in values):
                raise ValueError(f"{key} must be a list of non-empty strings")
        if "exact" in case and (not isinstance(case["exact"], str) or not case["exact"].strip()):
            raise ValueError("exact must be a non-empty string")
        if not any(case.get(key) for key in ("exact", "must_include", "must_not_include")):
            raise ValueError("Every case needs at least one explicit check")
    return cases


def _checks(answer: str, case: dict) -> list[bool]:
    result = [bool(answer.strip())]
    if "exact" in case:
        result.append(answer.strip() == case["exact"].strip())
    result.extend(value in answer for value in case.get("must_include", []))
    result.extend(value not in answer for value in case.get("must_not_include", []))
    return result


def _passing_report(report: dict) -> bool:
    try:
        cases = _validate_cases(report["cases"])
        if not report.get("completed") or len(report["rows"]) != len(cases):
            return False
        baseline, proposed, total = 0, 0, 0
        for case, row in zip(cases, report["rows"]):
            before = _checks(row["baseline_answer"], case)
            after = _checks(row["candidate_answer"], case)
            baseline += sum(before)
            proposed += sum(after)
            total += len(after)
        return (proposed == total and proposed > baseline and report.get("passed") is True
                and (baseline, proposed, total) == (report["baseline_score"], report["candidate_score"], report["total"]))
    except (KeyError, TypeError, ValueError, AttributeError):
        return False


async def evaluate_candidate(candidate_id: str, cases_path: Path,
                             side_query: Callable[[str, str], Awaitable[str]], *, model: str) -> dict:
    record = load_candidate(candidate_id)
    if record["status"] not in {"pending", "validated"}:
        raise ValueError("Only pending or validated candidates can be evaluated")
    cases = _load_cases(cases_path)
    if _current(candidate_file(record)) != record["baseline"]:
        raise ValueError("Active skill changed; stage a fresh candidate")
    # Invalidate any earlier pass before starting; an interrupted re-evaluation cannot publish it.
    record["status"] = "pending"
    record.pop("evaluation", None)
    record["evaluation_run"] = uuid.uuid4().hex
    _write_json(_record_path(candidate_id), record)
    rows = []
    system = ("Complete the user's task. Apply supplied skill guidance when relevant; "
              "explicit user instructions take priority. Do not use tools. Return only the task answer.")
    for case in cases:
        answers, checks = [], []
        for content in (record["baseline"], record["proposed"]):
            guidance = parse_frontmatter(content).body if content is not None else ""
            prompt = case["prompt"] + ("\n\n[Skill guidance]\n" + guidance if guidance else "")
            answer = await side_query(system, prompt)
            answers.append(answer)
            checks.append(_checks(answer, case))
        rows.append({"prompt": case["prompt"], "baseline_answer": answers[0], "candidate_answer": answers[1],
                     "baseline_checks": checks[0], "candidate_checks": checks[1]})
    baseline_score = sum(sum(row["baseline_checks"]) for row in rows)
    candidate_score = sum(sum(row["candidate_checks"]) for row in rows)
    total = sum(len(row["candidate_checks"]) for row in rows)
    passed = candidate_score == total and candidate_score > baseline_score
    report = {"completed": True, "passed": passed, "model": model, "time": _utc_now(),
              "fingerprint": record["fingerprint"], "cases": cases, "rows": rows,
              "baseline_score": baseline_score, "candidate_score": candidate_score, "total": total}
    current = load_candidate(candidate_id)
    if (current["fingerprint"] != record["fingerprint"] or current["status"] != "pending"
            or current.get("evaluation_run") != record["evaluation_run"]
            or _current(candidate_file(current)) != record["baseline"]):
        raise ValueError("Candidate changed during evaluation; results were not applied")
    current.update(status="validated" if passed else "pending", evaluation=report)
    _write_json(_record_path(candidate_id), current)
    return {"ok": True, "candidate_id": candidate_id, **report}


def _current(file: Path) -> str | None:
    return file.read_bytes().decode("utf-8") if file.exists() else None


def _apply(record: dict, content: str | None, status: str) -> dict:
    file = candidate_file(record)
    previous = _current(file)
    def write(value):
        if value is None:
            file.unlink()
        else:
            _write_text_atomic(file, value)
    write(content)
    updated = {**record, "status": status, "updated_at": _utc_now()}
    try:
        _write_json(_record_path(record["id"]), updated)
    except Exception:
        write(previous)
        raise
    from .skills import reset_skill_cache
    reset_skill_cache()
    return {"ok": True, "skill": record["skill"], "candidate_id": record["id"], "status": status,
            "version": parse_frontmatter(content).meta.get("version") if content is not None else None}


def accept_candidate(candidate_id: str, *, model: str) -> dict:
    record = load_candidate(candidate_id)
    report = record.get("evaluation") or {}
    if (record["status"] != "validated" or not _passing_report(report)
            or report.get("fingerprint") != record["fingerprint"] or report.get("model") != model):
        raise ValueError("Candidate needs a passing evaluation with the currently selected model")
    file = candidate_file(record)
    if _current(file) != record["baseline"]:
        raise ValueError("Active skill changed; stage and evaluate a fresh candidate")
    return _apply(record, record["proposed"], "accepted")


def rollback_candidate(candidate_id: str) -> dict:
    record = load_candidate(candidate_id)
    if record["status"] != "accepted":
        raise ValueError("Only accepted candidates can be rolled back")
    if _current(candidate_file(record)) != record["proposed"]:
        raise ValueError("Active skill changed; rollback would overwrite newer edits")
    return _apply(record, record["baseline"], "rolled_back")


def reject_candidate(candidate_id: str) -> dict:
    record = load_candidate(candidate_id)
    if record["status"] not in {"pending", "validated"}:
        raise ValueError("Only pending or validated candidates can be rejected")
    record["status"] = "rejected"
    _write_json(_record_path(candidate_id), record)
    return {"ok": True, "candidate_id": candidate_id, "status": "rejected"}
