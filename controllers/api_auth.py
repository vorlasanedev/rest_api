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

    def _transform_binary_to_url(self, model, records_data):
        """Replaces Base64 binary data with a short web URL."""
        if not records_data:
            return records_data
            
        # Ensure we are working with a list of dicts
        is_single = isinstance(records_data, dict)
        data = [records_data] if is_single else records_data
        
        # Identify binary fields
        fields_info = model.fields_get()
        binary_fields = [f for f, info in fields_info.items() if info.get('type') == 'binary']
        
        if not binary_fields:
            return records_data
            
        base_url = request.httprequest.url_root.rstrip('/')
        model_name = model._name
        
        for row in data:
            rec_id = row.get('id')
            if not rec_id: continue
            for field in binary_fields:
                if field in row and row[field]:
                    # Shorten binary data to a predictable Odoo URL
                    row[field] = f"{base_url}/web/image/{model_name}/{rec_id}/{field}"
        
        return data[0] if is_single else data

    def _expand_relations(self, model, records_data, nested_fields):
        """
        Expands related fields for dotted notation requests.
        records_data: list of dictionaries
        nested_fields: dict { 'root_field': ['sub_field1', 'sub.sub.field'] }
        """
        if not records_data or not nested_fields:
            return records_data

        fields_info = model.fields_get(list(nested_fields.keys()))
        
        for root_field, sub_fields in nested_fields.items():
            if root_field not in fields_info:
                continue
                
            field_type = fields_info[root_field]['type']
            relation = fields_info[root_field].get('relation')
            if not relation:
                continue
            
            RelModel = request.env[relation].sudo()
            
            # 1. Collect all related IDs
            related_ids = set()
            for row in records_data:
                val = row.get(root_field)
                if not val:
                    continue
                if isinstance(val, tuple): # Many2one (id, name)
                    related_ids.add(val[0])
                elif isinstance(val, list): # x2many [id1, id2]
                    related_ids.update(val)
                elif isinstance(val, int): # standard ID
                    related_ids.add(val)
            
            if not related_ids:
                continue
                
            # 2. Recursive expand (handle multiple levels of nesting if needed)
            # For now, let's process the immediate children.
            # Split sub_fields into direct children and their nested children
            # sub_fields might be ['name', 'child_id.name']
            
            direct_sub_fields = set()
            next_level_nested = {}
            
            for f in sub_fields:
                parts = f.split('.', 1)
                direct_sub_fields.add(parts[0])
                if len(parts) > 1:
                    if parts[0] not in next_level_nested:
                        next_level_nested[parts[0]] = []
                    next_level_nested[parts[0]].append(parts[1])
            
            # Always ensure 'id' and 'display_name' are fetched unless specific fields are strictly requested? 
            # Or trust user input. Let's trust user input but add 'id'.
            if 'id' not in direct_sub_fields:
                direct_sub_fields.add('id')
                
            # 3. Fetch related records
            # Note: We recursivley call ourselves to handle deep nesting
            rel_records = RelModel.browse(list(related_ids))
            rel_data_raw = rel_records.read(list(direct_sub_fields))
            
            # Transform binary if needed (optional, could be recursive, but let's stick to simple first)
            rel_data_raw = self._transform_binary_to_url(RelModel, rel_data_raw)
            if isinstance(rel_data_raw, dict): rel_data_raw = [rel_data_raw]

            # Recurse if there are deeper levels
            if next_level_nested:
                rel_data_raw = self._expand_relations(RelModel, rel_data_raw, next_level_nested)
            
            # Index by ID
            rel_map = {r['id']: r for r in rel_data_raw}
            
            # 4. Update original data
            for row in records_data:
                val = row.get(root_field)
                if not val:
                    row[root_field] = None if field_type == 'many2one' else []
                    continue
                    
                if isinstance(val, tuple): # M2O
                    row[root_field] = rel_map.get(val[0])
                elif isinstance(val, int): # M2O as ID
                    row[root_field] = rel_map.get(val)
                elif isinstance(val, list): # x2M
                    # Odoo returns list of IDs
                    expanded = [rel_map[i] for i in val if i in rel_map]
                    row[root_field] = expanded
        
        return records_data

    @http.route([
        '/api/v1/<string:model_name>/fields',
        '/api/v1/<string:model_name>',
        '/api/v1/<string:model_name>/<int:rec_id>'
    ], type='http', auth='api_key', methods=['GET', 'POST', 'PUT', 'DELETE'], csrf=False)
    def dispatch_rest(self, model_name, rec_id=None, **kwargs):
        """Generic REST Dispatcher using API Key Auth."""
        _logger.info("REST API: Request to %s (%s)", model_name, request.httprequest.method)
        Model = request.env.get(model_name)
        if Model is None:
            return self._json_response({'error': f"Model '{model_name}' not found"}, status=404)

        if request.httprequest.path.endswith('/fields'):
            return self._json_response(Model.sudo().fields_get())

        method = request.httprequest.method
        try:
            if method == 'GET':
                # 1. Merge Query Params + JSON Body Params
                params = request.params.copy()
                try:
                    if request.httprequest.data:
                        body_params = json.loads(request.httprequest.data)
                        if isinstance(body_params, dict):
                            params.update(body_params)
                except Exception:
                    pass  # Ignore invalid JSON in body for GET, stick to params

                use_image_url = str(params.get('image_url', '')).lower() == 'true'
                
                if rec_id:
                    record = Model.browse(rec_id)
                    if not record.exists():
                        return self._json_response({'error': "Not found"}, status=404)
                    fields_to_read = json.loads(params.get('fields', '[]') if isinstance(params.get('fields'), str) else json.dumps(params.get('fields')))
                    data = record.read(fields_to_read)[0]
                    if use_image_url:
                        data = self._transform_binary_to_url(Model, data)
                    return self._json_response(data)
                else:
                    # 2. Pagination Logic
                    limit = int(params.get('limit') or params.get('page_size') or 80)
                    page = int(params.get('page', 1))
                    offset = int(params.get('offset', 0))
                    
                    if 'page' in params and 'offset' not in params:
                        offset = (page - 1) * limit

                    # 3. Filter Logic
                    domain = params.get('domain', [])
                    if isinstance(domain, str):
                        domain = json.loads(domain)
                    
                    # is_active support (Allow 'is_active' OR 'active')
                    is_active_param = params.get('is_active')
                    if is_active_param is None:
                        is_active_param = params.get('active')

                    if is_active_param is not None:
                        is_active = str(is_active_param).lower() == 'true'
                        # Remove any existing 'active' term from domain to avoid conflict
                        domain = [d for d in domain if d[0] != 'active']
                        domain.append(('active', '=', is_active))
                        
                        # If searching for inactive, OR if we just want to control it explicitly,
                        # set active_test=False so we can find nothing or everything as requested.
                        # If we leave active_test=True, Odoo might force [('active','=',True)] logic 
                        # which conflicts with [('active','=',False)].
                        Model = Model.with_context(active_test=False)

                    # --- Field Parsing for Nested Support ---
                    raw_fields = params.get('fields', [])
                    if isinstance(raw_fields, str):
                        raw_fields = json.loads(raw_fields)
                    
                    fields_to_read = set()
                    nested_fields = {} # { 'root': ['sub1', 'sub2'] }
                    
                    if not raw_fields:
                        # empty fields means read all
                        pass
                    else:
                        for f in raw_fields:
                            if '.' in f:
                                parts = f.split('.', 1)
                                root = parts[0]
                                fields_to_read.add(root)
                                if root not in nested_fields:
                                    nested_fields[root] = []
                                nested_fields[root].append(parts[1])
                            else:
                                fields_to_read.add(f)
                    
                    fields_list = list(fields_to_read) if fields_to_read else []

                    total_count = Model.search_count(domain)
                    records = Model.search(domain, limit=limit, offset=offset)
                    results = records.read(fields_list)
                    
                    if use_image_url:
                        results = self._transform_binary_to_url(Model, results)
                    
                    # --- Expand Nested Relations ---
                    if nested_fields:
                         results = self._expand_relations(Model, results, nested_fields)
                        
                    # Calculate total pages
                    total_pages = (total_count + limit - 1) // limit if limit > 0 else 1

                    return self._json_response({
                        'count': len(results),
                        'total': total_count,
                        'page': page,
                        'total_pages': total_pages,
                        'limit': limit,
                        'offset': offset,
                        'results': results
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
