# Aryan — APT29 Raw Collection Queue

Status values:

- `discovered` — source located
- `cataloged` — metadata and rights recorded
- `preserved` — original artifact downloaded and hashed
- `blocked` — unavailable, gated, or legally unclear

Do not normalize or deduplicate material during this phase.

## Public logs and datasets

| Source | Material | Expected formats | Status |
|---|---|---|---|
| OTRF Security Datasets APT29 Day 1 | Host and network telemetry, per-host and combined Zeek, PCAPs | ZIP, JSON, Zeek TSV, PCAP | preserved |
| OTRF Security Datasets APT29 Day 2 | Host and network telemetry, per-host and combined Zeek, PCAPs | ZIP, JSON, Zeek TSV, PCAP | preserved |
| OTRF APT29 evaluation material | Dataset documentation and emulation workbook | Markdown, XLSX | preserved |
| OTRF atomic/compound datasets related to APT29 techniques | Technique-level Windows telemetry | JSON, EVTX, ZIP | discovered |
| Splunk Attack Data WINELOADER | Three Sysmon Event ID 7 records for DLL side-loading plus metadata | XML event text, YAML | preserved |
| Independent APT audit-log research datasets | Scenario telemetry requiring provenance review | JSON or eCAR-like records | discovered |

## Structured IOC collections

| Source | Material | Expected formats | Status |
|---|---|---|---|
| Microsoft MSTIC May 2021 NOBELIUM | 127 campaign indicators: 78 SHA-256, 41 domains, 7 IPs, and 1 URL | CSV | preserved |
| CISA APT29/SVR advisories | AA21-116A and AA23-347A TeamCity advisory preserved | PDF | preserved-partial |
| UK NCSC APT29 advisories | COVID-19, Further SVR TTPs, and 2024 cloud-access advisories preserved | PDF | preserved-partial |
| Mandiant APT29 technical annexes | Campaign hashes, domains, URLs, and malware names | HTML tables and appendices | discovered |
| Vendor GitHub indicator repositories | Report-linked indicator exports | CSV, JSON, TXT, STIX | discovered |
| ESET Operation Ghost | MISP event, MD5/SHA-1/SHA-256 lists, narrative IOC list, and white paper | JSON, text, ADOC, PDF | preserved |
| Mandiant SUNBURST countermeasures | Indicator CSVs, YARA, Snort, ClamAV, and OpenIOC material | CSV, YARA, rules, LDB, IOC | preserved |

## Reports and advisories

| Publisher | Initial targets | Status |
|---|---|---|
| Mandiant / Google Threat Intelligence | Trello phishing, UNC2452 merge, Credential Roaming, WINELOADER, Microsoft 365 operations | cataloged |
| Microsoft Threat Intelligence | NOBELIUM toolset, 2024 RDP campaign, responder guidance, and 2026 CaptiveCrunch | cataloged |
| CISA / FBI / NSA | Russian SVR operations and related joint advisories | cataloged |
| UK NCSC and partners | APT29 targeting, SVR tradecraft, and cloud initial-access advisories | preserved-partial |
| ESET Research | Operation Ghost / Dukes technical report and structured IOCs | preserved |
| F-Secure / WithSecure | The Dukes historical white paper; current direct URL redirects instead of returning PDF | blocked |
| Google Threat Intelligence Group | 2025 UNC6293 ASP/OAuth/device-code phishing; association to APT29 is explicitly low confidence | cataloged |
| Other incident-response vendors | Reports with firsthand APT29 observations or report-linked artifacts | discovered |

## Detection and research artifacts

| Artifact class | Collection target | Status |
|---|---|---|
| Sigma | 30 raw keyword-matching rules preserved; relevance review deferred | preserved-partial |
| YARA | NCSC/CISA report-embedded rules plus Mandiant standalone rules preserved | preserved-partial |
| Hunting queries | Microsoft Defender historical repo and 46 Sentinel YAML candidates preserved | preserved-partial |
| STIX/MISP | Seven MISP Galaxy source clusters plus license preserved without filtering | preserved-partial |
| Malware metadata | Hashes, family names, timestamps, and relationships; no binaries | discovered |
| ATT&CK mappings | Group, campaign, software, and technique mappings for cross-reference | discovered |

## Collection record required for every artifact

```yaml
artifact_id: unique-id
source_id: parent-source-id
landing_page: https://...
direct_url: https://...
retrieved_at: ISO-8601 timestamp
published_at: ISO-8601 timestamp or null
original_filename: filename.ext
media_type: value
byte_size: 0
sha256: hex-digest
license: text or URL
redistribution: allowed | restricted | unknown
status: preserved | blocked
notes: []
```

## Phase-one boundaries

- Preserve original bytes when permitted.
- Store metadata even when downloading is restricted.
- Do not download malware samples.
- Do not execute scripts, payloads, documents, or binaries from collected sources.
- Do not resolve conflicting aliases or attribution claims yet.
- Do not remove stale indicators; preserve their historical context.
- Do not use GOAD until collection and corpus analysis are complete.
