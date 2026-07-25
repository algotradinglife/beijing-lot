# Portable PDF font for BJ-ADHOC-BET-001

`NotoSansCJKsc-Regular.otf` is a project-tracked rendering dependency for the
independent adhoc betting slip. It is not a scheduled-freeze artifact and is
never copied into a research evidence package.

The file hash, upstream release, and licence hash are recorded in
`NotoSansCJKsc-Regular.provenance.json`; the SIL Open Font License text is in
`OFL.txt`. The publisher checks both file availability and glyph coverage
before emitting a PDF, so a missing/partial CJK font fails closed rather than
producing an unreadable betting slip.
