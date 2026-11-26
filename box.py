"""Box, through the Sprites connector gateway."""

import json
import secrets
import urllib.parse

import gateway

PAGE = 1000
FILE_FIELDS = "id,type,name,sha1,modified_at,size,extension"


def _multipart(attributes, filename, data):
    """Box upload body: the attributes part must come before the file part."""
    boundary = "roost-" + secrets.token_hex(12)
    safe = filename.replace('"', "").replace("\r", "").replace("\n", "")
    body = b"".join([
        f"--{boundary}\r\n".encode(),
        b'Content-Disposition: form-data; name="attributes"\r\n\r\n',
        json.dumps(attributes).encode(), b"\r\n",
        f"--{boundary}\r\n".encode(),
        f'Content-Disposition: form-data; name="file"; filename="{safe}"\r\n'.encode(),
        b"Content-Type: application/octet-stream\r\n\r\n",
        data, b"\r\n",
        f"--{boundary}--\r\n".encode(),
    ])
    return body, f"multipart/form-data; boundary={boundary}"


class Box:
    def _url(self, path, **params):
        url = gateway.base_url("box") + path
        return url + ("?" + urllib.parse.urlencode(params) if params else "")

    def folder_items(self, folder_id):
        """All entries in a folder, following offset pagination."""
        items, offset = [], 0
        while True:
            page = gateway.request(
                "GET",
                self._url(f"/2.0/folders/{folder_id}/items", fields=FILE_FIELDS, limit=PAGE, offset=offset),
            )
            entries = page.get("entries", [])
            items.extend(entries)
            offset += len(entries)
            if not entries or offset >= page.get("total_count", 0):
                return items

    def find_folder(self, name, parent_id="0"):
        """Id of the folder called `name` directly inside `parent_id`, or None."""
        for item in self.folder_items(parent_id):
            if item.get("type") == "folder" and item.get("name") == name:
                return item["id"]
        return None

    def ensure_folder(self, name, parent_id):
        """Id of folder `name` inside `parent_id`, creating it if needed."""
        try:
            return gateway.request("POST", self._url("/2.0/folders"),
                                   {"name": name, "parent": {"id": parent_id}})["id"]
        except gateway.GatewayError as e:
            if e.status == 409:  # already exists; Box names the existing item
                try:
                    return json.loads(e.body)["context_info"]["conflicts"][0]["id"]
                except (ValueError, KeyError, IndexError):
                    found = self.find_folder(name, parent_id)
                    if found:
                        return found
            raise

    def download(self, file_id):
        return gateway.request("GET", self._url(f"/2.0/files/{file_id}/content"), raw=True)

    def upload(self, folder_id, name, data):
        """Upload a new file; if the name is taken, upload a new version of that file.
        Returns the file entry."""
        body, ctype = _multipart({"name": name, "parent": {"id": folder_id}}, name, data)
        try:
            resp = gateway.request("POST", self._url("/upload/files/content"), body, {"Content-Type": ctype})
        except gateway.GatewayError as e:
            if e.status != 409:
                raise
            try:
                existing = json.loads(e.body)["context_info"]["conflicts"]["id"]
            except (ValueError, KeyError, TypeError):
                raise e from None
            return self.replace(existing, name, data)
        return resp["entries"][0]

    def replace(self, file_id, name, data):
        """Upload new content as a new version of an existing file."""
        body, ctype = _multipart({"name": name}, name, data)
        resp = gateway.request("POST", self._url(f"/upload/files/{file_id}/content"), body, {"Content-Type": ctype})
        return resp["entries"][0]

    def rename(self, file_id, name):
        return gateway.request("PUT", self._url(f"/2.0/files/{file_id}"), {"name": name})
