from datetime import datetime, timedelta
from odoo import models, fields, api
from odoo.tools import float_compare
from odoo.exceptions import UserError
from odoo.tools import DEFAULT_SERVER_DATETIME_FORMAT

class SaleOrder(models.Model):
    _inherit = 'sale.order'

    @api.multi
    def _action_confirm(self):
        super(SaleOrder, self)._action_confirm()

        expire_dates = []

        for line in self.order_line:
            ordered_qty = line.product_uom_qty
            last_date_expected = datetime.strptime(line.requested_date, DEFAULT_SERVER_DATETIME_FORMAT)
            if (ordered_qty > 1):
                delivery_interval = float(line.delivery_interval)
                if (delivery_interval > 0.0):
                    next_delivery_interval = delivery_interval
                    for _ in range(int(ordered_qty - 1)):
                        if (delivery_interval == 3.5):
                            if (last_date_expected.weekday() == 2):  
                                next_delivery_interval = 4.0
                            elif (last_date_expected.weekday() == 6):
                                next_delivery_interval = 3.0
                        last_date_expected = last_date_expected + timedelta(next_delivery_interval)

            expire_dates.append(last_date_expected)

        if expire_dates:
            self.write({
                'validity_date': max(expire_dates).strftime(DEFAULT_SERVER_DATETIME_FORMAT)
                })

class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'

    requested_date = fields.Datetime(required=True)

    delivery_interval = fields.Selection(
            string="Delivery",
            selection=[
                ('0.0', 'Repetition'),
                ('3.5', 'Twice a week'),
                ('7.0', 'Every week'),
                ('14.0', 'Every 2 weeks'),
                ('28.0', 'Every 4 weeks')],
            default='7.0',
            required=True)

    procurement_group_id = fields.Many2one(
            'procurement.group',
            'Procurement group',
            copy=False
            )

    @api.multi
    def _prepare_procurement_values(self, group_id=False):
        vals = super(SaleOrderLine, self)._prepare_procurement_values(group_id=group_id)
        self.ensure_one()
        if self.requested_date:
            vals.update({'date_planned': self.requested_date})
        return vals

    @api.onchange('product_uom', 'product_uom_qty', 'delivery_interval')
    def product_uom_change(self):
        super(SaleOrderLine, self).product_uom_change()

    @api.multi
    def _get_display_price(self, product):
        if float(self.delivery_interval) > 0.0:
            return super(SaleOrderLine, self)._get_display_price(product)
        else:
            final_price, rule_id = self.order_id.pricelist_id.get_product_price_rule(self.product_id, self.product_uom_qty or 1.0, self.order_id.partner_id)
            context_partner = dict(self.env.context, partner_id=self.order_id.partner_id.id, date=self.order_id.date_order)
            base_price, currency_id = self.with_context(context_partner)._get_real_price_currency(self.product_id, rule_id, self.product_uom_qty, self.product_uom, self.order_id.pricelist_id.id)
            if currency_id != self.order_id.pricelist_id.currency_id.id:
                base_price = self.env['res.currency'].browse(currency_id).with_context(context_partner).compute(base_price, self.order_id.pricelist_id.currency_id)
            return base_price

    @api.multi
    def _action_launch_procurement_rule(self):
        """
        Launch procurement group run method with required/custom fields genrated by a
        sale order line. procurement group will launch '_run_move', '_run_buy' or '_run_manufacture'
        depending on the sale order line product rule.
        """
        precision = self.env['decimal.precision'].precision_get('Product Unit of Measure')
        errors = []
        for line in self:
            if line.state != 'sale' or not line.product_id.type in ('consu','product'):
                continue
            qty = 0.0
            for move in line.move_ids.filtered(lambda r: r.state != 'cancel'):
                qty += move.product_qty
            if float_compare(qty, line.product_uom_qty, precision_digits=precision) >= 0:
                continue

            group_id = line.procurement_group_id or False
            if not group_id:
                group_id = self.env['procurement.group'].create({
                     'name': '/'.join([line.order_id.name, "#{line_id}".format(line_id=line.id)]), 
                     'move_type': line.order_id.picking_policy,
                     'sale_id': line.order_id.id,
                     'partner_id': line.order_id.partner_shipping_id.id,
                    })
                line.procurement_group_id = group_id
            else:
                # In case the procurement group is already created and the order was
                # cancelled, we need to update certain values of the group.
                updated_vals = {}
                if group_id.partner_id != line.order_id.partner_shipping_id:
                    updated_vals.update({'partner_id': line.order_id.partner_shipping_id.id})
                if group_id.move_type != line.order_id.picking_policy:
                    updated_vals.update({'move_type': line.order_id.picking_policy})
                if updated_vals:
                    group_id.write(updated_vals)

            values = line._prepare_procurement_values(group_id=group_id)
            product_qty = line.product_uom_qty - qty
            try:
                self.env['procurement.group'].run(line.product_id, product_qty, line.product_uom, line.order_id.partner_shipping_id.property_stock_customer, line.name, line.order_id.name, values)
            except UserError as error:
                errors.append(error.name)
        if errors:
            raise UserError('\n'.join(errors))
        return True
