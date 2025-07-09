import torch
import torch.nn as nn

try:
    from pointnet2_ops.pointnet2_modules import PointnetSAModule
except ImportError:
    print("Pointnet2_ops not found. Please install it from https://github.com/erikwijmans/Pointnet2_PyTorch")
    exit()

class PointNet2(nn.Module):
    def __init__(self):
        super(PointNet2, self).__init__()
        self.use_xyz = True
        self._build_model()
    def _build_model(self):
        self.SA_modules = nn.ModuleList()
        # 假设 WHUCAD 使用的模型接受 3D 输入 (XYZ)
        self.SA_modules.append(
            PointnetSAModule(npoint=512, radius=0.1, nsample=64, mlp=[0, 32, 32, 64], use_xyz=self.use_xyz)
        )
        self.SA_modules.append(
            PointnetSAModule(npoint=256, radius=0.2, nsample=64, mlp=[64, 64, 64, 128], use_xyz=self.use_xyz)
        )
        self.SA_modules.append(
            PointnetSAModule(npoint=128, radius=0.4, nsample=64, mlp=[128, 128, 128, 256], use_xyz=self.use_xyz)
        )
        self.SA_modules.append(
            PointnetSAModule(mlp=[256, 256, 512, 1024], use_xyz=self.use_xyz)
        )

        self.fc_layer = nn.Sequential(
            nn.Linear(1024, 512),
            nn.LeakyReLU(True),
            nn.Linear(512, 256),
            nn.LeakyReLU(True),
            nn.Linear(256, 256),
            nn.Tanh()
        )

    def _break_up_pc(self, pc):
        xyz = pc[..., 0:3].contiguous()
        features = pc[..., 3:].transpose(1, 2).contiguous() if pc.size(-1) > 3 else None
        return xyz, features

    def forward(self, pointcloud):
        xyz, features = self._break_up_pc(pointcloud)
        for module in self.SA_modules:
            xyz, features = module(xyz, features)
        return self.fc_layer(features.squeeze(-1))