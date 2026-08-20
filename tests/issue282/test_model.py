import torch

from issue282.model import DeepSetActionValueModel, distributional_loss


def _model_and_inputs():
    torch.manual_seed(282)
    model = DeepSetActionValueModel(cell_features=6, action_features=8, hidden=12)
    model.eval()
    cells = torch.randn(2, 9, 3, 6)
    mask = torch.tensor([[1] * 9, [1] * 7 + [0] * 2], dtype=torch.bool)
    actions = torch.randn(2, 8)
    return model, cells, mask, actions


def test_issue_encoding_is_permutation_invariant() -> None:
    model, cells, mask, actions = _model_and_inputs()
    permutation = torch.tensor([3, 1, 8, 0, 5, 2, 7, 4, 6])
    with torch.no_grad():
        original = model(cells, mask, actions)
        shuffled = model(cells[:, permutation], mask[:, permutation], actions)
    for name in ("positive_logit", "positive_magnitude", "q10", "q50", "q90"):
        assert torch.allclose(original[name], shuffled[name], atol=1e-6)


def test_quantile_heads_are_ordered_and_loss_is_finite() -> None:
    model, cells, mask, actions = _model_and_inputs()
    prediction = model(cells, mask, actions)
    assert torch.all(prediction["q10"] <= prediction["q50"])
    assert torch.all(prediction["q50"] <= prediction["q90"])
    target = torch.tensor([-16.0, 24.0])
    weight = torch.tensor([0.5, 0.5])
    loss = distributional_loss(prediction, target, issue_weight=weight)
    assert torch.isfinite(loss)
    loss.backward()
