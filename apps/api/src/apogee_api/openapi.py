"""Print the OpenAPI schema: ``python -m apogee_api.openapi > openapi.json``.

Used by ``make codegen``; needs no database or Redis.
"""

import json

from apogee_api.main import create_app

if __name__ == "__main__":
    print(json.dumps(create_app().openapi(), indent=2, sort_keys=True))
