{
    'name': 'POS Sale Details by Ticket',
    'version': '16.0',
    'category': 'Point Of Sale',
    'author': 'Pedro Matias Ghiglione',
    'license': 'LGPL-3',
    'summary': 'Customize the POS Sale Details report to group products by ticket.',
    'description': 'This module customizes the POS Sale Details report to group products by ticket instead of by category.',
    'website': 'http://naolhospital.com',
    'sequence': 7,
    'depends': ['pos_daily_sales_reports'],
    'data': [
        'views/point_of_sale_view.xml'
    ],
    'qweb': [
    ],
    'demo': [],
    'application': False,
    'installable':True,
    'auto_install':False,
}

