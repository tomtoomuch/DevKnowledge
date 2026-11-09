"""Executed inside the disposable KMS container against the actual Gateway."""
import json
import urllib.error
import urllib.request

BASE = "http://api-gateway:3107"


def call(method, path, payload=None, raw=None, extra_headers=None):
    data = json.dumps(payload).encode() if payload is not None else raw
    headers = {"Content-Type": "application/json", **(extra_headers or {})}
    if method in ("PATCH", "DELETE") and "If-Match" not in headers:
        current_status, current = call("GET", path)
        revision = current["revision"] if current_status == 200 else 0
        headers["If-Match"] = f'"{revision}"'
    request = urllib.request.Request(BASE + path, data=data, headers=headers, method=method)
    try:
        response = urllib.request.urlopen(request, timeout=15)
    except urllib.error.HTTPError as error:
        response = error
    with response:
        body = response.read()
        return response.status, json.loads(body) if body else None


path = "/api/v1/knowledges"
status, item = call("POST", path, {
    "knowledge_type": "COURSE_NOTE", "title": "Gateway end-to-end",
    "content": "Contenu transmis sans altération.",
}, extra_headers={"X-User-Id": "untrusted", "Authorization": "Bearer untrusted"})
assert status == 201, (status, item)
assert item["created_by_user_id"] is None
identifier = item["knowledge_id"]
item_path = path + "/" + identifier
try:
    assert call("GET", item_path) == (200, item)
    status, page = call("GET", path + "?knowledge_type=COURSE_NOTE&status=DRAFT&skip=0&limit=1")
    assert status == 200 and page["limit"] == 1 and page["total"] == 1
    assert page["items"][0]["knowledge_id"] == identifier
    status, updated = call("PATCH", item_path, {"title": "Titre modifié", "is_favorite": True})
    assert status == 200 and updated["is_favorite"] and updated["title"] == "Titre modifié"
    assert updated["revision"] == item["revision"] + 1
    status, matches = call("GET", path + "?q=titre&is_favorite=true&knowledge_type=COURSE_NOTE")
    assert status == 200 and matches["total"] == 1
    assert matches["items"][0]["knowledge_id"] == identifier
    assert call("GET", path + "?q=missing&is_favorite=true")[1]["total"] == 0
    assert call("GET", path + "?q=%20%20")[0] == 422
    assert call("PATCH", item_path, {"title": "stale"}, extra_headers={"If-Match": f'"{item["revision"]}"'})[0] == 412
    assert call("DELETE", item_path, extra_headers={"If-Match": f'"{item["revision"]}"'})[0] == 412
    assert call("PATCH", item_path, {"title": None})[0] == 422
    assert call("POST", path, raw=b'{"invalid":')[0] == 422
    assert call("GET", path + "?limit=0")[0] == 422
    assert call("GET", path + "/not-a-uuid")[0] == 422
    assert call("PUT", item_path, {})[0] == 405
    assert call("DELETE", item_path) == (204, None)
    assert call("GET", item_path)[0] == 404
    assert call("DELETE", item_path)[0] == 404
    status, page = call("GET", path + "/?limit=1")
    assert status == 200 and page["total"] == 0
finally:
    call("DELETE", item_path)
print("Gateway CRUD: 5 operations, filters, raw JSON, 204/404/405/422, anonymous identity OK")
