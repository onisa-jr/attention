import torch
import torch.nn.functional as F
from torch import nn, Tensor, BoolTensor
from typing import Optional


class Attention(nn.Module):
    def __init__(self, word_size:int=512, embed_dim:int=64) -> None:
        super().__init__()
        self.embed_dim = embed_dim
        self.dim_K = torch.tensor(embed_dim)
        self.query = nn.Linear(in_features=word_size, out_features=embed_dim, bias=True)
        self.key  = nn.Linear(in_features=word_size, out_features=embed_dim, bias=True)
        self.value = nn.Linear(in_features=word_size, out_features=embed_dim, bias=True)

    def self_attention(self, Q: Tensor, K: Tensor, V: Tensor,
                       mask:Optional[BoolTensor]=None) -> Tensor:
        """
        Perform self-attention on the input tensors.

        This is a simple implementation of self-attention that uses the dot product attention mechanism.
        If you are looking for attention with better performance, please try:

        * `F.scaled_dot_product_attention`
        * [Flash Attention](https://github.com/Dao-AILab/flash-attention)
        * [Memory-efficient attention](https://facebookresearch.github.io/xformers/components/ops.html)

        Args:
            Q (torch.Tensor): The query tensor.
            K (torch.Tensor): The key tensor.
            V (torch.Tensor): The value tensor.
            mask (Optional[torch.BoolTensor]): A mask tensor used to hide specific positions in the input sequence.
                It should have the same shape as Q, K, and must be a Boolean tensor with 0s indicating positions to be masked.
                Use `None` for no masking. Default is `None`.
        Returns:
            The output tensor of the self-attention layer.
        """
        # expected [b, seq, embed_dim]
        K_T = torch.transpose(K, -1, -2)
        score = torch.matmul(Q, K_T)                # Matmul
        score /= torch.sqrt(self.dim_K)             # Scale
        if mask is not None:                        # Mask (opt.)
            score = torch.masked_fill(score, mask==0, -torch.inf)
        score = torch.softmax(score, dim=-1)        # SoftMax
        Z = torch.matmul(score, V)                  # Matmul
        return Z

    def forward(self, x:Tensor, mask:Optional[BoolTensor]=None) -> Tensor:
        Q = self.query(x)
        K = self.key(x)
        V = self.value(x)
        Z = self.self_attention(Q, K, V, mask=mask)
        # Z = F.scaled_dot_product_attention(Q, K, V)
        return Z


class MultiheadAttention(nn.Module):
    r"""
    https://arxiv.org/abs/1706.03762
    """
    def __init__(self, word_size: int = 512, embed_dim: int = 64, n_head:int=8) -> None:
        super().__init__()
        self.n_head = n_head
        self.embed_dim = embed_dim
        self.dim_K = torch.tensor(embed_dim)
        self.proj = nn.Linear(in_features=embed_dim * n_head,
                             out_features=embed_dim, bias=False)
        self.multihead = nn.ModuleList([
            Attention(word_size, embed_dim) for _ in range(n_head)
        ])

    def forward(self, x: Tensor, mask:Optional[BoolTensor]=None) -> Tensor:
        Z_s = torch.cat([head(x, mask) for head in self.multihead], dim=1)
        Z = self.proj(Z_s)
        return Z


class  MultiQueryAttention(Attention):
    r"""
    https://arxiv.org/pdf/1911.02150.pdf
    """
    def __init__(self, word_size: int = 512, embed_dim: int = 64, n_query:int=8) -> None:
        super().__init__(word_size, embed_dim)
        self.n_query = n_query
        self.proj = nn.Linear(in_features=embed_dim * n_query,
                              out_features=embed_dim, bias=False)
        delattr(self, 'query')
        self.querys = nn.ModuleList([
            nn.Linear(in_features=word_size, out_features=embed_dim, bias=True)
            for _ in range(n_query)
        ])
        self.key = nn.Linear(in_features=word_size, out_features=embed_dim, bias=True)
        self.value = nn.Linear(in_features=word_size, out_features=embed_dim, bias=True)

    def forward(self, x: Tensor, mask:Optional[BoolTensor]=None) -> Tensor:
        K = self.key(x)
        V = self.value(x)
        Z_s = torch.cat([
            self.self_attention(query(x), K, V, mask) for query in self.querys
        ], dim=1)
        Z = self.proj(Z_s)
        return Z


class  GroupedQueryAttention(Attention):
    r"""
    https://arxiv.org/pdf/2305.13245.pdf
    """
    def __init__(self, word_size: int = 512, embed_dim: int = 64,
                 n_grouped: int = 4, n_query_each_group:int=2) -> None:
        super().__init__(word_size, embed_dim)
        delattr(self, 'query')
        delattr(self, 'key')
        delattr(self, 'value')

        self.grouped = nn.ModuleList([
            MultiQueryAttention(word_size, embed_dim, n_query=n_query_each_group)
            for _ in range(n_grouped)
        ])
        self.proj = nn.Linear(in_features=embed_dim * n_grouped,
                              out_features=embed_dim, bias=False)

    def forward(self, x: Tensor, mask:Optional[BoolTensor]=None) -> Tensor:
        Z_s = torch.cat([head(x, mask) for head in self.grouped], dim=1)
        Z = self.proj(Z_s)
        return Z
