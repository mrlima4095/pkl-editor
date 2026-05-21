# app.py
from flask import Flask, render_template, request, jsonify, send_file
import pickle
import joblib
import json
import os
from datetime import datetime

app = Flask(__name__)

class DictionaryExplorer:
    def __init__(self):
        self.data = {}
        self.current_file = None
        
    def load_from_pickle(self, filepath):
        with open(filepath, 'rb') as f:
            self.data = pickle.load(f)
        self.current_file = filepath
        return self.data
    
    def load_from_joblib(self, filepath):
        self.data = joblib.load(filepath)
        self.current_file = filepath
        return self.data
    
    def save_as_pickle(self, filepath):
        with open(filepath, 'wb') as f:
            pickle.dump(self.data, f)
            
    def save_as_joblib(self, filepath):
        joblib.dump(self.data, filepath)
    
    def get_value_by_path(self, path):
        current = self.data
        for key in path:
            if isinstance(current, dict):
                current = current.get(key)
            elif isinstance(current, list):
                try:
                    key = int(key)
                    current = current[key]
                except (ValueError, IndexError):
                    return None
            else:
                return None
        return current
    
    def set_value_by_path(self, path, value):
        current = self.data
        for key in path[:-1]:
            if isinstance(current, dict):
                if key not in current:
                    current[key] = {}
                current = current[key]
            elif isinstance(current, list):
                try:
                    key = int(key)
                    if key >= len(current):
                        current.extend([None] * (key - len(current) + 1))
                    current = current[key]
                except ValueError:
                    return False
        last_key = path[-1]
        
        if isinstance(current, dict):
            current[last_key] = self.parse_value(value)
        elif isinstance(current, list):
            try:
                idx = int(last_key)
                if idx >= len(current):
                    current.extend([None] * (idx - len(current) + 1))
                current[idx] = self.parse_value(value)
            except ValueError:
                return False
        return True
    
    def parse_value(self, value_str):
        try:
            return json.loads(value_str)
        except:
            return value_str

explorer = DictionaryExplorer()

@app.route('/')
def index():
    return render_template('explorer.html')

@app.route('/api/load', methods=['POST'])
def load_file():
    filepath = request.json.get('filepath')
    filetype = request.json.get('filetype', 'pickle')
    
    try:
        if filetype == 'pickle':
            data = explorer.load_from_pickle(filepath)
        else:
            data = explorer.load_from_joblib(filepath)
        
        return jsonify({
            'success': True,
            'data': convert_to_serializable(data),
            'filename': os.path.basename(filepath)
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/browse', methods=['POST'])
def browse():
    path = request.json.get('path', [])
    data = explorer.get_value_by_path(path)
    
    if data is None:
        return jsonify({'success': False, 'error': 'Path not found'})
    
    return jsonify({
        'success': True,
        'data': convert_to_serializable(data),
        'path': path,
        'type': get_type_name(data)
    })

@app.route('/api/edit', methods=['POST'])
def edit_value():
    path = request.json.get('path', [])
    value = request.json.get('value', '')
    
    if explorer.set_value_by_path(path, value):
        return jsonify({'success': True})
    return jsonify({'success': False, 'error': 'Failed to update value'})

@app.route('/api/save', methods=['POST'])
def save_file():
    filepath = request.json.get('filepath', '')
    filetype = request.json.get('filetype', 'pickle')
    
    if not filepath:
        filepath = explorer.current_file or 'exported_data'
    
    try:
        if filetype == 'pickle':
            if not filepath.endswith('.pkl'):
                filepath += '.pkl'
            explorer.save_as_pickle(filepath)
        else:
            if not filepath.endswith('.joblib'):
                filepath += '.joblib'
            explorer.save_as_joblib(filepath)
        
        return jsonify({'success': True, 'filepath': filepath})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/download', methods=['POST'])
def download():
    filetype = request.json.get('filetype', 'pickle')
    temp_file = f'temp_data_{datetime.now().timestamp()}'
    
    try:
        if filetype == 'pickle':
            temp_file += '.pkl'
            explorer.save_as_pickle(temp_file)
        else:
            temp_file += '.joblib'
            explorer.save_as_joblib(temp_file)
        
        return send_file(temp_file, as_attachment=True, download_name=f'data.{filetype}')
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})
    finally:
        if os.path.exists(temp_file):
            os.remove(temp_file)

def convert_to_serializable(obj):
    if isinstance(obj, dict):
        return {str(k): convert_to_serializable(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [convert_to_serializable(item) for item in obj]
    elif isinstance(obj, (int, float, str, bool, type(None))):
        return obj
    else:
        return str(obj)

def get_type_name(obj):
    if isinstance(obj, dict):
        return f'dict ({len(obj)} items)'
    elif isinstance(obj, list):
        return f'list ({len(obj)} items)'
    elif isinstance(obj, str):
        return f'str ({len(obj)} chars)'
    elif isinstance(obj, int):
        return 'int'
    elif isinstance(obj, float):
        return 'float'
    elif isinstance(obj, bool):
        return 'bool'
    elif obj is None:
        return 'None'
    else:
        return type(obj).__name__

if __name__ == '__main__':
    app.run(debug=True, port=5000)