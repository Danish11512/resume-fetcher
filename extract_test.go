package main

import "testing"

func byCanonical(reqs []Requirement) map[string]Requirement {
	m := map[string]Requirement{}
	for _, r := range reqs {
		m[r.Canonical] = r
	}
	return m
}

func TestExtractBulletsRequired(t *testing.T) {
	desc := "About the role:\nWe are hiring.\nRequirements:\n- 5+ years of experience with Go\n- Experience with Kubernetes and AWS\n"
	reqs := newExtractor().Extract(Job{ID: "1", Title: "Eng", DescriptionPlain: desc})
	got := byCanonical(reqs)
	for _, want := range []string{"Go", "Kubernetes", "AWS"} {
		r, ok := got[want]
		if !ok {
			t.Fatalf("missing canonical %s in %#v", want, reqs)
		}
		if r.Kind != "required" {
			t.Errorf("%s kind = %q, want required", want, r.Kind)
		}
	}
}

func TestExtractParagraphEmbedded(t *testing.T) {
	desc := "You will use Python daily to build internal tools and services."
	reqs := newExtractor().Extract(Job{ID: "1", DescriptionPlain: desc})
	got := byCanonical(reqs)
	r, ok := got["Python"]
	if !ok {
		t.Fatalf("Python not extracted from paragraph: %#v", reqs)
	}
	if r.Kind != "required" {
		t.Errorf("kind = %q, want required", r.Kind)
	}
	if r.Section != "" {
		t.Errorf("section = %q, want empty for unsectioned text", r.Section)
	}
}

func TestExtractPreferredSection(t *testing.T) {
	desc := "Requirements:\n- Strong Go skills\n\nNice to have:\n- Experience with Rust\n"
	reqs := newExtractor().Extract(Job{ID: "1", DescriptionPlain: desc})
	got := byCanonical(reqs)
	if r := got["Rust"]; r.Kind != "preferred" {
		t.Errorf("Rust kind = %q, want preferred", r.Kind)
	}
	if r := got["Go"]; r.Kind != "required" {
		t.Errorf("Go kind = %q, want required", r.Kind)
	}
}

func TestExtractInlineCue(t *testing.T) {
	desc := "Requirements:\n- Go experience\n- Bonus points for GraphQL experience\n"
	reqs := newExtractor().Extract(Job{ID: "1", DescriptionPlain: desc})
	got := byCanonical(reqs)
	if r := got["GraphQL"]; r.Kind != "preferred" {
		t.Errorf("GraphQL kind = %q, want preferred", r.Kind)
	}
	if r := got["Go"]; r.Kind != "required" {
		t.Errorf("Go kind = %q, want required", r.Kind)
	}
}

func TestExtractSynonymDedupe(t *testing.T) {
	desc := "Requirements:\n- Strong JS skills\n- Deep JavaScript knowledge\n"
	reqs := newExtractor().Extract(Job{ID: "1", DescriptionPlain: desc})
	count := 0
	for _, r := range reqs {
		if r.Canonical == "JavaScript" {
			count++
		}
	}
	if count != 1 {
		t.Fatalf("JavaScript appears %d times, want 1: %#v", count, reqs)
	}
}

func TestExtractEmpty(t *testing.T) {
	reqs := newExtractor().Extract(Job{ID: "1", DescriptionPlain: "We are a great company building things."})
	if len(reqs) != 0 {
		t.Fatalf("expected no requirements, got %#v", reqs)
	}
}

func TestGoPhraseBlacklist(t *testing.T) {
	desc := "ABOUT GO TO MARKET\nWe go to market fast. You prefer to go it alone. Ready to go beyond and go live.\nRequirements:\n- 5+ years with Go\n- Golang services\n"
	reqs := newExtractor().Extract(Job{ID: "1", DescriptionPlain: desc})
	got := byCanonical(reqs)
	r, ok := got["Go"]
	if !ok {
		t.Fatalf("Go missing despite language usage: %#v", reqs)
	}
	if r.Kind != "required" {
		t.Errorf("Go kind = %q, want required", r.Kind)
	}
	if len(reqs) != 1 {
		t.Errorf("expected exactly 1 requirement (Go), got %#v", reqs)
	}
}

func TestExpressNodeBareNoMatch(t *testing.T) {
	desc := "Please express interest. Each node of the graph matters. Express yourself clearly."
	reqs := newExtractor().Extract(Job{ID: "1", DescriptionPlain: desc})
	for _, r := range reqs {
		if r.Canonical == "Express.js" || r.Canonical == "Node.js" {
			t.Errorf("bare phrase matched %s: %#v", r.Canonical, reqs)
		}
	}
}

func TestExpressNodeRealMatch(t *testing.T) {
	desc := "Requirements:\n- Express.js and Node.js experience\n"
	reqs := newExtractor().Extract(Job{ID: "1", DescriptionPlain: desc})
	got := byCanonical(reqs)
	if _, ok := got["Express.js"]; !ok {
		t.Errorf("Express.js missing: %#v", reqs)
	}
	if _, ok := got["Node.js"]; !ok {
		t.Errorf("Node.js missing: %#v", reqs)
	}
}

func TestDesignTerms(t *testing.T) {
	desc := "Requirements:\n- Figma, Sketch, and prototyping skills\n- Wireframing and user research\n- Accessibility and WCAG knowledge\n"
	reqs := newExtractor().Extract(Job{ID: "1", DescriptionPlain: desc})
	got := byCanonical(reqs)
	for _, want := range []string{"Figma", "Sketch", "Prototyping", "Wireframing", "User Research", "Accessibility", "WCAG"} {
		if _, ok := got[want]; !ok {
			t.Errorf("design term %s missing: %#v", want, reqs)
		}
	}
}

func TestHomeDesignTerms(t *testing.T) {
	desc := "Experience with AutoCAD, Revit, and V-Ray for space planning and floor plans. BIM and CAD literacy expected.\n"
	reqs := newExtractor().Extract(Job{ID: "1", DescriptionPlain: desc})
	got := byCanonical(reqs)
	for _, want := range []string{"AutoCAD", "Revit", "V-Ray", "Space Planning", "Floor Plan", "BIM", "CAD"} {
		if _, ok := got[want]; !ok {
			t.Errorf("home-design term %s missing: %#v", want, reqs)
		}
	}
}
