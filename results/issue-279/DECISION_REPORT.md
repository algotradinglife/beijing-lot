# Issue #279 interim decision report

- Development support: 620 independent issues, 2014–2023.
- Action-feature surface: 30,368 lawful issue/action rows.
- 2024+ outcomes opened: 0.
- 2023 replay: dynamic -CNY1,161.34; fixed N7/K8 -CNY848.00;
  matched incremental loss -CNY313.34.
- Two N5/K128 TOP_VALUE decisions contribute -CNY480 matched delta.
- N changes at K8 contribute +CNY166.66 in aggregate; this is exploratory
  realized attribution, not stable causal Edge.
- Raw oracle argmax is invalid as a parameter label because K exposure and
  multiple-action hindsight push it toward N7/K512.
- Match-selection and outcome-direction effects are not identifiable from the
  inherited aggregate trace and must remain explicitly unresolved.

Decision: continue #279.  Build budget-matched conditional targets and persist
pre-outcome match/outcome/ticket traces before fitting the staged joint model.
