{
    'name': 'Dimension Product Configurator | Square Meter & Volume Pricing | Height \u00d7 Width',
    'version': '18.0.1.0.1',
    'category': 'Sales/Sales',
    'summary': 'Sell products by dimensions: enter height, width and depth, get the price per m\u00b2, m\u00b3, kg or linear meter instantly in Odoo Sales.',
    'description': 'static/description/index.html',
    'author': 'expodo.fr',
    'website': 'https://expodo.fr',
    'support': 'info@expodo.fr',
    'license': 'LGPL-3',
    'depends': ['sale_management'],
    'data': [
        'security/ir.model.access.csv',
        'views/dimension_product_views.xml',
        'views/dimension_configuration_views.xml',
        'views/dimension_configurator_views.xml',
        'views/dimension_line_selector_views.xml',
        'views/sale_order_views.xml',
        'views/menu.xml',
        'report/sale_report_inherit.xml',
    ],
    'demo': [
        'demo/demo_data.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'dimension_product_configurator/static/src/css/pricing_mode.css',
        ],
    },
    'images': ['static/description/banner.png', 'static/description/icon.png'],
    'installable': True,
    'application': True,
}
