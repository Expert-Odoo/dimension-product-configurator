{
    'name': 'Product Dimension Pricing, Made to Measure, Cut to Size, Sell by Square Meter m2, Cubic Meter m3, Kg and Linear Meter',
    'version': '20.0.1.0.3',
    'category': 'Sales/Sales',
    'summary': 'Sell made to measure and cut to size products: enter height, width and length, get the price by square meter m2, cubic meter m3, kilogram or linear meter on the sale order. Area based and volume based pricing for glass, tile, sheet metal, aluminium, timber, fabric and signage. Dimension product configurator with min and max validation.',
    'description': 'static/description/index.html',
    'author': 'expodo.fr',
    'website': 'https://expodo.fr',
    'support': 'info@expodo.fr',
    'license': 'LGPL-3',
    'depends': ['sale_management'],
    'data': [
        'security/ir.access.csv',
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
