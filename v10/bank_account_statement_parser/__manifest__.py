# -*- encoding: utf-8 -*-
# 2018 Léo-Paul Géneau

{
    'name': "Translation.ie Bank Statements",
    'category': 'Accounting & Finance',
    'summary': 'Import Bank Statements from Translation.ie',
    'website': "https://www.translation.ie",
    'version': '12.0.0.1',
    'author': "Translation.ie",
    'description': """
This module allows you to import the CSV Files from Translation.ie in Odoo: they are parsed and stored in human readable format in
Accounting / Bank and Cash / Bank Statements.
    """,

    'depends': ['account_bank_statement_import'],
    'external_dependencies': {
        'python': [
            'unicodecsv',
        ]
    },
    'data': [
        'views/account_bank_statement_import_view.xml',
        'views/bank_statement_view.xml',
        'views/suggestions_view.xml',
        'views/duplicates_view.xml',
    ],
    'installable': True, 
    'application': False,
}