"""Pull build history from a Jenkins server's JSON API.
Env: JENKINS_URL, JENKINS_USER, JENKINS_API_TOKEN (user/token optional for open servers)."""
import os
from datetime import datetime, timezone
from urllib.parse import quote

import requests

from .schemas import BuildIn


def fetch_builds(job: str, limit: int = 100) -> list[BuildIn]:
    base = os.getenv("JENKINS_URL")
    if not base:
        raise RuntimeError("JENKINS_URL is not set")
    auth = (os.getenv("JENKINS_USER"), os.getenv("JENKINS_API_TOKEN")) if os.getenv("JENKINS_USER") else None
    path = "/".join(f"job/{quote(p)}" for p in job.split("/"))  # supports folder/job names
    tree = f"allBuilds[number,result,duration,timestamp,url]{{0,{limit}}}"
    resp = requests.get(f"{base.rstrip('/')}/{path}/api/json", params={"tree": tree}, auth=auth, timeout=30)
    resp.raise_for_status()

    out = []
    for b in resp.json().get("allBuilds", []):
        if b.get("result") is None:  # still running
            continue
        started = datetime.fromtimestamp(b["timestamp"] / 1000, timezone.utc).replace(tzinfo=None)
        out.append(BuildIn(job_name=job, build_number=b["number"], status=b["result"],
                           duration_ms=b["duration"], started_at=started, url=b.get("url")))
    return out
