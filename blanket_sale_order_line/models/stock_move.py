from datetime import datetime, timedelta
from odoo import models, fields, api
from odoo.tools import DEFAULT_SERVER_DATETIME_FORMAT

class StockMove(models.Model):
    _inherit = "stock.move"

    def _assign_picking(self):
        result = super(StockMove, self)._assign_picking()
        if result:
            Picking = self.env['stock.picking']
            for move in self:
                ordered_qty = move.product_uom_qty
                sale_order_line = move.sale_line_id
                if (ordered_qty > 1 and sale_order_line):
                    delivery_interval = float(sale_order_line.delivery_interval)
                    if (delivery_interval > 0.0):
                        picking = Picking.search([
                            ('group_id', '=', move.group_id.id),
                            ('location_id', '=', move.location_id.id),
                            ('location_dest_id', '=', move.location_dest_id.id),
                            ('picking_type_id', '=', move.picking_type_id.id),
                            ('printed', '=', False),
                            ('state', 'in', ['draft', 'confirmed', 'waiting', 'partially_available', 'assigned'])], limit=1)
                        if picking:
                            move.write({'product_uom_qty': 1})
                            next_delivery_interval = delivery_interval
                            for _ in range(int(ordered_qty - 1)):
                                last_date_expected = datetime.strptime(move.date_expected, DEFAULT_SERVER_DATETIME_FORMAT)
                                if (delivery_interval == 3.5):
                                    if (last_date_expected.weekday() == 2):  
                                        next_delivery_interval = 4.0
                                    elif (last_date_expected.weekday() == 6):
                                        next_delivery_interval = 3.0
                                next_date_expected = last_date_expected + timedelta(next_delivery_interval)
                                backorder_picking = picking.copy({
                                    'name': '/',
                                    'move_lines': [],
                                    'move_line_ids': [],
                                    'backorder_id': picking.id
                                    })
                                backorder_move = move.copy({
                                    'date_expected': next_date_expected.strftime(DEFAULT_SERVER_DATETIME_FORMAT),
                                    'picking_id': backorder_picking.id
                                    })
                                backorder_move._action_confirm()
                                picking = backorder_picking
                                move = backorder_move
            return True
        else:
            return False
