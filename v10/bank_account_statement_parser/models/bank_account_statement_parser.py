# -*- encoding: utf-8 -*-
# 2018 Léo-Paul Géneau

import logging
import base64
import io
import hashlib
import unicodedata


import dateutil.parser
from odoo import _, exceptions, models, fields, api

try:
    import unicodecsv
except ImportError:
    pass

_logger = logging.getLogger(__name__)

class BankAccountStatementParser(models.TransientModel):
    _inherit = 'account.bank.statement.import'
    
    file_name = fields.Char("File Name")
    
    @api.multi
    def import_file(self):
        
        """ Process the file chosen in the wizard, create bank statement(s) and go to reconciliation. """
        self.ensure_one()
        # Let the appropriate implementation module parse the file and return the required data
        # The active_id is passed in context in case an implementation module requires information about the wizard state (see QIF)
        currency_code, account_number, stmts_vals = self.with_context(active_id=self.ids[0])._parse_file(base64.b64decode(self.data_file))
        # Check raw data
        self._check_parsed_data(stmts_vals)
        _logger.debug("Finding Journal")
        # Try to find the currency and journal in odoo
        c_code=str(currency_code)
        ac_number=str(account_number)
        currency, journal = self._find_additional_data(c_code, ac_number)
        _logger.debug("Journal is: " + str(journal))
        # If no journal found, ask the user about creating one
        if not journal:
            # The active_id is passed in context so the wizard can call import_file again once the journal is created
            return self.with_context(active_id=self.ids[0])._journal_creation_wizard(currency, account_number)
        # Prepare statement data to be used for bank statements creation
        stmts_vals = self._complete_stmts_vals(stmts_vals, journal, account_number)
        # Create the bank statements
        statement_ids, notifications = self._create_bank_statements(stmts_vals)
        # Now that the import worked out, set it as the bank_statements_source of the journal
        journal.bank_statements_source = 'file_import'
        # Finally display the imported bank statement
        bank_statement_view_id = self.env.ref('bank_account_statement_parser.bank_statement_view').id
        
        return {
            'type': 'ir.actions.act_window',
            'name': 'Bank Statement Display',
            'view_type': 'form',
            'res_model': 'account.bank.statement',
            'res_id': statement_ids[0],
            'views': [(bank_statement_view_id, 'form')],
            'view_id': bank_statement_view_id,
        }

    def _check_csv(self, file):
        try:
            fieldnames = ['NSC', 'AC', 'Type', 'Currency', 'Date', 'Partner', 'Description', 'Debit', 'Credit', 'Balance']
            
            dict = unicodecsv.DictReader(file, fieldnames=fieldnames, delimiter=',', encoding='iso-8859-1')
        except:
            return False
        return dict
        
    def _bank_statement_init(self, csv):
        line1 = next(csv)
        line2=self.get_data(line1)
        currency_code = line2['Currency']
        account_number = self._get_account_number(int(line2['NSC']+line2['AC']))

        bank_statement = {}
        bank_statement['name'] = str(self.file_name)
        bank_statement['date'] = self._string_to_date(line2['Date'])
        bank_statement['balance_start'] = float(line2['Balance'])
        bank_statement['balance_end_real'] = bank_statement['balance_start']
        bank_statement['transactions'] = []
        

        return currency_code, account_number, bank_statement


    def get_data(self,data):
        STRING_DATA = dict([(str(k), str(v)) for k, v in data.items()])
        print(STRING_DATA)
        return STRING_DATA

        
    def _get_account_number(self, account_number):
        journal = self.env['account.journal'].browse(self.env.context.get('journal_id', []))
        sanitized_account_number=str(journal.bank_account_id.sanitized_acc_number)
        slicing=sanitized_account_number[-14:]
        _logger.debug("san acc: " + str(slicing) + " acc: " + str(account_number))
        if slicing == str(account_number):
            return journal.bank_account_id.sanitized_acc_number
        else:
            return account_number
    
    def _string_to_date(self, date_string):
        return dateutil.parser.parse(date_string, dayfirst=True, fuzzy=True).date()
        
    def _import_id(self, line):
        m = hashlib.sha512()
        m.update(str(line).encode("utf-8"))
        m.hexdigest()
    
    def _find_partner(self, partner_name):
        partner = False
        if not partner_name.isspace():
            partner = self.env['res.partner'].search([('name','ilike',partner_name)], limit=1)
            _logger.debug("partner list: " + str(partner))
        return partner
    
    def _parse_file(self, data_file):
        rammm=data_file.encode('utf-8')
        csv = self._check_csv(io.BytesIO(data_file))
        if not csv:
            return super(AccountBankStatementImport, self)._parse_file(data_file)
        bank_statements_data = []
        
        try:
            currency_code, account_number, bank_statement = self._bank_statement_init(csv)
            
            for line in csv:
                # print("csv-------",csv)
                transaction = {}
                transaction['name'] = str(line['Description'])
                transaction['date'] = self._string_to_date(line['Date'])
                transaction['amount'] = float(line['Debit'] + line['Credit'])
                transaction['unique_import_id'] = self._import_id(line)
                transaction['ref'] = bank_statement['name'] + '-' + str(line['Description'])
                # _logger.debug("Partner is: " + line.get('Partner').encode('utf-8'))
                if line.get('Partner'):
                    partner = self._find_partner(line['Partner'])
                    _logger.debug("partner: " + str(partner) + " exists: " + str(partner))
                    if partner:
                        transaction['partner_id'] = partner.id
                    else:
                        transaction['partner_name'] = line['Partner']
                        transaction['partner_id'] = False
                bank_statement['transactions'].append(transaction)
                bank_statement['balance_end_real'] += float(transaction['amount'])
            bank_statements_data.append(bank_statement)
            print("bank_statements_data-------------",bank_statements_data)

        except Exception as e:
            _logger.debug("error parsing statement amount: " + str(csv), exc_info=True)
            raise exceptions.UserError(_(
                'The following problem occurred during import. The file might '
                'not be valid.'))
        return currency_code, account_number, bank_statements_data
        
    def _complete_stmts_vals(self, stmts_vals, journal, account_number):
        for st_vals in stmts_vals:
            st_vals['journal_id'] = journal.id

            for line_vals in st_vals['transactions']:
                unique_import_id = line_vals.get('unique_import_id')
                if unique_import_id:
                    sanitized_account_number = sanitize_account_number(account_number)
                    line_vals['unique_import_id'] = (sanitized_account_number and sanitized_account_number + '-' or '') + str(journal.id) + '-' + unique_import_id
                if not line_vals.get('bank_account_id') and not line_vals.get('partner_id'):
                    # Find the partner and his bank account or create the bank account. The partner selected during the
                    # reconciliation process will be linked to the bank when the statement is closed.
                    partner_id = False
                    bank_account_id = False
                    identifying_string = line_vals.get('account_number')
                    if identifying_string:
                        partner_bank = self.env['res.partner.bank'].search([('acc_number', '=', identifying_string)], limit=1)
                        if partner_bank:
                            bank_account_id = partner_bank.id
                            partner_id = partner_bank.partner_id.id
                        else:
                            bank_account_id = self.env['res.partner.bank'].create({'acc_number': line_vals['account_number']}).id
                    line_vals['partner_id'] = partner_id
                    line_vals['bank_account_id'] = bank_account_id

        return stmts_vals

class AccountJournal(models.Model):
    _inherit = 'account.journal'

    def _get_bank_statements_available_import_formats(self):
        formats = super(AccountJournal, self)._get_bank_statements_available_import_formats()
        formats.append('.csv')
        return formats