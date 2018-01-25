from datetime import datetime, timedelta
from odoo import models, fields, api
from odoo.tools import float_compare
from odoo.exceptions import UserError

class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'

    requested_date = fields.Datetime(required=True)

    delivery_interval = fields.Selection(
            string="Delivery interval",
            selection=[
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
