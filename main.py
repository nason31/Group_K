"""
Project Okavango Entry Point

This script serves as the main entry point for launching the Project Okavango
Streamlit dashboard.

Usage
-----
Run this script to start the application:

>>> python main.py

This will launch the Streamlit web application in your default browser.

Alternatively, you can run Streamlit directly:

>>> streamlit run app/streamlit_app.py

Notes
-----
- Ensure all dependencies are installed before running
- The app will download required datasets on first run
- Subsequent runs will use cached data for faster loading
"""

import os
import subprocess
import sys


def main():
    """Launch the Project Okavango Streamlit dashboard."""
    app_path = os.path.join("app", "streamlit_app.py")
    
    if not os.path.exists(app_path):
        print(f"Error: Could not find {app_path}")
        print("Please ensure you're running this script from the project root directory.")
        sys.exit(1)
    
    print("🌍 Launching Project Okavango Dashboard...")
    print(f"Starting Streamlit app: {app_path}\n")
    
    try:
        subprocess.run(["streamlit", "run", app_path], check=True)
    except FileNotFoundError:
        print("\n❌ Error: Streamlit is not installed or not in PATH.")
        print("Install it with: pip install streamlit")
        sys.exit(1)
    except KeyboardInterrupt:
        print("\n\n👋 Shutting down Project Okavango Dashboard...")
        sys.exit(0)


if __name__ == "__main__":
    main()
