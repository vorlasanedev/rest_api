{
    'name': 'REST API xRPC CRUD',
    'version': '18.0.1.1.0',
    'summary': 'Generic REST API with API Key Authentication (Odoo 18)',
    'category': 'Tools',
    'author': 'Soulivanh',
    'license': 'LGPL-3',
    'depends': ['base', 'web'],
    'data': [
        'security/ir.model.access.csv',
        'views/res_users_views.xml',
    ],
    'installable': True,
    'application': True,
}
