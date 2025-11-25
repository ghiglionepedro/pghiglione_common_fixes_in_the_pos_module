# -*- coding: utf-8 -*-


from odoo import fields, models, api, _
import base64
import os
from datetime import datetime,date
from datetime import *
from io import BytesIO
import xlsxwriter
from odoo import fields, models, api, _
from odoo.exceptions import ValidationError
from xlsxwriter.utility import xl_col_to_name
from pytz import timezone
from odoo.tools import config
from odoo.tools import format_datetime, format_date
import string
import random
from num2words import num2words
from dateutil.relativedelta import relativedelta
from odoo.tools.misc import xlwt
import pytz
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from reportlab.lib import colors
from reportlab.platypus import Table, TableStyle



class PosExcel(models.TransientModel):
    _inherit = "pos.details.wizard"

    file = fields.Binary()

    def print_excel_report(self):
        file_name = _('Product.xlsx')
        fp = BytesIO()
        workbook = xlsxwriter.Workbook(fp)
        worksheet = workbook.add_worksheet('Product')
        worksheet_payment = workbook.add_worksheet('Payment')
        worksheet_tax = workbook.add_worksheet('Tax')
        worksheet_total = workbook.add_worksheet('Final Totals')

        session_total_formate = workbook.add_format({'align': 'center',
                                                    'bold': True,
                                                    'valign': 'vcenter',
                                                    'size': 10,
                                                    'bg_color': 'gray',
                                                    'text_wrap': True})
        session_total_formate.set_border()
        session_total_formate1 = workbook.add_format({'align': 'center'})
        session_total_formate2 = workbook.add_format({'align': 'center',
                                                    'bold': True,
                                                    'valign': 'vcenter',
                                                    'size': 10,
                                                    'color': 'green',
                                                    'text_wrap': True})
        money_format = workbook.add_format({
            'num_format': '"$"#,##0.00',  # formato contable
            'align': 'right'
        })


        # Merge header cells for Product worksheet
        worksheet.merge_range('A1:G5', '%s\nSales Details\n%s - %s' % (self.env.user.company_id.name, self.start_date, self.end_date), session_total_formate2)
        
        # Product worksheet headers
        row = 5
        worksheet.write(row, 0, 'Sale No', session_total_formate)
        worksheet.set_column('A:A', 20)
        worksheet.set_row(5, 30)
        worksheet.write(row, 1, 'Product', session_total_formate)
        worksheet.set_column('B:B', 30)
        worksheet.write(row, 2, 'Qty', session_total_formate)
        worksheet.set_column('C:C', 10)
        worksheet.write(row, 3, 'Unit Price', session_total_formate)
        worksheet.set_column('D:D', 10)
        worksheet.write(row, 4, 'Discounts', session_total_formate)
        worksheet.set_column('E:E', 10)
        worksheet.write(row, 5, 'Comercial', session_total_formate)
        worksheet.set_column('F:F', 20)
        worksheet.write(row, 6, 'Subtotal (Discounts Deducted)', session_total_formate)
        worksheet.set_column('G:G', 20)

        # Payment worksheet headers
        worksheet_payment.write(3, 0, 'Date', session_total_formate)
        worksheet_payment.set_column('A:A', 10)
        worksheet_payment.set_row(3, 30)
        worksheet_payment.write(3, 1, 'Sale No', session_total_formate)
        worksheet_payment.set_column('B:B', 20)
        worksheet_payment.write(3, 2, 'Payment Method', session_total_formate)
        worksheet_payment.set_column('C:C', 30)
        worksheet_payment.write(3, 3, 'Amount', session_total_formate)
        worksheet_payment.set_column('D:D', 20)

        # Tax worksheet headers
        worksheet_tax.write(3, 0, 'No', session_total_formate)
        worksheet_tax.set_column('A:A', 10)
        worksheet_tax.set_row(3, 30)
        worksheet_tax.write(3, 1, 'Sale No', session_total_formate)
        worksheet_tax.set_column('B:B', 20)
        worksheet_tax.write(3, 2, 'Tax Name', session_total_formate)
        worksheet_tax.set_column('C:C', 30)
        worksheet_tax.write(3, 3, 'Tax Amount', session_total_formate)
        worksheet_tax.set_column('D:D', 30)
        worksheet_tax.write(3, 4, 'Base Amount', session_total_formate)
        worksheet_tax.set_column('E:E', 30)

        configs = self.pos_config_ids
        user_tz = pytz.timezone(self.env.context.get('tz') or self.env.user.tz or 'UTC')
        today = user_tz.localize(fields.Datetime.from_string(fields.Date.context_today(self)))
        today = today.astimezone(pytz.timezone('UTC'))
        if self.start_date:
            date_start = fields.Datetime.from_string(self.start_date)
        else:
            date_start = today
        if self.end_date:
            date_stop = fields.Datetime.from_string(self.end_date)
        else:
            date_stop = today + timedelta(days=1, seconds=-1)
        date_stop = max(date_stop, date_start)
        date_start = fields.Datetime.to_string(date_start)
        date_stop = fields.Datetime.to_string(date_stop)

        orders = self.env['pos.order'].search([
            ('date_order', '>=', date_start),
            ('date_order', '<=', date_stop),
            ('state', 'in', ['paid', 'invoiced', 'done']),
            ('config_id', 'in', configs.ids)
        ])

        user_currency = self.env.user.company_id.currency_id
        total = 0.0
        products_sold = {}
        taxes = {}
        payments = []
        product_data = []
        tax_data = []

        for order in orders:
            if user_currency != order.pricelist_id.currency_id:
                total += order.pricelist_id.currency_id._convert(
                    order.amount_total, user_currency, order.company_id, order.date_order or fields.Date.today())
            else:
                total += order.amount_total
            currency = order.session_id.currency_id
            for line in order.lines:
                key = (line.product_id, line.price_unit, line.discount)
                products_sold.setdefault(key, 0.0)
                products_sold[key] += line.qty
                sub_total_disc_deducted = (line.qty * line.price_unit) * (1 - (line.discount or 0.0) / 100.0)
                product_data.append({
                    'sale_no': order.name,
                    'product_name': line.product_id.name,
                    'quantity': line.qty,
                    'price_unit': line.price_unit,
                    'discount': line.discount,
                    'comercial': line.user_id.name,
                    'sub_total_disc_deducted': sub_total_disc_deducted
                })
                if line.tax_ids_after_fiscal_position:
                    line_taxes = line.tax_ids_after_fiscal_position.compute_all(line.price_unit * (1 - (line.discount or 0.0) / 100.0), currency, line.qty, product=line.product_id, partner=line.order_id.partner_id or False)
                    for tax in line_taxes['taxes']:
                        tax_data.append({
                            'sale_no': order.name,
                            'tax_name': tax['name'],
                            'tax_amount': tax['amount'],
                            'base_amount': tax['base']
                        })
                else:
                    tax_data.append({
                        'sale_no': order.name,
                        'tax_name': _('No Taxes'),
                        'tax_amount': 0.0,
                        'base_amount': line.price_subtotal_incl
                    })

        payment_ids = self.env["pos.payment"].search([('pos_order_id', 'in', orders.ids)]).ids
        if payment_ids:
            self.env.cr.execute("""
                SELECT payment.pos_order_id, COALESCE(method.name->>%s, method.name->>'en_US') p_name, sum(amount) total, payment.payment_date AS date
                FROM pos_payment AS payment,
                    pos_payment_method AS method
                WHERE payment.payment_method_id = method.id
                    AND payment.id IN %s
                GROUP BY payment.pos_order_id, method.name, payment.payment_date
            """, (self.env.lang, tuple(payment_ids),))
            payments = self.env.cr.dictfetchall()
        else:
            payments = []

        # Write product data to worksheet
        row = 6
        totals = 0.0
        for data in product_data:
            worksheet.write(row, 0, data['sale_no'], session_total_formate1)
            worksheet.write(row, 1, data['product_name'], session_total_formate1)
            worksheet.write(row, 2, data['quantity'], session_total_formate1)
            worksheet.write(row, 3, data['price_unit'], money_format)
            worksheet.write(row, 4, data['discount'], money_format)
            worksheet.write(row, 5, data['comercial'], session_total_formate1)
            worksheet.write(row, 6, data['sub_total_disc_deducted'],money_format)
            totals += data['sub_total_disc_deducted']
            row += 1
        
        worksheet.write(row + 2, 5, 'Total without taxes')
        worksheet.write(row + 2, 6, totals,money_format)

        # Write payment data to worksheet
        row = 4
        totals_payment = 0.0
        for payment in payments:
            order_name = self.env['pos.order'].browse(payment['pos_order_id']).name  # Obtener el nombre de la orden
            #worksheet_payment.write(row, 0, row - 3, session_total_formate1)
            worksheet_payment.write(row, 0, format_datetime(self.env, payment['date'], tz=user_tz, dt_format='d-M-Y H:M'), session_total_formate1)
            worksheet_payment.write(row, 1, order_name, session_total_formate1)  # Escribir el nombre de la orden
            worksheet_payment.write(row, 2, payment['p_name'], session_total_formate1)
            worksheet_payment.write(row, 3, payment['total'], money_format)
            totals_payment += payment.get('total')
            row += 1
        worksheet_payment.write(row+2,2,'Total payments',session_total_formate1)
        worksheet_payment.write(row+2,3, totals_payment,money_format) 
        # Write tax data to worksheet
        row = 4
        totals_taxs = 0.0
        for tax in tax_data:
            worksheet_tax.write(row, 0, row - 3, session_total_formate1)
            worksheet_tax.write(row, 1, tax['sale_no'], session_total_formate1)
            worksheet_tax.write(row, 2, tax['tax_name'], session_total_formate1)
            worksheet_tax.write(row, 3, tax['tax_amount'], money_format)
            worksheet_tax.write(row, 4, tax['base_amount'], money_format)
            totals_taxs += tax.get('tax_amount')
            row += 1
        worksheet_tax.write(row+2,2,'Total tax',session_total_formate1)
        worksheet_tax.write(row+2,3, totals_taxs,money_format)

        # Write final totals to worksheet
        row = 3
        worksheet_total.merge_range('A4:D6', total, session_total_formate)

        workbook.close()

        # Save and prepare the file for download
        file_download = base64.b64encode(fp.getvalue())
        fp.close()
        
        self.file = file_download
        
        return {
            'name': 'Product',
            'type': 'ir.actions.act_url',
            'url': '/web/content/%s/%d/file/%s?download=false' % (self._name, self.id, file_name),
        }


    def print_pdf_report(self):
        # Crear un buffer para guardar el PDF en memoria
        buffer = BytesIO()
        pdf_canvas = canvas.Canvas(buffer, pagesize=letter)
        width, height = letter  # Tamaño de la página

        # Encabezado general del reporte
        pdf_canvas.setFont("Helvetica-Bold", 16)
        pdf_canvas.drawString(50, height - 50, "Sales Details Report")
        pdf_canvas.setFont("Helvetica", 12)
        pdf_canvas.drawString(50, height - 80, f"Company: {self.env.user.company_id.name}")
        pdf_canvas.drawString(50, height - 100, f"Date Range: {self.start_date} - {self.end_date}")

        # Hojas simuladas en el PDF (una sección por hoja de Excel)
        y_start = height - 150  # Coordenada Y inicial

        # Hacer hoja 1: Detalles de productos
        y_start = self._add_product_details_section(pdf_canvas, y_start, width, height)

        # Hacer hoja 2: Payment
        pdf_canvas.showPage()  # Nueva página
        y_start = self._add_payment_section(pdf_canvas, width, height)

        # Hacer hoja 3: Tax
        pdf_canvas.showPage()  # Nueva página
        y_start = self._add_tax_section(pdf_canvas, width, height)

        # Hacer hoja 4: Final Totals
        pdf_canvas.showPage()  # Nueva página
        y_start = self._add_final_totals_section(pdf_canvas, width, height)

        # Finalizar el PDF
        pdf_canvas.save()
        buffer.seek(0)

        # Convertir a base64 para almacenarlo en un campo binario
        pdf_data = buffer.getvalue()
        buffer.close()
        self.file = base64.b64encode(pdf_data)

        return {
            'name': 'Product PDF',
            'type': 'ir.actions.act_url',
            'url': '/web/content/%s/%d/file/%s?download=false' % (self._name, self.id, 'Sales Details.pdf'),
        }


    # Función para la sección de detalles de productos
    def _add_product_details_section(self, pdf_canvas, y_start, width, height):
        pdf_canvas.setFont("Helvetica-Bold", 14)
        pdf_canvas.drawString(50, y_start, "Product Details")
        y_start -= 30

        # Encabezados de la tabla
        headers = ["No", "Product", "Qty", "Unit Price", "Discount", "UOM", "Subtotal"]
        data = [headers]

        # Obtener datos de productos
        products = self.get_products_data()  # Supón que ya tienes esta función implementada
        total = 0
        for idx, product in enumerate(products, start=1):
            sub_total = (product['quantity'] * product['price_unit']) * (1 - product['discount'] / 100)
            total += sub_total
            data.append([
                str(idx),
                product['product_name'],
                str(product['quantity']),
                f"{product['price_unit']:.2f}",
                f"{product['discount']:.2f}%",
                product['uom'],
                f"{sub_total:.2f}",
            ])

        # Dibujar la tabla
        table = Table(data, colWidths=[50, 150, 50, 80, 80, 80, 100])
        table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 10),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 8),
            ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
            ('GRID', (0, 0), (-1, -1), 1, colors.black),
        ]))

        table.wrapOn(pdf_canvas, width, height)
        table.drawOn(pdf_canvas, 50, y_start - len(data) * 20)

        return y_start - len(data) * 20 - 40


    def _add_payment_section(self, pdf_canvas, width, height):
        y_position = height - 300  # Ajusta según sea necesario
        pdf_canvas.setFont("Helvetica-Bold", 12)
        pdf_canvas.drawString(50, y_position, "Payment Details")
        y_position -= 20

        payments = self.get_payments_data()
        pdf_canvas.setFont("Helvetica", 10)

        if not payments:
            pdf_canvas.drawString(50, y_position, "No payment data available.")
            return y_position - 20

        # Agrega un encabezado para la tabla
        pdf_canvas.drawString(50, y_position, "No.")
        pdf_canvas.drawString(100, y_position, "Payment Method")
        pdf_canvas.drawString(300, y_position, "Total Amount")
        y_position -= 20

        # Recorre los datos de pagos y dibuja cada fila
        for idx, payment in enumerate(payments, start=1):
            pdf_canvas.drawString(50, y_position, str(idx))  # Número
            pdf_canvas.drawString(100, y_position, payment['payment_method'])  # Método de pago
            pdf_canvas.drawString(300, y_position, f"{payment['total_amount']:.2f}")  # Total
            y_position -= 20

        return y_position


# Implementa funciones similares para taxes y final totals



    def get_products_data(self):
        orders = self.env['pos.order'].search([
            ('date_order', '>=', self.start_date),
            ('date_order', '<=', self.end_date),
            ('state', 'in', ['paid', 'invoiced', 'done']),
            ('config_id', 'in', self.pos_config_ids.ids)
        ])

        products_sold = {}
        for order in orders:
            for line in order.lines:
                key = (line.product_id, line.price_unit, line.discount)
                products_sold.setdefault(key, 0.0)
                products_sold[key] += line.qty

        products = [{
            'product_name': product.name,
            'quantity': qty,
            'price_unit': price_unit,
            'discount': discount,
            'uom': product.uom_id.name,
        } for (product, price_unit, discount), qty in products_sold.items()]
    
        return products


    def get_payments_data(self):
        """
        Este método obtiene los datos de pagos relacionados con los pedidos de POS
        dentro del rango de fechas seleccionado.
        """
        orders = self.env['pos.order'].search([
            ('date_order', '>=', self.start_date),
            ('date_order', '<=', self.end_date),
            ('state', 'in', ['paid', 'invoiced', 'done']),
            ('config_id', 'in', self.pos_config_ids.ids)
        ])

        payment_ids = self.env['pos.payment'].search([
            ('pos_order_id', 'in', orders.ids)
        ]).ids

        if payment_ids:
            self.env.cr.execute("""
                SELECT 
                    COALESCE(method.name->>%s, method.name->>'en_US') AS payment_method,
                    SUM(amount) AS total_amount
                FROM pos_payment AS payment
                JOIN pos_payment_method AS method ON payment.payment_method_id = method.id
                WHERE payment.id IN %s
                GROUP BY method.name
            """, (self.env.lang, tuple(payment_ids)))
        
            payments = self.env.cr.dictfetchall()
        else:
            payments = []

        return payments


    def _add_tax_section(self, pdf_canvas, width, height):
        """
        Agrega la sección de detalles de impuestos al PDF.
        """
        y_position = height - 500  # Ajusta esta posición según tu diseño
        pdf_canvas.setFont("Helvetica-Bold", 12)
        pdf_canvas.drawString(50, y_position, "Tax Details")
        y_position -= 20

        taxes = self.get_taxes_data()  # Implementa o utiliza esta función para obtener los datos de impuestos.
        pdf_canvas.setFont("Helvetica", 10)

        if not taxes:
            pdf_canvas.drawString(50, y_position, "No tax data available.")
            return y_position - 20

        # Encabezados de la tabla
        pdf_canvas.drawString(50, y_position, "No.")
        pdf_canvas.drawString(100, y_position, "Tax Name")
        pdf_canvas.drawString(300, y_position, "Tax Amount")
        pdf_canvas.drawString(450, y_position, "Base Amount")
        y_position -= 20

        # Recorre los datos de impuestos y dibuja cada fila
        for idx, tax in enumerate(taxes, start=1):
            pdf_canvas.drawString(50, y_position, str(idx))  # Número
            pdf_canvas.drawString(100, y_position, tax['name'])  # Nombre del impuesto
            pdf_canvas.drawString(300, y_position, f"{tax['tax_amount']:.2f}")  # Monto del impuesto
            pdf_canvas.drawString(450, y_position, f"{tax['base_amount']:.2f}")  # Base imponible
            y_position -= 20

        return y_position



    def get_taxes_data(self):
        """
        Retorna una lista de diccionarios con los datos de impuestos.
        """
        taxes = {}
        orders = self.env['pos.order'].search([
            ('date_order', '>=', self.start_date),
            ('date_order', '<=', self.end_date),
            ('state', 'in', ['paid', 'invoiced', 'done']),
        ])
        for order in orders:
            for line in order.lines:
                if line.tax_ids_after_fiscal_position:
                    line_taxes = line.tax_ids_after_fiscal_position.compute_all(
                        line.price_unit * (1 - (line.discount or 0.0) / 100.0),
                        order.currency_id,
                        line.qty,
                        product=line.product_id,
                        partner=order.partner_id or False
                    )
                    for tax in line_taxes['taxes']:
                        tax_id = tax['id']
                        if tax_id not in taxes:
                            taxes[tax_id] = {
                                'name': tax['name'],
                                'tax_amount': 0.0,
                                'base_amount': 0.0
                            }
                        taxes[tax_id]['tax_amount'] += tax['amount']
                        taxes[tax_id]['base_amount'] += tax['base']
        return list(taxes.values())



    def _add_final_totals_section(self, pdf_canvas, width, height):
        """
        Agrega la sección de totales finales al PDF.
        """
        y_position = height - 700  # Ajusta la posición según sea necesario
        pdf_canvas.setFont("Helvetica-Bold", 12)
        pdf_canvas.drawString(50, y_position, "Final Totals")
        y_position -= 20

        total_amount = self.get_total_amount()  # Implementa esta función para obtener el monto total
        total_taxes = self.get_total_taxes()  # Implementa esta función para obtener los impuestos totales
        total_discount = self.get_total_discount()  # Implementa esta función para obtener los descuentos totales
        final_total = total_amount + total_taxes - total_discount

        pdf_canvas.setFont("Helvetica", 10)

        # Muestra los totales en el PDF
        pdf_canvas.drawString(50, y_position, f"Total Amount: {total_amount:.2f}")
        y_position -= 20
        pdf_canvas.drawString(50, y_position, f"Total Taxes: {total_taxes:.2f}")
        y_position -= 20
        pdf_canvas.drawString(50, y_position, f"Total Discount: {total_discount:.2f}")
        y_position -= 20
        pdf_canvas.drawString(50, y_position, f"Final Total: {final_total:.2f}")
        y_position -= 20

        return y_position


    def get_total_amount(self):
        """
        Calcula y devuelve el monto total de la venta.
        """
        total = 0.0
        orders = self.env['pos.order'].search([
            ('date_order', '>=', self.start_date),
            ('date_order', '<=', self.end_date),
            ('state', 'in', ['paid', 'invoiced', 'done']),
        ])
        for order in orders:
            total += order.amount_total
        return total

    def get_total_taxes(self):
        """
        Calcula y devuelve el total de impuestos.
        """
        total_taxes = 0.0
        orders = self.env['pos.order'].search([
            ('date_order', '>=', self.start_date),
            ('date_order', '<=', self.end_date),
            ('state', 'in', ['paid', 'invoiced', 'done']),
        ])
        for order in orders:
            total_taxes += order.amount_tax
        return total_taxes

    def get_total_discount(self):
        """
        Calcula y devuelve el total de descuentos.
        """
        total_discount = 0.0
        orders = self.env['pos.order'].search([
            ('date_order', '>=', self.start_date),
            ('date_order', '<=', self.end_date),
            ('state', 'in', ['paid', 'invoiced', 'done']),
        ])
        for order in orders:
             total_discount += order.amount_total - order.amount_tax
        return total_discount
