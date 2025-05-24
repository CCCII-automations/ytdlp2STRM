#!/usr/bin/env python3
"""
Diagnostic script to check ytdlp2STRM installation
"""
import os
import sys
import json

print("=" * 60)
print("ytdlp2STRM Installation Check")
print("=" * 60)

# Check current directory
print(f"\n1. Current directory: {os.getcwd()}")
print(f"   Script location: {os.path.abspath(__file__)}")

# Check directory structure
print("\n2. Directory structure:")
required_dirs = ['ui', 'ui/html', 'ui/static', 'config', 'clases']
for dir_path in required_dirs:
    exists = os.path.exists(dir_path)
    print(f"   {dir_path:20} {'✓ EXISTS' if exists else '✗ MISSING'}")
    if exists and os.path.isdir(dir_path):
        files = os.listdir(dir_path)
        if files:
            print(f"      Contents: {', '.join(files[:5])}")
            if len(files) > 5:
                print(f"      ... and {len(files) - 5} more files")

# Check specific files
print("\n3. Important files:")
important_files = [
    'config/routes.py',
    'config/config.json',
    'clases/config.py',
    'clases/folders.py',
    'clases/log.py',
    'clases/cron.py',
    'ui/html/index.html'
]
for file_path in important_files:
    exists = os.path.exists(file_path)
    print(f"   {file_path:30} {'✓ EXISTS' if exists else '✗ MISSING'}")

# Check config.json if it exists
print("\n4. Configuration:")
config_path = 'config/config.json'
if os.path.exists(config_path):
    try:
        with open(config_path, 'r') as f:
            config = json.load(f)
        print(f"   ✓ Config loaded successfully")
        print(f"   Port configured: {config.get('ytdlp2strm_port', 'NOT SET')}")
    except Exception as e:
        print(f"   ✗ Error loading config: {e}")
else:
    print(f"   ✗ Config file not found")

# Check Python imports
print("\n5. Python imports:")
modules_to_check = [
    ('flask', 'Flask'),
    ('clases.config', 'config'),
    ('clases.folders', 'folders'),
    ('clases.log', 'log'),
    ('clases.cron', 'cron'),
    ('config.routes', None)
]

for module_name, import_name in modules_to_check:
    try:
        if import_name:
            exec(f"from {module_name} import {import_name}")
        else:
            exec(f"import {module_name}")
        print(f"   {module_name:25} ✓ OK")
    except ImportError as e:
        print(f"   {module_name:25} ✗ FAILED: {e}")

# Check routes if possible
print("\n6. Checking Flask routes:")
try:
    from flask import Flask

    app = Flask(__name__, template_folder='ui/html', static_folder='ui/static', static_url_path='')

    # Try to import routes
    try:
        import config.routes

        print("   ✓ Routes imported successfully")
        print("   Registered routes:")
        for rule in app.url_map.iter_rules():
            methods = ','.join(sorted(rule.methods - {'HEAD', 'OPTIONS'}))
            print(f"      {rule.endpoint:25s} {methods:10s} {rule.rule}")
    except Exception as e:
        print(f"   ✗ Failed to import routes: {e}")

except Exception as e:
    print(f"   ✗ Failed to check routes: {e}")

# Check for index.html content
print("\n7. Checking UI files:")
index_path = 'ui/html/index.html'
if os.path.exists(index_path):
    with open(index_path, 'r') as f:
        content = f.read()
    print(f"   index.html size: {len(content)} bytes")
    print(f"   First 200 chars: {content[:200]}...")
else:
    print(f"   ✗ index.html not found")

print("\n" + "=" * 60)
print("Diagnostic complete")
print("=" * 60)