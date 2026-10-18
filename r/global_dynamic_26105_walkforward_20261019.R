# Rscript r/global_dynamic_walkforward_20261018.R ROOT IMPLEMENTATION_ROOT ISSUE forecast|replay
# Domain orchestration only: shared package owns clocks, fits, DC and selection.
args <- commandArgs(TRUE)
stopifnot(length(args)==4L,args[3]=='26105',args[4]%in%c('forecast','replay'))
root <- normalizePath(args[1],mustWork=TRUE); implementation_root <- normalizePath(args[2],mustWork=TRUE)
setwd(root); issue <- args[3]; mode <- args[4]
suppressPackageStartupMessages(library(tidyverse))
library(beidan)
invisible(python_backend(file.path(root,'.venv/bin/python')))
shared <- reticulate::import('beidan_backend.temporal_learning',convert=FALSE)
backend <- reticulate::import('beidan_backend.fundamental_probability',convert=FALSE)
paths <- reticulate::import('beidan_backend.catalog.paths',convert=FALSE)
out <- file.path(root,'results/global-dynamic-walkforward-20261018',issue)
dir.create(out,recursive=TRUE,showWarnings=FALSE)
policy_path <- 'config/global_dynamic_walkforward_20261018.json'
policy <- jsonlite::fromJSON(policy_path,simplifyVector=TRUE)
stopifnot(policy$base_model=='FM-1.7.1',!policy$prospective_admission,
 identical(policy$models,c('RAW','GLOBAL')),policy$rounds$budget_cny==2000)
source <- reticulate::py_str(paths$location('hot:global-dynamic-26105-20261019'))
census_path<-file.path(source,'coverage-census.rds');chunk_dir<-file.path(source,'native-chunks')
parsed_path<-reticulate::py_str(paths$location('hot:global-dynamic-26105-channel-parsed-20261019-v4/parsed.json'))
inventory_path<-reticulate::py_str(paths$location('hot:global-dynamic-26105-channel-inventory-20261018/inventory.json'))
chunks<-list.files(chunk_dir,pattern='^native-repair[.]rds$',full.names=TRUE)
stopifnot(length(chunks)==1L)
source_paths<-c(policy=policy_path,client='r/global_dynamic_26105_walkforward_20261019.R',
 fixtures=file.path(source,'fixtures.csv'),old_native=file.path(source,'native-forecasts.rds'),native_manifest=file.path(source,'native-manifest.json'),census=census_path,
 market_parsed=parsed_path,market_inventory=inventory_path,
 training='results/fm171-margin-shape-20261017/forecasts.rds',training_manifest='results/fm171-margin-shape-20261017/manifest.json',
 prior_labels='results/fm17-three-issues-20261013/labels.csv',prior_observed='results/fm171-draw-calibration-20261017/label-source-observations.csv',chunk1=chunks)
for(prior_issue in c('26103','26104')) {
 parent<-file.path('results/global-dynamic-walkforward-20261018',prior_issue)
 source_paths<-c(source_paths,set_names(c(file.path(parent,'frozen-forecasts.rds'),file.path(parent,'forecast-manifest.json'),file.path('docs/reviews',paste0('source-',prior_issue),'roster.json')),paste0(prior_issue,c('_forecasts','_manifest','_observations'))))
}
hashes<-map_chr(source_paths,~digest::digest(file=.x,algo='sha256'))
if(mode=='forecast'&&file.exists(file.path(out,'frozen-forecasts.rds')))stop('immutable forecast already exists')
parsed_bytes<-readBin(parsed_path,'raw',n=file.info(parsed_path)$size)
inventory_bytes<-readBin(inventory_path,'raw',n=file.info(inventory_path)$size)
parsed<-jsonlite::fromJSON(rawToChar(parsed_bytes),simplifyVector=FALSE)
inventory<-jsonlite::fromJSON(rawToChar(inventory_bytes),simplifyVector=FALSE)
stopifnot(digest::digest(parsed_bytes,serialize=FALSE,algo='sha256')==hashes[['market_parsed']],digest::digest(inventory_bytes,serialize=FALSE,algo='sha256')==hashes[['market_inventory']],parsed$inventory_sha256==hashes[['market_inventory']],parsed$network_attempts==0L,length(parsed$records)==730L)
channel_keys<-map_chr(parsed$records,~paste(.x$fixture_id,.x$kind))
stopifnot(!anyDuplicated(channel_keys),all(map_lgl(parsed$records,~.x$state%in%c('PARSED','OBSERVED_EMPTY'))))
channels<-set_names(parsed$records,channel_keys)
old<-readRDS(source_paths[['old_native']]);nm<-jsonlite::fromJSON(source_paths[['native_manifest']]);stopifnot(hashes[['old_native']]==nm$sha256)
fixtures<-read_csv(source_paths[['fixtures']],col_types=cols(.default=col_character(),slot=col_integer(),handicap=col_integer(),kickoff_at=col_datetime(),cutoff_utc=col_datetime()))
scope_n<-365L
stopifnot(nrow(fixtures)==scope_n,!anyDuplicated(fixtures$fixture_id),!nrow(problems(fixtures)),setequal(fixtures$fixture_id,paste0('26105:',seq_len(365L))),identical(is.na(fixtures$cutoff_utc),is.na(fixtures$kickoff_at)),all(fixtures$cutoff_utc[!is.na(fixtures$cutoff_utc)]==fixtures$kickoff_at[!is.na(fixtures$kickoff_at)]-lubridate::hours(24)))
roster<-bind_rows(inventory$fixtures)
for(id in fixtures$fixture_id) {
 f<-filter(fixtures,fixture_id==id);r<-filter(roster,fixture_id==id)
 stopifnot(nrow(r)==1L,f$provider_id==r$provider_id,f$home_id==r$home_id,f$away_id==r$away_id,f$handicap==r$handicap)
 if(is.na(f$cutoff_utc))next
 stopifnot(lubridate::ymd_hms(r$cutoff_utc,tz='UTC')==f$cutoff_utc)
}
# Same fixed UTC daily00 rule; expand only its event-calendar range for this issue.
stopifnot(any(!is.na(fixtures$cutoff_utc)))
first_epoch<-lubridate::ceiling_date(min(fixtures$cutoff_utc,na.rm=TRUE),unit='day',change_on_boundary=FALSE)
last_epoch<-lubridate::ceiling_date(max(fixtures$cutoff_utc,na.rm=TRUE),unit='day',change_on_boundary=FALSE)
policy$rounds$decision_epochs_utc<-format(seq(first_epoch,last_epoch,by='day'),'%Y-%m-%dT%H:%M:%SZ',tz='UTC')
census<-readRDS(census_path)
stopifnot(nrow(census$coverage)==2L*sum(!is.na(fixtures$cutoff_utc)),all(census$coverage$source_status=='PARSED'),
 nrow(census$unavailable)==2L*sum(is.na(fixtures$cutoff_utc)),
 setequal(census$unavailable$fixture_id,fixtures$fixture_id[is.na(fixtures$cutoff_utc)]),
 !anyDuplicated(census$unavailable[c('fixture_id','source')]),
 !any(census$coverage$fixture_id%in%census$unavailable$fixture_id),
 all(census$unavailable$reason=='Unresolved source kickoff; explicit cutoff unavailable'))
latest<-census$latest |> filter(source=='titan',valid_decimal,tied_vectors==1L,age_hours>=0,age_hours<=policy$market$maximum_age_hours) |> select(company_id,fixture_id,quote_at,odds_home,odds_draw,odds_away)
stopifnot(!anyDuplicated(latest[c('fixture_id','company_id')]))
fits<-list();native_status<-list()
for(p in chunks) {
 z<-readRDS(p);receipt<-jsonlite::fromJSON(file.path(dirname(p),'recent-receipt.json'))
 stopifnot(receipt$sha256==digest::digest(file=p,algo='sha256'),!z$analysis_quality_accepted,z$native_policy$recent_n==8L,z$native_policy$alpha==.5)
 fits<-c(fits,z$fits);native_status[[p]]<-z$status
}
ns<-bind_rows(native_status);stopifnot(nrow(ns)==scope_n,!anyDuplicated(ns$fixture_id),length(fits)>0L)
unresolved_ids<-fixtures$fixture_id[is.na(fixtures$cutoff_utc)]
stopifnot(!any(unresolved_ids%in%names(fits)),!any(unresolved_ids%in%names(old$entries)),
 all(ns$state[match(unresolved_ids,ns$fixture_id)]=='UNESTIMATED'),
 all(ns$reason[match(unresolved_ids,ns$fixture_id)]=='Unresolved source kickoff; explicit cutoff unavailable'))
train <- readRDS(source_paths[['training']]);tm<-jsonlite::fromJSON(source_paths[['training_manifest']])
stopifnot(hashes[['training']]==tm$sha256)
prior_labels <- read_csv(source_paths[['prior_labels']],col_types=cols(.default=col_character()))
observed <- read_csv(source_paths[['prior_observed']],col_types=cols(.default=col_character()))
training_prob <- train$probabilities |> filter(model=='SOURCE_FULL') |> select(fixture_id,outcome,probability) |> pivot_wider(names_from=outcome,values_from=probability)
history <- train$features |> filter(eligible) |> select(fixture_id,issue_code=issue_id,data_available_ts=cutoff_utc,entropy,local_mass) |>
 inner_join(training_prob,by='fixture_id',relationship='one-to-one') |>
 inner_join(prior_labels |> select(fixture_id,actual_outcome),by='fixture_id',relationship='one-to-one') |>
 left_join(observed |> rename(issue_code=issue_id,label_available_ts=observed_label_ts),by='issue_code',relationship='many-to-one') |> mutate(issue_year=2026L)
stopifnot(nrow(history)==322L,!anyNA(history),all(history$issue_code%in%policy$training_issues))
prior_issues<-policy$training_issues;prior_label_audit<-list()
for(prior_issue in c('26103','26104')) {
 prior<-readRDS(source_paths[[paste0(prior_issue,'_forecasts')]])
 manifest<-jsonlite::fromJSON(source_paths[[paste0(prior_issue,'_manifest')]])
 stopifnot(manifest$sha256==hashes[[paste0(prior_issue,'_forecasts')]],!prior$target_labels_opened)
 observation<-bind_rows(jsonlite::fromJSON(source_paths[[paste0(prior_issue,'_observations')]],simplifyVector=FALSE)$data)
 stopifnot(all(observation$issue_id==prior_issue),!anyDuplicated(observation$slot))
 labels<-observation |> filter(status=='完场',grepl('^[0-9]+-[0-9]+$',score)) |>
 transmute(fixture_id=paste0(issue_id,':',slot),label_available_ts=observed_at,
 margin=as.integer(sub('-.*$','',score))-as.integer(sub('^.*-','',score))+as.integer(handicap),
 actual_outcome=case_when(margin>0~'W',margin==0~'D',TRUE~'L')) |> select(-margin)
 features<-map_dfr(prior$entries,~.x$features |> mutate(issue_code=prior_issue,issue_year=2026L,data_available_ts=format(.x$cutoff$cutoff_utc,'%Y-%m-%dT%H:%M:%SZ',tz='UTC')))
 extra<-features |> inner_join(labels,by='fixture_id',relationship='one-to-one') |> select(all_of(names(history)))
 prior_label_audit[[prior_issue]]<-tibble(issue_id=prior_issue,forecast_rows=nrow(features),labelled_rows=nrow(extra),unsettled_or_missing=nrow(anti_join(features,labels,by='fixture_id')))
 history<-bind_rows(history,extra);prior_issues<-c(prior_issues,prior_issue)
}
stopifnot(!anyNA(history),!anyDuplicated(history$fixture_id),!issue%in%history$issue_code)
market_policy <- list(euro_weight=1,asian_weight=1,lambda_floor=.01,tail_tolerance=1e-10,max_quote_age_hours=48)
entries <- audit <- calibration <- list()
for(id in fixtures$fixture_id) {
 f <- fixtures |> filter(fixture_id==id); e <- old$entries[[id]]; n <- fits[[id]]
 row <- tibble(fixture_id=id,slot=f$slot,cutoff_utc=f$cutoff_utc,handicap=f$handicap,
 native_supported=!is.null(n),euro_companies=0L,asian_rows=0L,total_rows=0L,
 three_channel_fit=FALSE,market_consistent=FALSE,selected_source=NA_character_,
 state='UNESTIMATED',reason=ns$reason[match(id,ns$fixture_id)])
 if(is.null(n)||is.null(e)) {audit[[id]]<-row;next}
 cutoff <- e$cutoff
 stopifnot(identical(cutoff$cutoff_utc,f$cutoff_utc),e$identities$home_id==f$home_id,e$identities$away_id==f$away_id)
 eq <- latest |> filter(fixture_id==id)
 row$euro_companies<-nrow(eq)
 snapshots <- list(); channel_bindings <- list()
 for(kind in c('asian','total')) {
  cap<-channels[[paste(id,kind)]]
  stopifnot(!is.null(cap),cap$fixture_id==id,cap$kind==kind,cap$provider_id==f$provider_id)
  channel_hash<-beidan:::.score_margin_hash(cap)
  if(!length(cap$snapshots)) {snapshots[[kind]]<-tibble();channel_bindings[[kind]]<-channel_hash;next}
  price_names<-if(kind=='asian')c('home','away')else c('over','under')
  z<-tibble(line_value=map_dbl(cap$snapshots,'line_value'),
   home_price=map_dbl(cap$snapshots,~.x$odds[[price_names[1]]] %||% NA_real_),
   away_price=map_dbl(cap$snapshots,~.x$odds[[price_names[2]]] %||% NA_real_),
   complete=map_lgl(cap$snapshots,'complete'),phase=map_chr(cap$snapshots,'phase'),
   quote_at=lubridate::ymd_hms(map_chr(cap$snapshots,'snapshot_ts_hkt'),tz='UTC')) |>
   filter(complete,phase=='pregame',quote_at<cutoff$cutoff_utc,
     as.numeric(difftime(cutoff$cutoff_utc,quote_at,units='hours'))<=48)
  if(nrow(z))z<-z |> filter(quote_at==max(quote_at)) |> distinct(line_value,home_price,away_price,quote_at,.keep_all=TRUE)
  snapshots[[kind]]<-z;channel_bindings[[kind]]<-channel_hash
 }
 row$asian_rows<-nrow(snapshots$asian);row$total_rows<-nrow(snapshots$total)
 if(nrow(eq)<3L||nrow(snapshots$asian)!=1L||nrow(snapshots$total)!=1L) {
  row$reason<-'Missing/stale/ambiguous admitted three-channel evidence';audit[[id]]<-row;next
 }
 aq<-snapshots$asian |> transmute(company_id='8',fixture_id=id,quote_at,handicap=line_value,home_decimal=1+home_price,away_decimal=1+away_price)
 tq<-snapshots$total |> transmute(company_id='8',fixture_id=id,quote_at,line=line_value,over_decimal=1+home_price,under_decimal=1+away_price)
 if(tq$line<2.5) {row$reason<-'DC total inversion not admitted below2.5 under existing implementation';audit[[id]]<-row;next}
 if(any(!is.finite(c(aq$home_decimal,aq$away_decimal,tq$over_decimal,tq$under_decimal)))||
 any(c(aq$home_decimal,aq$away_decimal,tq$over_decimal,tq$under_decimal)<=1))stop('invalid admitted prices')
 total<-beidan:::total_market_constraint(tq |> transmute(company=company_id,line,over_hk=over_decimal-1,under_hk=under_decimal-1),c(.1,12))
 ft<-tibble(fixture_id=id,issue_id=issue,home=f$home,away=f$away)
 evidence<-list()
 for(kind in c('euro','asian','totals')) {
  selected<-switch(kind,euro=eq,asian=aq,totals=tq)
  for(j in seq_len(nrow(selected))) {
   z<-selected[j,];eid<-paste0(kind,'-',z$company_id);time<-format(z$quote_at,'%Y-%m-%dT%H:%M:%SZ',tz='UTC')
   evidence[[length(evidence)+1L]]<-list(evidence_id=eid,fixture_id=id,source_hash=beidan:::.score_margin_hash(z),row_key=eid,
    issue_code='HISTORICAL_QUOTE_PROXY',issue_year=2026L,label_available_ts=time,data_available_ts=time)
  }
 }
 b<-c(as.list(hashes[c('policy','client','old_native','census')]),channel_bindings,list(
 dc_market_input=beidan:::.score_margin_hash(list(euro=eq,asian=aq,total_mean=total$lambda_total,rho=-.1,policy=market_policy,fixture=ft,cutoff=cutoff)),
 direction_implementation=beidan:::.score_margin_code(implementation_root)))
 epoch<-shared$Cutoff$decision_epoch(issue,format(cutoff$cutoff_utc,'%Y-%m-%dT%H:%M:%SZ',tz='UTC'))
 ctx<-backend$build_adjustment_evidence_context(evidence,as.list(ft),epoch,b,
 shared$AvailabilityPolicy$historical_proxy('POSTEVENT_CAPTURE_PRIOR_QUOTE_CLOCK'),'HISTORICAL_DIAGNOSTIC',implementation_root)
 market<-project_dc_market_handicap(eq,aq,total$lambda_total,-.1,market_policy,ctx,ft,cutoff,implementation_root,'HISTORICAL_DIAGNOSTIC')
 row$three_channel_fit<-TRUE
 row$market_consistent<-max(abs(market$ordinary$residual))<=.05&&max(abs(market$asian$residual))<=.05
 # The existing uncertain-native policy directly selects a sufficient consistent market.
 # Missing lineups/opponent adjustment remains an explicit uncertainty, not fabricated evidence.
 params<-n$native$same_support_raw
 native_grid<-beidan:::dixon_coles_score_grid(params$lambda_home,params$lambda_away,0L,1e-10,-.1)$grid |> select(home_goals,away_goals,probability)
 native_at<-e$native_base$max_source_available_utc
 native_base<-list(grid=native_grid,cutoff=cutoff,model_id='FM171_SAME_SUPPORT_RAW',source_hashes=b,max_source_available_utc=native_at,intended_use='HISTORICAL_DIAGNOSTIC')
 market_base<-list(grid=market$grid,cutoff=cutoff,model_id='FM171_JOINT_MARKET',source_hashes=b,
   max_source_available_utc=max(eq$quote_at,aq$quote_at,tq$quote_at),intended_use='HISTORICAL_DIAGNOSTIC')
 native_time<-format(native_at,'%Y-%m-%dT%H:%M:%SZ',tz='UTC')
 evidence<-c(evidence,list(list(evidence_id='native-support',fixture_id=id,source_hash=beidan:::.score_margin_hash(n),
  row_key='native-support',issue_code='PRIOR_NATIVE_EVIDENCE',issue_year=2026L,label_available_ts=native_time,data_available_ts=native_time)))
 review<-list(confidence='uncertain',market_sufficient=TRUE,market_consistent=row$market_consistent,
  reason='Same-competition native support reviewed; all fresh unambiguous Titan Euro companies plus company8 Asian and total; fixed5pp residual criterion',
  counterevidence='Known lineups/injuries and opponent adjustment not quantified; later captures and date proxies authorize historical diagnostics only',
  evidence_ids=map_chr(evidence,'evidence_id'),cutoff_utc=format(cutoff$cutoff_utc,'%Y-%m-%dT%H:%M:%SZ',tz='UTC'),
  native_hash=beidan:::.score_margin_hash(native_base),market_hash=beidan:::.score_margin_hash(market_base),
  author='Codex fixed evidence audit',review_version='GLOBAL_DYNAMIC_20261018')
 sb<-c(b,list(fm_source_selection_inputs=beidan:::.score_margin_hash(list(native=native_base,market=market_base,review=review,fixture=ft,cutoff=cutoff)),
  fm_source_selection_code=digest::digest(paste(deparse(SelectFmProbabilitySource),collapse='\n'),algo='sha256'),fm_source_selection_dependencies=beidan:::.score_margin_code(implementation_root)))
 sc<-backend$build_adjustment_evidence_context(evidence,as.list(ft),epoch,sb,
  shared$AvailabilityPolicy$historical_proxy('POSTEVENT_FM_EVIDENCE_REVIEW'),'HISTORICAL_DIAGNOSTIC',implementation_root)
 selection<-SelectFmProbabilitySource(native_base,market_base,review,sc,ft,cutoff,implementation_root)
 row$selected_source<-selection$selected_source;base<-selection$base;grid<-base$grid;max_at<-base$max_source_available_utc
 judgement<-list(model_id='FM171_FULL100',rationale='Full distribution retained; no tail compression',
  bins=tibble(bin_id='all',min_margin=-Inf,max_margin=Inf,target_mass=1,evidence_id='native-support',reason='Explicit full100 research branch'))
 ab<-c(b,list(base_artifact=beidan:::.score_margin_hash(base),margin_judgement=beidan:::.score_margin_hash(judgement)))
 ac<-backend$build_adjustment_evidence_context(evidence,as.list(ft),epoch,ab,
  shared$AvailabilityPolicy$historical_proxy('POSTEVENT_FULL100_NO_TAIL'),'HISTORICAL_DIAGNOSTIC',implementation_root)
 final<-adjust_score_margin_distribution(base,judgement,ac,ft,cutoff,implementation_root)
 stopifnot(max(abs(final$grid$probability-grid$probability))<1e-12)
 q<-project_score_outcomes(final,f$handicap,implementation_root) |> select(outcome,probability) |> mutate(fixture_id=id,.before=1)
 margins<-grid |> mutate(margin=home_goals-away_goals) |> group_by(margin) |> summarise(probability=sum(probability),.groups='drop')
 feature<-q |> pivot_wider(names_from=outcome,values_from=probability) |>
  mutate(entropy=-sum(margins$probability*log(margins$probability)),local_mass=sum(margins$probability[abs(margins$margin+f$handicap)<=1]))
 fd<-list(cutoff=cutoff,features=feature,receipt=list(cutoff=cutoff,feature_hash=rlang::hash(feature),max_source_available_utc=max_at))
 key<-format(cutoff$cutoff_utc,'%Y%m%dT%H%M%SZ',tz='UTC')
 if(is.null(calibration[[key]])) {
  cp<-list(prior_issues=prior_issues,features=character(),minimum_ess=100,minimum_class_count=15L,epsilon=1e-8)
  calibration[[key]]<-beidan:::FitMarginShapeCalibration(history,cutoff,cp,as.list(hashes),implementation_root,file.path(root,'.venv/bin/python'))
 }
 calibrated<-beidan:::PredictMarginShapeCalibration(calibration[[key]],fd)
 entries[[id]]<-list(cutoff=cutoff,base=base,final=final,selection=selection,market=market,native=n,features=feature,
   RAW=q,GLOBAL=calibrated,calibration_key=key,source_receipt=list(quote_bindings=b,evidence=evidence),margins=margins)
 row$state<-'ESTIMATED_FULL100';row$reason<-'All three admitted quote channels reviewed; native supported; no tail compression'
 audit[[id]]<-row
 if(length(entries)%%10L==0L)message('frozen candidates ',length(entries),' / examined ',match(id,fixtures$fixture_id))
}
stopifnot(identical(map_chr(source_paths,~digest::digest(file=.x,algo='sha256')),hashes))
batch<-list(entries=entries,audit=bind_rows(audit),calibration=calibration,source_paths=source_paths,source_hashes=hashes,
 policy=policy,prior_label_audit=bind_rows(prior_label_audit),training_rows=nrow(history),source_implementation_root=implementation_root,prospective_admission=FALSE,target_labels_opened=FALSE)
path<-file.path(out,'frozen-forecasts.rds')
if(mode=='replay') {
 stopifnot(identical(batch,readRDS(path)))
 jsonlite::write_json(list(status='FULL_IDENTICAL_REPLAY',sha256=digest::digest(file=path,algo='sha256')),file.path(out,'forecast-replay.json'),auto_unbox=TRUE,pretty=TRUE)
}else {
 saveRDS(batch,path);write_csv(batch$audit,file.path(out,'forecast-audit.csv'))
 write_csv(tibble(name=names(source_paths),path=unname(source_paths),sha256=unname(hashes)),file.path(out,'source-manifest.csv'))
 jsonlite::write_json(list(sha256=digest::digest(file=path,algo='sha256'),scope=scope_n,estimated=length(entries),
  target_labels_opened=FALSE,prospective_admission=FALSE),file.path(out,'forecast-manifest.json'),auto_unbox=TRUE,pretty=TRUE)
}
print(batch$audit |> count(state,reason),n=Inf)
