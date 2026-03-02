import argparse
import subprocess
import os
import sys

def main():
    parser = argparse.ArgumentParser(description="JAYA-RESEARCH CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)
    
    # Run command (Backend)
    subparsers.add_parser("run", help="Start the Research API (Backend)")
    
    # Dashboard command (Frontend)
    subparsers.add_parser("dashboard", help="Start the UI Dashboard (Frontend)")

    args = parser.parse_args()

    base_dir = os.path.dirname(os.path.abspath(__file__))
    
    if args.command == "run":
        print("Starting Research API (Backend)...")
        target = os.path.join(base_dir, "src", "network", "research_api.py")
        try:
            subprocess.run([sys.executable, target], cwd=base_dir)
        except KeyboardInterrupt:
            print("\nBackend stopped.")
        
    elif args.command == "dashboard":
        print("Starting Dashboard (Frontend)...")
        ui_dir = os.path.join(base_dir, "ui")
        if not os.path.exists(ui_dir):
            print(f"Error: UI directory not found at {ui_dir}")
            sys.exit(1)
            
        shell = True if os.name == 'nt' else False
        try:
            subprocess.run(["npm", "run", "dev"], cwd=ui_dir, shell=shell)
        except KeyboardInterrupt:
            print("\nDashboard stopped.")

if __name__ == "__main__":
    main()
