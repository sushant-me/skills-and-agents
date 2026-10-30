import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from mcpaudit.cli import main
if __name__ == "__main__":
    sys.exit(main())
