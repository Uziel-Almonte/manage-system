#!/usr/bin/env python
"""
Script to generate OpenAPI specification from Flask-smorest app
"""
import json
import sys
import os

# Set up environment
os.environ.setdefault('FLASK_ENV', 'development')

try:
    from app.main import app, api
    
    with app.app_context():
        # Get the API spec from flask-smorest instance
        if api:
            spec = api.spec.to_dict()
            print(json.dumps(spec, indent=2))
        else:
            print("Error: API instance not found", file=sys.stderr)
            sys.exit(1)
except Exception as e:
    print(f"Error: {str(e)}", file=sys.stderr)
    import traceback
    traceback.print_exc()
    sys.exit(1)
