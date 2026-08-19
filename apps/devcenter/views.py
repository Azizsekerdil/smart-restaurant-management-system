"""AI Geliştirme Merkezi görünümleri."""

from __future__ import annotations

from django.conf import settings
from django.contrib import messages
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from apps.accounts.decorators import devcenter_enabled_required, require_permission
from apps.ai.providers import provider_status
from apps.devcenter import sandbox, services
from apps.devcenter.models import CodeProposal, CommandRun, Snapshot


@require_permission("devcenter.access")
@devcenter_enabled_required
def index(request):
    """Geliştirme Merkezi ana ekranı."""
    return render(
        request,
        "devcenter/index.html",
        {
            "page_title": "AI Geliştirme Merkezi",
            "proposals": CodeProposal.objects.order_by("-created_at")[:20],
            "project_files": services.list_project_files(limit=600),
            "recent_commands": CommandRun.objects.order_by("-created_at")[:20],
            "snapshots": Snapshot.objects.order_by("-created_at")[:10],
            "providers": [p for p in provider_status() if p["configured"]],
            "terminal_enabled": settings.DEVCENTER["TERMINAL_ENABLED"],
            "project_root": str(sandbox.project_root()),
            "git_branch": services.git_head()[0],
            "git_commit": services.git_head()[1],
            "allowed_commands": sandbox.command_help(),
        },
    )


@require_permission("devcenter.access")
@devcenter_enabled_required
def file_browser(request):
    """Düzenlenebilir dosya listesi ve içerik görüntüleyici."""
    pattern = request.GET.get("q", "")
    selected = request.GET.get("file", "")
    content = ""
    error = ""
    if selected:
        try:
            content = services.read_file(selected)
        except services.ProposalError as exc:
            error = str(exc)
    return render(
        request,
        "devcenter/files.html",
        {
            "page_title": "Proje Dosyaları",
            "files": services.list_project_files(pattern),
            "selected": selected,
            "content": content,
            "error": error,
            "pattern": pattern,
        },
    )


# ------------------------------------------------------------------
#  Terminal
# ------------------------------------------------------------------
@require_permission("devcenter.terminal")
@devcenter_enabled_required
def terminal(request):
    return render(
        request,
        "devcenter/terminal.html",
        {
            "page_title": "Güvenli Terminal",
            "history": CommandRun.objects.filter(user=request.user).order_by("-created_at")[:40],
            "allowed_commands": sandbox.command_help(),
            "project_root": str(sandbox.project_root()),
            "terminal_enabled": settings.DEVCENTER["TERMINAL_ENABLED"],
            "timeout": settings.DEVCENTER["COMMAND_TIMEOUT"],
        },
    )


@require_permission("devcenter.terminal")
@devcenter_enabled_required
@require_POST
def terminal_check(request):
    """Komutu çalıştırmadan önce güvenlik denetimini gösterir."""
    command = request.POST.get("command", "")
    check = sandbox.check_command(command)
    return JsonResponse(
        {
            "allowed": check.allowed,
            "reason": check.reason,
            "needs_confirmation": check.needs_confirmation,
            "parsed": check.parts or [],
            "working_directory": str(sandbox.project_root()),
        }
    )


@require_permission("devcenter.terminal")
@devcenter_enabled_required
@require_POST
def terminal_run(request):
    command = request.POST.get("command", "")
    confirmed = request.POST.get("confirmed") == "true"
    run = sandbox.run_command(command, user=request.user, confirmed=confirmed)
    return JsonResponse(
        {
            "id": run.pk,
            "status": run.status,
            "status_label": run.get_status_display(),
            "exit_code": run.exit_code,
            "stdout": run.stdout,
            "stderr": run.stderr,
            "duration_ms": run.duration_ms,
            "block_reason": run.block_reason,
            "needs_confirmation": run.status == CommandRun.Status.PENDING,
        }
    )


# ------------------------------------------------------------------
#  Kod önerileri
# ------------------------------------------------------------------
@require_permission("devcenter.access")
@devcenter_enabled_required
@require_POST
def proposal_create(request):
    instruction = request.POST.get("instruction", "")
    files = [f for f in request.POST.getlist("files") if f]
    try:
        proposal = services.create_proposal(
            instruction,
            files,
            user=request.user,
            provider=request.POST.get("provider", ""),
            model=request.POST.get("model", ""),
        )
    except services.ProposalError as exc:
        return JsonResponse({"ok": False, "detail": str(exc)}, status=400)
    return JsonResponse(
        {
            "ok": True,
            "proposal_id": proposal.pk,
            "explanation": proposal.explanation,
            "files": proposal.target_files,
            "diff": proposal.diff,
            "stats": services.diff_statistics(proposal.diff),
        }
    )


@require_permission("devcenter.access")
@devcenter_enabled_required
def proposal_detail(request, pk: int):
    proposal = get_object_or_404(CodeProposal, pk=pk)
    return render(
        request,
        "devcenter/proposal_detail.html",
        {
            "page_title": f"Kod Önerisi #{proposal.pk}",
            "proposal": proposal,
            "stats": services.diff_statistics(proposal.diff),
            "diff_lines": _annotate_diff(proposal.diff),
            "can_apply": request.user.has_perm_code("devcenter.apply"),
        },
    )


def _annotate_diff(diff_text: str) -> list[dict]:
    """Diff satırlarını arayüzde renklendirmek için sınıflandırır."""
    rows = []
    for line in (diff_text or "").splitlines():
        if line.startswith("+++") or line.startswith("---"):
            css = "diff-file"
        elif line.startswith("@@"):
            css = "diff-hunk"
        elif line.startswith("+"):
            css = "diff-add"
        elif line.startswith("-"):
            css = "diff-remove"
        else:
            css = "diff-context"
        rows.append({"text": line, "css": css})
    return rows


@require_permission("devcenter.access")
@devcenter_enabled_required
@require_POST
def proposal_test(request, pk: int):
    proposal = get_object_or_404(CodeProposal, pk=pk)
    command = request.POST.get("command", "pytest -q")
    check = sandbox.check_command(command)
    if not check.allowed:
        return JsonResponse({"ok": False, "detail": check.reason}, status=400)
    services.run_tests(proposal, user=request.user, command=command)
    return JsonResponse(
        {"ok": True, "passed": proposal.tests_passed, "output": proposal.test_output}
    )


@require_permission("devcenter.apply")
@devcenter_enabled_required
@require_POST
def proposal_apply(request, pk: int):
    proposal = get_object_or_404(CodeProposal, pk=pk)
    try:
        services.apply_proposal(
            proposal,
            user=request.user,
            create_branch=request.POST.get("create_branch", "true") == "true",
        )
    except services.ProposalError as exc:
        return JsonResponse({"ok": False, "detail": str(exc)}, status=400)
    return JsonResponse(
        {
            "ok": True,
            "branch": proposal.branch_name,
            "snapshot_id": proposal.snapshot_id,
            "message": (
                "Değişiklik uygulandı. Sorun çıkarsa 'Geri Al' düğmesiyle "
                "önceki duruma dönebilirsiniz."
            ),
        }
    )


@require_permission("devcenter.apply")
@devcenter_enabled_required
@require_POST
def proposal_revert(request, pk: int):
    proposal = get_object_or_404(CodeProposal, pk=pk)
    try:
        services.revert_proposal(proposal, user=request.user)
    except services.ProposalError as exc:
        return JsonResponse({"ok": False, "detail": str(exc)}, status=400)
    return JsonResponse({"ok": True, "message": "Değişiklikler geri alındı."})


@require_permission("devcenter.access")
@devcenter_enabled_required
@require_POST
def proposal_reject(request, pk: int):
    proposal = get_object_or_404(CodeProposal, pk=pk)
    services.reject_proposal(proposal, reason=request.POST.get("reason", ""), user=request.user)
    return JsonResponse({"ok": True})


# ------------------------------------------------------------------
#  Git
# ------------------------------------------------------------------
@require_permission("devcenter.access")
@devcenter_enabled_required
def git_panel(request):
    return render(
        request,
        "devcenter/git.html",
        {
            "page_title": "Git Paneli",
            "status": services.git_status(user=request.user),
            "diff": services.git_diff(user=request.user),
            "branch": services.git_head()[0],
            "commit": services.git_head()[1],
        },
    )


@require_permission("devcenter.access")
@devcenter_enabled_required
@require_POST
def git_commit_suggestion(request):
    ok, message = services.suggest_commit_message(user=request.user)
    return JsonResponse({"ok": ok, "message": message})


@require_permission("devcenter.access")
@devcenter_enabled_required
def snapshot_list(request):
    return render(
        request,
        "devcenter/snapshots.html",
        {
            "page_title": "Geri Alma Noktaları",
            "snapshots": Snapshot.objects.order_by("-created_at")[:50],
        },
    )


@require_permission("devcenter.apply")
@devcenter_enabled_required
@require_POST
def snapshot_restore(request, pk: int):
    snapshot = get_object_or_404(Snapshot, pk=pk)
    try:
        restored = services.restore_snapshot(snapshot, user=request.user)
    except services.ProposalError as exc:
        messages.error(request, str(exc))
        return redirect("devcenter:snapshots")
    messages.success(request, f"{restored} dosya geri yüklendi.")
    return redirect("devcenter:snapshots")
