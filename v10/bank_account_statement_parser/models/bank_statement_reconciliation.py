# -*- encoding: utf-8 -*-
# 2018 Léo-Paul Géneau

import logging
import datetime

from odoo import models, fields, api
from odoo.osv import expression

_logger = logging.getLogger(__name__)

class BankStatement(models.Model):
    _inherit = 'account.bank.statement'
    
    sanity_mode = fields.Boolean(string='Sanity Mode', default=False, help='search duplicates for transactions named HSE (the duplicate should be named HEALTH SERVICE EXECUTIVE) or WRXXXX (we will search if the sale order XXXX is already reconciled)')

class BankStatementLine(models.Model):
    _inherit = 'account.bank.statement.line'
    
    marked_as_duplicated = fields.Boolean(string='duplicate', default=False)
    duplicated = fields.Boolean(compute='_is_duplicated')
    duplicate_id = fields.Many2one('account.bank.statement.line')
    duplicates = fields.One2many('account.bank.statement.line', 'duplicate_id', compute='_duplicates')
    reconciled = fields.Boolean(compute='_is_reconciled')
    message = fields.Char(compute='_compute_message')
    suggestions_start_date = fields.Date(compute='_suggestions_start_date')
    suggestions_end_date = fields.Date(compute='_suggestions_end_date')
    reconciliation_suggestions = fields.One2many('account.move', 'suggested_statement_id', string='Reconciliation Suggestions', compute='_reconciliation_suggestions')
    
    reconciled_with = fields.Char(string="Reconciled With",compute='_reconciled_with')
    
    @api.depends('reconciled')
    def _reconciled_with(self):
        try:
            print(" i m fucking in for reconcilation with")

            for rec in self:
                reconciled_with = ''
                
                if rec.journal_entry_ids.ids:
                    for entry in rec.journal_entry_ids:
                        reconciled_with += entry.display_name + ', '
                        
                rec.reconciled_with = reconciled_with
        except Exception:
            _logger.error("ERROR FINDING RECONCILED ITEMS", exc_info=True)
    
    @api.one
    @api.depends('statement_id.sanity_mode', 'date', 'amount', 'name')
    def _duplicates(self):
        if not isinstance(self.id, models.NewId) and not self.reconciled:
            domain = [['name', '=', self.name], ['date', '=', self.date], ['amount', '=', self.amount], ['id', '!=', self.id]]
            if self.statement_id.sanity_mode:
                additionnal_domain = self._sanity_duplicate_research()
                if additionnal_domain:
                    domain = expression.OR([domain, additionnal_domain])

            self.duplicates = self.env['account.bank.statement.line'].search(domain)
            
    def _sanity_duplicate_research(self):
        if self.name[:3] == 'HSE':
            return [['name', '=', 'HEALTH SERVICE EXECUTIVE'], ['date', '=', self.date], ['amount', '=', self.amount]]
                
        elif not self.reconciled:
            split_name = self.name.split(' ')
            for str in split_name:
                if str[:2] == 'WR':
                    sale_order_name = str[2:]
                    sale_order = self.env['sale.order'].search([('name', '=', sale_order_name)])
                    if sale_order and all(payment_move_line.statement_id for invoice in sale_order.invoice_ids for payment_move_line in invoice.payment_move_line_ids):
                        return [['id', '=', sale_order.invoice_ids[0].payment_move_line_ids[0].move_id.statement_line_id.id]]

        return False
    
    @api.one
    @api.depends('marked_as_duplicated', 'duplicates')
    def _is_duplicated(self):
        if self.marked_as_duplicated or self.duplicates:
            self.duplicated = True
        else:
            self.duplicated = False
    
    @api.one
    @api.depends('journal_entry_ids', 'account_id')
    def _is_reconciled(self):
        print(" i m fucking in for reconcilation",self.account_id)
        print(" i m fucking in for reconcilation journal",self.journal_entry_ids.ids)
        self.reconciled = False
        if self.journal_entry_ids.ids or self.account_id.id:
            self.reconciled = True
    
    @api.one
    @api.depends('duplicated', 'partner_id', 'reconciled')
    def _compute_message(self):
        if self.duplicated:
            self.message = "This line is already in the database! Please remove it from the statement"
        
        elif not self.partner_id and not self.reconciled:
            self.message = "Please select a partner"
        
        else:
            self.message = ""
            
    def _current_date_plus_timedelta(self, timedelta):
        fmt = '%Y-%m-%d'
        return str(datetime.datetime.strptime(str(self.date), fmt) + timedelta)
    
    @api.one
    @api.depends('date')
    def _suggestions_start_date(self):
        self.suggestions_start_date = self._current_date_plus_timedelta(-datetime.timedelta(days=5))
    
    @api.one
    @api.depends('date')
    def _suggestions_end_date(self):
        self.suggestions_end_date = self._current_date_plus_timedelta(datetime.timedelta(days=5))
    
    @api.one
    @api.depends('reconciled', 'date', 'amount')
    def _reconciliation_suggestions(self):
        if self.amount >= 0 or self.reconciled:
            self.reconciliation_suggestions = []
        else:

            self.reconciliation_suggestions = self.env['account.move'].search([['amount', '=', -self.amount], ['date', '>=', self.suggestions_start_date], ['date', '<=', self.suggestions_end_date]])
            print(" i m fucking here for sex",self.reconciliation_suggestions)
    
   

    @api.multi
    def delete_line(self):
        for record in self.env['account.move.displayer'].search([]):
            record.unlink()
        for record in self.env['account.bank.statement.line.displayer'].search([]):
            
            print("record22222222222-------------------",record)
            record.unlink()
        self.statement_id.balance_end_real -= self.amount
        # self.statement_id.write({'line_ids': [(2,self.id)]})
        self.unlink()
        


    

        

    

    @api.multi
    def display_reconciliation_suggestions(self):
        self.ensure_one()
        suggestions_view_id = self.env.ref('bank_account_statement_parser.suggestions_view').id
        res_id = self.env['account.move.displayer'].create({'statement_line_id': self.id}).id
        
        return {
            'name': 'Reconciliation Suggestions',
            'type': 'ir.actions.act_window',
            'view_type': 'form',
            'view_mode': 'form',
            'res_model': 'account.move.displayer',
            'res_id': res_id,
            'views': [(suggestions_view_id, 'form')],
            'view_id': suggestions_view_id,
            'target': 'new',
        }
        
    @api.multi
    def display_duplicates(self):
        self.ensure_one()
        duplicates_view_id = self.env.ref('bank_account_statement_parser.duplicates_view').id
        res_id = self.env['account.bank.statement.line.displayer'].create({'statement_line_id': self.id}).id
        
        return {
            'name': 'Duplicate Suggestions',
            'type': 'ir.actions.act_window',
            'view_type': 'form',
            'view_mode': 'form',
            'res_model': 'account.bank.statement.line.displayer',
            'res_id': res_id,
            'views': [(duplicates_view_id, 'form')],
            'view_id': duplicates_view_id,
            'target': 'new',
        }
        
    @api.multi
    def open_statement(self):
        self.ensure_one()
        
        base_url = self.env['ir.config_parameter'].get_param('web.base.url')
        record_url = base_url + "/web#id=" + str(self.statement_id.id) + "&view_type=form&model=account.bank.statement&action=149"
        
        client_action = {
            'type': 'ir.actions.act_url',
            'name': 'Bank Statement Display',
            'target': 'new',
            'url': record_url,
        }
        return client_action
        
    @api.multi
    def get_move_lines_for_reconciliation_widget(self, excluded_ids=None, str=False, offset=0, limit=None):
        """ Returns move lines for the bank statement reconciliation widget, formatted as a list of dicts
        """
        aml_recs = self.get_move_lines_for_reconciliation_based_on_amount(excluded_ids=excluded_ids, str=str, offset=offset, limit=limit)
        target_currency = self.currency_id or self.journal_id.currency_id or self.journal_id.company_id.currency_id
        return aml_recs.prepare_move_lines_for_reconciliation_widget(target_currency=target_currency, target_date=self.date)
        
    def get_move_lines_for_reconciliation_based_on_amount(self, excluded_ids=None, str=False, offset=0, limit=None):
        domain = [('credit', '=', -self.amount)] if self.amount < 0 else [('debit', '=', self.amount)]
        
        # Domain factorized for all reconciliation use cases
        ctx = dict(self._context or {})
        ctx['bank_statement_line'] = self
        generic_domain = self.env['account.move.line'].with_context(ctx).domain_move_lines_for_reconciliation(excluded_ids=excluded_ids, str=str)
        domain = expression.AND([domain, generic_domain])

        move_lines = self.env['account.move.line'].search(domain, offset=offset, limit=limit, order="date_maturity asc, id asc")
        if not move_lines:
            return self.get_move_lines_for_reconciliation(excluded_ids=excluded_ids, str=str, offset=offset, limit=limit)
            
        return move_lines
        
class DuplicatesDisplayer(models.TransientModel):
    _name = 'account.bank.statement.line.displayer'
    
    statement_line_id = fields.Many2one('account.bank.statement.line', required=True, readonly=True)
    duplicates = fields.One2many(related='statement_line_id.duplicates')
        
class AccountMovesDisplayer(models.TransientModel):
    _name = 'account.move.displayer'
    
    statement_line_id = fields.Many2one('account.bank.statement.line')
    account_moves = fields.One2many(related='statement_line_id.reconciliation_suggestions')
    

class AccountMove(models.Model):
    _inherit = 'account.move'
    
    suggested_statement_id = fields.Many2one('account.bank.statement', string='Suggested Statement')
    
    @api.multi
    def open_statement(self):
        self.ensure_one()
        
        base_url = self.env['ir.config_parameter'].get_param('web.base.url')
        record_url = base_url + "/web#id=" + str(self.statement_line_id.statement_id.id) + "&view_type=form&model=account.bank.statement&action=149"
        
        client_action = {
            'type': 'ir.actions.act_url',
            'name': 'Bank Statement Display',
            'target': 'new',
            'url': record_url,
        }
        return client_action