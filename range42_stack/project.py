"""Render a project component from JSON on stdin without accessing infrastructure."""
import json
from pathlib import Path
import sys
from .plan import project_component


def main():
    try:
        result = project_component(json.load(sys.stdin), Path(__file__).resolve().parent.parent)
    except (ValueError, OSError, KeyError, TypeError) as error:
        print(json.dumps({'error': str(error)}))
        raise SystemExit(2) from None
    print(json.dumps(result))


if __name__ == '__main__':
    main()
