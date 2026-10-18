# Freeze label-free inputs for seven recent original eight-group rounds.
args <- commandArgs(TRUE)
stopifnot(length(args)==1L)
root <- normalizePath(args[[1]],mustWork=TRUE);setwd(root)
suppressPackageStartupMessages(library(tidyverse))
library(beidan,lib.loc=file.path(root,'results/margin-combination-study-20261018/library'))
out <- file.path(root,'results/margin-first-mapping-20261018')
dir.create(out,recursive=TRUE,showWarnings=FALSE)
target <- file.path(out,'inputs.rds')
stopifnot(!file.exists(target))
sources <- c(parent='results/fm171-full100-rebase-20261018/frozen-latest-replay.rds',
 manifest='results/full100-historical-rounds-20261018/input-manifest.json',
 producer='r/margin_first_mapping_inputs_20261018.R')
hashes <- vapply(sources,digest::digest,character(1),file=TRUE,algo='sha256')
parent <- readRDS(sources[['parent']])
manifest <- as_tibble(jsonlite::fromJSON(sources[['manifest']]))
stopifnot(parent$model_id=='FM-1.7.1',!parent$prospective_admission,length(parent$plans)==10L)
rounds <- list();inventory <- list()
for(i in 4:10) {
 p <- parent$plans[[i]];row <- manifest[i,];cutoff <- p$cutoff
 beidan:::match_require_cutoff(cutoff)
 forecast_path <- file.path('results',row$dataset,'frozen-probabilities.rds')
 plans_path <- file.path('results',row$dataset,'plans.rds')
 stopifnot(digest::digest(file=forecast_path,algo='sha256')==row$frozen_probability_sha256,
           digest::digest(file=plans_path,algo='sha256')==row$plans_sha256)
 forecast <- readRDS(forecast_path)
 original <- readRDS(plans_path)$plans[[row$sheet_index]]
 legs <- as_tibble(original$legs) |> select(group_slot,fixture_id) |> distinct() |>
   arrange(group_slot,fixture_id)
 stopifnot(nrow(legs)==56L,all(count(legs,group_slot)$n==7L))
 margins <- list();times <- list()
 for(id in unique(legs$fixture_id)) {
  e <- parent$grids[[paste(i,id,sep='|')]]
  stopifnot(identical(e$cutoff,cutoff))
  grid <- as_tibble(e$grid)
  h <- unique(forecast$probabilities$handicap[forecast$probabilities$fixture_id==id])
  stopifnot(length(h)==1L,is.finite(h),h==as.integer(h),
    all(is.finite(grid$probability)),all(grid$probability>=0),abs(sum(grid$probability)-1)<1e-9)
  m <- grid |> mutate(margin=home_goals-away_goals) |> group_by(margin) |>
    summarise(probability=sum(probability),.groups='drop') |>
    mutate(fixture_id=id,handicap=h,outcome=case_when(margin+h>0~'W',margin+h==0~'D',TRUE~'L'))
  q <- m |> group_by(fixture_id,outcome) |> summarise(probability=sum(probability),.groups='drop')
  ref <- p$probabilities |> filter(fixture_id==id)
  joined <- inner_join(q,ref,by=c('fixture_id','outcome'),relationship='one-to-one')
  stopifnot(nrow(joined)==3L,max(abs(joined$probability.x-joined$probability.y))<1e-9)
  margins[[id]] <- m
  times[[id]] <- forecast$entries[[id]]$base$max_source_available_utc
 }
 maximum_source <- do.call(max,times)
 stopifnot(maximum_source<cutoff$cutoff_utc)
 rounds[[as.character(i)]] <- list(index=i,dataset=p$dataset,sheet=p$sheet,cutoff=cutoff,
   legs=legs,margins=bind_rows(margins),probabilities=as_tibble(p$probabilities),
   source_receipt=list(cutoff=cutoff,max_source_available_utc=maximum_source,
     source_hashes=hashes,forecast_sha256=row$frozen_probability_sha256,plans_sha256=row$plans_sha256),
   original_tickets=as_tibble(p$tickets))
 inventory[[as.character(i)]] <- tibble(index=i,dataset=p$dataset,sheet=p$sheet,
   issue=cutoff$issue_id,cutoff_utc=cutoff$cutoff_utc,groups=8L,leg_rows=56L,
   distinct_fixtures=n_distinct(legs$fixture_id),cost_cny=2000L)
}
result <- list(rounds=rounds,model_id='FM-1.7.1',source_hashes=hashes,
 target_labels_opened=FALSE,prospective_admission=FALSE,
 policies=list(support_depth=c(4L,5L,Inf),windows=list(c(1L,125L),c(30L,154L)),
   ticket_cost_cny=2,group_ticket_count=125L,score='PRODUCT_OF_CATEGORY_MAXIMUM_MARGIN_MASS',
   ties='descending_score_then_lexicographic_ticket_id',normalize_truncated_mass=FALSE))
saveRDS(result,target)
write_csv(bind_rows(inventory),file.path(out,'input-inventory.csv'))
jsonlite::write_json(list(input_sha256=digest::digest(file=target,algo='sha256'),
 source_hashes=as.list(hashes),target_labels_opened=FALSE,rounds=7L,groups=56L,
 prospective_admission=FALSE),file.path(out,'input-manifest.json'),auto_unbox=TRUE,pretty=TRUE)
print(bind_rows(inventory))
