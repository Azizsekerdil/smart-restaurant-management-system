"""Geliştirme Merkezi iş mantığı: kod önerisi, diff, geri alma, git.

Değişmez kural: yapay zekânın önerdiği hiçbir kod, kullanıcı diff'i
görüp onaylamadan ve geri alma noktası oluşturulmadan uygulanmaz.
"""

from __future__ import annotations

import difflib
import json
import logging
import shutil
from datetime import datetime
from pathlib import Path

from django.conf import settings
from django.utils import timezone

from apps.ai import prompts
from apps.ai.gateway import AIUnavailable, ask
from apps.ai.models import AITask
from apps.core.models import AuditLog
from apps.core.services import record_audit
from apps.devcenter.models import CodeProposal, Snapshot
from apps.devcenter.sandbox import is_inside_root, project_root, run_command

logger = logging.getLogger("apps.devcenter")

# Yapay zekânın okuyabileceği / yazabileceği dosya türleri
EDITABLE_SUFFIXES = {".py", ".html", ".css", ".js", ".md", ".txt", ".json", ".yml", ".yaml"}

# Hiçbir koşulda değiştirilemeyecek yollar
PROTECTED_PATHS = {
    ".env",
    ".env.example",
    "db.sqlite3",
    "restaurant.sqlite3",
    ".git",
    ".venv",
    "media",
    "backups",
    "logs",
}


class ProposalError(Exception):
    """Kod önerisi oluşturulamadı veya uygulanamadı."""


# ------------------------------------------------------------------
#  Dosya erişimi
# ------------------------------------------------------------------
def is_editable(relative_path: str) -> tuple[bool, str]:
    """Dosyanın yapay zekâ tarafından düzenlenebilir olup olmadığını söyler."""
    clean = relative_path.replace("\\", "/").strip("/")
    if not clean:
        return False, "Yol boş."
    if ".." in clean.split("/"):
        return False, "Üst dizine çıkan yollar engellidir."
    if not is_inside_root(clean):
        return False, f"'{clean}' proje klasörü dışında."
    first = clean.split("/")[0]
    if first in PROTECTED_PATHS or clean in PROTECTED_PATHS:
        return False, f"'{clean}' korumalı bir yol; değiştirilemez."
    if Path(clean).suffix.lower() not in EDITABLE_SUFFIXES:
        return False, (
            f"'{Path(clean).suffix}' uzantısı düzenlenebilir değil. "
            f"İzin verilenler: {', '.join(sorted(EDITABLE_SUFFIXES))}"
        )
    return True, ""


def read_file(relative_path: str) -> str:
    ok, reason = is_editable(relative_path)
    if not ok:
        raise ProposalError(reason)
    path = project_root() / relative_path
    if not path.exists():
        return ""
    if path.stat().st_size > 400_000:
        raise ProposalError("Dosya çok büyük (400 KB üzeri).")
    return path.read_text(encoding="utf-8", errors="replace")


def list_project_files(pattern: str = "", limit: int = 400) -> list[str]:
    """Düzenlenebilir proje dosyalarını listeler."""
    root = project_root()
    skip_dirs = {
        ".git",
        ".venv",
        "venv",
        "node_modules",
        "__pycache__",
        "staticfiles",
        "media",
        "logs",
        "backups",
        ".pytest_cache",
        ".mypy_cache",
        ".ruff_cache",
        ".devcenter",
    }
    results: list[str] = []
    for path in root.rglob("*"):
        if len(results) >= limit:
            break
        if not path.is_file():
            continue
        parts = set(path.relative_to(root).parts)
        if parts & skip_dirs:
            continue
        if path.suffix.lower() not in EDITABLE_SUFFIXES:
            continue
        relative = path.relative_to(root).as_posix()
        if pattern and pattern.lower() not in relative.lower():
            continue
        results.append(relative)
    return sorted(results)


# ------------------------------------------------------------------
#  Diff
# ------------------------------------------------------------------
def build_diff(relative_path: str, new_content: str) -> str:
    """Birleşik (unified) diff üretir."""
    old = read_file(relative_path).splitlines(keepends=True)
    new = new_content.splitlines(keepends=True)
    return "".join(
        difflib.unified_diff(
            old,
            new,
            fromfile=f"a/{relative_path}",
            tofile=f"b/{relative_path}",
            lineterm="\n",
            n=3,
        )
    )


def diff_statistics(diff_text: str) -> dict:
    added = sum(
        1 for line in diff_text.splitlines() if line.startswith("+") and not line.startswith("+++")
    )
    removed = sum(
        1 for line in diff_text.splitlines() if line.startswith("-") and not line.startswith("---")
    )
    return {"added": added, "removed": removed, "total": added + removed}


# ------------------------------------------------------------------
#  Geri alma noktası
# ------------------------------------------------------------------
def create_snapshot(paths: list[str], *, label: str, user=None) -> Snapshot:
    """Değişecek dosyaların yedeğini alır."""
    snapshot_root = Path(settings.DEVCENTER["SNAPSHOT_DIR"])
    stamp = timezone.localtime().strftime("%Y%m%d-%H%M%S")
    directory = snapshot_root / f"{stamp}-{abs(hash(label)) % 10000:04d}"
    directory.mkdir(parents=True, exist_ok=True)

    saved: list[str] = []
    root = project_root()
    for relative in paths:
        source = root / relative
        if not source.exists():
            continue
        target = directory / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        saved.append(relative)

    branch, commit = git_head()
    return Snapshot.objects.create(
        label=label[:200],
        directory=str(directory),
        files=saved,
        git_branch=branch,
        git_commit=commit,
        created_by_user=user,
        created_by=user,
    )


def restore_snapshot(snapshot: Snapshot, *, user=None) -> int:
    """Yedeği geri yükler."""
    directory = Path(snapshot.directory)
    if not directory.exists():
        raise ProposalError("Geri alma noktası klasörü bulunamadı.")

    root = project_root()
    restored = 0
    for relative in snapshot.files or []:
        source = directory / relative
        if not source.exists():
            continue
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        restored += 1

    snapshot.is_restored = True
    snapshot.restored_at = timezone.now()
    snapshot.save(update_fields=["is_restored", "restored_at", "updated_at"])
    record_audit(
        AuditLog.Action.CODE_APPLY,
        user=user,
        obj=snapshot,
        description=f"Geri alma noktası geri yüklendi: {snapshot.label} ({restored} dosya)",
        severity=AuditLog.Severity.WARNING,
    )
    return restored


# ------------------------------------------------------------------
#  Git yardımcıları
# ------------------------------------------------------------------
def git_head() -> tuple[str, str]:
    """(dal, commit) döndürür. Git yoksa boş değer döner."""
    root = project_root()
    if not (root / ".git").exists():
        return "", ""
    try:
        import subprocess  # nosec B404

        # Argümanlar sabittir, kullanıcı girdisi içermez ve shell=False'tur.
        branch = subprocess.run(  # nosec B603 B607
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=str(root),
            capture_output=True,
            text=True,
            timeout=10,
            shell=False,
            check=False,
        ).stdout.strip()
        commit = subprocess.run(  # nosec B603 B607
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=str(root),
            capture_output=True,
            text=True,
            timeout=10,
            shell=False,
            check=False,
        ).stdout.strip()
        return branch, commit
    except Exception:
        return "", ""


def git_status(user=None) -> str:
    run = run_command("git status --short --branch", user=user)
    return run.stdout or run.stderr or "Git deposu bulunamadı."


def git_diff(user=None, path: str = "") -> str:
    command = "git diff --stat" if not path else f'git diff -- "{path}"'
    run = run_command(command, user=user)
    return run.stdout or run.stderr or "Değişiklik yok."


def suggest_commit_message(*, user=None) -> tuple[bool, str]:
    """Değişikliklere bakarak commit mesajı önerir."""
    run = run_command("git diff --stat", user=user)
    diff_summary = (run.stdout or "").strip()
    if not diff_summary:
        return False, "Commit edilecek değişiklik bulunamadı."

    try:
        response = ask(
            (
                "Aşağıdaki git diff özetine göre Türkçe, tek satırlık, en fazla 72 "
                "karakterlik bir commit mesajı öner. Conventional Commits biçimini "
                "kullan (feat:, fix:, refactor:, docs:, test:, chore:). "
                "Yalnızca mesajı yaz, açıklama ekleme.\n\n"
                f"{diff_summary[:3000]}"
            ),
            system=prompts.CODE_ASSISTANT,
            task=AITask.CODE,
            feature="commit_message",
            user=user,
            temperature=0.3,
            max_tokens=100,
        )
        return True, response.text.strip().strip('"').splitlines()[0][:120]
    except AIUnavailable as exc:
        return False, str(exc)


# ------------------------------------------------------------------
#  Kod önerisi üretme
# ------------------------------------------------------------------
def create_proposal(
    instruction: str,
    target_files: list[str],
    *,
    user=None,
    provider: str = "",
    model: str = "",
) -> CodeProposal:
    """Yapay zekâdan kod değişikliği ister ve diff olarak kaydeder.

    Dosyalar diske YAZILMAZ; yalnızca öneri kaydı oluşturulur.
    """
    if not settings.DEVCENTER["ENABLED"]:
        raise ProposalError("AI Geliştirme Merkezi kapalıdır.")
    if not instruction.strip():
        raise ProposalError("Talimat boş olamaz.")

    valid_files: list[str] = []
    context_parts: list[str] = []
    for relative in target_files[:6]:
        ok, reason = is_editable(relative)
        if not ok:
            raise ProposalError(reason)
        content = read_file(relative)
        valid_files.append(relative)
        context_parts.append(f"--- DOSYA: {relative} ---\n{content[:20000]}")

    if not valid_files:
        raise ProposalError("En az bir hedef dosya seçmelisiniz.")

    prompt = (
        f"TALİMAT:\n{instruction.strip()}\n\n"
        f"PROJE KÖKÜ: {project_root().name}\n"
        f"DEĞİŞTİRİLEBİLİR DOSYALAR:\n" + "\n\n".join(context_parts)
    )

    proposal = CodeProposal.objects.create(
        title=instruction.strip()[:200],
        instruction=instruction.strip(),
        target_files=valid_files,
        created_by_user=user,
        created_by=user,
        provider=provider,
        model=model,
    )

    try:
        response = ask(
            prompt,
            system=prompts.CODE_PATCH,
            task=AITask.CODE,
            feature="code_proposal",
            user=user,
            temperature=0.1,
            max_tokens=8000,
            json_mode=True,
            preferred_provider=provider,
            preferred_model=model,
        )
    except AIUnavailable as exc:
        proposal.status = CodeProposal.Status.FAILED
        proposal.explanation = str(exc)
        proposal.save(update_fields=["status", "explanation", "updated_at"])
        raise ProposalError(str(exc)) from exc

    try:
        data = json.loads(_extract_json(response.text))
    except ValueError as exc:
        proposal.status = CodeProposal.Status.FAILED
        proposal.explanation = (
            "Yapay zekâ yanıtı geçerli JSON değil. Daha güçlü bir model deneyin "
            "(ör. bulut sağlayıcı) veya talimatı sadeleştirin."
        )
        proposal.save(update_fields=["status", "explanation", "updated_at"])
        raise ProposalError(proposal.explanation) from exc

    diffs: list[str] = []
    changed_files: list[str] = []
    pending: dict[str, str] = {}
    for entry in data.get("files", []):
        path = str(entry.get("path", "")).replace("\\", "/").strip()
        content = entry.get("content")
        if not path or content is None:
            continue
        ok, reason = is_editable(path)
        if not ok:
            logger.warning("AI korumalı yola yazmayı denedi: %s (%s)", path, reason)
            continue
        diff = build_diff(path, content)
        if not diff:
            continue
        diffs.append(diff)
        changed_files.append(path)
        pending[path] = content

    if not diffs:
        proposal.status = CodeProposal.Status.FAILED
        proposal.explanation = (
            "Yapay zekâ uygulanabilir bir değişiklik üretmedi veya önerilen "
            "dosyalar korumalı. " + str(data.get("explanation", ""))[:500]
        )
        proposal.save(update_fields=["status", "explanation", "updated_at"])
        raise ProposalError(proposal.explanation)

    proposal.explanation = str(data.get("explanation", ""))[:4000]
    proposal.diff = "\n".join(diffs)[:200000]
    proposal.target_files = changed_files
    proposal.provider = response.provider
    proposal.model = response.model
    proposal.status = CodeProposal.Status.REVIEWING
    proposal.save()

    # Yeni içerikler geçici olarak saklanır; uygulama onaydan sonra yapılır.
    _store_pending(proposal, pending)

    record_audit(
        AuditLog.Action.AI_CALL,
        user=user,
        obj=proposal,
        description=(
            f"Kod önerisi oluşturuldu: {proposal.title[:100]} "
            f"({len(changed_files)} dosya, risk: {data.get('risk', 'bilinmiyor')})"
        ),
        severity=AuditLog.Severity.NOTICE,
    )
    return proposal


def _pending_path(proposal: CodeProposal) -> Path:
    directory = Path(settings.DEVCENTER["SNAPSHOT_DIR"]).parent / "pending"
    directory.mkdir(parents=True, exist_ok=True)
    return directory / f"proposal-{proposal.pk}.json"


def _store_pending(proposal: CodeProposal, files: dict[str, str]) -> None:
    _pending_path(proposal).write_text(json.dumps(files, ensure_ascii=False), encoding="utf-8")


def _load_pending(proposal: CodeProposal) -> dict[str, str]:
    path = _pending_path(proposal)
    if not path.exists():
        raise ProposalError("Önerinin içeriği bulunamadı. Öneriyi yeniden oluşturun.")
    return json.loads(path.read_text(encoding="utf-8"))


def _extract_json(text: str) -> str:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        segments = cleaned.split("```")
        cleaned = segments[1] if len(segments) > 1 else cleaned
        if cleaned.startswith("json"):
            cleaned = cleaned[4:]
    start, end = cleaned.find("{"), cleaned.rfind("}")
    return cleaned[start : end + 1] if start != -1 and end != -1 else cleaned


# ------------------------------------------------------------------
#  Test ve uygulama
# ------------------------------------------------------------------
def run_tests(proposal: CodeProposal, *, user=None, command: str = "pytest -q") -> CodeProposal:
    """Öneri için testleri çalıştırır."""
    run = run_command(command, user=user, confirmed=True)
    proposal.tests_run = True
    proposal.tests_passed = run.succeeded
    proposal.test_output = f"$ {command}\n\n{run.stdout}\n{run.stderr}"[:60000]
    proposal.save(update_fields=["tests_run", "tests_passed", "test_output", "updated_at"])
    return proposal


def apply_proposal(
    proposal: CodeProposal, *, user=None, create_branch: bool = True
) -> CodeProposal:
    """Onaylanan öneriyi uygular.

    Sıra: geri alma noktası -> (isteğe bağlı) ayrı git dalı -> dosya yazımı.
    Testler çalıştırılmış ve başarısızsa uygulama reddedilir.
    """
    if not settings.DEVCENTER["ENABLED"]:
        raise ProposalError("AI Geliştirme Merkezi kapalıdır.")
    if proposal.status == CodeProposal.Status.APPLIED:
        raise ProposalError("Bu öneri zaten uygulanmış.")
    if proposal.tests_run and not proposal.tests_passed:
        raise ProposalError(
            "Testler başarısız olduğu için değişiklik uygulanamaz. "
            "Önce testleri düzeltin veya öneriyi reddedin."
        )
    if not proposal.diff:
        raise ProposalError("Uygulanacak değişiklik yok.")

    files = _load_pending(proposal)

    snapshot = create_snapshot(
        list(files.keys()), label=f"Öneri #{proposal.pk}: {proposal.title[:80]}", user=user
    )
    proposal.snapshot = snapshot

    if create_branch and (project_root() / ".git").exists():
        branch_name = f"ai/oneri-{proposal.pk}-{datetime.now().strftime('%Y%m%d%H%M')}"
        run = run_command(f"git switch -c {branch_name}", user=user, confirmed=True)
        if run.succeeded:
            proposal.branch_name = branch_name
        else:
            logger.warning("Git dalı oluşturulamadı: %s", run.stderr[:200])

    root = project_root()
    written = 0
    try:
        for relative, content in files.items():
            ok, reason = is_editable(relative)
            if not ok:
                raise ProposalError(reason)
            target = root / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8", newline="\n")
            written += 1
    except Exception as exc:
        restore_snapshot(snapshot, user=user)
        proposal.status = CodeProposal.Status.FAILED
        proposal.save(update_fields=["status", "updated_at"])
        raise ProposalError(
            f"Uygulama sırasında hata oluştu, değişiklikler geri alındı: {exc}"
        ) from exc

    proposal.status = CodeProposal.Status.APPLIED
    proposal.applied_at = timezone.now()
    proposal.approved_by = user
    proposal.approved_at = proposal.approved_at or timezone.now()
    proposal.save()

    record_audit(
        AuditLog.Action.CODE_APPLY,
        user=user,
        obj=proposal,
        description=(
            f"Kod değişikliği uygulandı: {proposal.title[:100]} "
            f"({written} dosya, dal: {proposal.branch_name or 'mevcut dal'})"
        ),
        severity=AuditLog.Severity.CRITICAL,
    )
    return proposal


def revert_proposal(proposal: CodeProposal, *, user=None) -> CodeProposal:
    if proposal.snapshot is None:
        raise ProposalError("Bu öneri için geri alma noktası yok.")
    restore_snapshot(proposal.snapshot, user=user)
    proposal.status = CodeProposal.Status.REVERTED
    proposal.save(update_fields=["status", "updated_at"])
    return proposal


def reject_proposal(proposal: CodeProposal, *, reason: str = "", user=None) -> CodeProposal:
    proposal.status = CodeProposal.Status.REJECTED
    proposal.rejection_reason = reason[:300]
    proposal.save(update_fields=["status", "rejection_reason", "updated_at"])
    path = _pending_path(proposal)
    if path.exists():
        path.unlink()
    record_audit(
        AuditLog.Action.CODE_APPLY,
        user=user,
        obj=proposal,
        description=f"Kod önerisi reddedildi: {proposal.title[:100]}. Gerekçe: {reason}",
    )
    return proposal
