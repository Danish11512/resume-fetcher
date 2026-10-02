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
