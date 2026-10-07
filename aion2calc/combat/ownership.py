"""Private per-upload credentials, kept outside exported combat documents."""
import json
import re
import threading
import urllib.error
import urllib.parse
import urllib.request

from ..paths import data_file, read_json, write_user_json

FILE = ("log-ownership.json",)
LOCK = threading.RLock()
LIMIT = 2000


def clean(row):
    if not isinstance(row, dict):
        raise ValueError("Invalid upload credential")
    server = str(row.get("server") or "").rstrip("/")
    url = urllib.parse.urlsplit(server)
    if url.scheme not in ("https","http") or not url.hostname or url.username or url.password or url.query or url.fragment:
        raise ValueError("Invalid original server address")
    log_id, token = row.get("id"), row.get("delete_token")
    if not isinstance(log_id,str) or not re.fullmatch(r"[A-Za-z0-9]{6,16}",log_id):
        raise ValueError("Invalid upload ID")
    if not isinstance(token,str) or not re.fullmatch(r"[A-Za-z0-9_-]{20,128}",token):
        raise ValueError("Invalid private upload credential")
    return {"server":server,"id":log_id,"delete_token":token,"title":str(row.get("title") or log_id)[:200]}


def entries():
    with LOCK:
        rows = read_json(*FILE) if data_file(*FILE).exists() else []
        return [clean(row) for row in rows]


def merge(rows):
    if not isinstance(rows,list) or len(rows) > LIMIT:
        raise ValueError("Ownership backup must contain at most 2,000 credentials")
    validated = [clean(row) for row in rows]
    with LOCK:
        values = {(r["server"],r["id"]):r for r in entries()}
        for row in validated:
            values[(row["server"],row["id"])] = row
        if len(values) > LIMIT:
            raise ValueError("Ownership storage is full; back up and forget unused entries first")
        write_user_json(list(values.values()), *FILE)
        return list(values.values())


def remember(server, result, title=""):
    merge([{"server":server,"id":result["id"],"delete_token":result["delete_token"],"title":title}])


def forget(server, log_id):
    with LOCK:
        rows = [row for row in entries() if (row["server"],row["id"]) != (server,log_id)]
        write_user_json(rows,*FILE)
        return rows


def request(row, action, visibility=None):
    from .share import effective
    row = clean(row)
    if row["server"] != str(effective().get("url") or "").rstrip("/"):
        raise ValueError("Select this upload's original server in Settings before managing it")
    if action not in ("refresh","open","visibility","rotate","delete"):
        raise ValueError("Unknown upload management action")
    target = row["server"] + "/api/v1/logs/" + row["id"]
    headers = {"X-Log-Token":row["delete_token"],"User-Agent":"aion2calc"}
    body = None
    method = "GET"
    if action == "refresh":
        target += "/ownership"
    elif action == "open":
        target += "/raw"
    elif action == "delete":
        method = "DELETE"
    else:
        if visibility not in ("public","unlisted","private"):
            raise ValueError("Invalid visibility")
        target += "/visibility"
        method = "PUT"
        headers["Content-Type"] = "application/json"
        body = json.dumps({"visibility":visibility,"rotate":action=="rotate"}).encode()
    # Never forward an owner secret through an HTTP redirect to another destination.
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, newurl):
            return None
    try:
        req = urllib.request.Request(target,body,headers,method=method)
        with urllib.request.build_opener(NoRedirect).open(req,timeout=30) as response:
            result = json.load(response)
    except urllib.error.HTTPError as exc:
        raise ValueError(f"Upload management refused ({exc.code}); check the original server and private credential") from None
    if action == "delete":
        forget(row["server"],row["id"])
    return result
