{
        'name': 'Blanket Sale Order Line',
        'version': '1.0',
        'category': 'Sales',
        'summary': 'Sales Order Line, Blanket Order',
        'depends': [
            'sale_stock'
            ],
        'data': [
            'views/sale_order_view.xml',
            'views/stock_move_view.xml',
            'views/stock_picking_view.xml',
            'report/sale_report_templates.xml'
            ],
        'installable': True,
        }
