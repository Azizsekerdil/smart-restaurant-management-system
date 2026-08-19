"""Personel, vardiya, puantaj ve görev görünümleri."""

from __future__ import annotations

from datetime import date, timedelta

from django import forms
from django.contrib import messages
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from apps.accounts.decorators import require_permission
from apps.hr.models import (
    Attendance,
    Employee,
    LeaveRequest,
    Shift,
    ShiftAssignment,
    StaffTask,
)

_TEXT = {"class": "form-control"}
_SELECT = {"class": "form-select"}


class EmployeeForm(forms.ModelForm):
    class Meta:
        model = Employee
        fields = [
            "user",
            "employment_type",
            "hire_date",
            "termination_date",
            "hourly_rate",
            "monthly_salary",
            "weekly_hours_target",
            "emergency_contact",
            "emergency_phone",
            "notes",
            "is_active",
        ]
        widgets = {
            "user": forms.Select(attrs=_SELECT),
            "employment_type": forms.Select(attrs=_SELECT),
            "hire_date": forms.DateInput(attrs={**_TEXT, "type": "date"}),
            "termination_date": forms.DateInput(attrs={**_TEXT, "type": "date"}),
            "hourly_rate": forms.NumberInput(attrs={**_TEXT, "step": "0.01"}),
            "monthly_salary": forms.NumberInput(attrs={**_TEXT, "step": "0.01"}),
            "weekly_hours_target": forms.NumberInput(attrs=_TEXT),
            "emergency_contact": forms.TextInput(attrs=_TEXT),
            "emergency_phone": forms.TextInput(attrs=_TEXT),
            "notes": forms.Textarea(attrs={**_TEXT, "rows": 2}),
            "is_active": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }


@require_permission("staff.view", "shift.view")
def employee_list(request):
    employees = (
        Employee.objects.select_related("user").filter(is_active=True).order_by("user__first_name")
    )
    today = timezone.localdate()
    open_attendances = {
        a.employee_id: a
        for a in Attendance.objects.filter(check_out__isnull=True).select_related("employee")
    }
    return render(
        request,
        "hr/employee_list.html",
        {
            "page_title": "Personel",
            "employees": employees,
            "open_attendances": open_attendances,
            "today_shifts": ShiftAssignment.objects.filter(work_date=today).select_related(
                "employee__user", "shift"
            ),
            "pending_leaves": LeaveRequest.objects.filter(
                status=LeaveRequest.Status.PENDING
            ).count(),
        },
    )


@require_permission("staff.manage")
def employee_create(request):
    if request.method == "POST":
        form = EmployeeForm(request.POST)
        if form.is_valid():
            employee = form.save(commit=False)
            employee.created_by = request.user
            employee.save()
            messages.success(request, f"{employee} personel kaydı oluşturuldu.")
            return redirect("hr:employee_list")
    else:
        form = EmployeeForm()
    return render(request, "hr/employee_form.html", {"form": form, "page_title": "Yeni Personel"})


@require_permission("staff.view")
def employee_detail(request, pk: int):
    employee = get_object_or_404(Employee.objects.select_related("user"), pk=pk)
    today = timezone.localdate()
    month_start = today.replace(day=1)
    return render(
        request,
        "hr/employee_detail.html",
        {
            "page_title": str(employee),
            "employee": employee,
            "attendances": employee.attendances.order_by("-check_in")[:30],
            "assignments": employee.shift_assignments.filter(
                work_date__gte=today - timedelta(days=7)
            ).select_related("shift")[:30],
            "leaves": employee.leave_requests.order_by("-start_date")[:10],
            "month_hours": employee.hours_worked(month_start, today),
            "month_sales": employee.sales_total(month_start, today),
            "performance": employee.performance.order_by("-period_end")[:6],
        },
    )


@require_permission("shift.view")
def shift_schedule(request):
    """Haftalık vardiya planı."""
    start_str = request.GET.get("start", "")
    try:
        start = date.fromisoformat(start_str) if start_str else timezone.localdate()
    except ValueError:
        start = timezone.localdate()
    start = start - timedelta(days=start.weekday())
    days = [start + timedelta(days=i) for i in range(7)]

    assignments = ShiftAssignment.objects.filter(
        work_date__gte=start, work_date__lte=days[-1]
    ).select_related("employee__user", "shift")

    grid: dict[int, dict[str, list]] = {}
    for assignment in assignments:
        grid.setdefault(assignment.employee_id, {}).setdefault(
            assignment.work_date.isoformat(), []
        ).append(assignment)

    return render(
        request,
        "hr/shift_schedule.html",
        {
            "page_title": "Vardiya Planı",
            "days": days,
            "week_start": start,
            "prev_week": (start - timedelta(days=7)).isoformat(),
            "next_week": (start + timedelta(days=7)).isoformat(),
            "employees": Employee.objects.select_related("user").filter(is_active=True),
            "shifts": Shift.objects.filter(is_active=True),
            "grid": grid,
        },
    )


@require_permission("shift.manage")
@require_POST
def shift_assign(request):
    employee = get_object_or_404(Employee, pk=request.POST.get("employee_id"))
    shift = get_object_or_404(Shift, pk=request.POST.get("shift_id"))
    try:
        work_date = date.fromisoformat(request.POST.get("work_date", ""))
    except ValueError:
        return JsonResponse({"ok": False, "detail": "Geçersiz tarih."}, status=400)

    assignment, created = ShiftAssignment.objects.get_or_create(
        employee=employee,
        shift=shift,
        work_date=work_date,
        defaults={"created_by": request.user},
    )
    return JsonResponse(
        {
            "ok": True,
            "created": created,
            "id": assignment.pk,
            "label": f"{shift.name} ({shift.start_time:%H:%M})",
        }
    )


@require_permission("shift.manage")
@require_POST
def shift_remove(request, pk: int):
    ShiftAssignment.objects.filter(pk=pk).delete()
    return JsonResponse({"ok": True})


@require_permission("attendance.manage")
@require_POST
def attendance_toggle(request, pk: int):
    """Giriş/çıkış kaydı (tek düğme)."""
    employee = get_object_or_404(Employee, pk=pk)
    open_record = employee.attendances.filter(check_out__isnull=True).first()
    if open_record:
        open_record.check_out = timezone.now()
        open_record.break_minutes = int(request.POST.get("break_minutes") or 0)
        open_record.save(update_fields=["check_out", "break_minutes", "updated_at"])
        return JsonResponse(
            {"ok": True, "action": "check_out", "hours": str(open_record.worked_hours)}
        )

    today_assignment = employee.shift_assignments.filter(work_date=timezone.localdate()).first()
    record = Attendance.objects.create(
        employee=employee, assignment=today_assignment, created_by=request.user
    )
    return JsonResponse({"ok": True, "action": "check_in", "late": record.is_late})


@require_permission("shift.view")
def leave_list(request):
    leaves = LeaveRequest.objects.select_related("employee__user").order_by("-start_date")
    status = request.GET.get("status", "")
    if status:
        leaves = leaves.filter(status=status)
    return render(
        request,
        "hr/leave_list.html",
        {
            "page_title": "İzin Talepleri",
            "leaves": leaves[:100],
            "statuses": LeaveRequest.Status.choices,
            "kinds": LeaveRequest.Kind.choices,
            "employees": Employee.objects.select_related("user").filter(is_active=True),
            "current_status": status,
        },
    )


@require_permission("shift.view")
@require_POST
def leave_create(request):
    try:
        start = date.fromisoformat(request.POST["start_date"])
        end = date.fromisoformat(request.POST["end_date"])
    except (KeyError, ValueError):
        messages.error(request, "Geçersiz tarih aralığı.")
        return redirect("hr:leave_list")
    if end < start:
        messages.error(request, "Bitiş tarihi başlangıçtan önce olamaz.")
        return redirect("hr:leave_list")

    LeaveRequest.objects.create(
        employee_id=request.POST.get("employee_id"),
        kind=request.POST.get("kind", LeaveRequest.Kind.ANNUAL),
        start_date=start,
        end_date=end,
        reason=request.POST.get("reason", ""),
        created_by=request.user,
    )
    messages.success(request, "İzin talebi oluşturuldu.")
    return redirect("hr:leave_list")


@require_permission("attendance.manage")
@require_POST
def leave_decide(request, pk: int):
    leave = get_object_or_404(LeaveRequest, pk=pk)
    decision = request.POST.get("decision")
    if decision not in {LeaveRequest.Status.APPROVED, LeaveRequest.Status.REJECTED}:
        return JsonResponse({"ok": False, "detail": "Geçersiz karar."}, status=400)
    leave.status = decision
    leave.decided_by = request.user
    leave.decided_at = timezone.now()
    leave.decision_note = request.POST.get("note", "")[:300]
    leave.save(update_fields=["status", "decided_by", "decided_at", "decision_note", "updated_at"])
    return JsonResponse({"ok": True, "status": leave.get_status_display()})


@require_permission("staff.view")
def task_list(request):
    tasks = StaffTask.objects.select_related("assigned_to").order_by("-priority", "due_date")
    status = request.GET.get("status", "")
    if status:
        tasks = tasks.filter(status=status)
    else:
        tasks = tasks.exclude(status=StaffTask.Status.DONE)
    from apps.accounts.models import User

    return render(
        request,
        "hr/task_list.html",
        {
            "page_title": "Görevler",
            "tasks": tasks[:100],
            "statuses": StaffTask.Status.choices,
            "users": User.objects.filter(is_active=True),
            "current_status": status,
        },
    )


@require_permission("staff.view")
@require_POST
def task_create(request):
    StaffTask.objects.create(
        title=request.POST.get("title", "")[:200],
        description=request.POST.get("description", ""),
        assigned_to_id=request.POST.get("assigned_to") or None,
        due_date=request.POST.get("due_date") or None,
        priority=int(request.POST.get("priority") or 2),
        created_by=request.user,
    )
    messages.success(request, "Görev oluşturuldu.")
    return redirect("hr:task_list")


@require_permission("staff.view")
@require_POST
def task_complete(request, pk: int):
    task = get_object_or_404(StaffTask, pk=pk)
    task.status = StaffTask.Status.DONE
    task.completed_at = timezone.now()
    task.completed_by = request.user
    task.save(update_fields=["status", "completed_at", "completed_by", "updated_at"])
    return JsonResponse({"ok": True})


@require_permission("staff.view")
def performance_report(request):
    """Personel performans karşılaştırması."""
    today = timezone.localdate()
    start = today - timedelta(days=30)
    rows = []
    for employee in Employee.objects.select_related("user").filter(is_active=True):
        hours = employee.hours_worked(start, today)
        sales = employee.sales_total(start, today)
        from apps.orders.models import Order

        order_count = Order.objects.filter(
            waiter=employee.user, status=Order.Status.PAID, closed_at__date__gte=start
        ).count()
        rows.append(
            {
                "employee": employee,
                "hours": hours,
                "sales": sales,
                "orders": order_count,
                "avg_ticket": (sales / order_count) if order_count else 0,
                "sales_per_hour": (sales / hours) if hours else 0,
            }
        )
    rows.sort(key=lambda r: r["sales"], reverse=True)
    return render(
        request,
        "hr/performance.html",
        {"page_title": "Personel Performansı", "rows": rows, "start": start, "end": today},
    )
