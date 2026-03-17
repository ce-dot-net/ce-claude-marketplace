
import json
import os
from pathlib import Path

def get_config():
    """
    Get ACE configuration from multiple sources with priority:
    1. .antigravity/ace.json (Primary Project Config)
    2. .claude/settings.json (Legacy Project Config)
    3. ~/.config/ace/config.json (Global Config)
    """
    current_dir = Path.cwd()
    config = {
        'org': None,
        'project': None,
        'verbosity': 'detailed'
    }

    # 1. Try .antigravity/ace.json (Primary)
    ace_config_path = current_dir / '.antigravity' / 'ace.json'
    if ace_config_path.exists():
        try:
            with open(ace_config_path, 'r') as f:
                data = json.load(f)
                ace_section = data.get('ace', {})
                config['org'] = ace_section.get('org_id')
                config['project'] = ace_section.get('project_id')
                if 'verbosity' in ace_section:
                    config['verbosity'] = ace_section['verbosity']
                return config
        except Exception:
            pass

    # 2. Try .claude/settings.json (Legacy)
    settings_path = current_dir / '.claude' / 'settings.json'
    if not settings_path.exists():
        settings_path = current_dir.parent / '.claude' / 'settings.json'
        
    if settings_path.exists():
        try:
            with open(settings_path, 'r') as f:
                settings = json.load(f)
            
            env = settings.get('env', {})
            config['org'] = env.get('ACE_ORG_ID') or settings.get('orgId')
            config['project'] = env.get('ACE_PROJECT_ID') or settings.get('projectId')
            config['verbosity'] = env.get('ACE_VERBOSITY', 'detailed')
            
            if config['project']:
                return config
        except Exception:
            pass

    # 3. Try Global Config (~/.config/ace/config.json)
    try:
        global_config_path = Path.home() / '.config' / 'ace' / 'config.json'
        if global_config_path.exists():
            with open(global_config_path, 'r') as f:
                global_data = json.load(f)
                # Global config might have 'projectId' directly or 'orgs'
                if not config['project']:
                    config['project'] = global_data.get('projectId')
                if not config['org']:
                    # Try to infer org from project if possible, or use default
                    pass
                
                # If we found a project in global config, use it
                if config['project']:
                    return config
    except Exception:
        pass

    return config

def save_project_config(org_id, project_id, verbosity='detailed'):
    """Save context to .antigravity/ace.json"""
    try:
        config_dir = Path('.antigravity')
        config_dir.mkdir(exist_ok=True)
        config_path = config_dir / 'ace.json'
        
        data = {}
        if config_path.exists():
            try:
                with open(config_path, 'r') as f:
                    data = json.load(f)
            except:
                pass
        
        data['ace'] = {
            'org_id': org_id,
            'project_id': project_id,
            'verbosity': verbosity
        }
        
        with open(config_path, 'w') as f:
            json.dump(data, f, indent=2)
            
        return True, config_path
    except Exception as e:
        return False, str(e)
