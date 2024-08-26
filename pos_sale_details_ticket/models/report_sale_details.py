from odoo import models, api, fields
from odoo.tools import AND
from datetime import timedelta
import pytz

class ReportSaleDetails(models.AbstractModel):
    _inherit = 'report.point_of_sale.report_saledetails'

    @api.model
    def get_sale_details(self, date_start=False, date_stop=False, config_ids=False, session_ids=False):
        domain = [('state', 'in', ['paid', 'invoiced', 'done'])]
        if session_ids:
            domain = AND([domain, [('session_id', 'in', session_ids)]])
        else:
            if date_start:
                date_start = fields.Datetime.from_string(date_start)
            else:
                user_tz = pytz.timezone(self.env.context.get('tz') or self.env.user.tz or 'UTC')
                today = user_tz.localize(fields.Datetime.from_string(fields.Date.context_today(self)))
                date_start = today.astimezone(pytz.timezone('UTC')).replace(tzinfo=None)

            if date_stop:
                date_stop = fields.Datetime.from_string(date_stop)
                if date_stop < date_start:
                    date_stop = date_start + timedelta(days=1, seconds=-1)
            else:
                date_stop = date_start + timedelta(days=1, seconds=-1)

            domain = AND([domain,
                          [('date_order', '>=', fields.Datetime.to_string(date_start)),
                           ('date_order', '<=', fields.Datetime.to_string(date_stop))]
                          ])

            if config_ids:
                domain = AND([domain, [('config_id', 'in', config_ids)]])

        orders = self.env['pos.order'].search(domain)

        if config_ids:
            config_currencies = self.env['pos.config'].search([('id', 'in', config_ids)]).mapped('currency_id')
        else:
            config_currencies = self.env['pos.session'].search([('id', 'in', session_ids)]).mapped('config_id.currency_id')

        if config_currencies and all(i == config_currencies.ids[0] for i in config_currencies.ids):
            user_currency = config_currencies[0]
        else:
            user_currency = self.env.company.currency_id

        total = 0.0
        products_sold = {}
        taxes = {}
        refund_done = {}
        refund_taxes = {}
        for order in orders:
            if user_currency != order.pricelist_id.currency_id:
                total += order.pricelist_id.currency_id._convert(
                    order.amount_total, user_currency, order.company_id, order.date_order or fields.Date.today())
            else:
                total += order.amount_total
            currency = order.session_id.currency_id

            for line in order.lines:
                if line.qty >= 0:
                    products_sold, taxes = self._get_products_and_taxes_dict(order, line, products_sold, taxes, currency)
                else:
                    refund_done, refund_taxes = self._get_products_and_taxes_dict(order, line, refund_done, refund_taxes, currency)

        payment_ids = self.env["pos.payment"].search([('pos_order_id', 'in', orders.ids)]).ids
        if payment_ids:
            self.env.cr.execute("""
                SELECT method.id as id, payment.session_id as session, COALESCE(method.name->>%s, method.name->>'en_US') as name, method.is_cash_count as cash, 
                     sum(amount) total, method.journal_id journal_id
                FROM pos_payment AS payment,
                     pos_payment_method AS method
                WHERE payment.payment_method_id = method.id
                    AND payment.id IN %s
                GROUP BY method.name, method.is_cash_count, payment.session_id, method.id, journal_id
            """, (self.env.lang, tuple(payment_ids),))
            payments = self.env.cr.dictfetchall()
        else:
            payments = []

        configs = []
        sessions = []
        if config_ids:
            configs = self.env['pos.config'].search([('id', 'in', config_ids)])
            if session_ids:
                sessions = self.env['pos.session'].search([('id', 'in', session_ids)])
            else:
                sessions = self.env['pos.session'].search([('config_id', 'in', configs.ids), ('start_at', '>=', date_start), ('stop_at', '<=', date_stop)])
        else:
            sessions = self.env['pos.session'].search([('id', 'in', session_ids)])
            for session in sessions:
                configs.append(session.config_id)

        for payment in payments:
            payment['count'] = False

        for session in sessions:
            cash_counted = 0
            if session.cash_register_balance_end_real:
                cash_counted = session.cash_register_balance_end_real

            for payment in payments:
                account_payments = self.env['account.payment'].search([('pos_session_id', '=', session.id)])
                if payment['session'] == session.id:
                    if not payment['cash']:
                        for account_payment in account_payments:
                            if payment['id'] == account_payment.pos_payment_method_id.id:
                                payment['final_count'] = payment['total']
                                payment['money_counted'] = account_payment.amount
                                payment['money_difference'] = payment['money_counted'] - payment['final_count']
                                payment['cash_moves'] = []
                                if payment['money_difference'] > 0:
                                    move_name = 'Difference observed during the counting (Profit)'
                                    payment['cash_moves'] = [{'name': move_name, 'amount': payment['money_difference']}]
                                elif payment['money_difference'] < 0:
                                    move_name = 'Difference observed during the counting (Loss)'
                                    payment['cash_moves'] = [{'name': move_name, 'amount': payment['money_difference']}]
                                payment['count'] = True
                                break
                    else:
                        previous_session = self.env['pos.session'].search([('id', '<', session.id), ('state', '=', 'closed'), ('config_id', '=', session.config_id.id)], limit=1)
                        payment['final_count'] = payment['total'] + previous_session.cash_register_balance_end_real + session.cash_real_transaction
                        payment['money_counted'] = cash_counted
                        payment['money_difference'] = payment['money_counted'] - payment['final_count']
                        cash_moves = self.env['account.bank.statement.line'].search([('pos_session_id', '=', session.id)])
                        cash_in_out_list = []
                        cash_in_count = 0
                        cash_out_count = 0
                        if session.cash_register_balance_start > 0:
                            cash_in_out_list.append({
                                'name': 'Cash Opening',
                                'amount': session.cash_register_balance_start,
                            })
                        for cash_move in cash_moves:
                            if cash_move.amount > 0:
                                cash_in_count += 1
                                name = f'Cash in {cash_in_count}'
                            else:
                                cash_out_count += 1
                                name = f'Cash out {cash_out_count}'
                            if cash_move.move_id.journal_id.id == payment['journal_id']:
                                cash_in_out_list.append({
                                    'name': cash_move.payment_ref if cash_move.payment_ref else name,
                                    'amount': cash_move.amount
                                })
                        payment['cash_moves'] = cash_in_out_list
                        payment['count'] = True

        products = []
        refund_products = []
        for order_id, product_list in products_sold.items():
            order_dict = {
                'order_id': order_id.id,
                'order_name': order_id.name,
                'products': sorted([{
                    'product_id': product.id,
                    'product_name': product.name,
                    'code': product.default_code,
                    'quantity': qty,
                    'price_unit': price_unit,
                    'discount': discount,
                    'uom': product.uom_id.name
                } for (product, price_unit, discount), qty in product_list.items()], key=lambda l: l['product_name']),
            }
            products.append(order_dict)
        products = sorted(products, key=lambda l: str(l['order_name']))

        for order_id, product_list in refund_done.items():
            order_dict = {
                'order_id': order_id.id,
                'order_name': order_id.name,
                'products': sorted([{
                    'product_id': product.id,
                    'product_name': product.name,
                    'code': product.default_code,
                    'quantity': qty,
                    'price_unit': price_unit,
                    'discount': discount,
                    'uom': product.uom_id.name
                } for (product, price_unit, discount), qty in product_list.items()], key=lambda l: l['product_name']),
            }
            refund_products.append(order_dict)
        refund_products = sorted(refund_products, key=lambda l: str(l['order_name']))

        return {
            'currency_precision': user_currency.decimal_places,
            'total_paid': total,
            'payments': payments,
            'company_name': self.env.company.name,
            'taxes': sorted([{'tax_name': k, 'tax_amount': v} for k, v in taxes.items()], key=lambda l: l['tax_name']),
            'refund_tax_details': sorted([{'tax_name': k, 'tax_amount': v} for k, v in refund_taxes.items()], key=lambda l: l['tax_name']),
            'products': products,
            'refund_products': refund_products,
        }

    def _get_products_and_taxes_dict(self, order, line, products, taxes, currency):
        key1 = order
        key2 = (line.product_id, line.price_unit, line.discount)
        products.setdefault(key1, {})
        products[key1].setdefault(key2, 0.0)
        products[key1][key2] += line.qty

        if not line.tax_ids_after_fiscal_position:
            return products, taxes
        line_taxes = line.tax_ids_after_fiscal_position.compute_all(
            line.price_unit * (100.0 - line.discount) / 100.0,
            currency, line.qty, product=line.product_id, partner=line.order_id.partner_id or False
        )['taxes']
        for tax in line_taxes:
            taxes.setdefault(tax['name'], 0.0)
            taxes[tax['name']] += tax['amount']
        return products, taxes