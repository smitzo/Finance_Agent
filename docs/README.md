# FreightFlow AI Documentation

This directory explains the product from business behavior down to runtime implementation. The documents are intentionally separated so each one can stay focused and evolve with the code.

## Reading paths

### Product and operations

1. [Project overview](project-overview.md)
2. [Functional and technical flows](flows.md)
3. [Demo scenario catalogue](demo-scenarios.md)
4. [Frequently asked questions](faq.md)

### Architecture and engineering

1. [High-level design](high-level-design.md)
2. [Low-level design](low-level-design.md)
3. [Important code paths](code-guide.md)
4. [Architecture decisions and alternatives](architecture-decisions.md)
5. [Edge cases and failure handling](edge-cases.md)
6. [Improvement and scaling roadmap](improvements.md)

## Documentation contract

- The code and migrations are the executable source of truth.
- The root [README](../readme.md) is the setup and operator entry point.
- These documents describe the current implementation unless a section is explicitly labelled as a future improvement.
- Mermaid diagrams are stored inline so they render on GitHub and remain reviewable as text.
- Demo records are synthetic and use `DEMO-` or `CAR-DEMO` identifiers.

When behavior changes, update the closest focused document rather than growing one general-purpose file.
