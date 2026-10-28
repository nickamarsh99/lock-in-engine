"""Pull new raw clips from the "Lock-In Raw" Google Drive folder.

    python -m lockin.drive list            # clips in the folder
    python -m lockin.drive pull --skip-ids done.txt --out inbox/

Reads two environment variables, set in the Claude environment's settings:
  GDRIVE_SA_JSON        the service account's JSON key (the whole file's contents)
  GDRIVE_RAW_FOLDER_ID  the folder's ID, from its Drive URL

The service account has read-only access to that one folder. Name clips with the
post date first (2026-10-29.mov, or "2026-10-29 sunlight.mov") so each clip
matches its post in the engine.
"""
import argparse
import io
import json
import os
import re
import sys
from pathlib import Path

SCOPES = ["https://www.googleapis.com/auth/drive.readonly"]
VIDEO = re.compile(r"\.(mov|mp4|m4v|webm)$", re.I)


def service():
    key, folder = os.environ.get("GDRIVE_SA_JSON"), os.environ.get("GDRIVE_RAW_FOLDER_ID")
    if not key or not folder:
        sys.exit("Set GDRIVE_SA_JSON and GDRIVE_RAW_FOLDER_ID in the environment settings, then start a new session.")
    from google.oauth2 import service_account
    from googleapiclient.discovery import build
    creds = service_account.Credentials.from_service_account_info(json.loads(key), scopes=SCOPES)
    return build("drive", "v3", credentials=creds, cache_discovery=False), folder


def list_clips(svc, folder):
    q = f"'{folder}' in parents and trashed = false and mimeType contains 'video/'"
    files, token = [], None
    while True:
        r = svc.files().list(q=q, fields="nextPageToken, files(id, name, size, createdTime, mimeType)",
                             orderBy="createdTime", pageToken=token, pageSize=100).execute()
        files += r.get("files", [])
        token = r.get("nextPageToken")
        if not token:
            return files


def clip_date(name):
    m = re.match(r"(\d{4}-\d{2}-\d{2})", name)
    return m.group(1) if m else None


def download(svc, f, out_dir):
    from googleapiclient.http import MediaIoBaseDownload
    dest = Path(out_dir) / f"{f['id']}-{re.sub(r'[^A-Za-z0-9._-]+', '_', f['name'])}"
    with io.FileIO(dest, "wb") as fh:
        dl = MediaIoBaseDownload(fh, svc.files().get_media(fileId=f["id"]), chunksize=16 * 1024 * 1024)
        done = False
        while not done:
            _, done = dl.next_chunk()
    return dest


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=["list", "pull"])
    ap.add_argument("--skip-ids", help="file of Drive IDs already processed, one per line")
    ap.add_argument("--out", default="inbox")
    a = ap.parse_args(argv)
    svc, folder = service()
    clips = [f for f in list_clips(svc, folder) if VIDEO.search(f["name"]) or f["mimeType"].startswith("video/")]
    skip = set(Path(a.skip_ids).read_text().split()) if a.skip_ids and Path(a.skip_ids).exists() else set()
    new = [f for f in clips if f["id"] not in skip]
    if a.cmd == "list":
        for f in clips:
            print(f"{'new ' if f in new else 'done'}  {f['id']}  {clip_date(f['name']) or '(no date)'}  {f['name']}")
        return
    Path(a.out).mkdir(parents=True, exist_ok=True)
    pulled = []
    for f in new:
        path = download(svc, f, a.out)
        pulled.append({"id": f["id"], "name": f["name"], "date": clip_date(f["name"]), "path": str(path)})
        print(f"pulled {f['name']} -> {path}", file=sys.stderr)
    print(json.dumps(pulled, indent=1))


if __name__ == "__main__":
    main()
