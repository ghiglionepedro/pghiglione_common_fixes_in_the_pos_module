from odoo import models, fields

class ReportSaleDetailsInherited(models.AbstractModel):
    _inherit = 'report.point_of_sale.report_saledetails'

    def get_sale_details(self, date_start=False, date_stop=False, config_ids=False, session_ids=False):
        # Llamar al método original para obtener los detalles de ventas
        result = super(ReportSaleDetailsInherited, self).get_sale_details(date_start, date_stop, config_ids, session_ids)
        
        # Añadir el número de ticket/factura a cada producto vendido
        for product_category in result.get('products', []):
            for product in product_category.get('products', []):
                product_id = product['product_id']
                order_line = self.env['pos.order.line'].search([('product_id', '=', product_id)], limit=1)
                product['ticket_number'] = order_line.order_id.pos_reference if order_line else ''

        # Añadir el número de ticket/factura a cada pago
        for payment in result.get('payments', []):
            payment_id = payment['id']
            pos_payment = self.env['pos.payment'].search([('id', '=', payment_id)], limit=1)
            payment['ticket_number'] = pos_payment.pos_order_id.pos_reference if pos_payment else ''
        
        return result