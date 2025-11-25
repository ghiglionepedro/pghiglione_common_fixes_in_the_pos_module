from odoo import models, fields

class ReportSaleDetailsInherited(models.AbstractModel):
	_inherit = 'report.point_of_sale.report_saledetails'

	def _get_products_and_taxes_dict(self, line, products, taxes, currency):
	    key1 = line.product_id.product_tmpl_id.pos_categ_id.name
	    key2 = (line.product_id, line.price_unit, line.discount)
	    
	    # Añadir campos para la venta y factura
	    product_info = products.setdefault(key1, {}).setdefault(key2, {'quantity': 0.0, 'sales': [], 'invoices': []})
	    product_info['quantity'] += line.qty
	    
	    # Añadir información de la venta
	    sale_info = {
	        'sale_id': line.order_id.id,
	        'sale_name': line.order_id.name,
	        'sale_date': line.order_id.date_order,
	        'sale_amount': line.price_subtotal_incl,
	    }
	    if sale_info not in product_info['sales']:
	        product_info['sales'].append(sale_info)
	    
	    # Buscar las facturas relacionadas con el pedido
	    invoice_ids = self.env['account.move'].search([
	        ('pos_order_ids', 'in', line.order_id.id)  # Ajusta esto según el campo correcto
	    ]).ids

	    if invoice_ids:
	        invoices = self.env['account.move'].browse(invoice_ids)
	        for invoice in invoices:
	            invoice_info = {
	                'invoice_id': invoice.id,
	                'invoice_name': invoice.name,
	                'invoice_date': invoice.invoice_date,
	                'invoice_amount': invoice.amount_total,
	            }
	            if invoice_info not in product_info['invoices']:
	                product_info['invoices'].append(invoice_info)
	    
	    # Actualizar el diccionario de impuestos
	    if line.tax_ids_after_fiscal_position:
	        line_taxes = line.tax_ids_after_fiscal_position.sudo().compute_all(
	            line.price_unit * (1 - (line.discount or 0.0) / 100.0), currency, line.qty, product=line.product_id, partner=line.order_id.partner_id or False)
	        for tax in line_taxes['taxes']:
	            taxes.setdefault(tax['id'], {'name': tax['name'], 'tax_amount': 0.0, 'base_amount': 0.0})
	            taxes[tax['id']]['tax_amount'] += tax['amount']
	            taxes[tax['id']]['base_amount'] += tax['base']
	    else:
	        taxes.setdefault(0, {'name': _('No Taxes'), 'tax_amount': 0.0, 'base_amount': 0.0})
	        taxes[0]['base_amount'] += line.price_subtotal_incl

	    return products, taxes
