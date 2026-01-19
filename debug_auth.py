from odoo import api, SUPERUSER_ID
import logging

def run(env):
    print("--- Starting Auth Debug Script ---")
    
    login = 'vorlasanedev@gmail.com'
    User = env['res.users'].sudo()
    
    print(f"Searching for user: {login}")
    user = User.search([('login', '=', login)], limit=1)
    
    print(f"User found: {user}")
    print(f"User ID: {user.id}")
    print(f"User IDs: {user.ids}")
    
    if not user:
        print("ERROR: User not found!")
        return

    print(f"Current API Key: {user.rest_api_key}")
    
    try:
        print("Attempting to generate API Key...")
        # Simulating the controller logic
        if not user.rest_api_key:
             user.action_generate_api_key()
             print(f"New API Key generated: {user.rest_api_key}")
        else:
             print("API Key already exists. Forcing regeneration...")
             user.action_generate_api_key()
             print(f"New API Key generated: {user.rest_api_key}")
             
    except Exception as e:
        print(f"EXCEPTION CAUGHT: {e}")
        import traceback
        traceback.print_exc()

    print("--- Debug Script Finished ---")
