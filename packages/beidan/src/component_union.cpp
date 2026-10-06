#include <Rcpp.h>
#include <algorithm>
#include <unordered_map>
#include <vector>
#include <string>
#include <cmath>
#include "component_union_identity.h"
using Event = std::vector<std::pair<int,int>>;
using State = std::vector<Event>;

// Canonical residual states; one memo belongs to one weighted component call.
static State canonical(State state) {
  std::sort(state.begin(),state.end());
  state.erase(std::unique(state.begin(),state.end()),state.end());
  return state;
}
static std::string state_key(const State& state) {
  std::string key;
  for(const auto& event:state){
    for(const auto& leg:event){key+=std::to_string(leg.first)+":"+std::to_string(leg.second)+",";}
    key+=";";
  }
  return key;
}
// Bounded dense ternary representation for 10--15 connected fixtures. Larger
// components use the same exact Shannon rule without a global state array.
static double grid_measure(const State& state,const Rcpp::NumericMatrix& p) {
  int n=p.nrow();std::vector<size_t> power(n);size_t size=1;
  for(int i=n-1;i>=0;--i){power[i]=size;size*=3;}
  std::vector<unsigned char> covered(size,0);
  std::unordered_map<unsigned,std::vector<size_t>> offsets_cache;
  for(const auto& event:state){
    if(event.empty())return 1;
    unsigned fixed=0;size_t base=0;
    for(const auto& leg:event){fixed|=(1u<<leg.first);base+=(leg.second-1)*power[leg.first];}
    auto found=offsets_cache.find(fixed);
    if(found==offsets_cache.end()){
      std::vector<size_t> offsets(1,0);
      for(int i=n-1;i>=0;--i)if(!(fixed&(1u<<i))){
        size_t before=offsets.size();offsets.resize(before*3);
        for(size_t j=0;j<before;++j){offsets[before+j]=offsets[j]+power[i];offsets[2*before+j]=offsets[j]+2*power[i];}
      }
      found=offsets_cache.emplace(fixed,std::move(offsets)).first;
    }
    for(size_t offset:found->second)covered[base+offset]=1;
  }
  // Reduce conditional weights in fixed code order; no Monte Carlo approximation.
  std::vector<double> values(size/3);
  for(size_t i=0;i<values.size();++i){
    double total=0;
    for(int code=0;code<3;++code){volatile double term=p(n-1,code)*covered[3*i+code];total=total+term;}
    values[i]=total;
  }
  for(int f=n-2;f>=0;--f){
    size_t next=values.size()/3;
    for(size_t i=0;i<next;++i){double total=0;
      for(int code=0;code<3;++code){volatile double term=p(f,code)*values[3*i+code];total=total+term;}
      values[i]=total;
    }
    values.resize(next);
  }
  return values[0];
}
static double decompose(const State& state,const Rcpp::NumericMatrix& p,
                        std::unordered_map<std::string,double>& memo) {
  if(state.empty())return 0;
  int pivot=p.nrow();
  for(const auto& event:state){
    if(event.empty())return 1;
    for(const auto& leg:event)pivot=std::min(pivot,leg.first);
  }
  std::string key=state_key(state);
  auto found=memo.find(key);if(found!=memo.end())return found->second;
  double total=0;
  for(int code=1;code<=3;++code){
    State residual;bool satisfied=false;
    for(const auto& event:state){
      auto pos=std::find_if(event.begin(),event.end(),[pivot](const auto& leg){return leg.first==pivot;});
      if(pos==event.end()){residual.push_back(event);continue;}
      if(pos->second!=code)continue;
      Event reduced=event;reduced.erase(reduced.begin()+std::distance(event.begin(),pos));
      if(reduced.empty()){satisfied=true;break;}
      residual.push_back(std::move(reduced));
    }
    double value=satisfied?1:decompose(canonical(std::move(residual)),p,memo);
    // Separate operations preserve the R recursion's code-order double arithmetic.
    volatile double term=p(pivot,code-1)*value;
    total=total+term;
  }
  memo.emplace(std::move(key),total);return total;
}

// [[Rcpp::export]]
std::string ComponentUnionKernelIdentity() {return COMPONENT_UNION_SOURCE_HASH;}

// [[Rcpp::export]]
double ComponentUnionKernel(Rcpp::List events,Rcpp::CharacterVector fixtures,
                            Rcpp::NumericMatrix probabilities) {
  if(probabilities.nrow()!=fixtures.size()||probabilities.ncol()!=3)Rcpp::stop("invalid probability dimensions");
  std::unordered_map<std::string,int> index;
  bool normalized=true;
  for(int i=0;i<fixtures.size();++i){
    if(fixtures[i]==NA_STRING)Rcpp::stop("missing fixture identifier");
    std::string id=Rcpp::as<std::string>(fixtures[i]);
    if(id.empty()||index.count(id))Rcpp::stop("invalid fixture identifier");
    index.emplace(id,i);double mass=0;
    for(int j=0;j<3;++j){double q=probabilities(i,j);if(!std::isfinite(q)||q<0||q>1)Rcpp::stop("invalid probability");mass+=q;}
    if(std::abs(mass-1)>1e-9)Rcpp::stop("probabilities must sum to one within 1e-9");
    if(std::abs(mass-1)>2e-15)normalized=false;
  }
  State state;
  for(int i=0;i<events.size();++i){
    SEXP raw=events[i];
    if(TYPEOF(raw)!=INTSXP&&TYPEOF(raw)!=REALSXP)Rcpp::stop("event codes must be numeric");
    Rcpp::NumericVector values=Rcpp::as<Rcpp::NumericVector>(raw);
    if(values.size()==0){state.emplace_back();continue;}
    SEXP event_names=Rf_getAttrib(raw,R_NamesSymbol);
    if(TYPEOF(event_names)!=STRSXP)Rcpp::stop("event names required");
    Rcpp::CharacterVector names(event_names);
    if(names.size()!=values.size())Rcpp::stop("event names required");
    Event event;std::vector<int> used;
    for(int j=0;j<values.size();++j){
      if(names[j]==NA_STRING)Rcpp::stop("missing event fixture");
      std::string id=Rcpp::as<std::string>(names[j]);auto found=index.find(id);
      double code=values[j];
      if(found==index.end()||!std::isfinite(code)||code!=std::floor(code)||code<1||code>3)Rcpp::stop("invalid event assignment");
      if(std::find(used.begin(),used.end(),found->second)!=used.end())Rcpp::stop("duplicate event fixture");
      used.push_back(found->second);event.emplace_back(found->second,static_cast<int>(code));
    }
    state.push_back(std::move(event));
  }
  if(state.empty())return 0;
  // Caller canonicalizes once in R. Keep its initial order and prod/sum precision.
  bool same=true;
  for(const auto& event:state){if(event.size()!=state[0].size()){same=false;break;}
    for(size_t j=0;j<event.size();++j)if(event[j].first!=state[0][j].first){same=false;break;}}
  if(same){long double total=0;for(const auto& event:state){long double mass=1;
      for(const auto& leg:event)mass*=static_cast<long double>(probabilities(leg.first,leg.second-1));
      total+=static_cast<double>(mass);}return static_cast<double>(total);}
  if(normalized&&fixtures.size()>=10&&fixtures.size()<=15)return grid_measure(state,probabilities);
  std::unordered_map<std::string,double> memo;
  return decompose(canonical(std::move(state)),probabilities,memo);
}
