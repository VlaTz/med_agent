"""Tool: literature search via the Europe PMC REST API.

Europe PMC mirrors PubMed/PMC content, needs no API key, and returns PMID/DOI
directly -- simpler than raw NCBI E-utilities for a prototype.
"""
from __future__ import annotations

from typing import Optional

import httpx

from src.schemas import SourceRecord
from src.tools.cache import cached

BASE_URL = "https://www.ebi.ac.uk/europepmc/webservices/rest/search"


@cached("europe_pmc_search")
def search_literature(
    query: str,
    year_from: int,
    max_results: int = 20,
) -> list[SourceRecord]:
    """Search Europe PMC for `query`, restricted to publications from `year_from` onward."""
    params = {
        "query": f"({query}) AND PUB_YEAR:[{year_from} TO 2026]",
        "format": "json",
        "pageSize": max_results,
        "resultType": "core",
    }
    with httpx.Client(timeout=20.0) as client:
        resp = client.get(BASE_URL, params=params)
        resp.raise_for_status()
        payload = resp.json()

    records: list[SourceRecord] = []
    for hit in payload.get("resultList", {}).get("result", []):
        pmid = hit.get("pmid")
        doi = hit.get("doi")
        year_raw: Optional[str] = hit.get("pubYear")
        records.append(
            SourceRecord(
                source="europe_pmc",
                pmid=pmid,
                doi=doi,
                title=hit.get("title", "").strip(),
                year=int(year_raw) if year_raw and year_raw.isdigit() else None,
                abstract=hit.get("abstractText"),
                url=f"https://europepmc.org/article/MED/{pmid}" if pmid else (f"https://doi.org/{doi}" if doi else None),
                raw=hit,
            )
        )
    return records


@cached("europe_pmc_lookup")
def lookup_by_id(pmid: Optional[str] = None, doi: Optional[str] = None) -> Optional[SourceRecord]:
    """Re-query a single record by ID, used by the reviewer to verify a citation exists."""
    if not pmid and not doi:
        return None
    query = f"EXT_ID:{pmid} AND SRC:MED" if pmid else f'DOI:"{doi}"'
    results = search_literature(query, year_from=1990, max_results=1)
    return results[0] if results else None
