# app.py - Backend with tuple and advanced structure support
from flask import Flask, render_template, request, jsonify, send_file
import os
import pickle
import joblib
import json
from pathlib import Path
import tempfile
from typing import Any, Dict, List, Tuple, Set
import shutil
import traceback
import ast

app = Flask(__name__)
app.secret_key = 'windows_explorer_pickle_key_2024'

# Store active pickle data
active_pickle_data = None
active_pickle_path = None
active_pickle_type = None

# Supported advanced types
ADVANCED_TYPES = {
    'tuple': tuple,
    'set': set,
    'list': list,
    'dict': dict,
    'int': int,
    'float': float,
    'str': str,
    'bool': bool,
    'none': type(None)
}

def safe_serialize(obj):
    """Convert Python object to JSON-serializable format"""
    try:
        json.dumps(obj)
        return obj
    except:
        if hasattr(obj, '__dict__'):
            return {
                '__type__': obj.__class__.__name__,
                '__repr__': repr(obj)[:200],
                '__module__': obj.__class__.__module__
            }
        elif isinstance(obj, (tuple, set)):
            return {
                '__type__': type(obj).__name__,
                '__repr__': repr(obj)[:200],
                '__items__': list(obj) if isinstance(obj, (tuple, set)) else None
            }
        else:
            return {
                '__type__': type(obj).__name__,
                '__repr__': repr(obj)[:200]
            }

def load_pickle_file(filepath):
    """Load pickle or joblib file"""
    ext = Path(filepath).suffix.lower()
    try:
        if ext in ['.pkl', '.pickle']:
            with open(filepath, 'rb') as f:
                return pickle.load(f)
        elif ext == '.joblib':
            return joblib.load(filepath)
    except Exception as e:
        print(f"Error loading: {e}")
        return None

def save_pickle_file(filepath, data):
    """Save pickle or joblib file"""
    ext = Path(filepath).suffix.lower()
    try:
        if ext in ['.pkl', '.pickle']:
            with open(filepath, 'wb') as f:
                pickle.dump(data, f)
        elif ext == '.joblib':
            joblib.dump(data, filepath)
        return True
    except Exception as e:
        print(f"Error saving: {e}")
        return False

def navigate_in_data(data, path_parts):
    """Navigate through data structure using path parts"""
    current = data
    for part in path_parts:
        if part == '':
            continue
        if isinstance(current, dict):
            if part.isdigit():
                part = int(part)
            if part in current:
                current = current[part]
            else:
                return None
        elif isinstance(current, list):
            try:
                idx = int(part)
                if 0 <= idx < len(current):
                    current = current[idx]
                else:
                    return None
            except ValueError:
                return None
        elif isinstance(current, tuple):
            try:
                idx = int(part)
                if 0 <= idx < len(current):
                    current = current[idx]
                else:
                    return None
            except ValueError:
                return None
        else:
            return None
    return current

def get_item_info(name, value, path):
    """Get item information for display"""
    is_container = isinstance(value, (dict, list, tuple, set))
    
    # Check if complex object
    is_complex = False
    if not is_container and not isinstance(value, (str, int, float, bool, type(None))):
        is_complex = True
    
    if isinstance(value, dict):
        size = len(value)
        type_name = 'dictionary'
        icon = '📁'
    elif isinstance(value, list):
        size = len(value)
        type_name = 'list'
        icon = '📁'
    elif isinstance(value, tuple):
        size = len(value)
        type_name = 'tuple'
        icon = '📁'
    elif isinstance(value, set):
        size = len(value)
        type_name = 'set'
        icon = '📁'
    elif is_complex:
        size = 0
        type_name = value.__class__.__name__
        icon = '🔧'
    else:
        size = len(str(value)) if value else 0
        type_name = type(value).__name__
        icon = '📄'
    
    # Get safe preview
    try:
        if is_container:
            if isinstance(value, set):
                preview = f'{{{", ".join(repr(v)[:20] for v in list(value)[:3])}{"..." if len(value) > 3 else ""}}}'
            elif isinstance(value, tuple):
                preview = f'({", ".join(repr(v)[:20] for v in value[:3])}{"..." if len(value) > 3 else ""})'
            else:
                preview = None
        elif is_complex:
            preview = repr(value)[:50]
        else:
            preview = str(value)[:50]
    except:
        preview = 'Not available'
    
    return {
        'name': str(name),
        'is_container': is_container,
        'is_complex': is_complex,
        'size': size,
        'type': type_name,
        'icon': icon,
        'value_preview': preview,
        'path': path
    }

@app.route('/')
def index():
    return render_template('explorer.html')

@app.route('/api/load_pickle', methods=['POST'])
def load_pickle():
    """Load pickle/joblib file as virtual filesystem"""
    global active_pickle_data, active_pickle_path, active_pickle_type
    
    if 'file' not in request.files:
        return jsonify({'success': False, 'error': 'No file uploaded'})
    
    file = request.files['file']
    if file.filename == '':
        return jsonify({'success': False, 'error': 'Empty filename'})
    
    # Save temporarily
    temp_dir = tempfile.mkdtemp()
    temp_path = Path(temp_dir) / file.filename
    file.save(temp_path)
    
    # Load pickle
    try:
        data = load_pickle_file(temp_path)
        if data is None:
            return jsonify({'success': False, 'error': 'Error loading pickle/joblib file'})
        
        active_pickle_data = data
        active_pickle_path = str(temp_path)
        active_pickle_type = 'joblib' if file.filename.endswith('.joblib') else 'pickle'
        
        # Get root structure
        root_items = []
        if isinstance(data, dict):
            for key, value in data.items():
                root_items.append(get_item_info(key, value, str(key)))
        elif isinstance(data, (list, tuple, set)):
            for idx, value in enumerate(data):
                root_items.append(get_item_info(idx, value, str(idx)))
        else:
            root_items.append(get_item_info('root', data, ''))
        
        return jsonify({
            'success': True,
            'filename': file.filename,
            'root_type': type(data).__name__,
            'items': root_items,
            'current_path': '',
            'is_container': isinstance(data, (dict, list, tuple, set))
        })
    except Exception as e:
        traceback.print_exc()
        return jsonify({'success': False, 'error': f'Error loading: {str(e)}'})

@app.route('/api/browse')
def browse():
    """Navigate through pickle structure"""
    global active_pickle_data
    
    if active_pickle_data is None:
        return jsonify({'success': False, 'error': 'No pickle loaded'})
    
    path = request.args.get('path', '')
    path_parts = path.split('/') if path else []
    
    try:
        current = navigate_in_data(active_pickle_data, path_parts)
        
        if current is None:
            return jsonify({'success': False, 'error': 'Path not found'})
        
        # Determine how to list items
        items = []
        if isinstance(current, dict):
            for key, value in current.items():
                item_path = f"{path}/{key}" if path else str(key)
                items.append(get_item_info(key, value, item_path))
        elif isinstance(current, (list, tuple, set)):
            for idx, value in enumerate(current):
                item_path = f"{path}/{idx}" if path else str(idx)
                items.append(get_item_info(idx, value, item_path))
        else:
            # It's a value, not a container
            safe_value = safe_serialize(current)
            return jsonify({
                'success': True,
                'is_value': True,
                'value': str(current),
                'type': type(current).__name__,
                'is_complex': not isinstance(current, (str, int, float, bool, type(None), list, dict, tuple, set)),
                'value_raw': safe_value
            })
        
        # Sort: containers first
        items.sort(key=lambda x: (not x['is_container'], x['name']))
        
        return jsonify({
            'success': True,
            'is_container': True,
            'items': items,
            'current_path': path,
            'parent_path': '/'.join(path_parts[:-1]) if path_parts else None,
            'type': type(current).__name__
        })
    except Exception as e:
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/get_item')
def get_item():
    """Get specific item for editing"""
    global active_pickle_data
    
    path = request.args.get('path', '')
    path_parts = path.split('/') if path else []
    
    try:
        current = navigate_in_data(active_pickle_data, path_parts)
        
        if current is None:
            return jsonify({'success': False, 'error': 'Item not found'})
        
        is_editable = isinstance(current, (str, int, float, bool, type(None)))
        is_tuple_or_set = isinstance(current, (tuple, set))
        
        return jsonify({
            'success': True,
            'value': str(current),
            'type': type(current).__name__,
            'is_container': isinstance(current, (dict, list, tuple, set)),
            'is_editable': is_editable,
            'is_tuple_or_set': is_tuple_or_set,
            'raw_value': safe_serialize(current)
        })
    except Exception as e:
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/update_value', methods=['POST'])
def update_value():
    """Update value of an item (supports tuple, set, list, dict)"""
    global active_pickle_data
    
    data = request.json
    path = data.get('path', '')
    new_value = data.get('value')
    value_type = data.get('type', 'string')
    
    path_parts = path.split('/')
    if not path_parts:
        return jsonify({'success': False, 'error': 'Invalid path'})
    
    item_name = path_parts[-1]
    parent_parts = path_parts[:-1]
    
    # Navigate to parent
    parent = navigate_in_data(active_pickle_data, parent_parts) if parent_parts else active_pickle_data
    
    if parent is None:
        return jsonify({'success': False, 'error': 'Parent container not found'})
    
    # Convert value to proper type
    try:
        if value_type == 'int':
            converted_value = int(new_value)
        elif value_type == 'float':
            converted_value = float(new_value)
        elif value_type == 'bool':
            converted_value = new_value.lower() == 'true'
        elif value_type == 'none':
            converted_value = None
        elif value_type == 'tuple':
            # Parse tuple from string like "(1, 2, 3)" or "1,2,3"
            if isinstance(new_value, str):
                if new_value.startswith('(') and new_value.endswith(')'):
                    converted_value = ast.literal_eval(new_value)
                else:
                    parts = [p.strip() for p in new_value.split(',')]
                    converted_value = tuple(ast.literal_eval(p) if p else None for p in parts)
            else:
                converted_value = tuple(new_value)
        elif value_type == 'set':
            # Parse set from string like "{1, 2, 3}" or "1,2,3"
            if isinstance(new_value, str):
                if new_value.startswith('{') and new_value.endswith('}'):
                    converted_value = ast.literal_eval(new_value)
                else:
                    parts = [p.strip() for p in new_value.split(',')]
                    converted_value = {ast.literal_eval(p) if p else None for p in parts}
            else:
                converted_value = set(new_value)
        elif value_type == 'list':
            # Parse list from string
            if isinstance(new_value, str):
                converted_value = ast.literal_eval(new_value) if new_value.startswith('[') else [x.strip() for x in new_value.split(',')]
            else:
                converted_value = list(new_value)
        elif value_type == 'dict':
            # Parse dict from string
            if isinstance(new_value, str):
                converted_value = ast.literal_eval(new_value)
            else:
                converted_value = dict(new_value)
        else:  # string
            converted_value = str(new_value)
    except Exception as e:
        return jsonify({'success': False, 'error': f'Type conversion error: {str(e)}'})
    
    try:
        if isinstance(parent, dict):
            if item_name.isdigit():
                item_name = int(item_name)
            parent[item_name] = converted_value
        elif isinstance(parent, list):
            idx = int(item_name)
            if 0 <= idx < len(parent):
                parent[idx] = converted_value
            else:
                return jsonify({'success': False, 'error': 'Invalid index'})
        elif isinstance(parent, tuple):
            # Tuples are immutable, need to convert to list and back
            temp_list = list(parent)
            idx = int(item_name)
            if 0 <= idx < len(temp_list):
                temp_list[idx] = converted_value
                # Update parent in the original structure
                parent_container = navigate_in_data(active_pickle_data, parent_parts[:-1]) if len(parent_parts) > 1 else active_pickle_data
                if parent_container and isinstance(parent_container, (list, dict)):
                    last_key = parent_parts[-1] if parent_parts else None
                    if last_key and isinstance(parent_container, dict):
                        parent_container[last_key] = tuple(temp_list)
                    elif isinstance(parent_container, list):
                        parent_container[int(last_key)] = tuple(temp_list)
            else:
                return jsonify({'success': False, 'error': 'Invalid index'})
        elif isinstance(parent, set):
            return jsonify({'success': False, 'error': 'Cannot modify individual items in a set. Please edit the entire set.'})
        else:
            return jsonify({'success': False, 'error': 'Container does not support update'})
        
        # Auto-save
        save_pickle_file(active_pickle_path, active_pickle_data)
        
        return jsonify({'success': True, 'message': 'Value updated successfully'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/create_item', methods=['POST'])
def create_item():
    """Create new item (file, folder, tuple, set)"""
    global active_pickle_data
    
    data = request.json
    parent_path = data.get('path', '')
    item_name = data.get('name', '')
    item_type = data.get('item_type', 'file')  # 'file', 'folder', 'tuple', 'set'
    value_type = data.get('value_type', 'string')
    
    path_parts = parent_path.split('/') if parent_path else []
    
    # Navigate to parent
    parent = navigate_in_data(active_pickle_data, path_parts) if path_parts else active_pickle_data
    
    if parent is None:
        return jsonify({'success': False, 'error': 'Parent container not found'})
    
    if not isinstance(parent, (dict, list)):
        return jsonify({'success': False, 'error': 'Cannot create items here'})
    
    try:
        if isinstance(parent, dict):
            # Check if name exists
            key = int(item_name) if item_name.isdigit() else item_name
            if key in parent:
                return jsonify({'success': False, 'error': 'Item already exists'})
            
            if item_type == 'folder':
                parent[key] = {} if data.get('folder_type') == 'dict' else []
            elif item_type == 'tuple':
                parent[key] = ()
            elif item_type == 'set':
                parent[key] = set()
            else:
                # Create file with default value
                default_value = {
                    'string': '',
                    'int': 0,
                    'float': 0.0,
                    'bool': False,
                    'none': None,
                    'tuple': (),
                    'set': set(),
                    'list': [],
                    'dict': {}
                }.get(value_type, '')
                parent[key] = default_value
                
        elif isinstance(parent, list):
            if item_type == 'folder':
                parent.append({} if data.get('folder_type') == 'dict' else [])
            elif item_type == 'tuple':
                parent.append(())
            elif item_type == 'set':
                parent.append(set())
            else:
                default_value = {
                    'string': '',
                    'int': 0,
                    'float': 0.0,
                    'bool': False,
                    'none': None,
                    'tuple': (),
                    'set': set(),
                    'list': [],
                    'dict': {}
                }.get(value_type, '')
                parent.append(default_value)
        
        # Auto-save
        save_pickle_file(active_pickle_path, active_pickle_data)
        
        return jsonify({'success': True, 'message': 'Item created successfully'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/rename_item', methods=['POST'])
def rename_item():
    """Rename key in dictionary"""
    global active_pickle_data
    
    data = request.json
    path = data.get('path', '')
    new_name = data.get('new_name', '')
    
    path_parts = path.split('/')
    if not path_parts:
        return jsonify({'success': False, 'error': 'Invalid path'})
    
    item_name = path_parts[-1]
    parent_parts = path_parts[:-1]
    
    # Navigate to parent
    parent = navigate_in_data(active_pickle_data, parent_parts) if parent_parts else active_pickle_data
    
    if parent is None:
        return jsonify({'success': False, 'error': 'Parent container not found'})
    
    try:
        if isinstance(parent, dict):
            # Convert to int if numeric
            if item_name.isdigit():
                item_name = int(item_name)
            
            if item_name not in parent:
                return jsonify({'success': False, 'error': 'Item not found'})
            
            value = parent[item_name]
            # Try to convert new_name to int if possible
            if new_name.isdigit():
                new_name = int(new_name)
            
            del parent[item_name]
            parent[new_name] = value
            
        elif isinstance(parent, (list, tuple, set)):
            return jsonify({'success': False, 'error': 'Cannot rename items in lists, tuples, or sets'})
        else:
            return jsonify({'success': False, 'error': 'Container does not support rename'})
        
        # Auto-save
        save_pickle_file(active_pickle_path, active_pickle_data)
        
        return jsonify({'success': True, 'message': 'Item renamed successfully'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/delete_item', methods=['POST'])
def delete_item():
    """Delete an item"""
    global active_pickle_data
    
    data = request.json
    path = data.get('path', '')
    
    path_parts = path.split('/')
    if not path_parts:
        return jsonify({'success': False, 'error': 'Invalid path'})
    
    item_name = path_parts[-1]
    parent_parts = path_parts[:-1]
    
    # Navigate to parent
    parent = navigate_in_data(active_pickle_data, parent_parts) if parent_parts else active_pickle_data
    
    if parent is None:
        return jsonify({'success': False, 'error': 'Parent container not found'})
    
    try:
        if isinstance(parent, dict):
            key = int(item_name) if item_name.isdigit() else item_name
            if key in parent:
                del parent[key]
            else:
                return jsonify({'success': False, 'error': 'Item not found'})
        elif isinstance(parent, list):
            idx = int(item_name)
            if 0 <= idx < len(parent):
                del parent[idx]
            else:
                return jsonify({'success': False, 'error': 'Invalid index'})
        elif isinstance(parent, tuple):
            return jsonify({'success': False, 'error': 'Cannot delete items from tuples (immutable)'})
        elif isinstance(parent, set):
            # For sets, we need to find and remove the value
            value_to_remove = None
            for idx, val in enumerate(parent):
                if str(idx) == item_name:
                    value_to_remove = val
                    break
            if value_to_remove is not None:
                parent.remove(value_to_remove)
            else:
                return jsonify({'success': False, 'error': 'Item not found'})
        else:
            return jsonify({'success': False, 'error': 'Container does not support deletion'})
        
        # Auto-save
        save_pickle_file(active_pickle_path, active_pickle_data)
        
        return jsonify({'success': True, 'message': 'Item deleted successfully'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/download_pickle')
def download_pickle():
    """Download current pickle/joblib file"""
    global active_pickle_path
    
    if active_pickle_path is None:
        return jsonify({'success': False, 'error': 'No pickle loaded'})
    
    original_name = Path(active_pickle_path).name
    return send_file(active_pickle_path, as_attachment=True, download_name=original_name)

@app.route('/api/save_as', methods=['POST'])
def save_as():
    """Save current pickle to new file"""
    global active_pickle_data, active_pickle_path
    
    data = request.json
    new_filename = data.get('filename', '')
    
    if not new_filename:
        return jsonify({'success': False, 'error': 'Invalid filename'})
    
    if not new_filename.endswith(('.pkl', '.pickle', '.joblib')):
        new_filename += '.pkl'
    
    # Save in same directory as original file
    parent_dir = Path(active_pickle_path).parent
    new_path = parent_dir / new_filename
    
    if save_pickle_file(new_path, active_pickle_data):
        active_pickle_path = str(new_path)
        return jsonify({'success': True, 'message': f'File saved as {new_filename}'})
    else:
        return jsonify({'success': False, 'error': 'Error saving file'})

if __name__ == '__main__':
    app.run(debug=True, port=5000)