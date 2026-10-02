package main

import (
	"regexp"
	"sort"
	"strings"
)

var headerRe = regexp.MustCompile(`(?i)^(requirements|qualifications|skills|what you'|nice to have|preferred|bonus)`)
var prefHeaderRe = regexp.MustCompile(`(?i)^(nice to have|preferred|bonus)`)
var inlineCueRe = regexp.MustCompile(`(?i)\b(preferred|bonus|plus|nice to have)\b`)

// goPhraseRe: English phrases where the standalone word "go" is not the Go
// language (RE2 has no lookaheads, so matches are post-filtered per line).
var goPhraseRe = regexp.MustCompile(`(?i)go[- ]to[- ]market|go it alone|go[- ]live|go/no[- ]go|about go to|prefer to go|way we go|lets go|let's go|go beyond|go implement|go-getter`)

type term struct {
	canonical string
	re        *regexp.Regexp
}

type dictExtractor struct{ terms []term }

func newExtractor() *dictExtractor {
	keys := make([]string, 0, len(dictionary))
	for k := range dictionary {
		keys = append(keys, k)
	}
	sort.Strings(keys)
	terms := make([]term, 0, len(keys))
	for _, k := range keys {
		terms = append(terms, term{k, compileTerm(append([]string{k}, dictionary[k]...))})
	}
	return &dictExtractor{terms}
}

func compileTerm(aliases []string) *regexp.Regexp {
	sorted := append([]string(nil), aliases...)
	sort.Slice(sorted, func(i, j int) bool { return len(sorted[i]) > len(sorted[j]) })
	seen := map[string]bool{}
	qs := make([]string, 0, len(sorted))
	for _, a := range sorted {
		la := strings.ToLower(a)
		if seen[la] {
			continue
		}
		seen[la] = true
		qs = append(qs, regexp.QuoteMeta(la))
	}
	return regexp.MustCompile(`(?i)(?:^|[^a-z0-9])(` + strings.Join(qs, "|") + `)(?:[^a-z0-9]|$)`)
}

func (e *dictExtractor) Extract(j Job) []Requirement {
	kind := "required"
	section := ""
	seen := map[string]bool{}
	out := []Requirement{}
	for _, line := range strings.Split(j.DescriptionPlain, "\n") {
		t := strings.TrimSpace(line)
		if t == "" {
			continue
		}
		if m := headerRe.FindString(t); m != "" {
			section = strings.ToLower(m)
			if prefHeaderRe.MatchString(t) {
				kind = "preferred"
			} else {
				kind = "required"
			}
		}
		lineKind := kind
		if inlineCueRe.MatchString(t) {
			lineKind = "preferred"
		}
		for _, tm := range e.terms {
			if seen[tm.canonical] {
				continue
			}
			if tm.canonical == "Go" && goPhraseRe.MatchString(t) {
				continue
			}
			if sm := tm.re.FindStringSubmatch(t); sm != nil {
				seen[tm.canonical] = true
				out = append(out, Requirement{
					Term: sm[1], Canonical: tm.canonical, Kind: lineKind, Section: section,
				})
			}
		}
	}
	return out
}
