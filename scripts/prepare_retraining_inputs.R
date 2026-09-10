# Thin declared-path entry point; no settlement reads for new issues.
args <- commandArgs(trailingOnly=TRUE)
if(length(args)!=3) stop('Usage: Rscript scripts/prepare_retraining_inputs.R train|new output_dir python')
mode <- args[1];out <- args[2];python <- args[3]
for(p in c('python_bridge','probability_exploration','fundamentals_home_away',
 'goal_distribution_experiment','fundamentals_score_diagnostic','fundamentals_score_shape',
 'fundamentals_high_margin','fundamentals_three_issue_experts','fundamentals_expert_coverage',
 'fundamentals_next_issue','fundamentals_ev_returns','fundamentals_market_comparison','fundamentals_total_market','fundamentals_retraining')) source(paste0('r/',p,'.R'))
if(mode=='new') {
  x <- retraining_new_inputs(file.path(out,'new-inventories.json'),file.path(out,'new-context.json'),python,getwd(),file.path(out,'parse-cache'))
  saveRDS(x,file.path(out,'new-inputs-internal.rds'))
} else if(mode=='train') {
  a_path <- 'data/derived/fundamentals_417/three-issue-experts-v1/comparison.json'
  b_path <- 'data/derived/fundamentals_417/next-issue-100104-v1/comparison.json'
  a <- jsonlite::read_json(a_path,simplifyVector=TRUE)
  b <- jsonlite::read_json(b_path,simplifyVector=TRUE)
  accepted <- dplyr::filter(b$fixtures,scenario=='baseline',!is.na(actual_home),!is.na(actual_away))
  next_features <- dplyr::semi_join(b$features,accepted,by=c('issue','slot','provider_id'))
  next_features <- dplyr::left_join(next_features,dplyr::select(accepted,issue,slot,provider_id,actual_home,actual_away),by=c('issue','slot','provider_id'),relationship='one-to-one')
  next_features$draw_target <- next_features$actual_home-next_features$actual_away+next_features$handicap==0
  next_features$cover_target <- ifelse(next_features$handicap<0,1,-1)*(next_features$actual_home-next_features$actual_away+next_features$handicap)>0
  f <- dplyr::bind_rows(a$inputs$data,next_features)
  inv <- jsonlite::read_json('data/derived/fundamentals_417/ev-returns-v1/inventories.json')
  cuts <- stats::setNames(lapply(inv,`[[`,'cutoffs'),vapply(inv,`[[`,character(1),'issue'))
  market <- ev_market_probabilities(file.path(out,'training-market/euro.json'),file.path(out,'training-market/total.json'),f,cuts,getwd(),1e-10)
  f <- retraining_market_features(f,market,cuts)
  extra <- c('market_home_goals','market_away_goals','market_total','market_draw','market_cover','market_draw_gap','market_draw_delta','market_cover_delta')
  features <- list(draw=c(a$results$draw$receipt$features,extra),high=c(a$results$high$receipt$features,extra))
  fields <- unique(c('issue','slot','provider_id','handicap','draw_target','cover_target',unlist(features)))
  data <- dplyr::select(f,dplyr::all_of(fields))
  data$issue_code <- data$issue;data$issue <- NULL;data$issue_year <- 2010L
  data$data_available_ts <- vapply(seq_len(nrow(data)),function(i)cuts[[data$issue_code[i]]][[as.character(data$slot[i])]],character(1))
  data$label_available_ts <- format(as.POSIXct(data$data_available_ts,format='%Y-%m-%dT%H:%M:%S',tz='UTC')+6*3600,'%Y-%m-%dT%H:%M:%SZ',tz='UTC')
  paths <- c(a_path,b_path,file.path(out,c('training-market/euro.json','training-market/total.json')))
  jsonlite::write_json(list(data=data,features=features,source_hashes=stats::setNames(lapply(paths,function(p)digest::digest(file=p,algo='sha256')),paths)),file.path(out,'training.json'),auto_unbox=TRUE,dataframe='rows',digits=15,na='null')
  saveRDS(market,file.path(out,'training-market-internal.rds'))
  print(table(data$issue_code));print(table(market$status$status))
} else stop('Unknown mode')
