# Descriptive multiclass diagnostics; no fitting, tuning, selection or I/O.
# frame: one issue/slot/provider_id/model/outcome row; probability in [0,1],
# actual_outcome repeats the observed class within each fixture/model.
# All models must cover the same fixture identities. strata are explicit existing categorical columns (e.g. segment, league).
# outcomes fixes both the complete class universe and tie-breaking order.
# breaks fixes descriptive probability bins. Returns fixture scores and class
# calibration by strata/model; zero probability on the actual class gives Inf
# log loss (never clipped). Empty, missing, incomplete or inconsistent rows fail.
strategy_probability_diagnostics <- function(frame,strata,outcomes,breaks) {
  keys<-c('issue','slot','provider_id','model')
  stopifnot(is.character(strata),!anyDuplicated(strata),
    !any(strata %in% c(keys,'outcome','actual_outcome','probability')),
    is.character(outcomes),length(outcomes)>=2,!anyNA(outcomes),!anyDuplicated(outcomes),
    length(breaks)>=2,all(is.finite(breaks)),all(diff(breaks)>0),breaks[1]==0,tail(breaks,1)==1,
    all(c(keys,strata,'outcome','actual_outcome','probability') %in% names(frame)),nrow(frame)>0,
    !anyNA(frame[c(keys,strata,'outcome','actual_outcome','probability')]),
    !anyDuplicated(frame[c(keys,'outcome')]),is.character(frame$issue),is.character(frame$provider_id),
    is.character(frame$model),all(frame$outcome %in% outcomes),
    all(frame$actual_outcome %in% outcomes),all(is.finite(frame$probability)),
    all(frame$probability>=0 & frame$probability<=1))
  labels<-frame |> dplyr::distinct(dplyr::across(dplyr::all_of(c(keys[1:3],strata,'actual_outcome'))))
  stopifnot(!anyDuplicated(labels[keys[1:3]]),
    nrow(dplyr::distinct(frame,dplyr::across(dplyr::all_of(keys))))==
      nrow(labels)*dplyr::n_distinct(frame$model))
  checks<-frame |> dplyr::group_by(dplyr::across(dplyr::all_of(keys))) |>
    dplyr::summarise(classes=dplyr::n(),mass=sum(probability),.groups='drop')
  stopifnot(all(checks$classes==length(outcomes)),all(abs(checks$mass-1)<1e-8))
  z<-frame |> dplyr::mutate(observed=as.integer(outcome==actual_outcome),
    class_order=match(outcome,outcomes)) |>
    dplyr::group_by(dplyr::across(dplyr::all_of(keys))) |>
    dplyr::arrange(dplyr::desc(probability),class_order,.by_group=TRUE) |>
    dplyr::mutate(probability_rank=dplyr::row_number()) |> dplyr::ungroup()
  scores<-z |> dplyr::group_by(dplyr::across(dplyr::all_of(c(keys,strata)))) |>
    dplyr::summarise(brier=sum((probability-observed)^2),
      log_loss=-log(probability[observed==1]),top1=any(observed==1 & probability_rank==1),
      top2=any(observed==1 & probability_rank<=2),.groups='drop')
  summary<-scores |> dplyr::group_by(dplyr::across(dplyr::all_of(c(strata,'model')))) |>
    dplyr::summarise(fixtures=dplyr::n(),issues=dplyr::n_distinct(issue),
      brier=mean(brier),log_loss=mean(log_loss),top1=mean(top1),top2=mean(top2),.groups='drop')
  calibration<-z |> dplyr::mutate(bin=cut(probability,breaks,include.lowest=TRUE)) |>
    dplyr::group_by(dplyr::across(dplyr::all_of(c(strata,'model','outcome','bin')))) |>
    dplyr::summarise(fixtures=dplyr::n(),issues=dplyr::n_distinct(issue),
      predicted=mean(probability),observed=mean(observed),gap=observed-predicted,.groups='drop')
  list(scores=scores,summary=summary,calibration=calibration)
}

# Descriptive two-period standardization of a per-observation value (e.g. hit,
# Brier or CNY); no causal claim, fitting or future weights. frame columns:
# segment, stratum, value. reference/target explicitly identify the two segments;
# all strata must occur in both. Return full count/weight/mean ledger and exact
# additive decomposition. Uses reference cell means for the composition effect,
# target weights for the within-stratum effect (order-dependent, disclosed).
# Empty, NA/nonfinite values, absent segments or unmatched strata fail; zero
# counts are not imputed and target-only strata are never silently dropped.
strategy_composition_diagnostics <- function(frame,reference,target) {
  stopifnot(all(c('segment','stratum','value') %in% names(frame)),nrow(frame)>0,
    !anyNA(frame[c('segment','stratum','value')]),all(is.finite(frame$value)),
    length(reference)==1,length(target)==1,!is.na(reference),!is.na(target),reference!=target,
    all(c(reference,target) %in% frame$segment))
  ledger<-frame |> dplyr::filter(segment %in% c(reference,target)) |>
    dplyr::group_by(segment,stratum) |> dplyr::summarise(n=dplyr::n(),mean=mean(value),.groups='drop') |>
    dplyr::group_by(segment) |> dplyr::mutate(weight=n/sum(n)) |> dplyr::ungroup()
  a<-ledger |> dplyr::filter(segment==reference) |> dplyr::select(-segment)
  b<-ledger |> dplyr::filter(segment==target) |> dplyr::select(-segment)
  stopifnot(setequal(a$stratum,b$stratum))
  cells<-dplyr::inner_join(a,b,by='stratum',suffix=c('_reference','_target'),relationship='one-to-one') |>
    dplyr::mutate(composition=(weight_target-weight_reference)*mean_reference,
      within=weight_target*(mean_target-mean_reference))
  summary<-tibble::tibble(reference=reference,target=target,
    reference_mean=sum(cells$weight_reference*cells$mean_reference),
    target_mean=sum(cells$weight_target*cells$mean_target),
    composition=sum(cells$composition),within=sum(cells$within)) |>
    dplyr::mutate(change=target_mean-reference_mean)
  stopifnot(abs(summary$change-summary$composition-summary$within)<1e-8)
  list(ledger=ledger,cells=cells,summary=summary)
}

# Verify required local inputs against a named SHA-256 receipt.
# root: directory; hashes: named list/vector; required: nonempty filenames.
# Returns invisible TRUE; reads files, never writes; missing/invalid hashes,
# missing files and mismatches stop before downstream analysis.
strategy_verify_diagnostic_inputs <- function(root, hashes, required) {
  if (!is.character(root) || length(root)!=1L || is.na(root) ||
      !is.character(required) || !length(required) || anyNA(required) ||
      any(!nzchar(required)) || anyDuplicated(required) ||
      is.null(names(hashes)) || anyDuplicated(names(hashes)))
    stop("invalid required input receipt")
  for (name in required) {
    expected <- hashes[[name]]
    if (!is.character(expected) || length(expected)!=1L || is.na(expected) ||
        !grepl("^[0-9a-f]{64}$",expected))
      stop("missing or invalid SHA-256: ",name)
    path <- file.path(root,name)
    if (!file.exists(path) || dir.exists(path) ||
        !identical(digest::digest(file=path,algo="sha256"),expected))
      stop("input hash mismatch or missing file: ",name)
  }
  invisible(TRUE)
}
