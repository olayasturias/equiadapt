import math

import kornia as K
import torch
import torch.nn as nn
import torch.nn.functional as F


class RotationEquivariantConvLift(nn.Module):
    def __init__(self, in_channels, out_channels, kernel_size, num_rotations=4, stride=1, padding=0, bias=True,
                 device='cuda'):
        super().__init__()
        self.weights = nn.Parameter(torch.empty(out_channels, in_channels, kernel_size, kernel_size).to(device))
        torch.nn.init.kaiming_uniform_(self.weights, a=math.sqrt(5))
        if bias:
            self.bias = nn.Parameter(torch.empty(out_channels).to(device))
            torch.nn.init.zeros_(self.bias)
        else:
            self.bias = None
        self.in_channels = in_channels
        self.out_channels = out_channels
        self.stride = stride
        self.padding = padding
        self.num_rotations = num_rotations
        self.kernel_size = kernel_size

    def get_rotated_weights(self, weights, num_rotations=4):
        device = weights.device
        weights = weights.flatten(0, 1).unsqueeze(0).repeat(num_rotations, 1, 1, 1)
        rotated_weights = K.geometry.rotate(
            weights,
            torch.linspace(0., 360., steps=num_rotations + 1, dtype=torch.float32)[:num_rotations].to(device),
        )
        rotated_weights = rotated_weights.reshape(
            self.num_rotations, self.out_channels, self.in_channels, self.kernel_size, self.kernel_size
        ).transpose(0, 1)
        return rotated_weights.flatten(0, 1)

    def forward(self, x):
        """
        x shape: (batch_size, in_channels, height, width)
        :return: (batch_size, out_channels, num_rotations, height, width)
        """
        batch_size = x.shape[0]
        rotated_weights = self.get_rotated_weights(self.weights, self.num_rotations)
        # shape (out_channels * num_rotations, in_channels, kernel_size, kernel_size)
        x = F.conv2d(x, rotated_weights, stride=self.stride, padding=self.padding)
        x = x.reshape(batch_size, self.out_channels, self.num_rotations, x.shape[2], x.shape[3])
        if self.bias is not None:
            x = x + self.bias[None, :, None, None, None]
        return x


class RotoReflectionEquivariantConvLift(nn.Module):
    def __init__(self, in_channels, out_channels, kernel_size, num_rotations=4, stride=1, padding=0, bias=True,
                 device='cuda'):
        super().__init__()
        num_group_elements = 2 * num_rotations
        self.weights = nn.Parameter(torch.empty(out_channels, in_channels, kernel_size, kernel_size).to(device))
        torch.nn.init.kaiming_uniform_(self.weights, a=math.sqrt(5))
        if bias:
            self.bias = nn.Parameter(torch.empty(out_channels).to(device))
            torch.nn.init.zeros_(self.bias)
        else:
            self.bias = None
        self.in_channels = in_channels
        self.out_channels = out_channels
        self.stride = stride
        self.padding = padding
        self.num_rotations = num_rotations
        self.kernel_size = kernel_size
        self.num_group_elements = num_group_elements

    def get_rotoreflected_weights(self, weights, num_rotations=4):
        device = weights.device
        weights = weights.flatten(0, 1).unsqueeze(0).repeat(num_rotations, 1, 1, 1)
        rotated_weights = K.geometry.rotate(
            weights,
            torch.linspace(0., 360., steps=num_rotations + 1, dtype=torch.float32)[:num_rotations].to(device),
        )
        reflected_weights = K.geometry.hflip(rotated_weights)
        rotoreflected_weights = torch.cat([rotated_weights, reflected_weights], dim=0)
        rotoreflected_weights = rotoreflected_weights.reshape(
            self.num_group_elements, self.out_channels, self.in_channels, self.kernel_size, self.kernel_size
        ).transpose(0, 1)
        return rotoreflected_weights.flatten(0, 1)

    def forward(self, x):
        """
        x shape: (batch_size, in_channels, height, width)
        :return: (batch_size, out_channels, num_group_elements, height, width)
        """
        batch_size = x.shape[0]
        rotoreflected_weights = self.get_rotoreflected_weights(self.weights, self.num_rotations)
        # shape (out_channels * num_group_elements, in_channels, kernel_size, kernel_size)
        x = F.conv2d(x, rotoreflected_weights, stride=self.stride, padding=self.padding)
        x = x.reshape(batch_size, self.out_channels, self.num_group_elements, x.shape[2], x.shape[3])
        if self.bias is not None:
            x = x + self.bias[None, :, None, None, None]
        return x

class RotationEquivariantConv(nn.Module):
    def __init__(self, in_channels, out_channels, kernel_size, num_rotations=4, stride=1, padding=0, bias=True, device='cuda'):
        super().__init__()
        self.weights = nn.Parameter(torch.empty(out_channels, in_channels, num_rotations, kernel_size, kernel_size).to(device))
        torch.nn.init.kaiming_uniform_(self.weights, a=math.sqrt(5))
        if bias:
            self.bias = nn.Parameter(torch.empty(out_channels).to(device))
            torch.nn.init.zeros_(self.bias)
        else:
            self.bias = None
        self.in_channels = in_channels
        self.out_channels = out_channels
        self.stride = stride
        self.padding = padding
        self.num_rotations = num_rotations
        self.kernel_size = kernel_size
        indices = torch.arange(num_rotations).view((1, 1, num_rotations, 1, 1)).repeat(
            num_rotations, out_channels * in_channels, 1, kernel_size, kernel_size
        )
        self.permute_indices_along_group = (
                (indices - torch.arange(num_rotations)[:, None, None, None, None]) % num_rotations
        ).to(device)
        self.angle_list = torch.linspace(0., 360., steps=num_rotations + 1, dtype=torch.float32)[:num_rotations].to(device)

    def get_rotated_permuted_weights(self, weights, num_rotations=4):
        device = weights.device
        weights = weights.flatten(0, 1).unsqueeze(0).repeat(num_rotations, 1, 1, 1, 1)
        permuted_weights = torch.gather(weights, 2, self.permute_indices_along_group)
        rotated_permuted_weights = K.geometry.rotate(
                    permuted_weights.flatten(1, 2),
                    self.angle_list,
                )
        rotated_permuted_weights = rotated_permuted_weights.reshape(
            self.num_rotations, self.out_channels, self.in_channels, self.num_rotations, self.kernel_size, self.kernel_size
        ).transpose(0, 1).reshape(
           self.out_channels * self.num_rotations, self.in_channels * self.num_rotations, self.kernel_size, self.kernel_size
        )
        return rotated_permuted_weights

    def forward(self, x):
        """
        x shape: (batch_size, in_channels, num_rotations, height, width)
        :return: (batch_size, out_channels, num_rotations, height, width)
        """
        batch_size = x.shape[0]
        x = x.flatten(1, 2)
        # shape (batch_size, in_channels * num_rotations, height, width)
        rotated_permuted_weights = self.get_rotated_permuted_weights(self.weights, self.num_rotations)
        # shape (out_channels * num_rotations, in_channels * num_rotations, kernal_size, kernal_size)
        x = F.conv2d(x, rotated_permuted_weights, stride=self.stride, padding=self.padding)
        x = x.reshape(batch_size, self.out_channels, self.num_rotations, x.shape[2], x.shape[3])
        if self.bias is not None:
            x = x + self.bias[None, :, None, None, None]
        return x

class RotoReflectionEquivariantConv(nn.Module):
    def __init__(self, in_channels, out_channels, kernel_size, num_rotations=4, stride=1, padding=0, bias=True, device='cuda'):
        super().__init__()
        num_group_elements = 2 * num_rotations
        self.weights = nn.Parameter(torch.empty(out_channels, in_channels, num_group_elements, kernel_size, kernel_size).to(device))
        torch.nn.init.kaiming_uniform_(self.weights, a=math.sqrt(5))
        if bias:
            self.bias = nn.Parameter(torch.empty(out_channels).to(device))
            torch.nn.init.zeros_(self.bias)
        else:
            self.bias = None
        self.in_channels = in_channels
        self.out_channels = out_channels
        self.stride = stride
        self.padding = padding
        self.num_rotations = num_rotations
        self.kernel_size = kernel_size
        self.num_group_elements = num_group_elements
        indices = torch.arange(num_rotations).view((1, 1, num_rotations, 1, 1)).repeat(
            num_rotations, out_channels * in_channels, 1, kernel_size, kernel_size
        )
        self.permute_indices_along_group = (indices - torch.arange(num_rotations)[:, None, None, None, None]) % num_rotations
        self.permute_indices_along_group_inverse = (indices + torch.arange(num_rotations)[:, None, None, None, None]) % num_rotations
        self.permute_indices_upper_half = torch.cat([
          self.permute_indices_along_group, self.permute_indices_along_group_inverse + num_rotations
        ], dim=2)
        self.permute_indices_lower_half = torch.cat([
          self.permute_indices_along_group_inverse + num_rotations, self.permute_indices_along_group
        ], dim=2)
        self.permute_indices = torch.cat([
            self.permute_indices_upper_half, self.permute_indices_lower_half
        ], dim=0).to(device)
        self.angle_list = torch.cat([
                        torch.linspace(0., 360., steps=num_rotations + 1, dtype=torch.float32)[:num_rotations],
                        torch.linspace(0., 360., steps=num_rotations + 1, dtype=torch.float32)[:num_rotations]
                    ]).to(device)

    def get_rotoreflected_permuted_weights(self, weights, num_rotations=4):
        weights = weights.flatten(0, 1).unsqueeze(0).repeat(self.num_group_elements, 1, 1, 1, 1)
        # shape (num_group_elements, out_channels * in_channels, num_group_elements, kernel_size, kernel_size)
        permuted_weights = torch.gather(weights, 2, self.permute_indices)
        rotated_permuted_weights = K.geometry.rotate(
                    permuted_weights.flatten(1, 2),
                    self.angle_list
                )
        rotoreflected_permuted_weights = torch.cat([
            rotated_permuted_weights[:self.num_rotations],
            K.geometry.hflip(rotated_permuted_weights[self.num_rotations:])
        ])
        rotoreflected_permuted_weights = rotoreflected_permuted_weights.reshape(
            self.num_group_elements, self.out_channels, self.in_channels, self.num_group_elements, self.kernel_size, self.kernel_size
        ).transpose(0, 1).reshape(
           self.out_channels * self.num_group_elements, self.in_channels * self.num_group_elements, self.kernel_size, self.kernel_size
        )
        return rotoreflected_permuted_weights

    def forward(self, x):
        """
        x shape: (batch_size, in_channels, num_group_elements, height, width)
        :return: (batch_size, out_channels, num_group_elements, height, width)
        """
        batch_size = x.shape[0]
        x = x.flatten(1, 2)
        # shape (batch_size, in_channels * num_group_elements, height, width)
        rotoreflected_permuted_weights = self.get_rotoreflected_permuted_weights(self.weights, self.num_rotations)
        # shape (out_channels * num_group_elements, in_channels * num_group_elements, kernel_size, kernel_size)
        x = F.conv2d(x, rotoreflected_permuted_weights, stride=self.stride, padding=self.padding)
        x = x.reshape(batch_size, self.out_channels, self.num_group_elements, x.shape[2], x.shape[3])
        if self.bias is not None:
            x = x + self.bias[None, :, None, None, None]
        return x
    
class CustomEquivariantNetwork(nn.Module):
    def __init__(self, 
                 in_shape, 
                 out_channels, 
                 kernel_size, 
                 group_type='rotation', 
                 num_rotations=4, 
                 num_layers=1,
                 device='cuda' if torch.cuda.is_available() else 'cpu'):
        super().__init__()
        
        if group_type == 'rotation':
            layer_list = [RotationEquivariantConvLift(in_shape[0], out_channels, kernel_size, num_rotations, device=device)]
            for i in range(num_layers - 1):
                layer_list.append(nn.ReLU())
                layer_list.append(RotationEquivariantConv(out_channels, out_channels, 1, num_rotations, device=device))
            self.eqv_network = nn.Sequential(*layer_list)
        elif group_type == 'roto-reflection':
            layer_list = [RotoReflectionEquivariantConvLift(in_shape[0], out_channels, kernel_size, num_rotations, device=device)]
            for i in range(num_layers - 1):
                layer_list.append(nn.ReLU())
                layer_list.append(RotoReflectionEquivariantConv(out_channels, out_channels, 1, num_rotations, device=device))
            self.eqv_network = nn.Sequential(*layer_list)
        else:
            raise ValueError('group_type must be rotation or roto-reflection for now.')

    def forward(self, x):
        """
        x shape: (batch_size, in_channels, height, width)
        :return: (batch_size, group_size)
        """
        feature_map = self.eqv_network(x)
        group_activatiobs = torch.mean(feature_map, dim=(1, 3, 4))
        
        return group_activatiobs
