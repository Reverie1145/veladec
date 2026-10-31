#!/usr/bin/env python3
"""veladec entry point: python3 veladec.py <command> <target> [options]"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from veladec.cli import main

if __name__ == '__main__':
    sys.exit(main())
