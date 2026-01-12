from odoo import http, fields
from odoo.http import request
import json
import logging
from datetime import datetime

_logger = logging.getLogger(__name__)

class ApiAuthController(http.Controller):

    def _json_response(self, data, status=200):
        return request.make_response(
            json.dumps(data, default=str),
            headers=[('Content-Type', 'application/json')],
            status=status
        )

    @http.route("/api", type="http", auth="none", methods=["GET"], csrf=False)
    def api_index(self, **kwargs):
        return self._json_response({
            "status": "online",
            "message": "Odoo REST API is active",
            "endpoints": ["/api/ping", "/api/login", "/api/v1/<model>"]
        })

    @http.route("/api/ping", type="http", auth="none", methods=["GET"], csrf=False)
    def api_ping(self, **kwargs):
        _logger.info("REST API: Ping received")
        return self._json_response({"status": "alive", "version": "1.2.3"})

    @http.route("/api/login", type="http", auth="none", methods=["POST"], csrf=False)
    def api_login(self, **kwargs):
        """Returns the API Key after successful credentials check."""
        _logger.info("REST API: Login attempt started")
        try:
            body = json.loads(request.httprequest.data)
        except Exception:
            return self._json_response({"error": "Invalid JSON body"}, status=400)

        data = body.get('params', body) if isinstance(body, dict) else body
        login = (data.get("login") or data.get("email") or "").strip()
        password = (data.get("password") or "")
        dbname = (data.get("db") or data.get("db_name") or data.get("database") or "").strip()
        
        from odoo.service import db as odoo_db
        available_dbs = odoo_db.list_dbs()

        # 1. Provide specific error if user input a typo
        if dbname and dbname not in available_dbs:
            _logger.warning("REST API: Login failed - Database '%s' does not exist", dbname)
            return self._json_response({
                "error": "Invalid database name",
                "message": f"Database '{dbname}' was not found on this server.",
                "available_databases": available_dbs
            }, status=400)

        # 2. Auto-select if only one DB exists and none provided
        if not dbname and not request.db:
            if len(available_dbs) == 1:
                dbname = available_dbs[0]
                _logger.info("REST API: Auto-selected database '%s'", dbname)
            elif len(available_dbs) > 1:
                return self._json_response({
                    "error": "Multiple databases found",
                    "message": "Please specify the 'db' field in your request.",
                    "available_databases": available_dbs
                }, status=400)

        if dbname:
            request.session.db = dbname
            try:
                request.update_env(user=None)
            except Exception as e:
                _logger.error("REST API: Failed to bind to database '%s': %s", dbname, str(e))
                return self._json_response({"error": "Database connection failed"}, status=500)
        
        if not request.db:
            _logger.warning("REST API: Login failed - No database selected")
            return self._json_response({"error": "No database selected."}, status=400)

        _logger.info("REST API: Authenticating user '%s' on database '%s'", login, request.db)
        User = request.env["res.users"].sudo()
        target_user = User.search(["|", ("login", "=", login), ("email", "=", login)], limit=1)
        
        if not target_user:
            return self._json_response({"error": "User not found"}, status=404)

        credential = {'login': target_user.login, 'password': password, 'type': 'password'}
        user_agent_env = {'interactive': False, 'base_location': request.httprequest.url_root.rstrip('/')}
        
        try:
            res = User._login(db=request.db, credential=credential, user_agent_env=user_agent_env)
            uid = res.get('uid') if isinstance(res, dict) else res
            if not uid:
                return self._json_response({"error": "Invalid credentials"}, status=401)
            
            # Authentication successful -> ensure API Key exists
            user = User.browse(uid)
            if not user.rest_api_key:
                user.action_generate_api_key()
            
            return self._json_response({
                "uid": user.id,
                "name": user.name,
                "api_key": user.rest_api_key,
            })
        except Exception as e:
            return self._json_response({"error": "Authentication failed", "message": str(e)}, status=401)

    @http.route("/api/logout", type="http", auth="none", methods=["POST", "GET"], csrf=False)
    def api_logout(self, **kwargs):
        """Clears the current session."""
        _logger.info("REST API: Logout requested")
        try:
            request.session.logout()
            return self._json_response({"status": "success", "message": "Logged out successfully"})
        except Exception as e:
            return self._json_response({"error": "Logout failed", "message": str(e)}, status=500)

    @http.route('/api/v1/<string:model_name>/fields', type='http', auth='api_key', methods=['GET'], csrf=False)
    def api_v1_fields(self, model_name, **kwargs):
        """Returns metadata for all fields of a model."""
        try:
            Model = request.env.get(model_name)
            if Model is None:
                return self._json_response({'error': f"Model '{model_name}' not found"}, status=404)
            
            # We use sudo() for discovery since metadata is technically safe
            # but usually it should follow Odoo ACLs.
            return self._json_response(Model.sudo().fields_get())
        except Exception as e:
            _logger.error("REST API Metadata Error: %s", str(e))
            return self._json_response({'error': 'Forbidden or Server Error', 'message': str(e)}, status=403)

    @http.route([
        '/api/v1/<string:model_name>',
        '/api/v1/<string:model_name>/<int:rec_id>'
    ], type='http', auth='api_key', methods=['GET', 'POST', 'PUT', 'DELETE'], csrf=False)
    def dispatch_rest(self, model_name, rec_id=None, **kwargs):
        """Generic REST Dispatcher using API Key Auth."""
        _logger.info("REST API: Request to %s (%s)", model_name, request.httprequest.method)
        Model = request.env.get(model_name)
        if Model is None:
            return self._json_response({'error': f"Model '{model_name}' not found"}, status=404)

        method = request.httprequest.method
        try:
            if method == 'GET':
                if rec_id:
                    record = Model.browse(rec_id)
                    if not record.exists():
                        return self._json_response({'error': "Not found"}, status=404)
                    fields_to_read = json.loads(request.params.get('fields', '[]'))
                    return self._json_response(record.read(fields_to_read)[0])
                else:
                    domain = json.loads(request.params.get('domain', '[]'))
                    fields_to_read = json.loads(request.params.get('fields', '[]'))
                    limit = int(request.params.get('limit', 80))
                    offset = int(request.params.get('offset', 0))
                    records = Model.search(domain, limit=limit, offset=offset)
                    return self._json_response({
                        'total': Model.search_count(domain),
                        'results': records.read(fields_to_read)
                    })
            
            elif method == 'POST':
                body = json.loads(request.httprequest.data)
                vals = body.get('params', body)
                
                # Specialized logic for res.users
                if model_name == 'res.users':
                    login = vals.get('login')
                    email = vals.get('email')
                    
                    # 1. Duplication Check
                    domain = []
                    if login: domain.append(('login', '=', login))
                    if email: domain.append(('email', '=', email))
                    if domain and Model.sudo().search_read(['|'] + domain if len(domain) > 1 else domain, ['id'], limit=1):
                        return self._json_response({'error': 'Conflict', 'message': 'A user with this login or email already exists.'}, status=409)
                    
                    # 2. Password Validation
                    password = vals.get('password')
                    confirm_password = vals.get('confirm_password')
                    if password or confirm_password:
                        if password != confirm_password:
                            return self._json_response({'error': 'Bad Request', 'message': 'Passwords do not match.'}, status=400)
                        # Odoo uses 'password' field for creation
                        vals.pop('confirm_password', None)

                record = Model.create(vals)
                
                # Auto-generate API Key for new users
                if model_name == 'res.users':
                    record.action_generate_api_key()
                    return self._json_response({
                        'id': record.id, 
                        'display_name': record.display_name,
                        'api_key': record.rest_api_key
                    }, status=201)

                return self._json_response({'id': record.id, 'display_name': record.display_name}, status=201)
            
            elif method == 'PUT':
                if not rec_id: return self._json_response({'error': "ID required"}, status=400)
                record = Model.browse(rec_id)
                if not record.exists(): return self._json_response({'error': "Not found"}, status=404)
                body = json.loads(request.httprequest.data)
                vals = body.get('params', body)

                # Specialized logic for res.users update
                if model_name == 'res.users':
                    password = vals.get('password')
                    confirm_password = vals.get('confirm_password')
                    if password or confirm_password:
                        if password != confirm_password:
                            return self._json_response({'error': 'Bad Request', 'message': 'Passwords do not match.'}, status=400)
                        vals.pop('confirm_password', None)

                record.write(vals)
                return self._json_response({'success': True})
            
            elif method == 'DELETE':
                if not rec_id: return self._json_response({'error': "ID required"}, status=400)
                record = Model.browse(rec_id)
                if not record.exists(): return self._json_response({'error': "Not found"}, status=404)
                record.unlink()
                return self._json_response({'success': True}, status=204)
                
            return self._json_response({'error': "Method not allowed"}, status=405)
        except Exception as e:
            _logger.exception("REST API Error")
            return self._json_response({'error': str(e)}, status=500)
