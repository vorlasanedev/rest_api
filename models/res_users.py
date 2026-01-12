from odoo import models, fields, api
import secrets

class ResUsers(models.Model):
    _inherit = 'res.users'

    rest_api_key = fields.Char(string='REST API Key', readonly=True, copy=False)

    def action_generate_api_key(self):
        self.ensure_one()
        key = secrets.token_hex(32)
        self.write({'rest_api_key': key})
        return key
