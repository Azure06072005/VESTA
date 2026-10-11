"""src/models/multimodal_fusion.py

F302: Multimodal Cross-Attention Fusion Architecture
Combines:
1. Text Embeddings from PhoBERT-base (768-dim [CLS] representation)
2. Tabular Accounting Ratios (24 RankGauss normalized fundamental & technical features)
3. Macro Regime State (4-state categorical / Gray code representation)

Fuses all 3 modalities via a lightweight Multi-Head Cross-Attention Transformer layer
to produce a dense 128-dim Multi-Modal Sentiment-Alpha Vector.

Multi-Task Objectives:
1. Sentiment Classification Head: 3 classes (Negative, Neutral, Positive).
2. Market Directional Prediction Head: 3 classes (Down: -1, Flat: 0, Up: +1 at T+5).
3. Continuous Return Regression Head: Huber Loss on T+5 percentage return.
"""
from __future__ import annotations

import dataclasses
from typing import List, Optional

import torch
import torch.nn as nn
import torch.nn.functional as F
from transformers import AutoConfig, AutoModel

DEFAULT_FUNDAMENTAL_FEATURES = [
    "vni_fracdiff_d020",
    "rankgauss_volume_z",
    "pe_ratio",
    "pb_ratio",
    "ps_ratio",
    "p_cf_ratio",
    "ev_ebitda",
    "dividend_yield",
    "market_cap",
    "roe",
    "roa",
    "roic",
    "gross_margin",
    "net_margin",
    "current_ratio",
    "quick_ratio",
    "debt_to_equity",
    "financial_leverage",
    "bank_nim",
    "bank_cir",
    "bank_ldr",
    "bank_npl",
    "bank_car",
    "bank_casa",
]

REGIME_TO_ID = {
    "BULL": 0,
    "BEAR": 1,
    "CRISIS_HIGH_VOL": 2,
    "SIDEWAYS": 3,
}

ID_TO_REGIME = {v: k for k, v in REGIME_TO_ID.items()}


@dataclasses.dataclass
class MultimodalFusionOutput:
    loss: Optional[torch.Tensor] = None
    loss_sentiment: Optional[torch.Tensor] = None
    loss_direction: Optional[torch.Tensor] = None
    loss_return: Optional[torch.Tensor] = None
    sentiment_logits: Optional[torch.Tensor] = None
    direction_logits: Optional[torch.Tensor] = None
    return_preds: Optional[torch.Tensor] = None
    alpha_vector: Optional[torch.Tensor] = None  # 128-dim multimodal fusion embedding


class MultimodalCrossAttentionFusion(nn.Module):
    """Multimodal Cross-Attention Fusion Model for Vietnamese Financial Markets."""

    def __init__(
        self,
        phobert_model_name: str = "vinai/phobert-base-v2",
        phobert_checkpoint: Optional[str] = None,
        freeze_phobert_layers: int = 8,  # Freeze first 8 layers to save VRAM on 6GB GPU
        num_fundamental_features: int = len(DEFAULT_FUNDAMENTAL_FEATURES),
        num_regimes: int = 4,
        hidden_dim: int = 128,
        num_heads: int = 4,
        num_fusion_layers: int = 2,
        dropout_prob: float = 0.15,
        weight_sentiment: float = 0.4,
        weight_direction: float = 0.4,
        weight_return: float = 0.2,
        use_macro_gating: bool = True,
        direction_class_weights: Optional[torch.Tensor] = None,
    ) -> None:
        super().__init__()
        self.hidden_dim = hidden_dim
        self.weight_sentiment = weight_sentiment
        self.weight_direction = weight_direction
        self.weight_return = weight_return
        self.use_macro_gating = use_macro_gating
        if direction_class_weights is not None:
            self.register_buffer("direction_class_weights", direction_class_weights)
        else:
            self.direction_class_weights = None

        # ---------------------------------------------------------------------
        # 1. Modality 1: Text Encoder (PhoBERT)
        # ---------------------------------------------------------------------
        self.config = AutoConfig.from_pretrained(phobert_model_name, local_files_only=True)
        self.text_encoder = AutoModel.from_pretrained(phobert_model_name, config=self.config, local_files_only=True)
        phobert_dim = self.config.hidden_size  # 768

        # If a trained F301 checkpoint is provided, load compatible weights
        if phobert_checkpoint and phobert_checkpoint != "":
            self._load_phobert_checkpoint(phobert_checkpoint)

        # Freeze lower layers of text encoder to drastically reduce VRAM & train time
        if freeze_phobert_layers > 0:
            self._freeze_lower_layers(freeze_phobert_layers)

        self.text_projection = nn.Sequential(
            nn.Linear(phobert_dim, hidden_dim),
            nn.LayerNorm(hidden_dim),
            nn.Dropout(dropout_prob),
        )

        # ---------------------------------------------------------------------
        # 2. Modality 2: Tabular Accounting & Technical Features
        # ---------------------------------------------------------------------
        self.num_fundamentals = num_fundamental_features
        self.fundamental_projection = nn.Sequential(
            nn.Linear(num_fundamental_features, hidden_dim),
            nn.GELU(),
            nn.Dropout(dropout_prob),
            nn.Linear(hidden_dim, hidden_dim),
            nn.LayerNorm(hidden_dim),
        )

        # ---------------------------------------------------------------------
        # 3. Modality 3: Macro Regime State
        # ---------------------------------------------------------------------
        self.regime_embedding = nn.Embedding(num_regimes, hidden_dim)
        self.regime_projection = nn.Sequential(
            nn.Linear(hidden_dim, hidden_dim),
            nn.LayerNorm(hidden_dim),
        )

        # ---------------------------------------------------------------------
        # 4. Cross-Attention Multimodal Transformer Fusion
        # ---------------------------------------------------------------------
        fusion_layer = nn.TransformerEncoderLayer(
            d_model=hidden_dim,
            nhead=num_heads,
            dim_feedforward=hidden_dim * 2,
            dropout=dropout_prob,
            activation="gelu",
            batch_first=True,
            norm_first=True,
        )
        self.transformer_fusion = nn.TransformerEncoder(
            fusion_layer,
            num_layers=num_fusion_layers,
        )

        # Dimension reduction to produce 128-dim Multi-Modal Sentiment-Alpha Vector
        self.alpha_bottleneck = nn.Sequential(
            nn.Linear(hidden_dim * 3, hidden_dim),
            nn.GELU(),
            nn.LayerNorm(hidden_dim),
            nn.Dropout(dropout_prob),
        )

        # Macro Regime Gating module (attenuates alpha conviction under adverse macro regimes per F203)
        if self.use_macro_gating:
            self.macro_gate = nn.Sequential(
                nn.Linear(hidden_dim, hidden_dim),
                nn.Sigmoid(),
            )
            nn.init.constant_(self.macro_gate[0].bias, 1.0)
        else:
            self.macro_gate = None

        # ---------------------------------------------------------------------
        # 5. Multi-Task Output Heads
        # ---------------------------------------------------------------------
        # Head 1: Sentiment Polarity (0: Negative, 1: Neutral, 2: Positive)
        self.sentiment_head = nn.Linear(hidden_dim, 3)

        # Head 2: Market Forward Return Direction at T+5 (0: Down, 1: Flat, 2: Up)
        self.direction_head = nn.Linear(hidden_dim, 3)

        # Head 3: Forward Return Magnitude at T+5 (Continuous regression)
        self.return_head = nn.Linear(hidden_dim, 1)

    def _load_phobert_checkpoint(self, checkpoint_path: str) -> None:
        """Loads weights from F301 PhoBertFinDPO checkpoint into text encoder."""
        try:
            try:
                state_dict = torch.load(checkpoint_path, map_location="cpu", weights_only=False)
            except TypeError:
                state_dict = torch.load(checkpoint_path, map_location="cpu")
            # Extract encoder keys
            encoder_dict = {}
            for k, v in state_dict.items():
                if k.startswith("encoder."):
                    encoder_dict[k.replace("encoder.", "")] = v
                elif not k.startswith("sentiment_head.") and not k.startswith("policy_head."):
                    encoder_dict[k] = v

            missing, unexpected = self.text_encoder.load_state_dict(encoder_dict, strict=False)
            print(f" -> Successfully loaded F301 text weights from {checkpoint_path} (Missing keys: {len(missing)})")
        except Exception as e:
            print(f" [WARNING] Could not load F301 checkpoint ({e}). Using base pretrained weights.")

    def _freeze_lower_layers(self, n_layers: int) -> None:
        """Freezes embeddings and first n transformer layers of text encoder."""
        if hasattr(self.text_encoder, "embeddings"):
            for p in self.text_encoder.embeddings.parameters():
                p.requires_grad = False
        if hasattr(self.text_encoder, "encoder") and hasattr(self.text_encoder.encoder, "layer"):
            for layer in self.text_encoder.encoder.layer[:n_layers]:
                for p in layer.parameters():
                    p.requires_grad = False
            print(f" -> Frozen lower {n_layers} PhoBERT layers (preserving VRAM on 6GB GPU).")

    def forward(
        self,
        input_ids: Optional[torch.Tensor] = None,
        attention_mask: Optional[torch.Tensor] = None,
        fundamentals: Optional[torch.Tensor] = None,
        regime_ids: Optional[torch.Tensor] = None,
        sentiment_labels: Optional[torch.Tensor] = None,
        direction_labels: Optional[torch.Tensor] = None,
        return_targets: Optional[torch.Tensor] = None,
        text_cls: Optional[torch.Tensor] = None,
    ) -> MultimodalFusionOutput:
        # 1. Encode Text Modality
        if text_cls is None:
            text_outputs = self.text_encoder(input_ids=input_ids, attention_mask=attention_mask)
            text_cls = text_outputs.last_hidden_state[:, 0, :]  # [B, 768]
        t_token = self.text_projection(text_cls).unsqueeze(1)  # [B, 1, hidden_dim]

        # 2. Encode Tabular Fundamentals Modality
        # Handle possible NaN values in fundamentals
        fund_clean = torch.nan_to_num(fundamentals, nan=0.0, posinf=3.0, neginf=-3.0)
        f_token = self.fundamental_projection(fund_clean).unsqueeze(1)  # [B, 1, hidden_dim]

        # 3. Encode Macro Regime Modality
        r_emb = self.regime_embedding(regime_ids)
        r_token = self.regime_projection(r_emb).unsqueeze(1)  # [B, 1, hidden_dim]

        # 4. Concatenate Modality Sequence: [B, 3, hidden_dim]
        # Token 0: Text, Token 1: Fundamentals, Token 2: Macro Regime
        modal_seq = torch.cat([t_token, f_token, r_token], dim=1)

        # Cross-Attention across modalities
        fused_seq = self.transformer_fusion(modal_seq)  # [B, 3, hidden_dim]

        # Flatten & bottleneck to extract 128-dim Multi-Modal Sentiment-Alpha Vector
        fused_flat = fused_seq.reshape(fused_seq.size(0), -1)  # [B, 3 * hidden_dim]
        alpha_vec = self.alpha_bottleneck(fused_flat)  # [B, 128]

        # Apply Macro Regime Gating (MHI-aware attenuation)
        if self.use_macro_gating and self.macro_gate is not None:
            gate = self.macro_gate(r_token.squeeze(1))  # [B, hidden_dim] in (0, 1)
            alpha_vec = alpha_vec * gate

        # 5. Multi-Task Predictions
        sentiment_logits = self.sentiment_head(alpha_vec)
        direction_logits = self.direction_head(alpha_vec)
        return_preds = self.return_head(alpha_vec).squeeze(-1)

        # 6. Loss Calculation
        loss_sentiment: Optional[torch.Tensor] = None
        loss_direction: Optional[torch.Tensor] = None
        loss_return: Optional[torch.Tensor] = None
        total_loss: Optional[torch.Tensor] = None

        if sentiment_labels is not None:
            loss_sentiment = F.cross_entropy(sentiment_logits, sentiment_labels)

        if direction_labels is not None:
            # direction_labels should be in {0: Down, 1: Flat, 2: Up}
            if self.direction_class_weights is not None:
                loss_direction = F.cross_entropy(direction_logits, direction_labels, weight=self.direction_class_weights)
            else:
                loss_direction = F.cross_entropy(direction_logits, direction_labels)

        if return_targets is not None:
            clean_targets = torch.nan_to_num(return_targets, nan=0.0)
            loss_return = F.smooth_l1_loss(return_preds, clean_targets)

        # Compute weighted total loss
        active_losses: List[torch.Tensor] = []
        if loss_sentiment is not None:
            active_losses.append(self.weight_sentiment * loss_sentiment)
        if loss_direction is not None:
            active_losses.append(self.weight_direction * loss_direction)
        if loss_return is not None:
            active_losses.append(self.weight_return * loss_return)

        if active_losses:
            total_loss = sum(active_losses)

        return MultimodalFusionOutput(
            loss=total_loss,
            loss_sentiment=loss_sentiment,
            loss_direction=loss_direction,
            loss_return=loss_return,
            sentiment_logits=sentiment_logits,
            direction_logits=direction_logits,
            return_preds=return_preds,
            alpha_vector=alpha_vec,
        )

    @torch.no_grad()
    def extract_alpha_vector(
        self,
        input_ids: torch.Tensor,
        attention_mask: torch.Tensor,
        fundamentals: torch.Tensor,
        regime_ids: torch.Tensor,
    ) -> torch.Tensor:
        """Utility for downstream backtesting (F303) and execution (F401) to obtain 128-dim alpha vector."""
        out = self.forward(
            input_ids=input_ids,
            attention_mask=attention_mask,
            fundamentals=fundamentals,
            regime_ids=regime_ids,
        )
        return out.alpha_vector  # [B, 128]

