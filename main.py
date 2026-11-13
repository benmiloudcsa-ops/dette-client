import flet as ft
from datetime import datetime
import urllib.parse
import pandas as pd
from fpdf import FPDF
import requests
import threading
import time

# --- إعدادات Supabase السحابية ---
SUPABASE_URL = "https://osvdhhqllhmdeybsuoss.supabase.co"    # رابط مشروعك في Supabase
SUPABASE_KEY = "sb_publishable_BdSna0lbc71VC3tn2Wu0Yw_4x3RX-nS" # مفتاح الـ Anon/Public API

headers = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json",
    "Prefer": "return=representation"
}

# --- الفئة المساعدة لتوليد ملفات PDF مع دعم Unicode والخط العريض العربي ---
class PDFReport(FPDF):
    def header(self):
        try:
            self.add_font("ArabicFont", "", "C:/Windows/Fonts/arial.ttf", uni=True)
            self.add_font("ArabicFont", "B", "C:/Windows/Fonts/arialbd.ttf", uni=True)
            self.set_font("ArabicFont", "B", 14)
        except:
            self.set_font("Arial", "B", 14)
        self.cell(0, 10, 'Customer Debt Report - تقرير ديون الزبون', 0, 1, 'C')
        self.ln(5)

# --- دالّات التعامل مع السحابة (Supabase REST API) ---
def add_client(name, phone):
    url = f"{SUPABASE_URL}/rest/v1/clients"
    data = {"name": name, "phone": phone if phone else None}
    requests.post(url, headers=headers, json=data)

def delete_client(client_id):
    requests.delete(f"{SUPABASE_URL}/rest/v1/transactions?client_id=eq.{client_id}", headers=headers)
    requests.delete(f"{SUPABASE_URL}/rest/v1/clients?id=eq.{client_id}", headers=headers)

def add_transaction(client_id, amount, trans_type, date_str=None, note=""):
    url = f"{SUPABASE_URL}/rest/v1/transactions"
    data = {
        "client_id": client_id,
        "amount": amount,
        "type": trans_type,
        "note": note.strip() if note else None
    }
    if date_str:
        data["date"] = date_str
    requests.post(url, headers=headers, json=data)

def get_dashboard_stats():
    res_clients = requests.get(f"{SUPABASE_URL}/rest/v1/clients?select=id", headers=headers)
    total_clients = len(res_clients.json()) if res_clients.status_code == 200 else 0
    
    res_txs = requests.get(f"{SUPABASE_URL}/rest/v1/transactions?select=amount,type", headers=headers)
    total_debt = 0
    total_paid = 0
    if res_txs.status_code == 200:
        for t in res_txs.json():
            if t["type"] == 'debt':
                total_debt += t["amount"]
            elif t["type"] == 'payment':
                total_paid += t["amount"]
    net_debt = total_debt - total_paid
    return total_clients, net_debt

def get_clients_summary(search_query=""):
    url = f"{SUPABASE_URL}/rest/v1/clients?select=id,name,phone,transactions(amount,type)"
    if search_query:
        url += f"&or=(name.ilike.*{search_query}*,phone.ilike.*{search_query}*)"
    
    response = requests.get(url, headers=headers)
    if response.status_code == 200:
        data = response.json()
        results = []
        for c in data:
            c_id = c["id"]
            name = c["name"]
            phone = c["phone"]
            txs = c.get("transactions", [])
            total_debt = sum(t["amount"] for t in txs if t["type"] == 'debt') - sum(t["amount"] for t in txs if t["type"] == 'payment')
            results.append((c_id, name, phone, total_debt))
        return results
    return []

def get_client_period_report(client_id, start_date, end_date):
    url_prev = f"{SUPABASE_URL}/rest/v1/transactions?client_id=eq.{client_id}&date=lt.{start_date}&select=amount,type"
    res_prev = requests.get(url_prev, headers=headers)
    previous_balance = 0
    if res_prev.status_code == 200:
        for t in res_prev.json():
            if t["type"] == 'debt':
                previous_balance += t["amount"]
            else:
                previous_balance -= t["amount"]
                
    url_txs = f"{SUPABASE_URL}/rest/v1/transactions?client_id=eq.{client_id}&date=gte.{start_date}&date=lte.{end_date}&select=id,amount,type,date,note&order=date.asc,id.asc"
    res_txs = requests.get(url_txs, headers=headers)
    transactions = []
    if res_txs.status_code == 200:
        for t in res_txs.json():
            transactions.append((t["id"], t["amount"], t["type"], t["date"], t.get("note", "")))
            
    return previous_balance, transactions

# --- واجهة المستخدم الاحترافية ---
def main(page: ft.Page):
    page.title = "نظام إدارة ديون الزبائن - Gafaire"
    page.rtl = True  
    page.theme_mode = ft.ThemeMode.DARK
    page.bgcolor = "#0f172a"
    page.scroll = ft.ScrollMode.AUTO
    page.padding = 20
    page.window.maximized = True

    stat_clients_text = ft.Text("0", size=22, weight=ft.FontWeight.BOLD, color="white")
    stat_debt_text = ft.Text("0.00 دج", size=22, weight=ft.FontWeight.BOLD, color="#f87171")

    def update_dashboard_stats():
        c_count, n_debt = get_dashboard_stats()
        stat_clients_text.value = str(c_count)
        stat_debt_text.value = f"{n_debt:,.2f} دج"
        try:
            page.update()
        except:
            pass

    dashboard_card_clients = ft.Container(
        content=ft.Row([
            ft.Icon(ft.Icons.PEOPLE, size=35, color="#38bdf8"),
            ft.Column([
                ft.Text("إجمالي الزبائن", size=12, color="#94a3b8"),
                stat_clients_text
            ], spacing=2)
        ], alignment=ft.MainAxisAlignment.START, spacing=15),
        padding=15, bgcolor="#1e293b", border_radius=12, expand=True
    )

    dashboard_card_debt = ft.Container(
        content=ft.Row([
            ft.Icon(ft.Icons.ACCOUNT_BALANCE_WALLET, size=35, color="#f87171"),
            ft.Column([
                ft.Text("إجمالي الديون المعلقة", size=12, color="#94a3b8"),
                stat_debt_text
            ], spacing=2)
        ], alignment=ft.MainAxisAlignment.START, spacing=15),
        padding=15, bgcolor="#1e293b", border_radius=12, expand=True
    )

    dashboard_header = ft.ResponsiveRow([
        ft.Column([dashboard_card_clients], col={"xs": 12, "sm": 6}),
        ft.Column([dashboard_card_debt], col={"xs": 12, "sm": 6}),
    ])

    name_input = ft.TextField(label="اسم الزبون", prefix_icon=ft.Icons.PERSON, expand=True, focused_border_color="#38bdf8")
    phone_input = ft.TextField(label="رقم الهاتف", prefix_icon=ft.Icons.PHONE, keyboard_type=ft.KeyboardType.PHONE, expand=True, focused_border_color="#38bdf8")
    add_client_btn = ft.FilledButton("إضافة زبون", icon=ft.Icons.PERSON_ADD, bgcolor="#0284c7", color="white", on_click=lambda e: handle_add_client())

    search_input = ft.TextField(label="بحث سريع عن زبون بالاسم أو الهاتف...", prefix_icon=ft.Icons.SEARCH, expand=True, focused_border_color="#38bdf8", on_change=lambda e: refresh_table())

    def show_snack(message, color="green"):
        page.snack_bar = ft.SnackBar(ft.Text(message, color="white"), bgcolor=color)
        page.snack_bar.open = True
        page.update()

    # --- دالة التحديث اليدوي ---
    def manual_refresh(e):
        refresh_table()
        update_dashboard_stats()
        show_snack("تم تحديث البيانات بنجاح", "blue")

    refresh_btn = ft.FilledButton("تحديث", icon=ft.Icons.REFRESH, bgcolor="#334155", color="white", on_click=manual_refresh)
    export_excel_btn = ft.FilledButton("تصدير Excel", icon=ft.Icons.TABLE_CHART, bgcolor="#16a34a", color="white", on_click=lambda e: export_excel(e))

    def export_excel(e):
        clients_data = get_clients_summary(search_input.value if search_input.value else "")
        if not clients_data:
            show_snack("لا توجد بيانات لتصديرها!", "orange")
            return
        
        data_list = []
        for c in clients_data:
            c_id, name, phone, debt = c
            data_list.append({
                "معرف الزبون": c_id,
                "اسم الزبون": name,
                "رقم الهاتف": phone if phone else "غير محدد",
                "إجمالي الدين (دج)": debt
            })
        
        df = pd.DataFrame(data_list)
        file_name = f"clients_debt_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
        df.to_excel(file_name, index=False)
        show_snack(f"تم تصدير ملف Excel بنجاح باسم: {file_name}", "green")

    clients_table = ft.DataTable(
        columns=[
            ft.DataColumn(ft.Text("اسم الزبون", weight=ft.FontWeight.BOLD, color="#cbd5e1")),
            ft.DataColumn(ft.Text("الهاتف", weight=ft.FontWeight.BOLD, color="#cbd5e1")),
            ft.DataColumn(ft.Text("إجمالي الدين", weight=ft.FontWeight.BOLD, color="#cbd5e1")),
            ft.DataColumn(ft.Text("الإجراءات المتاحة", weight=ft.FontWeight.BOLD, color="#cbd5e1")),
        ],
        rows=[]
    )
    
    table_container = ft.Row([clients_table], scroll=ft.ScrollMode.AUTO, expand=True)

    trans_amount_input = ft.TextField(label="المبلغ (دج)", keyboard_type=ft.KeyboardType.NUMBER, expand=True)
    trans_date_input = ft.TextField(label="التاريخ", value=datetime.now().strftime("%Y-%m-%d"), expand=True)
    trans_note_input = ft.TextField(label="ملاحظة العملية (اختياري)", prefix_icon=ft.Icons.NOTE, expand=True)
    trans_title_text = ft.Text("", weight=ft.FontWeight.BOLD, size=15, color="#38bdf8")
    current_trans_data = {"cid": None, "type": ""}

    def confirm_transaction(e):
        try:
            amt = float(trans_amount_input.value)
            date_val = trans_date_input.value.strip()
            note_val = trans_note_input.value.strip()
            add_transaction(current_trans_data['cid'], amt, current_trans_data['type'], date_val, note_val)
            trans_amount_input.value = ""
            trans_note_input.value = ""
            trans_container.visible = False
            show_snack("تم تسجيل المعاملة بنجاح!")
            refresh_table()
            update_dashboard_stats()
        except ValueError:
            trans_amount_input.error_text = "أدخل مبلغاً صحيحاً"
            page.update()

    trans_container = ft.Container(
        content=ft.Column([
            trans_title_text,
            ft.ResponsiveRow([
                ft.Column([trans_amount_input], col={"xs": 12, "sm": 6}),
                ft.Column([trans_date_input], col={"xs": 12, "sm": 6}),
            ]),
            ft.Row([trans_note_input]),
            ft.Row([
                ft.FilledButton("تأكيد العملية", icon=ft.Icons.CHECK, bgcolor="#10b981", color="white", on_click=confirm_transaction), 
                ft.TextButton("إلغاء", icon=ft.Icons.CLOSE, on_click=lambda e: setattr(trans_container, 'visible', False) or page.update())
            ], wrap=True)
        ], tight=True),
        padding=15, bgcolor="#1e293b", border_radius=12, visible=False
    )

    def open_trans_form(cid, name, trans_type):
        delete_container.visible = False
        report_container.visible = False
        current_trans_data['cid'] = cid
        current_trans_data['type'] = trans_type
        action_name = "إضافة دين جديد" if trans_type == 'debt' else "تسجيل عملية تسديد"
        trans_title_text.value = f"{action_name} للزبون: {name}"
        trans_amount_input.value = ""
        trans_note_input.value = ""
        trans_container.visible = True
        page.update()

    delete_title_text = ft.Text("", weight=ft.FontWeight.BOLD, size=15, color="#f87171")
    current_delete_data = {"cid": None, "name": ""}

    delete_container = ft.Container(
        content=ft.Column([
            delete_title_text,
            ft.Row([
                ft.FilledButton("تأكيد الحذف النهائي", icon=ft.Icons.DELETE, bgcolor="#ef4444", color="white", on_click=lambda e: (delete_client(current_delete_data['cid']), setattr(delete_container, 'visible', False), show_snack(f"تم حذف الزبون ({current_delete_data['name']})", "red"), refresh_table(), update_dashboard_stats())),
                ft.TextButton("إلغاء", icon=ft.Icons.CLOSE, on_click=lambda e: setattr(delete_container, 'visible', False) or page.update())
            ], wrap=True)
        ], tight=True),
        padding=15, bgcolor="#1e293b", border_radius=12, visible=False
    )

    def open_delete_form(cid, name):
        trans_container.visible = False
        report_container.visible = False
        current_delete_data['cid'] = cid
        current_delete_data['name'] = name
        delete_title_text.value = f"⚠️ هل أنت متأكد من رغبتك في حذف الزبون ({name}) وجميع معاملاته؟"
        delete_container.visible = True
        page.update()

    report_title = ft.Text("", weight=ft.FontWeight.BOLD, size=16, color="#38bdf8")
    start_date_input = ft.TextField(label="من تاريخ", value="2026-01-01", expand=True)
    end_date_input = ft.TextField(label="إلى تاريخ", value=datetime.now().strftime("%Y-%m-%d"), expand=True)
    report_results_column = ft.Column(spacing=5)
    current_report_client = {"cid": None, "name": "", "phone": ""}
    
    cached_report_text = {"text": ""}

    def generate_report(e):
        cid = current_report_client['cid']
        name = current_report_client['name']
        s_date = start_date_input.value.strip()
        e_date = end_date_input.value.strip()
        
        prev_balance, txs = get_client_period_report(cid, s_date, e_date)
        report_results_column.controls.clear()
        
        report_lines = [
            f"📋 *تقرير كشف حساب زبون*",
            f"👤 الزبون: {name}",
            f"📅 الفترة من: {s_date} إلى {e_date}",
            f"─────────────────",
            f"💰 الرصيد السابق: {prev_balance:.2f} دج",
            f"─────────────────"
        ]
        
        report_results_column.controls.append(ft.Text(f"الرصيد السابق قبل {s_date}: {prev_balance:.2f} دج", weight=ft.FontWeight.BOLD, size=14, color="#38bdf8" if prev_balance <= 0 else "#f87171"))
        report_results_column.controls.append(ft.Divider())
        
        if not txs:
            report_results_column.controls.append(ft.Text("لا توجد حركات مسجلة خلال هذه الفترة.", color="#94a3b8", italic=True))
            report_lines.append("لا توجد حركات مسجلة خلال هذه الفترة.")
        else:
            running_balance = prev_balance
            for t_id, amt, t_type, t_date, note in txs:
                note_str = f" ({note})" if note else ""
                if t_type == 'debt':
                    running_balance += amt
                    t_desc = f"دين: +{amt:.2f} دج{note_str}"
                    t_color = "#f87171"
                    report_lines.append(f"▫️ {t_date} | {t_desc} | الرصيد: {running_balance:.2f}")
                else:
                    running_balance -= amt
                    t_desc = f"تسديد: -{amt:.2f} دج{note_str}"
                    t_color = "#34d399"
                    report_lines.append(f"▫️ {t_date} | {t_desc} | الرصيد: {running_balance:.2f}")
                
                report_results_column.controls.append(
                    ft.Row([
                        ft.Text(f"التاريخ: {t_date}", size=12, color="#94a3b8"),
                        ft.Text(t_desc, color=t_color, weight=ft.FontWeight.BOLD, size=13),
                        ft.Text(f"الرصيد: {running_balance:.2f} دج", size=12, italic=True, color="#cbd5e1")
                    ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN, wrap=True)
                )
            report_lines.append(f"─────────────────")
            report_lines.append(f"📌 *الرصيد الإجمالي النهائي: {running_balance:.2f} دج*")
            
        cached_report_text["text"] = "\n".join(report_lines)
        page.update()

    def send_whatsapp(e):
        phone = current_report_client['phone']
        report_text = cached_report_text["text"]
        if not report_text:
            show_snack("الرجاء إنشاء التقرير أولاً!", "orange")
            return
        if not phone:
            show_snack("رقم هاتف هذا الزبون غير مسجل!", "red")
            return
            
        clean_phone = phone.strip().replace(" ", "").replace("+", "")
        if clean_phone.startswith("0"):
            clean_phone = "213" + clean_phone[1:]
            
        encoded_text = urllib.parse.quote(report_text)
        whatsapp_url = f"https://wa.me/{clean_phone}?text={encoded_text}"
        
        # استخدام page.launch_url المدعومة في Flet لتشغيل التطبيقات الخارجية على أندرويد
        page.launch_url(whatsapp_url)
        show_snack("جاري فتح الواتساب لإرسال التقرير...")

    def export_pdf(e):
        cid = current_report_client['cid']
        name = current_report_client['name']
        s_date = start_date_input.value.strip()
        e_date = end_date_input.value.strip()
        
        prev_balance, txs = get_client_period_report(cid, s_date, e_date)
        
        pdf = PDFReport()
        pdf.add_page()
        
        try:
            pdf.add_font("ArabicFont", "", "C:/Windows/Fonts/arial.ttf", uni=True)
            pdf.add_font("ArabicFont", "B", "C:/Windows/Fonts/arialbd.ttf", uni=True)
            pdf.set_font("ArabicFont", "", 11)
        except:
            pdf.set_font("Arial", "", 11)
            
        pdf.cell(0, 8, f"اسم الزبون: {name}", 0, 1)
        pdf.cell(0, 8, f"الفترة: من {s_date} إلى {e_date}", 0, 1)
        pdf.cell(0, 8, f"الرصيد السابق: {prev_balance:.2f} دج", 0, 1)
        pdf.ln(5)
        
        pdf.set_font("ArabicFont", "B", 10)
        pdf.cell(30, 7, "التاريخ", 1)
        pdf.cell(40, 7, "المعاملة", 1)
        pdf.cell(35, 7, "المبلغ (دج)", 1)
        pdf.cell(85, 7, "ملاحظة", 1)
        pdf.ln()
        
        pdf.set_font("ArabicFont", "", 9)
        for t in txs:
            t_id, amt, t_type, t_date, note = t
            t_str = "دين (+)" if t_type == 'debt' else "تسديد (-)"
            pdf.cell(30, 6, str(t_date), 1)
            pdf.cell(40, 6, t_str, 1)
            pdf.cell(35, 6, f"{amt:.2f}", 1)
            pdf.cell(85, 6, str(note) if note else "", 1)
            pdf.ln()
            
        file_name = f"report_{name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
        pdf.output(file_name)
        show_snack(f"تم تصدير ملف PDF بنجاح: {file_name}", "green")

    export_pdf_btn = ft.FilledButton("تصدير PDF", icon=ft.Icons.PICTURE_AS_PDF, bgcolor="#dc2626", color="white", on_click=export_pdf)

    report_container = ft.Container(
        content=ft.Column([
            report_title,
            ft.ResponsiveRow([
                ft.Column([start_date_input], col={"xs": 12, "sm": 6}),
                ft.Column([end_date_input], col={"xs": 12, "sm": 6}),
            ]),
            ft.Row([
                ft.FilledButton("عرض التقرير", icon=ft.Icons.SEARCH, bgcolor="#0284c7", color="white", on_click=generate_report), 
                ft.FilledButton("إرسال عبر الواتساب", icon=ft.Icons.CHAT, bgcolor="#059669", color="white", on_click=send_whatsapp), 
                export_pdf_btn,
                ft.TextButton("إغلاق", icon=ft.Icons.CLOSE, on_click=lambda e: setattr(report_container, 'visible', False) or page.update())
            ], wrap=True),
            ft.Divider(),
            report_results_column
        ], tight=True),
        padding=15, bgcolor="#1e293b", border_radius=12, visible=False
    )

    def open_report_form(cid, name, phone):
        trans_container.visible = False
        delete_container.visible = False
        current_report_client['cid'] = cid
        current_report_client['name'] = name
        current_report_client['phone'] = phone if phone else ""
        report_title.value = f"📊 كشف حساب وتفاصيل الفترة للزبون: {name}"
        report_results_column.controls.clear()
        cached_report_text["text"] = ""
        report_container.visible = True
        page.update()

    def refresh_table():
        clients_table.rows.clear()
        clients = get_clients_summary(search_input.value if search_input.value else "")
        
        if not clients:
            clients_table.rows.append(
                ft.DataRow(cells=[
                    ft.DataCell(ft.Text("لا توجد نتائج مطابقة للبحث", color="#64748b")),
                    ft.DataCell(ft.Text("-", color="#64748b")),
                    ft.DataCell(ft.Text("-", color="#64748b")),
                    ft.DataCell(ft.Text("-", color="#64748b")),
                ])
            )
        else:
            for client in clients:
                c_id, name, phone, debt = client
                row_color = "#3f1d1d" if debt > 0 else "#064e3b"
                
                actions_row = ft.Row([
                    ft.OutlinedButton("دين +", icon=ft.Icons.ADD, icon_color="#f87171", on_click=lambda e, cid=c_id, cname=name: open_trans_form(cid, cname, 'debt')),
                    ft.OutlinedButton("تسديد -", icon=ft.Icons.REMOVE, icon_color="#34d399", on_click=lambda e, cid=c_id, cname=name: open_trans_form(cid, cname, 'payment')),
                    ft.OutlinedButton("تقرير", icon=ft.Icons.ASSESSMENT, icon_color="#38bdf8", on_click=lambda e, cid=c_id, cname=name, cphone=phone: open_report_form(cid, name, cphone)),
                    ft.TextButton("حذف", icon=ft.Icons.DELETE_OUTLINE, icon_color="#ef4444", on_click=lambda e, cid=c_id, cname=name: open_delete_form(cid, name)),
                ], spacing=2, wrap=True)

                clients_table.rows.append(
                    ft.DataRow(
                        color=row_color,
                        cells=[
                            ft.DataCell(ft.Text(name, weight=ft.FontWeight.BOLD, color="white")),
                            ft.DataCell(ft.Text(phone if phone else "غير محدد", color="#94a3b8")),
                            ft.DataCell(ft.Text(f"{debt:,.2f} دج", color="#f87171" if debt > 0 else "#34d399", weight=ft.FontWeight.BOLD)),
                            ft.DataCell(actions_row),
                        ]
                    )
                )
        try:
            page.update()
        except:
            pass

    def handle_add_client():
        if name_input.value and name_input.value.strip():
            add_client(name_input.value.strip(), phone_input.value.strip() if phone_input.value else "")
            name_input.value = ""
            phone_input.value = ""
            show_snack("تم إضافة الزبون بنجاح  !")
            refresh_table()
            update_dashboard_stats()
        else:
            show_snack("الرجاء إدخال اسم الزبون على الأقل!", "red")

    add_client_section = ft.Container(
        content=ft.Column([
            ft.Text("✨ إضافة زبون جديد ", size=16, weight=ft.FontWeight.BOLD, color="#38bdf8"),
            ft.ResponsiveRow([
                ft.Column([name_input], col={"xs": 12, "sm": 5}),
                ft.Column([phone_input], col={"xs": 12, "sm": 4}),
                ft.Column([add_client_btn], col={"xs": 12, "sm": 3}),
            ], alignment=ft.MainAxisAlignment.START)
        ]),
        padding=15, bgcolor="#1e293b", border_radius=12
    )

    page.add(
        ft.Row([
            ft.Icon(ft.Icons.CLOUD, size=28, color="#38bdf8"),
            ft.Text("نظام تسيير وإدارة الديون  ", size=22, weight=ft.FontWeight.BOLD, color="white")
        ], spacing=10),
        ft.Divider(color="#334155"),
        dashboard_header,
        ft.Divider(height=10, color="transparent"),
        add_client_section,
        ft.Divider(height=15, color="transparent"),
        trans_container,   
        delete_container,  
        report_container,  
        ft.ResponsiveRow([
            ft.Column([search_input], col={"xs": 12, "sm": 7}),
            ft.Column([refresh_btn], col={"xs": 6, "sm": 2}),
            ft.Column([export_excel_btn], col={"xs": 6, "sm": 3}),
        ], alignment=ft.MainAxisAlignment.START),
        ft.Divider(height=10, color="transparent"),
        ft.Text("📋 قائمة الزبائن والديون", size=18, weight=ft.FontWeight.BOLD, color="white"),
        table_container
    )

    # --- تشغيل خيط التحديث التلقائي في الخلفية (Background Polling) كل 10 ثوانٍ ---
    def background_sync():
        while True:
            time.sleep(10)
            try:
                refresh_table()
                update_dashboard_stats()
            except:
                pass

    sync_thread = threading.Thread(target=background_sync, daemon=True)
    sync_thread.start()

    refresh_table()
    update_dashboard_stats()
    if __name__ == "__main__":
        ft.app(target=main)
