testthat::test_that('settlement verifier rejects malformed identity and accounting', {
 root<-normalizePath('../..');work<-tempfile('settlement-entry-');dir.create(work)
 on.exit(unlink(work,recursive=TRUE),add=TRUE)
 for(case in c('valid','missing_handicap','fractional_slot','missing_net','bad_net','bad_parent','fractional_plan_slot','missing_group_hit','missing_group_gross','missing_group_stake')) {
  base<-file.path(work,case);dir.create(base)
  main<-file.path(base,'main');structure<-file.path(base,'structure');report<-file.path(base,'report')
  for(p in c(main,structure,report))dir.create(p)
  fixtures<-lapply(1:7,function(i)list(provider_id=as.character(i),slot=i,handicap=0))
  if(case=='fractional_plan_slot')fixtures[[1]]$slot<-1.9
  option<-list(fixtures=1:7,state_ids=1L,stake=2,sleeve_id=1)
  parent<-character()
  for(i in 1:2) {
   directory<-c(main,structure)[i];arm<-c('JOINT','U4')[i]
   plan<-list(fixtures=fixtures,arms=setNames(list(list(options=list(option))),arm))
   saveRDS(plan,file.path(directory,'plan.rds'))
   receipt<-list(scope=list('100101'),bindings=list('100101'=list(file='plan.rds',
    sha256=digest::digest(file=file.path(directory,'plan.rds'),algo='sha256'))))
   if(i==2)receipt$parent_receipt_sha256<-parent[1]
   jsonlite::write_json(receipt,file.path(directory,'plans-receipt.json'),auto_unbox=TRUE)
   parent[i]<-digest::digest(file=file.path(directory,'plans-receipt.json'),algo='sha256')
  }
  labels<-data.frame(issue='100101',slot=1:7,provider_id=as.character(1:7),handicap=0,
                     actual_direction='W',spf_sp=2)
  if(case=='missing_handicap')labels$handicap<-NULL
  if(case=='fractional_slot')labels$slot[1]<-1.9
  label_path<-file.path(base,'labels.csv');write.csv(labels,label_path,row.names=FALSE)
  groups<-data.frame(issue='100101',policy=c('JOINT','U4'),sleeve_id=1,hit=TRUE,gross=166.4,stake=2)
  if(startsWith(case,'missing_group_'))groups[[sub('missing_group_','',case)]]<-NULL
  periods<-data.frame(issue='100101',policy=c('JOINT','U4'),gross=166.4,stake=2,hits=1,net=164.4,stage='ORIGINAL')
  if(case=='missing_net')periods$net<-NULL
  if(case=='bad_net')periods$net<-100
  curves<-data.frame(policy=rep(c('JOINT','U4'),each=2),period=rep(0:1,2),
                     equity_cny=rep(c(100000,100164.4),2),drawdown_cny=0)
  summary<-data.frame(policy=c('JOINT','U4'),evaluation='ALL',issues=1,stake_cny=2,
    net_cny=164.4,hit_issues=1,max_drawdown_cny=0,max_drawdown_percent=0,roi_percent=8220)
  for(name in c('groups','periods','curves','summary'))
   write.csv(get(name),file.path(report,paste0(if(name=='periods')'rows' else name,'.csv')),row.names=FALSE)
  files<-list.files(report,full.names=TRUE)
  rp<-list(scope=list('100101'),parent_hashes=as.list(parent),
   labels_sha256=digest::digest(file=label_path,algo='sha256'),
   files=setNames(as.list(vapply(files,digest::digest,character(1),file=TRUE,algo='sha256')),basename(files)))
  if(case=='bad_parent')rp$parent_hashes[[1]]<-paste(rep('0',64),collapse='')
  jsonlite::write_json(rp,file.path(report,'receipt.json'),auto_unbox=TRUE)
  params<-list(main=main,structure=structure,main_sha256=parent[1],structure_sha256=parent[2],labels=label_path,output=report)
  config<-file.path(base,'params.json');jsonlite::write_json(params,config,auto_unbox=TRUE)
  output<-file.path(base,'proof.json');log<-file.path(base,'run.log')
  status<-system2(file.path(R.home('bin'),'Rscript'),shQuote(c(file.path(root,'scripts/check_n7_purchase_settlement.R'),config,output)),stdout=log,stderr=log)
  if(case=='valid') {
   testthat::expect_equal(status,0L,info=paste(readLines(log),collapse='\n'))
   testthat::expect_true(file.exists(output))
  } else {
   testthat::expect_true(status!=0L,info=case)
   testthat::expect_false(file.exists(output),info=case)
  }
 }
})
