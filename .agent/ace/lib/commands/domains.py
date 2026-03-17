
import json
from pathlib import Path
from ..config import get_config

def run():
    """
    Show active domains for the current session.
    Reads from /tmp/ace-domains-{project}.json associated with session.
    """
    try:
        config = get_config()
        if not config['project']:
             print("⚠️ [ACE] No project context found.")
             return

        domain_file = Path(f"/tmp/ace-domains-{config['project']}.json")
        
        if not domain_file.exists():
            print("ℹ️  [ACE] No active domains for this session.")
            return
            
        try:
            data = json.loads(domain_file.read_text())
            
            print("🌐 [ACE] Active Domains:")
            
            # abstract vs concrete
            abstract = data.get('abstract', [])
            concrete = data.get('concrete', [])
            
            if abstract:
                print("\n  Conceptual:")
                for d in abstract:
                    print(f"   • {d}")
                    
            if concrete:
                print("\n  Technical:")
                for d in concrete:
                    print(f"   • {d}")
                    
        except json.JSONDecodeError:
            print("❌ [ACE] Error reading domain file.")
            
    except Exception as e:
        print(f"❌ [ACE] Domains command failed: {e}")
