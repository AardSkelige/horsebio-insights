import time

import requests


def send(call, pauses, unavailable, refused):
    for pause in (*pauses, None):
        try:
            response = call()
        except requests.RequestException as exc:
            error = unavailable(exc)
        else:
            if response.status_code < 300:
                return response
            error = refused(response)
            if response.status_code != 429 and response.status_code < 500:
                raise error
        if pause is None:
            raise error
        time.sleep(pause)
