package main

import (
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"strings"
)

func writeOutputs(results []JobResult, dir string) error {
	if err := os.MkdirAll(dir, 0o755); err != nil {
		return err
	}
	data, err := json.MarshalIndent(results, "", "  ")
	if err != nil {
		return err
	}
	if err := os.WriteFile(filepath.Join(dir, "requirements.json"), append(data, '\n'), 0o644); err != nil {
		return err
	}
	var md strings.Builder
	md.WriteString("# Job Requirements\n")
	for _, r := range results {
		fmt.Fprintf(&md, "\n## %s (%s)\n\n### Required\n", r.Title, r.JobID)
		for _, req := range r.Required {
			fmt.Fprintf(&md, "- %s (`%s`)\n", req.Canonical, req.Term)
		}
		md.WriteString("\n### Preferred\n")
		for _, req := range r.Preferred {
			fmt.Fprintf(&md, "- %s (`%s`)\n", req.Canonical, req.Term)
		}
	}
	return os.WriteFile(filepath.Join(dir, "requirements.md"), []byte(md.String()), 0o644)
}
