from odoo import models, http, fields
from odoo.http import request
import logging
import werkzeug.exceptions

_logger = logging.getLogger(__name__)

class IrHttp(models.AbstractModel):
    _inherit = 'ir.http'

    @classmethod
    def _auth_method_api_key(cls):
        # Extract key from header X-API-Key or Authorization
        key = cls._extract_api_key()
        if not key:
            _logger.warning("REST API AUTH: Missing API Key in request headers")
            raise werkzeug.exceptions.Unauthorized("API Key required")

        # Search for user with this key
        user = request.env['res.users'].sudo().search([('rest_api_key', '=', key)], limit=1)

        if not user:
            _logger.warning("REST API AUTH: Invalid API Key provided: %s", key[:8] + "...")
            raise werkzeug.exceptions.Unauthorized("Invalid API Key")

        _logger.info("REST API AUTH: Successfully authenticated user %s (ID: %s)", user.login, user.id)
        
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
