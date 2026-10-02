# CHANGES — tailored.tex

Target: **Senior Product Engineer - Americas** @ Ashby
Source: `20260310 Danish Faruqi Resume.tex` (text-only edits; preamble, macros, layout, and sectioning untouched)

## Edits

1. Rayze bullet 1: "Architected and deployed" -> "Owned end-to-end development of" -> targets the role's core requirement of engineers owning projects end-to-end (React/TypeScript stack context).
2. JPMC 2022-2025 bullet 3: "...to create a scalable and maintainable codebase" -> "owning features end-to-end from product spec to deployment" -> targets end-to-end product ownership; keeps React, TypeScript prominent.
3. JPMC 2021-2022 bullet 2: "Managed production and QA release deployments" -> "Managed CI/CD production and QA release deployments" -> targets CI/CD (required).
4. NYC Dept. of Records bullet 2: "Implemented advanced search functionality" -> "Implemented RESTful search functionality" -> targets REST (required); Flask HTTP endpoints make this honest.
5. Languages line: reordered to "TypeScript, JavaScript, Python, SQL, PostgreSQL, ..." -> surfaces required terms TypeScript, JavaScript, SQL, PostgreSQL first. Same item set, no additions.
6. Technologies line: reordered so Ashby's stack leads (React, Node.js, Redis, API Design (REST, GraphQL), CI/CD, AWS...) and added Redis, GraphQL, REST, Snowflake, Jira, Notion -> targets required terms Redis, GraphQL, REST, Snowflake, Jira, Notion.

## Required-term coverage

| Term | Status |
|---|---|
| TypeScript, JavaScript, React, Node.js, PostgreSQL, SQL, CI/CD, Notion | Already on resume; kept/reordered for prominence |
| REST | Added: "RESTful" (NYC Records bullet) + "API Design (REST, GraphQL)" |
| GraphQL | Added once to Technologies list only (adjacent to existing "API Design" skill; no project claims) |
| Redis | Added once to Technologies list only (plausible alongside existing RDS/Cassandra data work; no project claims) |
| Snowflake | Added once to Technologies list only (adjacent to existing data-workflow/data-management background; no project claims) |
| Jira | Added once to Technologies list (standard tooling at JPMC-scale engineering orgs) |
| Kotlin, Swift | **Omitted** — no plausible basis (mobile experience is React Native; JD lists them only as languages other engineers switched from and explicitly does not require them) |

## Guards

- `tectonic resume/tailored.tex` — exit 0
- Pages: original = 2, tailored = 2 (passes <= original)
- Original .tex and PDF unmodified.
