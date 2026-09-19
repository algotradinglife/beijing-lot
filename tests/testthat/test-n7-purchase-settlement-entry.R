testthat::test_that('settlement verifier rejects identity/accounting errors and distinguishes funded debt', {
 root<-normalizePath('../..');work<-tempfile('settlement-entry-');dir.create(work)
 on.exit(unlink(work,recursive=TRUE),add=TRUE)
 for(case in c('valid','bankrupt','bankrupt_bad_funding','bankrupt_bad_stop_issue',
  'missing_handicap','fractional_slot','missing_net','bad_net','bad_parent',
  'fractional_plan_slot','missing_group_hit','missing_group_gross','missing_group_stake')) {
  bankrupt<-startsWith(case,'bankrupt');n<-if(bankrupt)100L else 1L
  ids<-if(bankrupt)sprintf('%06d',1:n) else '100101'
  stake<-if(bankrupt)1024 else 2;gross<-if(bankrupt)0 else 166.4
  base<-file.path(work,case);dir.create(base)
  main<-file.path(base,'main');structure<-file.path(base,'structure');report<-file.path(base,'report')
  for(p in c(main,structure,report))dir.create(p)
  fixtures<-lapply(1:7,function(i)list(provider_id=as.character(i),slot=i,handicap=0))
  if(case=='fractional_plan_slot')fixtures[[1]]$slot<-1.9
  option<-list(fixtures=1:7,state_ids=1L,stake=stake,sleeve_id=1)
  parent<-character()
  for(i in 1:2) {
   directory<-c(main,structure)[i];arm<-c('JOINT','U4')[i]
   plan<-list(fixtures=fixtures,arms=setNames(list(list(options=list(option))),arm))
   saveRDS(plan,file.path(directory,'plan.rds'))
   binding<-list(file='plan.rds',sha256=digest::digest(file=file.path(directory,'plan.rds'),algo='sha256'))
   receipt<-list(scope=as.list(ids),bindings=setNames(rep(list(binding),n),ids))
   if(i==2)receipt$parent_receipt_sha256<-parent[1]
   jsonlite::write_json(receipt,file.path(directory,'plans-receipt.json'),auto_unbox=TRUE)
   parent[i]<-digest::digest(file=file.path(directory,'plans-receipt.json'),algo='sha256')
  }
  labels<-data.frame(issue=rep(ids,each=7),slot=rep(1:7,n),provider_id=as.character(rep(1:7,n)),handicap=0,
                     actual_direction=if(bankrupt)'D' else 'W',spf_sp=2)
  if(case=='missing_handicap')labels$handicap<-NULL
  if(case=='fractional_slot')labels$slot[1]<-1.9
  label_path<-file.path(base,'labels.csv');write.csv(labels,label_path,row.names=FALSE)
  groups<-expand.grid(issue=ids,policy=c('JOINT','U4'),stringsAsFactors=FALSE)
  groups$sleeve_id<-1;groups$hit<-!bankrupt;groups$gross<-gross;groups$stake<-stake
  periods<-groups[c('issue','policy','gross','stake')];periods$hits<-as.integer(!bankrupt)
  periods$net<-gross-stake;periods$stage<-'ORIGINAL'
  curves<-summary<-list()
  for(policy in c('JOINT','U4'))for(basis in c('FUNDED','SHADOW')) {
   stopped<-if(bankrupt && basis=='FUNDED')seq_len(n)>=98L else rep(FALSE,n)
   st<-rep(stake,n);gr<-rep(gross,n);st[stopped]<-gr[stopped]<-0
   net<-gr-st;eq<-100000+c(0,cumsum(net));dd<-cummax(eq)-eq
   c<-data.frame(policy=policy,accounting_basis=basis,issue=c(NA_character_,ids),period=0:n,
    equity_cny=eq,drawdown_cny=dd,stake=c(0,st),gross=c(0,gr),net=c(0,net),hits=c(0,as.integer(gr>0)),
    stopped=c(FALSE,stopped),stop_started=c(FALSE,stopped & seq_len(n)==98L))
   if(case=='bankrupt_bad_funding' && basis=='FUNDED')c$equity_cny[n+1]<--2400
   curves[[length(curves)+1L]]<-c
   for(evaluation in c('ALL','ORIGINAL'))summary[[length(summary)+1L]]<-data.frame(
    policy=policy,accounting_basis=basis,evaluation=evaluation,issues=n,stake_cny=sum(st),
    net_cny=sum(net),hit_issues=sum(gr>0),profit_issues=sum(net>0),winning_groups=sum(gr>0),
    cash_cny=sum(1024-st),max_drawdown_cny=max(dd),max_drawdown_percent=100*max(dd/cummax(eq)),
    minimum_equity_cny=min(eq),net_without_best_cny=sum(net)-max(net),roi_percent=100*sum(net)/sum(st),
    bet_issues=sum(st>0),stopped_issues=sum(stopped),funding_stop_issue=if(bankrupt)'000098' else NA_character_)
  }
  curves<-do.call(rbind,curves);summary<-do.call(rbind,summary)
  funded_groups<-groups[!bankrupt | match(groups$issue,ids)<98L,]
  if(case=='bankrupt_bad_stop_issue')summary$funding_stop_issue<-'000097'
  if(startsWith(case,'missing_group_'))groups[[sub('missing_group_','',case)]]<-NULL
  if(case=='missing_net')periods$net<-NULL
  if(case=='bad_net')periods$net<-100
  for(name in c('groups','funded_groups','periods','curves','summary'))
   write.csv(get(name),file.path(report,paste0(if(name=='periods')'rows' else name,'.csv')),row.names=FALSE)
  files<-list.files(report,full.names=TRUE)
  rp<-list(scope=as.list(ids),parent_hashes=as.list(parent),
   labels_sha256=digest::digest(file=label_path,algo='sha256'),
   files=setNames(as.list(vapply(files,digest::digest,character(1),file=TRUE,algo='sha256')),basename(files)))
  if(case=='bad_parent')rp$parent_hashes[[1]]<-paste(rep('0',64),collapse='')
  jsonlite::write_json(rp,file.path(report,'receipt.json'),auto_unbox=TRUE)
  params<-list(main=main,structure=structure,main_sha256=parent[1],structure_sha256=parent[2],labels=label_path,output=report)
  config<-file.path(base,'params.json');jsonlite::write_json(params,config,auto_unbox=TRUE)
  output<-file.path(base,'proof.json');log<-file.path(base,'run.log')
  status<-system2(file.path(R.home('bin'),'Rscript'),shQuote(c(file.path(root,'scripts/check_n7_purchase_settlement.R'),config,output)),stdout=log,stderr=log)
  if(case %in% c('valid','bankrupt')) {
   testthat::expect_equal(status,0L,info=paste(readLines(log),collapse='\n'))
   testthat::expect_true(file.exists(output))
  } else {
   testthat::expect_true(status!=0L,info=case)
   testthat::expect_false(file.exists(output),info=case)
  }
 }
})
