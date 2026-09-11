"""Cutoff-bound score-grid exponential tilting for #422 retrospective research."""
from pathlib import Path
import numpy as np
import pandas as pd
from scipy.optimize import minimize
from scipy.special import logsumexp
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler, OneHotEncoder
from src.temporal_learning.core import (Cutoff, AvailabilityPolicy, AvailabilityFilter,
    PartitionPolicy, WeightingPolicy, temporal_client,
    stable_json_hash, TemporalContractError)

NUMERIC = (
    "handicap", "neutral", "home_overall_goals_for_pg", "away_overall_goals_for_pg",
    "home_overall_goals_against_pg", "away_overall_goals_against_pg",
    "home_venue_goals_for_pg", "away_venue_goals_for_pg",
    "home_venue_goals_against_pg", "away_venue_goals_against_pg",
    "home_overall_points_pg", "away_overall_points_pg",
    "home_venue_points_pg", "away_venue_points_pg",
    "home_overall_n", "away_overall_n", "home_venue_n", "away_venue_n",
    "market_home_goals", "market_away_goals", "home_goal_gap", "away_goal_gap")
MODEL_VERSION = "422-score-remap-0.1.0"

# Domain clients retain the standard context call; issue partitioning is shared.
from src.temporal_learning.issue_partitions import prepare_issue_learning_context as prepare_learning_context


def grid_basis(home, away, handicap):
    """Fixed cell statistics, goals scaled by four; no data-dependent thresholds."""
    h, a = np.asarray(home, float), np.asarray(away, float)
    if h.shape != a.shape or not np.isfinite(h).all() or not np.isfinite(a).all():
        raise ValueError("Finite matched goal vectors required")
    if (h < 0).any() or (a < 0).any() or (h != np.floor(h)).any() or (a != np.floor(a)).any():
        raise ValueError("Nonnegative integer goals required")
    if not np.isfinite(handicap) or handicap != int(handicap):
        raise ValueError("Integer home handicap required")
    d, total = h-a, (h+a)/4
    return np.stack([h/4, a/4, (d+handicap == 0), (abs(d) >= 3),
                     (h > 0) & (a > 0), total*(d == 0),
                     total*(abs(d) == 1), total*(abs(d) == 2)], axis=-1).astype(float)


def tilt_scores(probabilities, basis, design, coefficients, *, cutoff):
    """Return normalized cell probabilities, preserving zero support; no fitting/I/O.

    Arrays: fixtures x cells, fixtures x cells x 8, fixtures x features,
    features x 8. Cutoff is explicit even for pure prediction. No outcome input.
    """
    if not isinstance(cutoff, Cutoff):
        raise ValueError("Explicit cutoff required")
    p, b, x, coef = map(lambda a: np.asarray(a, float),
                        (probabilities, basis, design, coefficients))
    if p.ndim != 2 or b.shape != (*p.shape, 8) or x.ndim != 2 or x.shape[0] != len(p) or coef.shape != (x.shape[1], 8):
        raise ValueError("Score/design shape mismatch")
    if not all(np.isfinite(v).all() for v in (p,b,x,coef)) or (p < 0).any() or not np.allclose(p.sum(1),1,atol=1e-8,rtol=0):
        raise ValueError("Finite normalized score grids required")
    logp = np.full(p.shape, -np.inf)
    np.log(p, out=logp, where=p>0)
    logits = logp + np.einsum("nsb,nb->ns", b, x@coef)
    result = np.exp(logits-logsumexp(logits,axis=1,keepdims=True))
    if not np.isfinite(result).all():
        raise ValueError("Nonfinite tilted distribution")
    return result


def score_metrics(probabilities, home, away, handicap, actual_home, actual_away):
    """Per-fixture score/WDL losses and event diagnostics; natural-log nats.

    Zero observed-cell mass is floored at 1e-15 for log scoring, explicitly counted.
    Conditional total error is measured only in the realized net-goal stratum.
    """
    p = np.asarray(probabilities,float)
    h,a = np.asarray(home),np.asarray(away)
    ah,aa = np.asarray(actual_home),np.asarray(actual_away)
    if p.ndim != 2 or h.shape != p.shape or a.shape != p.shape or len(ah)!=len(p) or len(aa)!=len(p):
        raise ValueError("Metric dimensions differ")
    if not np.isfinite(p).all() or (p<0).any() or not np.allclose(p.sum(1),1,atol=1e-8,rtol=0):
        raise ValueError("Invalid probability mass")
    net=h-a; truth=ah-aa; line=np.asarray(handicap)[:,None]
    wdl=np.stack([(p*(net+line>0)).sum(1),(p*(net+line==0)).sum(1),
                  (p*(net+line<0)).sum(1)],axis=1)
    y=np.where(truth+np.asarray(handicap)>0,0,np.where(truth+np.asarray(handicap)==0,1,2))
    mass=(p*((h==ah[:,None])&(a==aa[:,None]))).sum(1)
    same=net==truth[:,None]; denom=(p*same).sum(1)
    cmean=np.divide((p*same*(h+a)).sum(1),denom,out=np.full(len(p),np.nan),where=denom>0)
    conditional_actual=np.divide(mass,denom,out=np.zeros(len(p)),where=denom>0)
    conditional_squares=np.divide((p*p*same).sum(1),denom*denom,
                                  out=np.full(len(p),np.nan),where=denom>0)
    order=np.argsort(-wdl,axis=1,kind="stable")
    result=dict(score_logloss=-np.log(np.maximum(mass,1e-15)),
        zero_score_mass=mass==0,score_brier=(p*p).sum(1)-2*mass+1,
        wdl_logloss=-np.log(np.maximum(wdl[np.arange(len(p)),y],1e-15)),
        wdl_brier=((wdl-np.eye(3)[y])**2).sum(1),
        top1=order[:,0]==y,top2=(order[:,:2]==y[:,None]).any(1),
        p_W=wdl[:,0],p_D=wdl[:,1],p_L=wdl[:,2],
        draw_actual=y==1,large_probability=(p*(abs(net)>=3)).sum(1),large_actual=abs(truth)>=3,
        btts_probability=(p*((h>0)&(a>0))).sum(1),btts_actual=(ah>0)&(aa>0),
        conditional_total_expected=cmean,conditional_total_actual=ah+aa,
        conditional_total_error=cmean-ah-aa,
        conditional_total_logloss=-np.log(np.maximum(conditional_actual,1e-15)),
        conditional_total_brier=conditional_squares-2*conditional_actual+1)
    return pd.DataFrame(result)


@temporal_client
def fit_remapper(history, probabilities, basis, home, away, *, cutoff, repository_root,
                 source_hashes, method, penalties, availability_policy, intended_use,
                 partition_policy, weighting_policy):
    """Fit and select a penalized cell tilt using shared prior-only partitions.

    history index must match array row indices and includes unique fixture_id,
    chronology, NUMERIC/competition, actual_home/away. All preprocessing fits on
    fit only; tune selects penalty; calibration only measures frozen selection.
    Returns transformer/coefficients and complete shared receipt, no writes.
    """
    if method not in {"GLOBAL","CONDITIONAL","MARKET_CONTEXT"} or not penalties or any(v<=0 for v in penalties):
        raise ValueError("Known method and explicit positive penalty grid required")
    if history.fixture_id.duplicated().any() or not np.array_equal(history.index,np.arange(len(history))):
        raise ValueError("Unique fixtures with positional indices required")
    context=prepare_learning_context(history,cutoff,source_hashes=source_hashes,
        repository_root=Path(repository_root),implementation_modules=("src.conditional_score.model",),
        implementation_distributions=("numpy","pandas","scipy","scikit-learn"),
        availability=AvailabilityFilter(availability_policy,data_available_column="data_available_ts"),
        intended_use=intended_use,partition_policy=partition_policy,weighting_policy=weighting_policy)
    fit,tune,calibration=(context.partitions[k] for k in ("fit","tune","calibration"))
    transformer=None
    if method in {"CONDITIONAL","MARKET_CONTEXT"}:
        columns=list(NUMERIC) if method=="CONDITIONAL" else [
            "handicap","market_home_goals","market_away_goals","home_goal_gap","away_goal_gap"]
        transforms=[
            ("numbers",make_pipeline(SimpleImputer(strategy="median",add_indicator=True,
                                                   keep_empty_features=True),StandardScaler()),columns)]
        if method=="CONDITIONAL":
            transforms.append(("league",OneHotEncoder(handle_unknown="ignore",sparse_output=False),["competition"]))
        transformer=ColumnTransformer(transforms)
        transformer.fit(fit)
    def design(frame):
        if method=="GLOBAL": return np.ones((len(frame),1))
        return np.column_stack([np.ones(len(frame)),transformer.transform(frame)])
    x=design(fit); p=probabilities[fit.index]; b=basis[fit.index]
    # Scoring features of actual goals, without opening any target outcome.
    y=np.stack([grid_basis([r.actual_home],[r.actual_away],r.handicap)[0]
                for r in fit.itertuples()])
    weights=context.weights.loc[fit.index].to_numpy()
    weights=weights/weights.sum()
    def objective(flat, penalty):
        coef=flat.reshape(x.shape[1],8)
        q=tilt_scores(p,b,x,coef,cutoff=cutoff)
        logp=np.full(p.shape,-np.inf);np.log(p,out=logp,where=p>0)
        logits=logp+np.einsum("nsb,nb->ns",b,x@coef)
        loss=np.dot(weights,logsumexp(logits,axis=1)-(y*(x@coef)).sum(1))
        gradient=x.T@((np.einsum("ns,nsb->nb",q,b)-y)*weights[:,None])
        return loss+penalty/2*np.square(coef).sum(),(gradient+penalty*coef).ravel()
    candidates=[]
    for penalty in penalties:
        solution=minimize(objective,np.zeros(x.shape[1]*8),args=(penalty,),jac=True,
                          method="L-BFGS-B",options={"maxiter":150,"ftol":1e-10})
        if not solution.success: raise RuntimeError("Score optimization failed: "+solution.message)
        coef=solution.x.reshape(x.shape[1],8)
        q=tilt_scores(probabilities[tune.index],basis[tune.index],design(tune),coef,cutoff=cutoff)
        metric=score_metrics(q,home[tune.index],away[tune.index],tune.handicap,
                             tune.actual_home,tune.actual_away)
        candidates.append((float(metric.score_logloss.mean()),float(penalty),coef))
    loss,penalty,coef=min(candidates,key=lambda c:(c[0],-c[1]))
    metrics={}
    for name,part in (("fit",fit),("validation",tune),("calibration",calibration)):
        q=tilt_scores(probabilities[part.index],basis[part.index],design(part),coef,cutoff=cutoff)
        m=score_metrics(q,home[part.index],away[part.index],part.handicap,part.actual_home,part.actual_away)
        metrics[name]={"rows":len(part),"issues":part.issue_code.nunique(),
                       **m[["score_logloss","score_brier","wdl_logloss","wdl_brier","top1","top2"]].mean().to_dict()}
    receipt=dict(context.receipt.payload)
    receipt.update(model_version=MODEL_VERSION,method=method,selected_parameters={"penalty":penalty},
        candidate_metrics=[{"penalty":c[1],"validation_score_logloss":c[0]} for c in candidates],
        coefficients=coef.tolist(),metrics=metrics,
        fit_support=len(fit),fit_issue_support=fit.issue_code.nunique(),
        feature_names=["intercept"]+(transformer.get_feature_names_out().tolist() if transformer else []),
        weight_ledger=context.weight_ledger.to_json(orient="records",date_format="iso"),
        gate_predicates={"optimization_converged":True,"prospective":intended_use=="PROSPECTIVE_DECISION"})
    if transformer is not None:
        numeric=transformer.named_transformers_["numbers"]
        receipt["preprocessing"]={
            "imputer_statistics":numeric[0].statistics_.tolist(),
            "missing_indicator_columns":numeric[0].indicator_.features_.tolist(),
            "scale_mean":numeric[1].mean_.tolist(),
            "scale_scale":numeric[1].scale_.tolist(),
            "league_categories":([v.tolist() for v in transformer.named_transformers_["league"].categories_]
                                  if "league" in transformer.named_transformers_ else [])}
    else:
        receipt["preprocessing"]={}
    receipt["artifact_sha256"]=stable_json_hash(receipt)
    return dict(transformer=transformer,coefficients=coef,receipt=receipt,cutoff=cutoff,
                method=method)


def predict_remapper(artifact, frame, probabilities, basis, *, cutoff):
    """Predict from frozen coefficients. Reject wrong target/earlier cutoff; no labels."""
    trained=artifact["cutoff"]
    if not isinstance(cutoff,Cutoff) or cutoff.target_issue!=trained.target_issue or cutoff.cutoff_ts<trained.cutoff_ts:
        raise TemporalContractError("Prediction cutoff must match frozen issue and follow training")
    if {"actual_home","actual_away","spf_sp"} & set(frame):
        raise ValueError("Target prediction frame must be label-free")
    transformer=artifact["transformer"]
    x=np.ones((len(frame),1)) if transformer is None else np.column_stack([np.ones(len(frame)),transformer.transform(frame)])
    return tilt_scores(probabilities,basis,x,artifact["coefficients"],cutoff=cutoff)
