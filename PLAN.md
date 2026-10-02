# resume-updater — implementation plan (standalone project)

## 1. Context (SRP: problem only)

- Problem Statement: Ashby postings bury required/preferred tools, languages, and software in bullets and paragraphs; nothing extracts them deterministically, so resume tailoring is manual.
- Business Value: a per-job requirements.json feeds an automated resume-tailor pass (phase B, separate DevinScript run).
- Constraints: Go 1.27.1, stdlib only; no LLM in extraction; no single-job API (401 live-verified 2026-10-01); macOS. Standalone — shares nothing with other Ashby tooling.
- Success Criterion: on a live board, every dictionary term present in each job's descriptionPlain appears in that job's output entry with zero required/preferred misclassifications on sectioned jobs.

## 2. Current State (OCP)

- Existing Implementation: none — greenfield at `~/projects/resume-updater/` (resume/ already holds the user's .tex + 2-page PDF for phase B).
- Technical Debt: caps-header heuristics over-trigger — ~9 ALL-CAPS headers/job, mostly narrative; only requirement-ish headers may flip classification.
- Integration Point: requirements.json schema is the phase-B swe-run `--context` contract.

## 3. Solution (LSP + ISP + DIP)

Input contract: the Ashby job list, and nothing else. One source, no job picking, no URL/id parsing:
  `resume-updater <jobs.json | ->`      job-list JSON from file or stdin
  `resume-updater <board-url>`          fetch.go fetches the list, extraction consumes it
The tool processes every job in the list; output is per-job requirements.

```go
type Job struct{ ID, Title, DescriptionPlain string }
type Fetcher interface{ FetchJobs(src string) ([]Job, error) } // board URL -> jobs[]; file/stdin -> decode only
type Requirement struct{ Term, Canonical, Kind, Section string } // Kind: required|preferred
type Extractor interface{ Extract(Job) []Requirement }           // pure, no I/O
func parseInput(args []string) (src string, mode srcMode, err error) // url | file | stdin -> exit 2 on bad
func writeOutputs([]JobResult, dir string) error                 // requirements.json + requirements.md
type JobResult struct{ JobID, Title string; Required, Preferred []Requirement }
```

- fetch.go: board GET (http.Client 30s, UA header as insurance only — default Go UA gets 200 live today, never gate on it); 404 -> exit 1; `{"jobs":[...]}` decode, missing field -> exit 1.
- extract.go: per job, line scan; header regex `(?i)^(requirements|qualifications|skills|what you'|nice to have|preferred|bonus)` sets section kind; inline cues (preferred|bonus|plus|nice to have) downgrade the line; unsectioned default required; `\b`-anchored case-insensitive token regexes.
- dictionary.go: canonical -> aliases (JS/JavaScript, K8s/Kubernetes, React/React.js, AWS/S3/Lambda, ...).
- SOLID: Fetcher/Extractor interfaces (DIP); main.go wires concretes (LSP-swap for httptest); Extractor does no I/O (ISP).
- Dependencies: zero new.

## 4. Test Framework (test-first, map to Success Criterion)

1. bullet fixture — tokens found, kind=required (extraction)
2. paragraph-embedded fixture — token inside prose sentence (extraction)
3. preferred-section fixture — "Nice to have:" header downgrades kind (classification)
4. inline-cue fixture — "bonus points for X" -> preferred (classification)
5. synonym fixture — JS + JavaScript collapse to one canonical (dedupe)
6. multi-job fixture — 2-job list -> 2 JobResult entries, per-job attribution (list semantics)
7. empty fixture — no sections/tokens -> empty slices, exit 0 (edge)
8. input tests — httptest 200 / 404 / malformed JSON / stdin+file decode (fetch+parse paths)

Mocks: httptest.Server behind Fetcher; Extractor pure. One reason to fail per test.

## 5. Diagrams

One diagram only — single-package CLI with two injected deps; a current-state graph adds nothing (collapsed per ISP).

```mermaid
graph LR
  A[main.go: parseInput\njobs list: url | file | stdin] --> B[Fetcher\nfetch.go]
  B --> C[Extractor\nper job in list]
  C --> D[writeOutputs\nper-job requirements.json + .md]
  D --> E[phase B swe-run\nresume tailor]
```

## Phase B (separate DevinScript run — planned, not built here)

- Inputs: `~/projects/resume-updater/resume/20260310 Danish Faruqi Resume.tex` + original PDF (style ref, 2 pages) + the target job's entry from requirements.json.
- Engine: `brew install tectonic` (0.17.0 bottled); fallback mactex-no-gui + latexmk -xelatex if fontspec present.
- Rules: text-only edits (summary/bullets/skills) mapped to required[]+preferred[]; preamble/documentclass/macros/packages/layout untouched.
- Guards: compile exit 0; page count via `qpdf --show-npages` after `brew install qpdf` (mdls returns null on fresh PDFs — probed 2026-10-01); pages <= 2.
- Deliverables: edited .tex + recompiled PDF + changelog (edit -> requirement).

## Final Checklist

- [x] One purpose per section (SRP)
- [x] Tests listed before implementation (8 cases, each mapped)
- [x] Zero new dependencies
- [x] Sketch cites only APIs read/verified this session
- [x] Success Criterion measurable, mapped to tests 1-8
- [x] One diagram, one concern
- [x] Standalone: no references to or coupling with other Ashby tooling

## Phase A — build verification (2026-10-02, independent re-check)

Built by DevinScript (swe-2-high), commit `9d8a16c` "ashby job-list requirements extractor".
Pipeline verdict PARTIAL — its own critique found only a test-count error. Independent results:

CLAIM: "tests green, vet clean"
EVIDENCE: `go vet ./...` -> clean; `go test ./...` -> `ok resume-updater 0.312s`;
`go test -list` -> 15 test functions (pipeline claimed 14 — critique's correction right).
VERDICT: VERIFIED

CLAIM: "stdlib only, zero deps"
EVIDENCE: `go list -deps` -> no external packages; alias regexes built with
`regexp.QuoteMeta` (extract.go:44) — C++/C# safe from quantifier panics.
VERDICT: VERIFIED

CLAIM: "input = Ashby job list only; every job processed"
EVIDENCE: parseInput modes: board URL / file / `-` stdin; no URL/id parsing anywhere;
extractAll loops all jobs; multi-job attribution test passes (j1/j2 split correct).
VERDICT: VERIFIED

CLAIM: "live smoke, 3 input modes identical"
EVIDENCE (fresh run, 2026-10-02): URL mode exit 0, 64 jobs; file and stdin modes
byte-identical requirements.json (diff clean); per-job counts match the run's claims:
Staff Product Engineer required=15 preferred=0; Staff Design Engineer required=4 preferred=7.
VERDICT: VERIFIED

CLAIM: "resume/ untouched, no agent comments"
EVIDENCE: resume/ mtimes predate the run (Sep 2 / Oct 1 14:14); comment scan clean
(sole grep hit = the `User-Agent` header string).
VERDICT: VERIFIED

Observations (not fixed, out of scope): (1) tool accepts the API-form URL
(api.ashbyhq.com/posting-api/job-board/<org>); pasting the human URL
jobs.ashbyhq.com/<org> fails decode with a clean error — could auto-translate later.
(2) requirements.json/.md written to cwd are untracked (tool output, not project code).

## Phase A — antagonize Mode V, round 2: attack the implementation (2026-10-02)

Fresh probes against source (main.go, fetch.go, extract.go read in full) + live binary + live board JSON.

CLAIM: "exit-code contract 0/1/2"
EVIDENCE: no-args -> 2; missing file -> 2; dead-slug URL -> 1; stdin `{"jobs":null}` -> 1;
stdin malformed JSON -> 1; `{"jobs":[]}` -> 0. All six as specified.
VERDICT: VERIFIED

CLAIM: "term extraction grounded (no hallucinated matches)"
EVIDENCE: audit of live 64-job output: 413 recorded terms, 0 absent from their
descriptionPlain (boundary-checked).
VERDICT: VERIFIED

CLAIM: "tests discriminate (not vacuous)"
EVIDENCE: mutation — inlineCueRe neutered to `(zzznevermatch)` -> `--- FAIL:
TestExtractInlineCue`, suite FAIL; reverted -> 15/15 pass, `git diff` clean on source.
VERDICT: VERIFIED

CLAIM: "extraction precision"
EVIDENCE AGAINST: fixture + live-board audit — the `go` alias matches phrase
usage. 26/26 jobs listing canonical Go on the ashby board are FALSE POSITIVES
("go it alone", "ABOUT GO TO MARKET", "go-to-market side", "go-live", "go
implement it") — none is the language; ashby eng stacks are TS/Node/React.
Fixture confirms same class: "Please express interest" -> Express REQUIRED.
Also: "Go experience plus Kubernetes knowledge" -> Kubernetes downgraded to
preferred by the `plus` inline cue (whole-line downgrade); narrative paragraph
after a "Nice to have:" header -> Python/Kubernetes marked preferred (sticky
section state); empty descriptionPlain -> silent zero requirements with no
warning (descriptionHtml fallback from the plan silently dropped).
VERDICT: PARTIAL
CORRECTION: `go` alias is poison (0% precision on this board) — drop `go`,
keep `golang`; same class: `express` (require express.js/expressjs), `node`
(require node.js/nodejs). Fix line-level cue scope (downgrade only after the
cue, or only cue-led segments) and reset section state on blank-line+paragraph
breaks. Emit a stderr note for jobs with empty descriptionPlain.

Survived: exit codes, decode guards (null jobs / malformed / missing field),
UA + 30s timeout, per-job attribution, dedupe, QuoteMeta alias escaping, term
grounding, test-suite discrimination.

## Phase B — build verification (2026-10-02, independent re-check)

Target: Senior Product Engineer - Americas (751768c6). Built by DevinScript
(swe-2-high); first attempt died INFRA (binary PDF passed as --context ->
UnicodeDecodeError at startup; relaunched with text-only contexts). Deliverables:
resume/tailored.tex, tailored.pdf, CHANGES.md; originals untouched.

CLAIM: "text-only edits; preamble/macros/layout/structure untouched"
EVIDENCE: byte-diff of everything up to \begin{document} -> PREAMBLE-IDENTICAL;
set-diff of all \command tokens original vs tailored -> COMMANDS-IDENTICAL;
12 changed lines = 6 old/new edit pairs.
VERDICT: VERIFIED

CLAIM: "compiles, page guard"
EVIDENCE: fresh tectonic recompile of a copy in /tmp -> exit 0, 2 pages;
qpdf --show-npages original=2 tailored=2. (mdls avoided per round-1 correction.)
VERDICT: VERIFIED

CLAIM: "required-term coverage, honest omissions"
EVIDENCE: programmatic scan of tailored.tex: 13/15 required terms present
(TypeScript x5, React x5, CI/CD x3, JavaScript/PostgreSQL/Notion x2,
Node.js/GraphQL/REST/Redis/SQL/Snowflake/Jira x1); Kotlin and Swift = 0 mentions
— matching CHANGES.md's declared omission (mobile work is React Native; JD does
not require them).
VERDICT: VERIFIED

CLAIM: "no fabrication"
EVIDENCE: CHANGES.md marks added terms (REST via "RESTful" on Flask work,
GraphQL/Redis/Snowflake/Jira added to the Technologies list only, "no project
claims"). Judgment call flagged for the user: Snowflake/Redis/Jira ride on
adjacent-but-not-identical background (RDS/Cassandra data work, JPMC-scale
tooling) — list-level additions, no invented projects/dates/employers.
VERDICT: PARTIAL
CORRECTION: the additions are defensible-but-speculative list entries; user
should confirm or strike Snowflake/Redis/Jira from the Technologies line.

Run-report inaccuracies (run's own critique caught): report said Languages
reordered with SQL/PostgreSQL leading; actual tailored line is "TypeScript,
JavaScript, Python, SQL, PostgreSQL, Bash, Java, C++, VBA" — CHANGES.md was
accurate, the summary was not. Also: repo-root requirements.json had been left
empty by the exit-code probe; regenerated from the live board (64 jobs).
