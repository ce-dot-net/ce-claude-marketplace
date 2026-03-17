
import sys
from .commands import (
    search, learn, configure, bootstrap, status, patterns, doctor,
    tune, clear, top, delta, export, import_cmd, cleanup, domains, init_rules
)

def main():
    if len(sys.argv) < 2:
        print("Usage: adapter.py [search|learn|configure|bootstrap|status|patterns|doctor|tune|clear|top|delta|export|import] ...")
        sys.exit(1)
        
    command = sys.argv[1]
    
    if command == "search":
        if len(sys.argv) < 3:
            print("Usage: adapter.py search <query>")
            sys.exit(1)
        search.run(sys.argv[2])
        
    elif command == "learn":
        if len(sys.argv) < 5:
            print("Usage: adapter.py learn <task> <trajectory> <success>")
            sys.exit(1)
        learn.run(sys.argv[2], sys.argv[3], sys.argv[4])
        
    elif command == "configure":
        if len(sys.argv) < 4:
            print("Usage: adapter.py configure <org_id> <project_id>")
            sys.exit(1)
        configure.run(sys.argv[2], sys.argv[3])
        
    elif command == "bootstrap":
        mode = sys.argv[2] if len(sys.argv) > 2 else "hybrid"
        bootstrap.run(mode)
        
    elif command == "status":
        status.run()
        
    elif command == "patterns":
        patterns.run()
        
    elif command == "doctor":
        doctor.run()

    elif command == "tune":
        tune.run(sys.argv[2:])

    elif command == "clear":
        clear.run()

    elif command == "top":
        limit = sys.argv[2] if len(sys.argv) > 2 else "10"
        top.run(limit)

    elif command == "delta":
        delta.run(sys.argv[2:])

    elif command == "export":
        export.run(sys.argv[2:])

    elif command == "import":
        import_cmd.run(sys.argv[2:])
        
    elif command == "start":
        if len(sys.argv) < 3:
            print("Usage: adapter.py start <prompt>")
            sys.exit(1)
        # Import dynamically to avoid circular imports or heavy startup
        from .hooks import pre
        pre.run(sys.argv[2])

    elif command == "finish":
        if len(sys.argv) < 3:
            print("Usage: adapter.py finish <task_description> [transcript_path]")
            sys.exit(1)
        # Import dynamically
        from .hooks import post
        task_desc = sys.argv[2]
        transcript_path = sys.argv[3] if len(sys.argv) > 3 else None
        post.run(task_desc, transcript_path)

    elif command == "cleanup":
        cleanup.run()

    elif command == "domains":
        domains.run()
    elif command == 'init-rules':
        init_rules.run()
    else:
        print(f"Unknown command: {command}")
        sys.exit(1)

if __name__ == "__main__":
    main()
