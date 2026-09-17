"""Gated attention MIL head (Ilse, Tomczak & Welling, ICML 2018) for slide-level A/O/G.

Input: one bag of tile embeddings (N × D). Output: class logits (1 × C) and the
attention weight of every tile (N,), which is rendered as the heatmap.
"""

from __future__ import annotations

import torch
from torch import nn


class GatedAttentionMIL(nn.Module):
    def __init__(self, in_dim: int = 768, hidden: int = 256, attn_dim: int = 128, n_classes: int = 3, dropout: float = 0.25):
        super().__init__()
        self.embed = nn.Sequential(nn.Linear(in_dim, hidden), nn.ReLU(), nn.Dropout(dropout))
        self.attn_v = nn.Sequential(nn.Linear(hidden, attn_dim), nn.Tanh())
        self.attn_u = nn.Sequential(nn.Linear(hidden, attn_dim), nn.Sigmoid())
        self.attn_w = nn.Linear(attn_dim, 1)
        self.classifier = nn.Linear(hidden, n_classes)
        self.config = {"in_dim": in_dim, "hidden": hidden, "attn_dim": attn_dim, "n_classes": n_classes, "dropout": dropout}

    def forward(self, bag: torch.Tensor):
        h = self.embed(bag)  # (N, hidden)
        scores = self.attn_w(self.attn_v(h) * self.attn_u(h))  # (N, 1)
        attention = torch.softmax(scores, dim=0)  # (N, 1)
        slide = (attention * h).sum(dim=0, keepdim=True)  # (1, hidden)
        return self.classifier(slide), attention.squeeze(1)

    @classmethod
    def from_config(cls, config: dict) -> "GatedAttentionMIL":
        return cls(**config)
