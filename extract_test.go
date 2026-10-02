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
