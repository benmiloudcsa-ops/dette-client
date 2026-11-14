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

# --- حالة التطبيق العامة (تخزين الثيم الحالي، يبدأ بالثيم الأزرق الملكي) ---
app_state = {
    "theme": "royal"  # الخيارات المتاحة: "royal", "light_blue", "accounting", "butcher_modern", "dark", "light"
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

def get_clients_summary(search_query="", debtors_only=False):
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
            
            if debtors_only and total_debt <= 0:
                continue
                
            results.append((c_id, name, phone, total_debt))
        
        results.sort(key=lambda x: x[3], reverse=True)
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

# --- التطبيق الرئيسي ---
def main(page: ft.Page):
    page.title = "نظام إدارة ديون الزبائن - Gafaire"
    page.rtl = True  
    page.window.maximized = True

    APP_PASSWORD = "admin123"

    # دالة تحديد الألوان بناءً على الثيم المختار
    def get_colors():
        t = app_state["theme"]
        if t == "royal":
            return {
                "bg": "#0d1b2a",          # أزرق ملكي عميق جداً للخلفية
                "card_bg": "#1b263b",     # أزرق ملكي داكن للبطاقات
                "text_main": "#ffffff",
                "text_sec": "#90e0ef",
                "border": "#415a77",
                "row_debt": "#3a1c1c",    # لون هادئ للديون
                "row_clear": "#133b32",   # لون هادئ للصافي
                "primary": "#48cae4",
                "accent_btn": "#0077b6"
            }
        elif t == "light_blue":
            return {
                "bg": "#f0f9ff",          
                "card_bg": "#ffffff",     
                "text_main": "#0f172a",
                "text_sec": "#475569",
                "border": "#bae6fd",
                "row_debt": "#fee2e2",    
                "row_clear": "#f0fdf4",   
                "primary": "#0284c7",     
                "accent_btn": "#0284c7"
            }
        elif t == "accounting":
            return {
                "bg": "#f4f6f8",          
                "card_bg": "#ffffff",     
                "text_main": "#111827",
                "text_sec": "#4b5563",
                "border": "#d1d5db",
                "row_debt": "#fef2f2",    
                "row_clear": "#f0fdf4",   
                "primary": "#047857",     
                "accent_btn": "#059669"
            }
        elif t == "butcher_modern":
            return {
                "bg": "#121417",          
                "card_bg": "#1e2229",     
                "text_main": "#f3f4f6",
                "text_sec": "#9ca3af",
                "border": "#2f3640",
                "row_debt": "#321e23",    
                "row_clear": "#142d22",   
                "primary": "#d4af37",     
                "accent_btn": "#2c3e50"   
            }
        elif t == "dark":
            return {
                "bg": "#0f172a",
                "card_bg": "#1e293b",
                "text_main": "white",
                "text_sec": "#94a3b8",
                "border": "#334155",
                "row_debt": "#3f1d1d",
                "row_clear": "#064e3b",
                "primary": "#38bdf8",
                "accent_btn": "#0284c7"
            }
        else:  # light
            return {
                "bg": "#f8fafc",
                "card_bg": "white",
                "text_main": "#1e293b",
                "text_sec": "#64748b",
                "border": "#e2e8f0",
                "row_debt": "#fee2e2",
                "row_clear": "#ecfdf5",
                "primary": "#0284c7",
                "accent_btn": "#0284c7"
            }

    # دالة تغيير الثيم عبر القائمة المنسدلة
    def change_theme(e):
        app_state["theme"] = e.control.value
        if len(page.views) > 0 and page.views[-1].route == "/login":
            show_login_view()
        else:
            load_main_dashboard()

    # --- شاشة تسجيل الدخول ---
    def show_login_view():
        page.views.clear()
        c = get_colors()
        page.theme_mode = ft.ThemeMode.LIGHT if app_state["theme"] in ["light", "accounting", "light_blue"] else ft.ThemeMode.DARK
        page.bgcolor = c["bg"]

        password_input = ft.TextField(
            label="كلمة المرور",
            password=True,
            can_reveal_password=True,
            prefix_icon=ft.Icons.LOCK,
            width=320,
            focused_border_color=c["primary"]
        )
        error_text = ft.Text("", color="#dc2626" if app_state["theme"] in ["light", "accounting", "light_blue"] else "#f87171", size=13)

        def verify_password(e):
            if password_input.value == APP_PASSWORD:
                load_main_dashboard()
            else:
                error_text.value = "❌ كلمة المرور غير صحيحة، يرجى المحاولة مرة أخرى."
                page.update()

        theme_dropdown = ft.Dropdown(
            value=app_state["theme"],
            options=[
                ft.dropdown.Option("royal", "💙 أزرق ملكي"),
                ft.dropdown.Option("light_blue", "🌐 أزرق فاتح"),
                ft.dropdown.Option("accounting", "💚 الثيم المحاسبي"),
                ft.dropdown.Option("butcher_modern", "🥩 جزارة عصرية"),
                ft.dropdown.Option("dark", "🌙 داكن"),
                ft.dropdown.Option("light", "☀️ فاتح")
            ],
            width=160,
            text_size=13,
            on_change=change_theme
        )

        # شعار الجزارة العصرية الدائري[cite: 3]
        store_logo = ft.Container(
            content=ft.Column([
                ft.Image(
                    src="logo.png",
                    width=120,
                    height=120,
                    border_radius=60,
                    fit=ft.ImageFit.CONTAIN
                )
            ], horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=0),
            alignment=ft.alignment.center
        )

        login_view = ft.View(
            "/login",
            [
                ft.Row([theme_dropdown], alignment=ft.MainAxisAlignment.END),
                ft.Column([
                    ft.Container(
                        content=ft.Column([
                            store_logo,
                            ft.Divider(height=5, color="transparent"),
                            ft.Text("تسجيل الدخول للنظام", size=20, weight=ft.FontWeight.BOLD, color=c["text_main"]),
                            ft.Text("يرجى إدخال كلمة المرور للمتابعة", size=13, color=c["text_sec"]),
                            ft.Divider(height=10, color="transparent"),
                            password_input,
                            error_text,
                            ft.Divider(height=5, color="transparent"),
                            ft.FilledButton(
                                "فتح التطبيق", 
                                icon=ft.Icons.LOGIN, 
                                bgcolor=c["accent_btn"], 
                                color="white", 
                                width=320, 
                                on_click=verify_password
                            )
                        ], horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=10),
                        padding=30,
                        bgcolor=c["card_bg"],
                        border_radius=16,
                        border=ft.border.all(1, c["border"]) if app_state["theme"] in ["light", "accounting", "light_blue"] else None,
                        shadow=ft.BoxShadow(spread_radius=1, blur_radius=15, color=ft.Colors.BLACK12 if app_state["theme"] in ["light", "accounting", "light_blue"] else ft.Colors.BLACK54)
                    )
                ], alignment=ft.MainAxisAlignment.CENTER, horizontal_alignment=ft.CrossAxisAlignment.CENTER, expand=True)
            ],
            vertical_alignment=ft.MainAxisAlignment.CENTER,
            horizontal_alignment=ft.MainAxisAlignment.CENTER,
            bgcolor=c["bg"],
            padding=20
        )
        page.views.append(login_view)
        page.update()

    def logout():
        show_login_view()

    # --- لوحة التحكم الرئيسية لنظام إدارة الديون ---
    def load_main_dashboard():
        page.views.clear()
        c = get_colors()
        page.theme_mode = ft.ThemeMode.LIGHT if app_state["theme"] in ["light", "accounting", "light_blue"] else ft.ThemeMode.DARK
        page.bgcolor = c["bg"]

        stat_clients_text = ft.Text("0", size=22, weight=ft.FontWeight.BOLD, color=c["text_main"])
        stat_debt_text = ft.Text("0.00 دج", size=22, weight=ft.FontWeight.BOLD, color="#f87171" if app_state["theme"] not in ["light", "accounting", "light_blue"] else "#dc2626")

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
                ft.Icon(ft.Icons.PEOPLE, size=35, color=c["primary"]),
                ft.Column([
                    ft.Text("إجمالي الزبائن", size=12, color=c["text_sec"]),
                    stat_clients_text
                ], spacing=2)
            ], alignment=ft.MainAxisAlignment.START, spacing=15),
            padding=15, bgcolor=c["card_bg"], border_radius=12, border=ft.border.all(1, c["border"]) if app_state["theme"] in ["light", "accounting", "light_blue"] else None, expand=True
        )

        dashboard_card_debt = ft.Container(
            content=ft.Row([
                ft.Icon(ft.Icons.ACCOUNT_BALANCE_WALLET, size=35, color="#f87171" if app_state["theme"] not in ["light", "accounting", "light_blue"] else "#dc2626"),
                ft.Column([
                    ft.Text("إجمالي الديون المعلقة", size=12, color=c["text_sec"]),
                    stat_debt_text
                ], spacing=2)
            ], alignment=ft.MainAxisAlignment.START, spacing=15),
            padding=15, bgcolor=c["card_bg"], border_radius=12, border=ft.border.all(1, c["border"]) if app_state["theme"] in ["light", "accounting", "light_blue"] else None, expand=True
        )

        dashboard_header = ft.ResponsiveRow([
            ft.Column([dashboard_card_clients], col={"xs": 12, "sm": 6}),
            ft.Column([dashboard_card_debt], col={"xs": 12, "sm": 6}),
        ])

        name_input = ft.TextField(label="اسم الزبون", prefix_icon=ft.Icons.PERSON, expand=True, focused_border_color=c["primary"])
        phone_input = ft.TextField(label="رقم الهاتف", prefix_icon=ft.Icons.PHONE, keyboard_type=ft.KeyboardType.PHONE, expand=True, focused_border_color=c["primary"])
        add_client_btn = ft.FilledButton("إضافة زبون", icon=ft.Icons.PERSON_ADD, bgcolor=c["accent_btn"], color="white", on_click=lambda e: handle_add_client())

        search_input = ft.TextField(label="بحث سريع عن زبون بالاسم أو الهاتف...", prefix_icon=ft.Icons.SEARCH, expand=True, focused_border_color=c["primary"], on_change=lambda e: refresh_table())
        
        debtors_filter = ft.Checkbox(
            label="عرض المدينين فقط", 
            value=True, 
            active_color=c["primary"],
            on_change=lambda e: refresh_table()
        )

        def show_snack(message, color="green"):
            page.snack_bar = ft.SnackBar(ft.Text(message, color="white"), bgcolor=color)
            page.snack_bar.open = True
            page.update()

        def manual_refresh(e):
            refresh_table()
            update_dashboard_stats()
            show_snack("تم تحديث البيانات بنجاح", "blue")

        refresh_btn = ft.FilledButton("تحديث", icon=ft.Icons.REFRESH, bgcolor="#334155" if app_state["theme"] not in ["light", "accounting", "light_blue"] else "#64748b", color="white", on_click=manual_refresh)
        export_excel_btn = ft.FilledButton("تصدير Excel", icon=ft.Icons.TABLE_CHART, bgcolor="#16a34a", color="white", on_click=lambda e: export_excel(e))
        logout_btn = ft.FilledButton("تسجيل الخروج", icon=ft.Icons.LOGOUT, bgcolor="#ef4444", color="white", on_click=lambda e: logout())
        
        theme_dropdown = ft.Dropdown(
            value=app_state["theme"],
            options=[
                ft.dropdown.Option("royal", "💙 أزرق ملكي"),
                ft.dropdown.Option("light_blue", "🌐 أزرق فاتح"),
                ft.dropdown.Option("accounting", "💚 الثيم المحاسبي"),
                ft.dropdown.Option("butcher_modern", "🥩 جزارة عصرية"),
                ft.dropdown.Option("dark", "🌙 داكن"),
                ft.dropdown.Option("light", "☀️ فاتح")
            ],
            width=160,
            text_size=13,
            on_change=change_theme
        )

        def export_excel(e):
            clients_data = get_clients_summary(
                search_input.value if search_input.value else "",
                debtors_filter.value
            )
            if not clients_data:
                show_snack("لا توجد بيانات لتصديرها!", "orange")
                return
            
            data_list = []
            for c_item in clients_data:
                c_id, name, phone, debt = c_item
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
                ft.DataColumn(ft.Text("اسم الزبون", weight=ft.FontWeight.BOLD, color=c["text_main"])),
                ft.DataColumn(ft.Text("الهاتف", weight=ft.FontWeight.BOLD, color=c["text_main"])),
                ft.DataColumn(ft.Text("إجمالي الدين", weight=ft.FontWeight.BOLD, color=c["text_main"])),
                ft.DataColumn(ft.Text("الإجراءات المتاحة", weight=ft.FontWeight.BOLD, color=c["text_main"])),
            ],
            rows=[]
        )
        
        table_container = ft.Row([clients_table], scroll=ft.ScrollMode.AUTO, expand=True)

        trans_amount_input = ft.TextField(label="المبلغ (دج)", keyboard_type=ft.KeyboardType.NUMBER, expand=True)
        trans_date_input = ft.TextField(label="التاريخ", value=datetime.now().strftime("%Y-%m-%d"), expand=True)
        trans_note_input = ft.TextField(label="ملاحظة العملية (اختياري)", prefix_icon=ft.Icons.NOTE, expand=True)
        trans_title_text = ft.Text("", weight=ft.FontWeight.BOLD, size=15, color=c["primary"])
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
            padding=15, bgcolor=c["card_bg"], border_radius=12, border=ft.border.all(1, c["border"]) if app_state["theme"] in ["light", "accounting", "light_blue"] else None, visible=False
        )

        def open_trans_form(cid, name, trans_type):
            report_container.visible = False
            current_trans_data['cid'] = cid
            current_trans_data['type'] = trans_type
            action_name = "إضافة دين جديد" if trans_type == 'debt' else "تسجيل عملية تسديد"
            trans_title_text.value = f"{action_name} للزبون: {name}"
            trans_amount_input.value = ""
            trans_note_input.value = ""
            trans_container.visible = True
            page.update()

        report_title = ft.Text("", weight=ft.FontWeight.BOLD, size=16, color=c["primary"])
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
            
            report_results_column.controls.append(ft.Text(f"الرصيد السابق قبل {s_date}: {prev_balance:.2f} دج", weight=ft.FontWeight.BOLD, size=14, color=c["primary"] if prev_balance <= 0 else "#f87171"))
            report_results_column.controls.append(ft.Divider())
            
            if not txs:
                report_results_column.controls.append(ft.Text("لا توجد حركات مسجلة خلال هذه الفترة.", color=c["text_sec"], italic=True))
                report_lines.append("لا توجد حركات مسجلة خلال هذه الفترة.")
            else:
                running_balance = prev_balance
                for t_id, amt, t_type, t_date, note in txs:
                    note_str = f" ({note})" if note else ""
                    if t_type == 'debt':
                        running_balance += amt
                        t_desc = f"دين: +{amt:.2f} دج{note_str}"
                        t_color = "#f87171" if app_state["theme"] not in ["light", "accounting", "light_blue"] else "#dc2626"
                        report_lines.append(f"▫️ {t_date} | {t_desc} | الرصيد: {running_balance:.2f}")
                    else:
                        running_balance -= amt
                        t_desc = f"تسديد: -{amt:.2f} دج{note_str}"
                        t_color = "#34d399" if app_state["theme"] not in ["light", "accounting", "light_blue"] else "#059669"
                        report_lines.append(f"▫️ {t_date} | {t_desc} | الرصيد: {running_balance:.2f}")
                    
                    report_results_column.controls.append(
                        ft.Row([
                            ft.Text(f"التاريخ: {t_date}", size=12, color=c["text_sec"]),
                            ft.Text(t_desc, color=t_color, weight=ft.FontWeight.BOLD, size=13),
                            ft.Text(f"الرصيد: {running_balance:.2f} دج", size=12, italic=True, color=c["text_main"])
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
                    ft.FilledButton("عرض التقرير", icon=ft.Icons.SEARCH, bgcolor=c["accent_btn"], color="white", on_click=generate_report), 
                    ft.FilledButton("إرسال عبر الواتساب", icon=ft.Icons.CHAT, bgcolor="#059669", color="white", on_click=send_whatsapp), 
                    export_pdf_btn,
                    ft.TextButton("إغلاق", icon=ft.Icons.CLOSE, on_click=lambda e: setattr(report_container, 'visible', False) or page.update())
                ], wrap=True),
                ft.Divider(),
                report_results_column
            ], tight=True),
            padding=15, bgcolor=c["card_bg"], border_radius=12, border=ft.border.all(1, c["border"]) if app_state["theme"] in ["light", "accounting", "light_blue"] else None, visible=False
        )

        def open_report_form(cid, name, phone):
            trans_container.visible = False
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
            clients = get_clients_summary(
                search_input.value if search_input.value else "",
                debtors_only=debtors_filter.value
            )
            
            if not clients:
                clients_table.rows.append(
                    ft.DataRow(cells=[
                        ft.DataCell(ft.Text("لا توجد نتائج مطابقة للبحث أو الفلتر", color=c["text_sec"])),
                        ft.DataCell(ft.Text("-", color=c["text_sec"])),
                        ft.DataCell(ft.Text("-", color=c["text_sec"])),
                        ft.DataCell(ft.Text("-", color=c["text_sec"])),
                    ])
                )
            else:
                for client in clients:
                    c_id, name, phone, debt = client
                    row_color = c["row_debt"] if debt > 0 else c["row_clear"]
                    
                    actions_row = ft.Row([
                        ft.IconButton(
                            icon=ft.Icons.ADD_CIRCLE_OUTLINE,
                            icon_color="#f87171" if app_state["theme"] not in ["light", "accounting", "light_blue"] else "#dc2626",
                            tooltip="إضافة دين (+)",
                            on_click=lambda e, cid=c_id, cname=name: open_trans_form(cid, cname, 'debt')
                        ),
                        ft.IconButton(
                            icon=ft.Icons.REMOVE_CIRCLE_OUTLINE,
                            icon_color="#34d399" if app_state["theme"] not in ["light", "accounting", "light_blue"] else "#059669",
                            tooltip="تسجيل تسديد (-)",
                            on_click=lambda e, cid=c_id, cname=name: open_trans_form(cid, cname, 'payment')
                        ),
                        ft.IconButton(
                            icon=ft.Icons.ASSESSMENT,
                            icon_color=c["primary"],
                            tooltip="كشف الحساب والتقرير",
                            on_click=lambda e, cid=c_id, cname=name, cphone=phone: open_report_form(cid, name, cphone)
                        ),
                    ], spacing=2)

                    clients_table.rows.append(
                        ft.DataRow(
                            color=row_color,
                            cells=[
                                ft.DataCell(ft.Text(name, weight=ft.FontWeight.BOLD, color=c["text_main"])),
                                ft.DataCell(ft.Text(phone if phone else "غير محدد", color=c["text_sec"])),
                                ft.DataCell(ft.Text(f"{debt:,.2f} دج", color="#f87171" if debt > 0 and app_state["theme"] not in ["light", "accounting", "light_blue"] else ("#dc2626" if debt > 0 else "#059669"), weight=ft.FontWeight.BOLD)),
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
                ft.Text("✨ إضافة زبون جديد ", size=16, weight=ft.FontWeight.BOLD, color=c["primary"]),
                ft.ResponsiveRow([
                    ft.Column([name_input], col={"xs": 12, "sm": 5}),
                    ft.Column([phone_input], col={"xs": 12, "sm": 4}),
                    ft.Column([add_client_btn], col={"xs": 12, "sm": 3}),
                ], alignment=ft.MainAxisAlignment.START)
            ]),
            padding=15, bgcolor=c["card_bg"], border_radius=12, border=ft.border.all(1, c["border"]) if app_state["theme"] in ["light", "accounting", "light_blue"] else None
        )

        main_view = ft.View(
            "/",
            [
                ft.Row([
                    ft.Row([
                        ft.Icon(ft.Icons.STOREFRONT, size=28, color=c["primary"]),
                        ft.Text("نظام تسيير وإدارة الديون", size=22, weight=ft.FontWeight.BOLD, color=c["text_main"])
                    ], spacing=10),
                    ft.Row([
                        theme_dropdown,
                        logout_btn
                    ], spacing=10)
                ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
                ft.Divider(color=c["border"]),
                dashboard_header,
                ft.Divider(height=10, color="transparent"),
                add_client_section,
                ft.Divider(height=15, color="transparent"),
                trans_container,   
                report_container,   
                ft.ResponsiveRow([
                    ft.Column([search_input], col={"xs": 12, "sm": 6}),
                    ft.Column([debtors_filter], col={"xs": 12, "sm": 3}),
                    ft.Column([refresh_btn], col={"xs": 6, "sm": 1.5}),
                    ft.Column([export_excel_btn], col={"xs": 6, "sm": 1.5}),
                ], alignment=ft.MainAxisAlignment.START, vertical_alignment=ft.CrossAxisAlignment.CENTER),
                ft.Divider(height=10, color="transparent"),
                ft.Text("📋 قائمة الزبائن والديون", size=18, weight=ft.FontWeight.BOLD, color=c["text_main"]),
                table_container
            ],
            bgcolor=c["bg"],
            padding=20,
            scroll=ft.ScrollMode.AUTO
        )
        page.views.append(main_view)
        page.update()

        refresh_table()
        update_dashboard_stats()

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

    # بدء التطبيق بعرض شاشة تسجيل الدخول
    show_login_view()
# --- طريقة التشغيل الصحيحة في الجذر (خارج الدالة تماماً) ---
if __name__ == "__main__":
    ft.app(target=main)
