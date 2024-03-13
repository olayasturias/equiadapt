# Layers for vector neuron networks
# Taken from Vector Neurons: A General Framework for SO(3)-Equivariant Networks (https://arxiv.org/abs/2104.12229) paper and
# their codebase https://github.com/FlyingGiraffe/vnn

import torch
import torch.nn as nn
from typing import Tuple

EPS = 1e-6


class VNLinear(nn.Module):
    def __init__(self, in_channels: int, out_channels: int):
        super(VNLinear, self).__init__()
        self.map_to_feat = nn.Linear(in_channels, out_channels, bias=False)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        """
        x: point features of shape [B, N_feat, 3, N_samples, ...]
        """
        x_out = self.map_to_feat(x.transpose(1, -1)).transpose(1, -1)
        return x_out


class VNBilinear(nn.Module):
    def __init__(self, in_channels1: int, in_channels2: int, out_channels: int):
        super(VNBilinear, self).__init__()
        self.map_to_feat = nn.Bilinear(
            in_channels1, in_channels2, out_channels, bias=False
        )

    def forward(self, x: torch.Tensor, labels: torch.Tensor) -> torch.Tensor:
        """
        x: point features of shape [B, N_feat, 3, N_samples, ...]
        """
        labels = labels.repeat(1, x.shape[2], 1).float()
        x_out = self.map_to_feat(x.transpose(1, -1), labels).transpose(1, -1)
        return x_out


class VNSoftplus(nn.Module):
    def __init__(
        self,
        in_channels: int,
        share_nonlinearity: bool = False,
        negative_slope: float = 0.0,
    ):
        super(VNSoftplus, self).__init__()
        if share_nonlinearity:
            self.map_to_dir = nn.Linear(in_channels, 1, bias=False)
        else:
            self.map_to_dir = nn.Linear(in_channels, in_channels, bias=False)
        self.negative_slope = negative_slope

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        """
        x: point features of shape [B, N_feat, 3, N_samples, ...]
        """
        d = self.map_to_dir(x.transpose(1, -1)).transpose(1, -1)
        dotprod = (x * d).sum(2, keepdim=True)
        angle_between = torch.acos(
            dotprod
            / (
                torch.norm(x, dim=2, keepdim=True) * torch.norm(d, dim=2, keepdim=True)
                + EPS
            )
        )
        mask = torch.cos(angle_between / 2) ** 2
        d_norm_sq = (d * d).sum(2, keepdim=True)
        x_out = self.negative_slope * x + (1 - self.negative_slope) * (
            mask * x + (1 - mask) * (x - (dotprod / (d_norm_sq + EPS)) * d)
        )
        return x_out


class VNLeakyReLU(nn.Module):
    def __init__(
        self,
        in_channels: int,
        share_nonlinearity: bool = False,
        negative_slope: float = 0.2,
    ):
        super(VNLeakyReLU, self).__init__()
        if share_nonlinearity:
            self.map_to_dir = nn.Linear(in_channels, 1, bias=False)
        else:
            self.map_to_dir = nn.Linear(in_channels, in_channels, bias=False)
        self.negative_slope = negative_slope

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        """
        x: point features of shape [B, N_feat, 3, N_samples, ...]
        """
        d = self.map_to_dir(x.transpose(1, -1)).transpose(1, -1)
        dotprod = (x * d).sum(2, keepdim=True)
        mask = (dotprod >= 0).float()
        d_norm_sq = (d * d).sum(2, keepdim=True)
        x_out = self.negative_slope * x + (1 - self.negative_slope) * (
            mask * x + (1 - mask) * (x - (dotprod / (d_norm_sq + EPS)) * d)
        )
        return x_out


class VNLinearLeakyReLU(nn.Module):
    def __init__(
        self,
        in_channels: int,
        out_channels: int,
        dim: int = 5,
        share_nonlinearity: bool = False,
        negative_slope: float = 0.2,
    ):
        super(VNLinearLeakyReLU, self).__init__()
        self.dim = dim
        self.negative_slope = negative_slope

        self.map_to_feat = nn.Linear(in_channels, out_channels, bias=False)
        self.batchnorm = VNBatchNorm(out_channels, dim=dim)

        if share_nonlinearity:
            self.map_to_dir = nn.Linear(in_channels, 1, bias=False)
        else:
            self.map_to_dir = nn.Linear(in_channels, out_channels, bias=False)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        """
        x: point features of shape [B, N_feat, 3, N_samples, ...]
        """
        # Linear
        p = self.map_to_feat(x.transpose(1, -1)).transpose(1, -1)
        # BatchNorm
        p = self.batchnorm(p)
        # LeakyReLU
        d = self.map_to_dir(x.transpose(1, -1)).transpose(1, -1)
        dotprod = (p * d).sum(2, keepdims=True)
        mask = (dotprod >= 0).float()
        d_norm_sq = (d * d).sum(2, keepdims=True)
        x_out = self.negative_slope * p + (1 - self.negative_slope) * (
            mask * p + (1 - mask) * (p - (dotprod / (d_norm_sq + EPS)) * d)
        )
        return x_out


class VNBatchNorm(nn.Module):
    def __init__(self, num_features: int, dim: int):
        super(VNBatchNorm, self).__init__()
        self.dim = dim
        if dim == 3 or dim == 4:
            self.bn1d = nn.BatchNorm1d(num_features)
        elif dim == 5:
            self.bn2d = nn.BatchNorm2d(num_features)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        """
        x: point features of shape [B, N_feat, 3, N_samples, ...]
        """
        # norm = torch.sqrt((x*x).sum(2))
        norm = torch.norm(x, dim=2) + EPS
        if self.dim == 3 or self.dim == 4:
            norm_bn = self.bn1d(norm)
        elif self.dim == 5:
            norm_bn = self.bn2d(norm)
        norm = norm.unsqueeze(2)
        norm_bn = norm_bn.unsqueeze(2)
        x = x / norm * norm_bn

        return x


class VNMaxPool(nn.Module):
    def __init__(self, in_channels: int):
        super(VNMaxPool, self).__init__()
        self.map_to_dir = nn.Linear(in_channels, in_channels, bias=False)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        """
        x: point features of shape [B, N_feat, 3, N_samples, ...]
        """
        d = self.map_to_dir(x.transpose(1, -1)).transpose(1, -1)
        dotprod = (x * d).sum(2, keepdims=True)
        idx = dotprod.max(dim=-1, keepdim=False)[1]
        index_tuple = torch.meshgrid([torch.arange(j) for j in x.size()[:-1]]) + (idx,)
        x_max = x[index_tuple]
        return x_max


def mean_pool(x: torch.Tensor, dim: int = -1, keepdim: bool = False) -> torch.Tensor:
    return x.mean(dim=dim, keepdim=keepdim)


class VNStdFeature(nn.Module):
    def __init__(
        self,
        in_channels: int,
        dim: int = 4,
        normalize_frame: bool = False,
        share_nonlinearity: bool = False,
        negative_slope: float = 0.2,
    ):
        super(VNStdFeature, self).__init__()
        self.dim = dim
        self.normalize_frame = normalize_frame

        self.vn1 = VNLinearLeakyReLU(
            in_channels,
            in_channels // 2,
            dim=dim,
            share_nonlinearity=share_nonlinearity,
            negative_slope=negative_slope,
        )
        self.vn2 = VNLinearLeakyReLU(
            in_channels // 2,
            in_channels // 4,
            dim=dim,
            share_nonlinearity=share_nonlinearity,
            negative_slope=negative_slope,
        )
        if normalize_frame:
            self.vn_lin = nn.Linear(in_channels // 4, 2, bias=False)
        else:
            self.vn_lin = nn.Linear(in_channels // 4, 3, bias=False)

    def forward(self, x: torch.Tensor) -> Tuple[torch.Tensor, torch.Tensor]:
        """
        x: point features of shape [B, N_feat, 3, N_samples, ...]
        """
        z0 = x
        z0 = self.vn1(z0)
        z0 = self.vn2(z0)
        z0 = self.vn_lin(z0.transpose(1, -1)).transpose(1, -1)

        if self.normalize_frame:
            v1 = z0[:, 0, :]
            v1_norm = torch.sqrt((v1 * v1).sum(1, keepdims=True))  # type: ignore
            u1 = v1 / (v1_norm + EPS)
            v2 = z0[:, 1, :]
            v2 = v2 - (v2 * u1).sum(1, keepdims=True) * u1  # type: ignore
            v2_norm = torch.sqrt((v2 * v2).sum(1, keepdims=True))  # type: ignore
            u2 = v2 / (v2_norm + EPS)

            # compute the cross product of the two output vectors
            u3 = torch.cross(u1, u2)
            z0 = torch.stack([u1, u2, u3], dim=1).transpose(1, 2)
        else:
            z0 = z0.transpose(1, 2)

        if self.dim == 4:
            x_std = torch.einsum("bijm,bjkm->bikm", x, z0)
        elif self.dim == 3:
            x_std = torch.einsum("bij,bjk->bik", x, z0)
        elif self.dim == 5:
            x_std = torch.einsum("bijmn,bjkmn->bikmn", x, z0)

        return x_std, z0
