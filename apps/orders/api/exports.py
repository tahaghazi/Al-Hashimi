"""Financial Excel export — a multi-sheet workbook for accountants/auditors.

Sheets:
  1. ملخص          — Executive summary with formulas
  2. الفواتير       — One row per invoice (order-level totals + formulas)
  3. تفاصيل الفواتير — One row per line item (unit price, qty, line total)
  4. بيانات العملاء  — Full customer financial profile (orders, payments, balance)
  5. المدفوعات      — Every payment record
  6. المخزون        — Current inventory with value formulas
  7. سجل النشاط     — Audit log
"""
import io
from collections import defaultdict

from django.contrib.auth import get_user_model
from django.db.models import Count, Sum
from django.http import HttpResponse
from django.utils import timezone
from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from rest_framework.views import APIView

from apps.orders.models import BalanceNote, Order, UserBalance
from apps.products.models import Product
from apps.users.api.permissions import IsSuperAdmin
from apps.users.audit import log_action
from apps.users.models import AuditLog

HEAD_FILL = PatternFill("solid", fgColor="0F4C81")
HEAD_FONT = Font(bold=True, color="FFFFFF", size=11)
TITLE_FONT = Font(bold=True, size=14, color="0F4C81")
SUB_FONT = Font(bold=True, size=11, color="0F4C81")
TOTAL_FILL = PatternFill("solid", fgColor="E8F0FE")
TOTAL_FONT = Font(bold=True, size=11)
MONEY = "#,##0.00"
INT_FMT = "#,##0"
THIN_BORDER = Border(
    bottom=Side(style="thin", color="CCCCCC"),
)
CENTER = Alignment(horizontal="center", vertical="center")
RIGHT = Alignment(horizontal="right", vertical="center")
WRAP = Alignment(horizontal="right", vertical="center", wrap_text=True)


def _sheet(wb, title, headers):
    ws = wb.create_sheet(title)
    ws.sheet_view.rightToLeft = True
    ws.append(headers)
    for c, _ in enumerate(headers, 1):
        cell = ws.cell(row=1, column=c)
        cell.fill = HEAD_FILL
        cell.font = HEAD_FONT
        cell.alignment = CENTER
    ws.freeze_panes = "A2"
    return ws


def _autofit(ws, widths):
    for c, w in enumerate(widths, 1):
        ws.column_dimensions[get_column_letter(c)].width = w


def _money_cols(ws, cols, start_row=2):
    for col in cols:
        for r in range(start_row, ws.max_row + 1):
            ws.cell(row=r, column=col).number_format = MONEY


def _totals_row(ws, label_col, formula_cols, label="الإجمالي"):
    """Append a bold totals row with SUM formulas."""
    r = ws.max_row + 1
    ws.cell(row=r, column=label_col, value=label).font = TOTAL_FONT
    for col in formula_cols:
        letter = get_column_letter(col)
        cell = ws.cell(row=r, column=col)
        cell.value = f"=SUM({letter}2:{letter}{r - 1})"
        cell.font = TOTAL_FONT
        cell.number_format = MONEY
        cell.fill = TOTAL_FILL
    return r


def build_financial_workbook(start, end, user_id, actor_name=""):
    User = get_user_model()
    orders = Order.objects.select_related("user").prefetch_related("order_items__product__brand")
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

    # Pre-fetch orders list for reuse
    orders_list = list(orders)
    order_count = len(orders_list)
    payments_list = list(payments.order_by("timestamp"))

    # ================================================================
    # 1. SUMMARY  ملخص
    # ================================================================
    ws = wb.create_sheet("ملخص")
    ws.sheet_view.rightToLeft = True
    ws["A1"] = "Black Rock — التقرير المالي التفصيلي"
    ws["A1"].font = TITLE_FONT
    ws.merge_cells("A1:B1")

    sales = sum((o.total for o in orders_list), 0)
    scrap = sum((o.supplement for o in orders_list), 0)
    disc = sum((o.discount for o in orders_list), 0)
    paid = sum((p.amount for p in payments_list), 0)
    total_items = sum(
        sum(it.quantity for it in o.order_items.all()) for o in orders_list
    )

    rows = [
        ("الفترة", f"{start or 'الكل'}  →  {end or 'الكل'}"),
        ("عدد الفواتير", order_count),
        ("عدد الأصناف المباعة", total_items),
        ("", ""),
        ("إجمالي المبيعات", float(sales)),
        ("إجمالي الخردة (مضاف)", float(scrap)),
        ("إجمالي الخصومات", float(disc)),
        ("الإجمالي المستحق (مبيعات + خردة - خصم)", float(sales + scrap - disc)),
        ("", ""),
        ("إجمالي المدفوعات", float(paid)),
        ("الرصيد المتبقي (مستحق - مدفوع)", float((sales + scrap - disc) - paid)),
        ("", ""),
        ("عدد عمليات الدفع", len(payments_list)),
        ("", ""),
        ("أُنشئ بواسطة", actor_name),
        ("تاريخ التصدير", timezone.localtime(timezone.now()).strftime("%Y-%m-%d %H:%M")),
    ]
    for i, (k, v) in enumerate(rows, start=3):
        ws.cell(row=i, column=1, value=k).font = Font(bold=True)
        c = ws.cell(row=i, column=2, value=v)
        if isinstance(v, float):
            c.number_format = MONEY
        elif isinstance(v, int):
            c.number_format = INT_FMT
    _autofit(ws, [40, 30])

    # ================================================================
    # 2. INVOICES  الفواتير  (one row per order, with formulas)
    # ================================================================
    ws = _sheet(wb, "الفواتير", [
        "رقم الفاتورة",      # A
        "العميل",            # B
        "هاتف العميل",       # C
        "التاريخ",           # D
        "عدد الأصناف",       # E
        "المبيعات",          # F
        "الخردة",            # G
        "الخصم",             # H
        "المستحق",           # I  (formula: F+G-H)
        "ملاحظات",           # J
    ])
    for o in orders_list:
        items_count = sum(it.quantity for it in o.order_items.all())
        r = ws.max_row + 1
        ws.cell(row=r, column=1, value=o.id)
        ws.cell(row=r, column=2, value=o.user.first_name)
        ws.cell(row=r, column=3, value=o.user.phone or "—")
        ws.cell(row=r, column=4, value=timezone.localtime(o.created_at).strftime("%Y-%m-%d"))
        ws.cell(row=r, column=5, value=items_count)
        ws.cell(row=r, column=6, value=float(o.total))
        ws.cell(row=r, column=7, value=float(o.supplement))
        ws.cell(row=r, column=8, value=float(o.discount))
        # Formula: sales + scrap - discount
        ws.cell(row=r, column=9, value=f"=F{r}+G{r}-H{r}")
        ws.cell(row=r, column=10, value="")
    _money_cols(ws, [6, 7, 8, 9])
    if order_count > 0:
        _totals_row(ws, label_col=2, formula_cols=[5, 6, 7, 8, 9], label="الإجمالي")
        # Make the totals row qty column integer format
        ws.cell(row=ws.max_row, column=5).number_format = INT_FMT
    _autofit(ws, [12, 22, 16, 14, 12, 14, 12, 12, 14, 20])

    # ================================================================
    # 3. INVOICE LINE ITEMS  تفاصيل الفواتير  (one row per item)
    # ================================================================
    ws = _sheet(wb, "تفاصيل الفواتير", [
        "رقم الفاتورة",      # A
        "العميل",            # B
        "تاريخ الفاتورة",    # C
        "البطارية",          # D
        "الماركة",           # E
        "SKU",               # F
        "سعر الوحدة",        # G
        "الكمية",            # H
        "إجمالي السطر",      # I  (formula: G*H)
        "السعر الحالي",      # J  (current product price for comparison)
        "فرق السعر",         # K  (formula: J-G, shows if price changed)
    ])
    for o in orders_list:
        date_str = timezone.localtime(o.created_at).strftime("%Y-%m-%d")
        for it in o.order_items.all():
            r = ws.max_row + 1
            ws.cell(row=r, column=1, value=o.id)
            ws.cell(row=r, column=2, value=o.user.first_name)
            ws.cell(row=r, column=3, value=date_str)
            ws.cell(row=r, column=4, value=it.product.name)
            ws.cell(row=r, column=5, value=it.product.brand.name if it.product.brand_id else "—")
            ws.cell(row=r, column=6, value=it.product.sku or "—")
            ws.cell(row=r, column=7, value=float(it.fixed_price))
            ws.cell(row=r, column=8, value=it.quantity)
            # Formula: unit price * quantity
            ws.cell(row=r, column=9, value=f"=G{r}*H{r}")
            ws.cell(row=r, column=10, value=float(it.product.price))
            # Formula: current price - invoice price (positive = price went up)
            ws.cell(row=r, column=11, value=f"=J{r}-G{r}")
    _money_cols(ws, [7, 9, 10, 11])
    if ws.max_row > 1:
        tr = _totals_row(ws, label_col=2, formula_cols=[8, 9], label="الإجمالي")
        ws.cell(row=tr, column=8).number_format = INT_FMT
    _autofit(ws, [12, 22, 14, 24, 18, 14, 14, 10, 14, 14, 14])

    # ================================================================
    # 4. CUSTOMER DETAILS  بيانات العملاء
    # ================================================================
    ws = _sheet(wb, "بيانات العملاء", [
        "العميل",             # A
        "الهاتف",             # B
        "عدد الفواتير",       # C
        "عدد الأصناف المشتراة",# D
        "إجمالي المبيعات",    # E
        "إجمالي الخردة",      # F
        "إجمالي الخصومات",    # G
        "إجمالي المستحق",     # H  (formula: E+F-G)
        "إجمالي المدفوعات",   # I
        "الرصيد المتبقي",     # J  (formula: H-I)
        "نسبة السداد %",      # K  (formula: I/H*100)
        "آخر فاتورة",        # L
        "آخر دفعة",          # M
    ])

    # Aggregate per customer
    cust_orders = defaultdict(list)
    for o in orders_list:
        cust_orders[o.user_id].append(o)

    cust_payments = defaultdict(list)
    for p in payments_list:
        cust_payments[p.user_id].append(p)

    # All customers with balance records
    balances = UserBalance.objects.select_related("user").filter(
        user__is_staff=False, user__deleted=False
    )
    seen_users = set()
    for b in balances:
        uid = b.user_id
        seen_users.add(uid)
        user_orders = cust_orders.get(uid, [])
        user_payments = cust_payments.get(uid, [])

        c_sales = sum(float(o.total) for o in user_orders)
        c_scrap = sum(float(o.supplement) for o in user_orders)
        c_disc = sum(float(o.discount) for o in user_orders)
        c_items = sum(sum(it.quantity for it in o.order_items.all()) for o in user_orders)
        c_paid = sum(float(p.amount) for p in user_payments)

        last_order = max((o.created_at for o in user_orders), default=None)
        last_pay = max((p.timestamp for p in user_payments), default=None)

        r = ws.max_row + 1
        ws.cell(row=r, column=1, value=b.user.first_name)
        ws.cell(row=r, column=2, value=b.user.phone or "—")
        ws.cell(row=r, column=3, value=len(user_orders))
        ws.cell(row=r, column=4, value=c_items)
        ws.cell(row=r, column=5, value=c_sales)
        ws.cell(row=r, column=6, value=c_scrap)
        ws.cell(row=r, column=7, value=c_disc)
        # Formula: sales + scrap - discount
        ws.cell(row=r, column=8, value=f"=E{r}+F{r}-G{r}")
        ws.cell(row=r, column=9, value=c_paid)
        # Formula: due - paid
        ws.cell(row=r, column=10, value=f"=H{r}-I{r}")
        # Formula: payment ratio (guard /0)
        ws.cell(row=r, column=11, value=f'=IF(H{r}=0,"—",I{r}/H{r}*100)')
        ws.cell(row=r, column=11).number_format = "0.0"
        ws.cell(row=r, column=12, value=(
            timezone.localtime(last_order).strftime("%Y-%m-%d") if last_order else "—"
        ))
        ws.cell(row=r, column=13, value=(
            timezone.localtime(last_pay).strftime("%Y-%m-%d") if last_pay else "—"
        ))

    _money_cols(ws, [5, 6, 7, 8, 9, 10])
    if ws.max_row > 1:
        tr = _totals_row(ws, label_col=1, formula_cols=[3, 4, 5, 6, 7, 8, 9, 10], label="الإجمالي")
        ws.cell(row=tr, column=3).number_format = INT_FMT
        ws.cell(row=tr, column=4).number_format = INT_FMT
    _autofit(ws, [22, 16, 12, 16, 16, 14, 14, 16, 16, 16, 12, 14, 14])

    # ================================================================
    # 5. PAYMENTS  المدفوعات
    # ================================================================
    ws = _sheet(wb, "المدفوعات", [
        "العميل",     # A
        "الهاتف",     # B
        "المبلغ",     # C
        "الطريقة",    # D
        "ملاحظة",     # E
        "التاريخ",    # F
    ])
    src = dict(BalanceNote.PaymentSource.choices)
    for p in payments_list:
        ws.append([
            p.user.first_name,
            p.user.phone or "—",
            float(p.amount),
            src.get(p.source, p.source or "—"),
            p.note or "",
            timezone.localtime(p.timestamp).strftime("%Y-%m-%d %H:%M"),
        ])
    _money_cols(ws, [3])
    if ws.max_row > 1:
        _totals_row(ws, label_col=1, formula_cols=[3], label="الإجمالي")
    _autofit(ws, [22, 16, 14, 16, 30, 18])

    # ================================================================
    # 6. INVENTORY  المخزون
    # ================================================================
    ws = _sheet(wb, "المخزون", [
        "البطارية",   # A
        "الماركة",    # B
        "SKU",        # C
        "السعر",      # D
        "المخزون",    # E
        "القيمة",     # F  (formula: D*E)
    ])
    for pr in Product.objects.filter(deleted=False).select_related("brand").order_by("brand__name", "name"):
        r = ws.max_row + 1
        ws.cell(row=r, column=1, value=pr.name)
        ws.cell(row=r, column=2, value=pr.brand.name if pr.brand_id else "—")
        ws.cell(row=r, column=3, value=pr.sku or "—")
        ws.cell(row=r, column=4, value=float(pr.price))
        ws.cell(row=r, column=5, value=pr.stock)
        # Formula: price * stock
        ws.cell(row=r, column=6, value=f"=D{r}*E{r}")
    _money_cols(ws, [4, 6])
    if ws.max_row > 1:
        _totals_row(ws, label_col=1, formula_cols=[5, 6], label="الإجمالي")
        ws.cell(row=ws.max_row, column=5).number_format = INT_FMT
    _autofit(ws, [24, 18, 14, 14, 12, 16])

    # ================================================================
    # 7. AUDIT LOG  سجل النشاط
    # ================================================================
    ws = _sheet(wb, "سجل النشاط", ["الموظف", "العملية", "العنصر", "التفاصيل", "الوقت"])
    audit = AuditLog.objects.all()
    if start:
        audit = audit.filter(created_at__date__gte=start)
    if end:
        audit = audit.filter(created_at__date__lte=end)
    for a in audit.order_by("-created_at")[:2000]:
        ws.append([
            a.actor_username or "—",
            a.get_action_display(),
            a.entity,
            a.object_repr,
            timezone.localtime(a.created_at).strftime("%Y-%m-%d %H:%M"),
        ])
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
