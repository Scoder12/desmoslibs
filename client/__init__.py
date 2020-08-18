"""Client for interacting with desmos."""
import requests
import os
import base64
import json


try:
    with open("thumb.png", "rb") as f:
        thumb_data = "data:image/png;base64," + base64.b64encode(f.read()).decode()
except:
    raise OSError("Unable to open thumb.png, no image to use for thumbnail")


def check_status(r, expect=200):
    if r.status_code != expect:
        raise AssertionError(
            f"Excepted code {expect} got {r.status_code}, text: {r.text}"
        )


def request_assert(r, cond):
    if not cond:
        raise AssertionError(f"Assertion failed, text {r.text!r}")


def tryjson(r):
    try:
        return r.json()
    except:
        raise AssertionError(f"Unable to decode json from {r.text!r}")


headers = {
    "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/80.0.3987.149 Safari/537.36",
    "x-requested-with": "XMLHttpRequest",
}


class DesmosClient:
    def __init__(self):
        self.s = requests.Session()

    def login(self, email, password):
        r = self.s.post(
            "https://www.desmos.com/account/login_xhr",
            data={"email": email, "password": password},
            headers=headers,
        )
        check_status(r)
        request_assert(r, r.text == "{}")

    def _save(self, data):
        r = self.s.post("https://www.desmos.com/api/v1/calculator/save", data=data)
        check_status(r)
        return r.json()

    def create(self, data, graph_hash):
        return self._save(
            {
                "thumb_data": thumb_data,
                "graph_hash": graph_hash,
                "my_graphs": "true",
                "is_update": "false",
                "calc_state": json.dumps(data, separators=(",", ":")),
            }
        )

    def update(self, data, graph_hash, parent_hash):
        return self._save(
            {
                "parent_hash": parent_hash,
                "recovery_parent_hash": parent_hash,
                "thumb_data": thumb_data,
                "graph_hash": graph_hash,
                "my_graphs": "true",
                "is_update": "true",
                "calc_state": json.dumps(data, separators=(",", ":")),
            }
        )
