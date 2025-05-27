#!/usr/bin/env python
# -*- coding: utf-8 -*-

import argparse
import os
import sys
from app import app, socketio

def main():
    """Main entry point for the CLI."""
    parser = argparse.ArgumentParser(
        description="Stimulus Generator - Experiment Stimulus Generation Tool"
    )
    
    subparsers = parser.add_subparsers(dest="command", help="commands")
    
    # webui command
    webui_parser = subparsers.add_parser("webui", help="start Web interface")
    webui_parser.add_argument("--host", type=str, default="0.0.0.0", help="host address")
    webui_parser.add_argument("--port", type=int, default=5000, help="port number")
    webui_parser.add_argument("--debug", action="store_true", help="enable debug mode")
    webui_parser.add_argument("--share", action="store_true", help="create public link")
    
    # Parse arguments
    args = parser.parse_args()
    
    # Handle commands
    if args.command == "webui":
        print(f"Starting Stimulus Generator Web interface...")
        print(f"Access http://127.0.0.1:{args.port} to open the Web interface")
        
        # Start the web server
        socketio.run(
            app,
            host=args.host,
            port=args.port,
            debug=args.debug,
            allow_unsafe_werkzeug=True,
            log_output=args.debug
        )
    else:
        parser.print_help()
        return 1
    
    return 0

if __name__ == "__main__":
    sys.exit(main()) 