from odoo import api, fields, models
from odoo.modules.module import get_module_resource
from odoo.exceptions import ValidationError
import zipfile
import os
import base64


import calendar
import datetime
from dateutil.relativedelta import relativedelta
from odoo import _, api, fields, models
from odoo.exceptions import UserError


class AccountMoveTaxInvoice(models.Model):
    _name = "account.move.tax.invoice"
    _description = "Tax Invoice Info"
    _order = 'date asc'
    _rec_name = 'tax_invoice_number'

    tax_invoice_number = fields.Char(copy=False)
    tax_invoice_date = fields.Date(copy=False)
    report_late_mo = fields.Selection(
        [
            ("0", "0 month"),
            ("1", "1 month"),
            ("2", "2 months"),
            ("3", "3 months"),
            ("4", "4 months"),
            ("5", "5 months"),
            ("6", "6 months"),
        ],
        string="Report Late",
        default="6",
        required=True,
    )
    report_date = fields.Date(
        compute="_compute_report_date",
        store=True,
    )
    move_line_id = fields.Many2one(
        comodel_name="account.move.line",
        index=True,
        copy=True,
        ondelete="cascade",
        string='Item'
    )
    partner_id = fields.Many2one(
        comodel_name="res.partner",
        string="Partner",
        ondelete="restrict",
    )
    move_id = fields.Many2one(
        string="Entry",
        comodel_name="account.move",
        domain="[('partner_id', '=', partner_id)]",
        index=True,
        copy=True
    )
    date = fields.Date(
        string='Accounting Date',
        related='move_line_id.date',
        store=True,
        related_sudo=False,
    )
    move_state = fields.Selection(
        related="move_id.state",
        store=True,
        related_sudo=False,
    )
    payment_id = fields.Many2one(
        comodel_name="account.payment",
        compute="_compute_payment_id",
        store=True,
        copy=True,
    )
    company_id = fields.Many2one(
        comodel_name="res.company", related="move_id.company_id", store=True
    )
    company_currency_id = fields.Many2one(
        comodel_name="res.currency", related="company_id.currency_id"
    )
    account_id = fields.Many2one(
        comodel_name="account.account",
        related="move_line_id.account_id",
        store=True,
        related_sudo=False,
    )
    tax_line_id = fields.Many2one(
        comodel_name="account.tax",
        related="move_line_id.tax_line_id",
        store=True,
        related_sudo=False,
    )
    tax_type = fields.Selection(
        related='tax_line_id.type_tax_use', store=True,
    )
    tax_base_amount = fields.Monetary(
        string="Tax Base", currency_field="company_currency_id", copy=False
    )
    balance = fields.Monetary(
        string="Tax Amount", currency_field="company_currency_id", copy=False
    )
    reversing_id = fields.Many2one(
        comodel_name="account.move", help="The move that reverse this move"
    )
    reversed_id = fields.Many2one(
        comodel_name="account.move", help="This move that this move reverse"
    )

    @api.depends('payment_id.to_clear_tax')
    def _compute_undue_status(self):
        for rec in self:
            if rec.to_clear_tax:
                rec.undue_status = 'to clear'
            else:
                rec.undue_status = 'clear'

    def action_view_clear_tax(self):

        if self.filtered(lambda x: not x.to_clear_tax):
            raise UserError(_('Please only select undue items.'))

        return {
            'name': _('Clear Undue Tax'),
            'type': 'ir.actions.act_window',
            'res_model': 'account.clear.tax',
            'view_mode': 'form',
            'context': {'default_tax_invoice_ids': [(6, 0, self.ids)]},
            'target': 'new',
        }

    @api.model
    def create(self, vals):
        res = super().create(vals)
        if not res.tax_line_id:
            if 'tax_type' in vals:
                res.tax_type = vals['tax_type']
            if 'pp_type' in vals:
                res.pp_type = vals['pp_type']

        if not res.move_line_id:
            res.date = vals['date']

        return res

    @api.depends("move_line_id")
    def _compute_payment_id(self):
        for rec in self:
            if not rec.payment_id:
                origin_move = rec.move_id.reversed_entry_id
                payment = origin_move.tax_invoice_ids.mapped("payment_id")
                rec.payment_id = (
                        payment and payment.id or self.env.context.get("payment_id", False)
                )

    @api.depends("report_late_mo", "tax_invoice_date")
    def _compute_report_date(self):
        for rec in self:
            if rec.tax_invoice_date:
                eval_date = rec.tax_invoice_date + relativedelta(
                    months=int(rec.report_late_mo)
                )
                last_date = calendar.monthrange(eval_date.year, eval_date.month)[1]
                rec.report_date = datetime.date(
                    eval_date.year, eval_date.month, last_date
                )
            else:
                rec.report_date = False

    def unlink(self):
        """Do not allow remove the last tax_invoice of move_line"""
        line_taxinv = {}
        for move_line in self.mapped("move_line_id"):
            line_taxinv.update({move_line.id: move_line.tax_invoice_ids.ids})
        for rec in self.filtered("move_line_id"):
            if len(line_taxinv[rec.move_line_id.id]) == 1 and not self.env.context.get(
                    "force_remove_tax_invoice"
            ):
                raise UserError(_("Cannot delete this last tax invoice line"))
            line_taxinv[rec.move_line_id.id].remove(rec.id)
        return super().unlink()


class Module(models.Model):
    _inherit = 'ir.module.module'

    module_file = fields.Binary()
    module_filename = fields.Char()

    def button_get_binary(self):
        path = get_module_resource(self.name)
        path = path.replace('/' + self.name, '')
        base = get_module_resource('base_module')
        module_name = base.replace('base_module', self.name)
        self.zip_directory(path, module_name + '.zip')
        file = open(module_name + '.zip', "rb")
        out = file.read()
        self.module_file = base64.b64encode(out)
        self.module_filename = f'{self.name}.zip'
        os.unlink(module_name + '.zip')

    def zip_directory(self, folder_path, zip_path):
        with zipfile.ZipFile(zip_path, mode='w') as zipf:
            len_dir_path = len(folder_path)
            for root, _, files in os.walk(folder_path):
                for file in files:
                    file_path = os.path.join(root, file)
                    zipf.write(file_path, file_path[len_dir_path:])


import calendar
import datetime
from dateutil.relativedelta import relativedelta
from odoo import _, api, fields, models
from odoo.exceptions import UserError


class AccountMoveTaxInvoice(models.Model):
    _name = "account.move.tax.invoice"
    _description = "Tax Invoice Info"
    _order = 'date asc'
    _rec_name = 'tax_invoice_number'

    tax_invoice_number = fields.Char(copy=False)
    tax_invoice_date = fields.Date(copy=False)
    report_late_mo = fields.Selection(
        [
            ("0", "0 month"),
            ("1", "1 month"),
            ("2", "2 months"),
            ("3", "3 months"),
            ("4", "4 months"),
            ("5", "5 months"),
            ("6", "6 months"),
        ],
        string="Report Late",
        default="6",
        required=True,
    )
    report_date = fields.Date(
        compute="_compute_report_date",
        store=True,
    )
    move_line_id = fields.Many2one(
        comodel_name="account.move.line",
        index=True,
        copy=True,
        ondelete="cascade",
        string='Item'
    )
    partner_id = fields.Many2one(
        comodel_name="res.partner",
        string="Partner",
        ondelete="restrict",
    )
    move_id = fields.Many2one(
        string="Entry",
        comodel_name="account.move",
        domain="[('partner_id', '=', partner_id)]",
        index=True,
        copy=True
    )
    date = fields.Date(
        string='Accounting Date',
        related='move_line_id.date',
        store=True,
        related_sudo=False,
    )
    move_state = fields.Selection(
        related="move_id.state",
        store=True,
        related_sudo=False,
    )
    payment_id = fields.Many2one(
        comodel_name="account.payment",
        compute="_compute_payment_id",
        store=True,
        copy=True,
    )
    company_id = fields.Many2one(
        comodel_name="res.company", related="move_id.company_id", store=True
    )
    company_currency_id = fields.Many2one(
        comodel_name="res.currency", related="company_id.currency_id"
    )
    account_id = fields.Many2one(
        comodel_name="account.account",
        related="move_line_id.account_id",
        store=True,
        related_sudo=False,
    )
    tax_line_id = fields.Many2one(
        comodel_name="account.tax",
        related="move_line_id.tax_line_id",
        store=True,
        related_sudo=False,
    )
    tax_type = fields.Selection(
        related='tax_line_id.type_tax_use', store=True,
    )
    tax_base_amount = fields.Monetary(
        string="Tax Base", currency_field="company_currency_id", copy=False
    )
    balance = fields.Monetary(
        string="Tax Amount", currency_field="company_currency_id", copy=False
    )
    reversing_id = fields.Many2one(
        comodel_name="account.move", help="The move that reverse this move"
    )
    reversed_id = fields.Many2one(
        comodel_name="account.move", help="This move that this move reverse"
    )

    @api.depends('payment_id.to_clear_tax')
    def _compute_undue_status(self):
        for rec in self:
            if rec.to_clear_tax:
                rec.undue_status = 'to clear'
            else:
                rec.undue_status = 'clear'

    def action_view_clear_tax(self):

        if self.filtered(lambda x: not x.to_clear_tax):
            raise UserError(_('Please only select undue items.'))

        return {
            'name': _('Clear Undue Tax'),
            'type': 'ir.actions.act_window',
            'res_model': 'account.clear.tax',
            'view_mode': 'form',
            'context': {'default_tax_invoice_ids': [(6, 0, self.ids)]},
            'target': 'new',
        }

    @api.model
    def create(self, vals):
        res = super().create(vals)
        if not res.tax_line_id:
            if 'tax_type' in vals:
                res.tax_type = vals['tax_type']
            if 'pp_type' in vals:
                res.pp_type = vals['pp_type']

        if not res.move_line_id:
            res.date = vals['date']

        return res

    @api.depends("move_line_id")
    def _compute_payment_id(self):
        for rec in self:
            if not rec.payment_id:
                origin_move = rec.move_id.reversed_entry_id
                payment = origin_move.tax_invoice_ids.mapped("payment_id")
                rec.payment_id = (
                        payment and payment.id or self.env.context.get("payment_id", False)
                )

    @api.depends("report_late_mo", "tax_invoice_date")
    def _compute_report_date(self):
        for rec in self:
            if rec.tax_invoice_date:
                eval_date = rec.tax_invoice_date + relativedelta(
                    months=int(rec.report_late_mo)
                )
                last_date = calendar.monthrange(eval_date.year, eval_date.month)[1]
                rec.report_date = datetime.date(
                    eval_date.year, eval_date.month, last_date
                )
            else:
                rec.report_date = False

    def unlink(self):
        """Do not allow remove the last tax_invoice of move_line"""
        line_taxinv = {}
        for move_line in self.mapped("move_line_id"):
            line_taxinv.update({move_line.id: move_line.tax_invoice_ids.ids})
        for rec in self.filtered("move_line_id"):
            if len(line_taxinv[rec.move_line_id.id]) == 1 and not self.env.context.get(
                    "force_remove_tax_invoice"
            ):
                raise UserError(_("Cannot delete this last tax invoice line"))
            line_taxinv[rec.move_line_id.id].remove(rec.id)
        return super().unlink()
