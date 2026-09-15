# Signed-handicap refinement of the shared frozen-block draw model.
# Source draw_refresh.R. History/target contracts and chronology are inherited;
# handicap is an additional finite signed integer, never inferred from labels.
# Strengths are positive pseudo-counts, probabilities are fractions. No I/O
# except implementation hashing and the parent's explicit Python bridge.
draw_handicap_fit <- function(history, block, cutoff, repository_root, source_hashes,
                              market_edges, gap_edges, prior_strength, recent_strength,
                              handicap_strength, handicap_recent_strength,
                              delay_hours, recent_issues, minimum_ess, python, gap_mode, refinement_cols) {
 stopifnot(identical(refinement_cols,'handicap') || identical(refinement_cols,c('handicap','total_band')),
  all(refinement_cols %in% names(history)),!anyNA(history[refinement_cols]),'handicap' %in% names(history),is.numeric(history$handicap),
  all(is.finite(history$handicap)),all(history$handicap==trunc(history$handicap)),
  length(handicap_strength)==1,is.finite(handicap_strength),handicap_strength>0,
  length(handicap_recent_strength)==1,is.finite(handicap_recent_strength),handicap_recent_strength>0,
  !'handicap_implementation' %in% names(source_hashes))
 implementation<-digest::digest(file=file.path(repository_root,'r/draw_handicap_refresh.R'),algo='sha256')
 source_hashes$handicap_implementation<-implementation
 parent<-draw_refresh_fit(history,block,cutoff,repository_root,source_hashes,
  market_edges,gap_edges,prior_strength,recent_strength,delay_hours,recent_issues,minimum_ess,python,gap_mode)
 ctx<-jsonlite::fromJSON(parent$context_json,simplifyVector=FALSE)
 rows<-dplyr::bind_rows(ctx$rows)
 core<-reticulate::import('src.temporal_learning.core')
 rows<-draw_refresh_bins(rows,cutoff,market_edges,gap_edges,gap_mode)
 cells<-rows |> dplyr::group_by(dplyr::across(dplyr::all_of(c(refinement_cols,'market_bin','secondary_bin')))) |>
  dplyr::summarise(h_n=dplyr::n(),h_rate=sum(long_mass*(actual=='D'))/sum(long_mass),
   h_recent_rows=sum(recent_mass>0),h_recent_issues=dplyr::n_distinct(issue_code[recent_mass>0]),
   h_recent_ess=if(sum(recent_mass)>0)core$effective_sample_size(reticulate::np_array(recent_mass)) else 0,
   h_recent_rate=if(sum(recent_mass)>0)sum(recent_mass*(actual=='D'))/sum(recent_mass) else 0,
   .groups='drop')
 artifact<-list(refinement_cols=refinement_cols,parent=parent,cells=cells,handicap_strength=handicap_strength,
  handicap_recent_strength=handicap_recent_strength,implementation_sha256=implementation,
  historical_admission=FALSE)
 artifact$seal<-digest::digest(artifact,algo='sha256');artifact
}

# Each long/recent child distribution shrinks toward its corresponding parent
# distribution, then the two normalized components are blended. Unseen handicap
# cells reproduce the parent exactly. W:L ratio is preserved, no forced floor.
draw_handicap_predict <- function(artifact,frame,cutoff,alpha,repository_root,python) {
 stopifnot(identical(digest::digest(artifact[names(artifact)!='seal'],algo='sha256'),artifact$seal),
  identical(digest::digest(file=file.path(repository_root,'r/draw_handicap_refresh.R'),algo='sha256'),artifact$implementation_sha256),
  all(artifact$refinement_cols %in% names(frame)),!anyNA(frame[artifact$refinement_cols]),'handicap' %in% names(frame),is.numeric(frame$handicap),
  all(is.finite(frame$handicap)),all(frame$handicap==trunc(frame$handicap)))
 z<-draw_refresh_predict(artifact$parent,frame,cutoff,alpha,repository_root,python)
 z<-dplyr::left_join(z,artifact$cells,by=c(artifact$refinement_cols,'market_bin','secondary_bin'),relationship='many-to-one')
 for(n in c('h_n','h_rate','h_recent_rows','h_recent_issues','h_recent_ess','h_recent_rate'))z[[n]][is.na(z[[n]])]<-0
 z$parent_D<-z$new_D
 z$handicap_long_D<-(z$h_n*z$h_rate+artifact$handicap_strength*z$long_D)/(z$h_n+artifact$handicap_strength)
 z$handicap_recent_D<-(z$h_recent_ess*z$h_recent_rate+artifact$handicap_recent_strength*z$recent_D)/
  (z$h_recent_ess+artifact$handicap_recent_strength)
 z$new_D<-(1-alpha)*z$handicap_long_D+alpha*z$handicap_recent_D
 z$new_W<-z$q_W*(1-z$new_D)/(1-z$q_D)
 z$new_L<-z$q_L*(1-z$new_D)/(1-z$q_D)
 z$model_seal<-artifact$seal;z
}
