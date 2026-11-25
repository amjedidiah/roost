"""Box, through the Sprites connector gateway."""

import urllib.parse

import gateway

PAGE = 1000
FILE_FIELDS = "id,type,name,sha1,modified_at,size,extension"


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

    def download(self, file_id):
        return gateway.request("GET", self._url(f"/2.0/files/{file_id}/content"), raw=True)
