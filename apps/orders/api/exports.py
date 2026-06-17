"""Financial Excel export — a multi-sheet workbook for accountants/auditors."""
import io
from datetime import datetime

from django.contrib.auth import get_user_model
from django.db.models import Sum
from django.http import HttpResponse
from django.utils import timezone
from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
from rest_framework.views import APIView

from apps.orders.models import BalanceNote, Order, OrderItem, UserBalance
from apps.products.models import Product
from apps.users.api.permissions import IsSuperAdmin
from apps.users.audit import log_action
from apps.users.models import AuditLog

HEAD_FILL = PatternFill("solid", fgColor="0F4C81")
HEAD_FONT = Font(bold=True, color="FFFFFF")
TITLE_FONT = Font(bold=True, size=14, color="0F4C81")
MONEY = "#,##0.00"


def _sheet(wb, title, headers):
    ws = wb.create_sheet(title)
    ws.sheet_view.rightToLeft = True
    ws.append(headers)
    for c, _ in enumerate(headers, 1):
        cell = ws.cell(row=1, column=c)
        cell.fill = HEAD_FILL
        cell.font = HEAD_FONT
        cell.alignment = Alignment(horizontal="center")
    ws.freeze_panes = "A2"
    return ws


def _autofit(ws, widths):
    for c, w in enumerate(widths, 1):
        ws.column_dimensions[get_column_letter(c)].width = w


def build_financial_workbook(start, end, user_id, actor_name=""):
    User = get_user_model()
    orders = Order.objects.select_related("user").prefetch_related("order_items__product")
    if start:
        orders = orders.filter(created_at__date__gte=start)
    if end:
        orders = orders.filter(created_at__date__lte=end)
    if user_id:
        orders = orders.filter(user_id=user_id)
    orders = orders.order_by("created_at")

    payments = BalanceNote.objects.select_related("user")
    if start:
        payments = payments.filter(timestamp__date__gte=start)
    if end:
        payments = payments.filter(timestamp__date__lte=end)
    if user_id:
        payments = payments.filter(user_id=user_id)

    wb = Workbook()
    wb.remove(wb.active)

    # ---- Summary ----
    ws = wb.create_sheet("ملخص")
    ws.sheet_view.rightToLeft = True
    ws["A1"] = "Black Rock — التقرير المالي"
    ws["A1"].font = TITLE_FONT
    sales = orders.aggregate(s=Sum("total"))["s"] or 0
    scrap = orders.aggregate(s=Sum("supplement"))["s"] or 0
    disc = orders.aggregate(s=Sum("discount"))["s"] or 0
    paid = payments.aggregate(s=Sum("amount"))["s"] or 0
    rows = [
        ("الفترة", f"{start or '—'}  →  {end or '—'}"),
        ("عدد الفواتير", orders.count()),
        ("إجمالي المبيعات", sales),
        ("إجمالي الخردة", scrap),
        ("إجمالي الخصومات", disc),
        ("الإجمالي المستحق", sales + scrap - disc),
        ("إجمالي المدفوعات", paid),
        ("الرصيد المتبقي", (sales + scrap - disc) - paid),
        ("", ""),
        ("أُنشئ بواسطة", actor_name),
        ("تاريخ التصدير", timezone.localtime(timezone.now()).strftime("%Y-%m-%d %H:%M")),
    ]
    for i, (k, v) in enumerate(rows, start=3):
        ws.cell(row=i, column=1, value=k).font = Font(bold=True)
        c = ws.cell(row=i, column=2, value=v)
        if isinstance(v, (int, float)) and k not in ("عدد الفواتير",):
            c.number_format = MONEY
    _autofit(ws, [24, 30])

    # ---- Invoices ----
    ws = _sheet(wb, "الفواتير", ["رقم", "العميل", "التاريخ", "البطاريات", "المبيعات", "الخردة", "الخصم", "المستحق"])
    for o in orders:
        items = "، ".join(f"{it.product.name}×{it.quantity}" for it in o.order_items.all())
        ws.append([o.id, o.user.first_name, timezone.localtime(o.created_at).strftime("%Y-%m-%d"),
                   items, float(o.total), float(o.supplement), float(o.discount), float(o.amount_to_pay())])
    for col in (5, 6, 7, 8):
        for r in range(2, ws.max_row + 1):
            ws.cell(row=r, column=col).number_format = MONEY
    _autofit(ws, [8, 22, 14, 40, 14, 12, 12, 14])

    # ---- Payments ----
    ws = _sheet(wb, "المدفوعات", ["العميل", "المبلغ", "الطريقة", "ملاحظة", "التاريخ"])
    src = dict(BalanceNote.PaymentSource.choices)
    for p in payments.order_by("timestamp"):
        ws.append([p.user.first_name, float(p.amount), src.get(p.source, p.source or "—"),
                   p.note or "", timezone.localtime(p.timestamp).strftime("%Y-%m-%d %H:%M")])
    for r in range(2, ws.max_row + 1):
        ws.cell(row=r, column=2).number_format = MONEY
    _autofit(ws, [22, 14, 16, 30, 18])

    # ---- Inventory ----
    ws = _sheet(wb, "المخزون", ["البطارية", "الماركة", "السعر", "المخزون", "القيمة"])
    for pr in Product.objects.filter(deleted=False).select_related("brand"):
        ws.append([pr.name, pr.brand.name if pr.brand_id else "—", float(pr.price), pr.stock,
                   float(pr.price) * pr.stock])
    for col in (3, 5):
        for r in range(2, ws.max_row + 1):
            ws.cell(row=r, column=col).number_format = MONEY
    _autofit(ws, [24, 18, 12, 12, 14])

    # ---- Customer balances ----
    ws = _sheet(wb, "أرصدة العملاء", ["العميل", "الهاتف", "إجمالي الفواتير", "المدفوع", "المتبقي"])
    for b in UserBalance.objects.select_related("user").filter(user__is_staff=False, user__deleted=False):
        ws.append([b.user.first_name, b.user.phone or "—", float(b.orders_total),
                   float(b.paid_amount), float(b.amount_to_pay())])
    for col in (3, 4, 5):
        for r in range(2, ws.max_row + 1):
            ws.cell(row=r, column=col).number_format = MONEY
    _autofit(ws, [22, 16, 16, 14, 14])

    # ---- Audit ----
    ws = _sheet(wb, "سجل النشاط", ["الموظف", "العملية", "العنصر", "التفاصيل", "الوقت"])
    audit = AuditLog.objects.all()
    if start:
        audit = audit.filter(created_at__date__gte=start)
    if end:
        audit = audit.filter(created_at__date__lte=end)
    for a in audit.order_by("-created_at")[:2000]:
        ws.append([a.actor_username or "—", a.get_action_display(), a.entity,
                   a.object_repr, timezone.localtime(a.created_at).strftime("%Y-%m-%d %H:%M")])
    _autofit(ws, [18, 12, 14, 36, 18])

    out = io.BytesIO()
    wb.save(out)
    out.seek(0)
    return out


class ExportFinancialView(APIView):
    permission_classes = [IsSuperAdmin]

    def get(self, request):
        start = request.GET.get("start") or None
        end = request.GET.get("end") or None
        user_id = request.GET.get("user") or None
        actor = getattr(request.user, "username", "")
        buf = build_financial_workbook(start, end, user_id, actor_name=actor)
        log_action(request, AuditLog.Action.EXPORT, entity="Financial",
                   object_repr=f"{start or ''}..{end or ''}")
        stamp = timezone.localtime(timezone.now()).strftime("%Y%m%d-%H%M")
        resp = HttpResponse(
            buf.getvalue(),
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        resp["Content-Disposition"] = f'attachment; filename="blackrock-finance-{stamp}.xlsx"'
        return resp
