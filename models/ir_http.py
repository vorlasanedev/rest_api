from odoo import models, http, fields
from odoo.http import request
import werkzeug.exceptions

class IrHttp(models.AbstractModel):
    _inherit = 'ir.http'

    @classmethod
    def _auth_method_api_key(cls):
        # Extract key from header X-API-Key or Authorization
        key = cls._extract_api_key()
        if not key:
            raise werkzeug.exceptions.Unauthorized("API Key required")

        # Search for user with this key
        # We use sudo() because this is an auth method running before env is set
        user = request.env['res.users'].sudo().search([('rest_api_key', '=', key)], limit=1)

        if not user:
            raise werkzeug.exceptions.Unauthorized("Invalid API Key")

        # Update environment with the user
        request.update_env(user=user.id)

    @classmethod
    def _extract_api_key(cls):
        # 1. Check X-API-Key header
        key = request.httprequest.headers.get("X-API-Key")
        if key:
            return key.strip()

        # 2. Check Authorization: Bearer <key>
        auth_header = request.httprequest.headers.get("Authorization")
        if auth_header and isinstance(auth_header, str) and auth_header.lower().startswith("bearer "):
            return auth_header.split(" ", 1)[1].strip()

        # 3. Check query params as fallback
        return request.params.get("api_key")
