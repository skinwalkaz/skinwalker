# Aryan Research Lane — APT29 Reconnaissance

## Scope

Identify authoritative government and vendor reporting that provides one or more of the following:

- Attributed APT29 procedures
- Host or network indicators
- Detection guidance
- ATT&CK mappings
- Procedures suitable for controlled GOAD emulation

This phase is collection only. Preserve reports, IOC files, advisories, log datasets, and their provenance without normalizing them for the agent. The collected material is not proof that any single behavior or indicator uniquely identifies APT29.

## Alias handling

Track publisher-specific names without silently treating them as perfectly equivalent:

| Name | Publisher or context |
|---|---|
| APT29 | MITRE and Mandiant usage |
| Midnight Blizzard | Current Microsoft usage |
| NOBELIUM | Earlier Microsoft usage |
| UNC2452 | Mandiant cluster later merged into APT29 |
| Cozy Bear, The Dukes | Common public aliases |
| SVR cyber actors | Government attribution context |

Store the source's original name on every observation and resolve it to an internal actor only through a sourced alias relationship.

## Prioritized sources

### Priority 1 — Mandiant: Tracking APT29 Phishing Campaigns

- Source: [Tracking APT29 Phishing Campaigns](https://cloud.google.com/blog/topics/threat-intelligence/tracking-apt29-phishing-campaigns/)
- Value: Detailed Windows and Active Directory procedures with commands and investigative context.
- Observable procedures include:
  - Domain user and administrator-group enumeration
  - Domain-controller discovery with `nltest`
  - Searching SYSVOL policy files for Group Policy Preference credentials
  - Registry Run Key persistence
  - SMB-based lateral movement
- GOAD suitability: **High**. These behaviors fit an isolated Active Directory lab and produce Windows, Sysmon, PowerShell, SMB, and domain-controller telemetry.
- IOC value: Campaign-specific and secondary to the documented behavior.
- Initial use: First structured vendor report and first Aryan-proposed GOAD scenario.

### Priority 1 — Mandiant: Windows Credential Roaming

- Source: [They See Me Roaming](https://cloud.google.com/blog/topics/threat-intelligence/apt29-windows-credential-roaming/)
- Value: Describes atypical LDAP queries and abuse of Active Directory Credential Roaming data.
- Observable evidence includes Windows Security Event ID 4662 and access to credential-roaming attributes.
- GOAD suitability: **Medium to high**, subject to confirming that the required feature and safe test conditions can be reproduced.
- Research value: Strong example of behavior-based hunting that is more useful than a short-lived IOC.

### Priority 1 — Microsoft: NOBELIUM early-stage toolset

- Source: [Breaking down NOBELIUM's latest early-stage toolset](https://www.microsoft.com/en-us/security/blog/?p=93658)
- IOC repository: [Microsoft MSTIC May 2021 NOBELIUM indicators](https://github.com/microsoft/mstic/tree/master/Indicators/May21-NOBELIUM)
- Value: EnvyScout, BoomBox, NativeZone, and VaporRage infection-chain reporting with a downloadable indicator collection.
- IOC types: File hashes, domains, URLs, and related campaign artifacts, subject to verification against the repository files.
- GOAD suitability: **Medium**. Emulate safe behaviors and execution chains; do not download or execute original malware.
- License note: The MSTIC repository states that documentation/content is CC BY 4.0 and code is MIT licensed.

### Priority 2 — Microsoft: NOBELIUM email campaign

- Source: [New sophisticated email-based attack from NOBELIUM](https://www.microsoft.com/security/blog/2021/05/27/new-sophisticated-email-based-attack-from-nobelium/)
- Value: Documents phishing, LNK/DLL execution, `rundll32`, payload deployment, and associated indicators.
- GOAD suitability: **Medium**. Start after endpoint ingestion works; simulate the execution chain with harmless payloads.

### Priority 2 — Mandiant: WINELOADER campaign

- Source: [APT29 Uses WINELOADER to Target German Political Parties](https://cloud.google.com/blog/topics/threat-intelligence/apt29-wineloader-german-political-parties)
- Value: Provides a technical annex, ATT&CK mappings, infrastructure, ROOTSAW delivery, DLL side-loading, and host discovery behavior.
- GOAD suitability: **Medium**. Reproduce observable procedure patterns with inert test components rather than malware.
- IOC value: Useful as historical campaign context; retain collection and validity dates.

### Priority 2 — CISA/FBI: Russian SVR operations

- Source: [AA21-116A — Russian Foreign Intelligence Service Cyber Operations](https://www.cisa.gov/sites/default/files/publications/AA21-116A_Russian_Foreign_Intelligence_Service_Cyber_Operations_508C.pdf)
- Value: Government attribution context, aliases, defensive guidance, and an overview of SVR targeting and tradecraft.
- GOAD suitability: **Low to medium** as a direct procedure source; high value for attribution provenance and cross-checking vendor claims.
- Redistribution note: Verify the treatment of jointly authored content before redistributing extracted material.

### Priority 3 — Mandiant: UNC2452 merged into APT29

- Source: [Assembling the Russian Nesting Doll](https://cloud.google.com/blog/topics/threat-intelligence/unc2452-merged-into-apt29/)
- Value: Documents Mandiant's reasoning for merging UNC2452 into APT29 and describes on-premises, cloud, credential, and operational-security behavior.
- GOAD suitability: **Low** for cloud-only procedures and **medium** for on-premises behaviors.
- Research value: Important for alias provenance and for separating reported attribution reasoning from raw observables.

## Candidate report for later structured extraction

### Report identity

```yaml
source_id: mandiant-apt29-trello-phishing
publisher: Mandiant
source_type: vendor-report
actor_name_in_source: APT29
redistribution: restricted-or-unknown
intended_use: derived-observations-with-citations
```

### Derived observations

| Observation | Evidence source | Expected telemetry | GOAD use |
|---|---|---|---|
| Actor enumerates domain users and privileged groups | Mandiant report | Sysmon process creation; Security 4688 | Safe discovery step |
| Actor discovers domain controllers | Mandiant report | Process creation and command line | Safe discovery step |
| Actor searches SYSVOL XML for stored GPP credentials | Mandiant report | Process, SMB share, file-access events | Strong AD hunting scenario |
| Actor establishes Run Key persistence | Mandiant report | Sysmon registry events; process lineage | Safe inert persistence test |
| Actor stages lateral movement over SMB | Mandiant report | Logons, share access, network connections, service/process events | Controlled multi-host scenario |

These are report-derived observations. They must retain the report URL and publication context when normalized.

## Deferred GOAD candidate

GOAD emulation is intentionally deferred until public-source collection, corpus inventory, normalization, and initial agent work are complete. The following candidate is retained only so useful source material is not lost.

Name: `apt29-ad-discovery-and-persistence-v1`

Scope:

1. Begin from an assumed-compromised, low-privilege workstation account.
2. Enumerate local administrators, domain users, privileged groups, and domain controllers.
3. Search a controlled SYSVOL fixture for a nonfunctional test credential marker.
4. Create inert user-level Run Key persistence.
5. Perform an authorized SMB connection to a second lab host using test credentials.
6. Remove created persistence and restore the snapshot.

Required telemetry:

- Sysmon process, registry, network, DNS, and file events
- Windows Security process creation, logon, and share-access events
- Domain-controller object-access auditing where applicable
- Packet or Zeek telemetry for SMB and DNS
- Exact execution timestamps and step results

Safety constraints:

- Isolated GOAD network only
- No original malware or public C2 infrastructure
- Inert files and synthetic credentials
- No internet-routable callbacks
- Snapshot before execution and cleanup afterward

## Source-quality rubric

Score each source from 0–2 in five areas:

1. **Provenance:** unclear, secondary, or firsthand/government-attributed
2. **Technical detail:** narrative only, partial observables, or reproducible procedures
3. **Temporal context:** absent, partial, or explicit first/last observed dates
4. **Detection value:** attribution only, IOC-only, or behavior plus telemetry guidance
5. **Reusability:** unclear rights, citation-only, or clearly licensed structured content

Never convert the total directly into attribution confidence. The score prioritizes research effort; it does not prove the publisher's analytic judgment.

## Immediate collection actions for Aryan

1. Inventory and preserve the Microsoft MSTIC APT29/NOBELIUM IOC files without transforming them.
2. Collect authoritative Mandiant, Microsoft, CISA, NCSC, and other vendor reports with their publication metadata.
3. Find public APT29 log datasets, record their formats and sizes, and hash downloaded archives.
4. Locate related public Sigma, YARA, STIX, MISP, and hunting-query artifacts.
5. Record direct artifact URLs, landing pages, retrieval dates, and license or redistribution terms.
6. Track dead links, gated downloads, duplicate indicators, and reports that cite one another.
7. Do not deduplicate, normalize, score, or convert the collected contents yet.

## Collection snapshot — 2026-09-18

- OTRF APT29 dataset: 124 files covering Day 1/Day 2 host telemetry, Zeek logs, PCAP archives, documentation, and the emulation workbook.
- Microsoft MSTIC: 127 May 2021 NOBELIUM indicators (78 SHA-256 hashes, 41 domains, 7 IP addresses, and 1 URL).
- Government advisories: CISA AA21-116A plus two NCSC technical advisories, including report-embedded indicators and detection material.
- Microsoft hunting content: archived Defender hunting repository plus 52 alias/campaign-matched Sentinel artifacts (46 YAML files).
- Detection rules: 30 raw Sigma candidates plus Mandiant YARA, Snort, ClamAV, and OpenIOC countermeasures retained for later manual relevance review.
- Structured context: seven full MISP Galaxy cluster files retaining actor aliases, campaigns, malware relationships, and references.
- Additional test telemetry: three raw Sysmon Event ID 7 records from Splunk Attack Data's WINELOADER DLL-side-loading dataset.

All raw third-party material remains under `data/raw/apt29/`, is excluded from Git, and has not been normalized or treated as proof of attribution.
