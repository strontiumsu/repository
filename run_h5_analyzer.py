#!/usr/bin/env python3
"""
Simple launcher script for the H5 Image Analyzer GUI.
This script can be used to run the analyzer from the command line.
"""

import sys
import os

# Add current directory to Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    from h5_image_analyzer import main
    main()
except ImportError as e:
    print(f"Error importing required modules: {e}")
    print("Please install the required dependencies:")
    print("pip install -r requirements.txt")
    sys.exit(1)
except Exception as e:
    print(f"Error running H5 Image Analyzer: {e}")
    sys.exit(1)
