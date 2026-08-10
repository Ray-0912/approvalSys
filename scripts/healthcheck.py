from flask import current_app
import sys

sys.path.insert(0, '.')

from main import app


if __name__ == '__main__':
    with app.test_client() as client:
        response = client.get('/healthz')
        if response.status_code == 200:
            print('ok')
            raise SystemExit(0)
        print(response.get_data(as_text=True))
        raise SystemExit(1)
