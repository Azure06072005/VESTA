"""src/models/phobert_findpo.py

PhoBertFinDPO: Dual-Head Architecture for Vietnamese Financial Sentiment & FinDPO Market Alignment.
Reference: FinDPO (Financial Direct Preference Optimization, arXiv:2507.18417).

Architecture:
1. Backbone: vinai/phobert-base-v2 (RoBERTa architecture, hidden_size=768).
2. Head 1 (Sentiment Classification):
   Cross-Entropy Loss on 3 discrete classes: 0: NEGATIVE, 1: NEUTRAL, 2: POSITIVE.
3. Head 2 (FinDPO Policy Reward):
   Scalar policy value s(x, a).
   Bradley-Terry DPO Loss on (chosen, rejected) preference pairs conditioned on F203 regimes.
4. Multi-Task Objective:
   Loss_total = (1 - lambda) * Loss_CE + lambda * Loss_DPO
"""
from __future__ import annotations

import dataclasses
from typing import Optional

import torch
# pyrefly: ignore [missing-import]
import torch.nn as nn
import torch.nn.functional as F
from transformers import AutoConfig, AutoModel


@dataclasses.dataclass
class PhoBertFinDPOOutput:
    loss: Optional[torch.Tensor] = None
    loss_ce: Optional[torch.Tensor] = None
    loss_dpo: Optional[torch.Tensor] = None
    sentiment_logits: Optional[torch.Tensor] = None
    chosen_scores: Optional[torch.Tensor] = None
    rejected_scores: Optional[torch.Tensor] = None
    hidden_states: Optional[torch.Tensor] = None


class PhoBertFinDPO(nn.Module):
    def __init__(
        self,
        model_name: str = "vinai/phobert-base-v2",
        num_labels: int = 3,
        dropout_prob: float = 0.15,
        beta: float = 0.1,
        preference_weight: float = 0.4,
        class_weights: Optional[torch.Tensor] = None,
    ) -> None:
        super().__init__()
        self.config = AutoConfig.from_pretrained(model_name)
        self.encoder = AutoModel.from_pretrained(model_name, config=self.config)
        hidden_size = self.config.hidden_size

        self.num_labels = num_labels
        self.beta = beta
        self.preference_weight = preference_weight
        if class_weights is not None:
            self.register_buffer("class_weights", class_weights)
        else:
            self.register_buffer("class_weights", torch.ones(num_labels, dtype=torch.float32))

        self.dropout = nn.Dropout(dropout_prob)
        # Head 1: Supervised 3-class sentiment classifier
        self.sentiment_head = nn.Linear(hidden_size, num_labels)
        # Head 2: FinDPO policy reward / preference head
        self.policy_head = nn.Linear(hidden_size, 1)

    def extract_features(
        self,
        input_ids: torch.Tensor,
        attention_mask: torch.Tensor,
    ) -> torch.Tensor:
        """Extracts pooled [CLS] representation (first token) from encoder outputs."""
        outputs = self.encoder(input_ids=input_ids, attention_mask=attention_mask)
        # Sequence output shape: (batch_size, seq_len, hidden_size)
        cls_rep = outputs.last_hidden_state[:, 0, :]
        return cls_rep

    def forward(
        self,
        input_ids: torch.Tensor,
        attention_mask: torch.Tensor,
        labels: Optional[torch.Tensor] = None,
        chosen_input_ids: Optional[torch.Tensor] = None,
        chosen_attention_mask: Optional[torch.Tensor] = None,
        rejected_input_ids: Optional[torch.Tensor] = None,
        rejected_attention_mask: Optional[torch.Tensor] = None,
    ) -> PhoBertFinDPOOutput:
        # 1. Base input sentiment forward pass
        cls_rep = self.extract_features(input_ids, attention_mask)
        pooled_rep = self.dropout(cls_rep)
        sentiment_logits = self.sentiment_head(pooled_rep)

        loss_ce: Optional[torch.Tensor] = None
        if labels is not None:
            loss_ce = F.cross_entropy(sentiment_logits, labels, weight=self.class_weights)

        # 2. FinDPO preference forward pass (if preference inputs are supplied)
        loss_dpo: Optional[torch.Tensor] = None
        chosen_scores: Optional[torch.Tensor] = None
        rejected_scores: Optional[torch.Tensor] = None

        if (
            chosen_input_ids is not None
            and chosen_attention_mask is not None
            and rejected_input_ids is not None
            and rejected_attention_mask is not None
        ):
            # Encode chosen pairs
            chosen_rep = self.extract_features(chosen_input_ids, chosen_attention_mask)
            chosen_scores = self.policy_head(self.dropout(chosen_rep)).squeeze(-1)

            # Encode rejected pairs
            rejected_rep = self.extract_features(rejected_input_ids, rejected_attention_mask)
            rejected_scores = self.policy_head(self.dropout(rejected_rep)).squeeze(-1)

            # Bradley-Terry DPO Loss with temperature beta
            # L_dpo = -E[log(sigmoid(beta * (s_w - s_l)))]
            score_diff = self.beta * (chosen_scores - rejected_scores)
            loss_dpo = -F.logsigmoid(score_diff).mean()

        # 3. Combine multi-task loss
        total_loss: Optional[torch.Tensor] = None
        if loss_ce is not None and loss_dpo is not None:
            total_loss = (1.0 - self.preference_weight) * loss_ce + self.preference_weight * loss_dpo
        elif loss_ce is not None:
            total_loss = loss_ce
        elif loss_dpo is not None:
            total_loss = loss_dpo

        return PhoBertFinDPOOutput(
            loss=total_loss,
            loss_ce=loss_ce,
            loss_dpo=loss_dpo,
            sentiment_logits=sentiment_logits,
            chosen_scores=chosen_scores,
            rejected_scores=rejected_scores,
            hidden_states=cls_rep,
        )
