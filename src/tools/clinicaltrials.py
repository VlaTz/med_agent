"""Tool: trial registry search via the ClinicalTrials.gov API v2."""
from __future__ import annotations

from typing import Optional

import httpx

from src.schemas import SourceRecord
from src.tools.cache import cached

BASE_URL = "https://clinicaltrials.gov/api/v2/studies"


def _extract_year(date_str: Optional[str]) -> Optional[int]:
    if not date_str or len(date_str) < 4:
        return None
    try:
        return int(date_str[:4])
    except ValueError:
        return None


@cached("clinicaltrials_search")
def search_trials(condition: str, intervention: str, year_from: int, max_results: int = 20) -> list[SourceRecord]:
    """Search ClinicalTrials.gov v2 for trials matching a condition + intervention."""
    params = {
        "query.cond": condition,
        "query.intr": intervention,
        "pageSize": max_results,
        "sort": "LastUpdatePostDate:desc",
        "format": "json",
    }
    with httpx.Client(timeout=20.0) as client:
        resp = client.get(BASE_URL, params=params)
        resp.raise_for_status()
        payload = resp.json()

    records: list[SourceRecord] = []
    for study in payload.get("studies", []):
        protocol = study.get("protocolSection", {})
        ident = protocol.get("identificationModule", {})
        status = protocol.get("statusModule", {})
        design = protocol.get("designModule", {})
        nct_id = ident.get("nctId")
        year = _extract_year(status.get("startDateStruct", {}).get("date"))
        if year_from and year and year < year_from:
            continue
        records.append(
            SourceRecord(
                source="clinicaltrials",
                nct_id=nct_id,
                title=ident.get("briefTitle", "").strip(),
                year=year,
                abstract=protocol.get("descriptionModule", {}).get("briefSummary"),
                url=f"https://clinicaltrials.gov/study/{nct_id}" if nct_id else None,
                raw={
                    "phase": design.get("phases", []),
                    "enrollment": design.get("enrollmentInfo", {}).get("count"),
                    "overall_status": status.get("overallStatus"),
                    **study,
                },
            )
        )
    return records


@cached("clinicaltrials_lookup")
def lookup_by_nct(nct_id: str) -> Optional[SourceRecord]:
    """Re-query a single trial by NCT ID, used by the reviewer to verify a citation exists."""
    with httpx.Client(timeout=20.0) as client:
        resp = client.get(f"{BASE_URL}/{nct_id}", params={"format": "json"})
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        study = resp.json()

    protocol = study.get("protocolSection", {})
    ident = protocol.get("identificationModule", {})
    status = protocol.get("statusModule", {})
    return SourceRecord(
        source="clinicaltrials",
        nct_id=ident.get("nctId"),
        title=ident.get("briefTitle", "").strip(),
        year=_extract_year(status.get("startDateStruct", {}).get("date")),
        abstract=protocol.get("descriptionModule", {}).get("briefSummary"),
        url=f"https://clinicaltrials.gov/study/{ident.get('nctId')}",
        raw=study,
    )
