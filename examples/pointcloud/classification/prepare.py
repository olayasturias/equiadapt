import numpy as np
import warnings
import os
from torch.utils.data import Dataset, DataLoader

import pytorch_lightning as pl
import h5py
import glob

warnings.filterwarnings("ignore")


def translate_pointcloud(pointcloud):
    xyz1 = np.random.uniform(low=2.0 / 3.0, high=3.0 / 2.0, size=[3])
    xyz2 = np.random.uniform(low=-0.2, high=0.2, size=[3])

    translated_pointcloud = np.add(np.multiply(pointcloud, xyz1), xyz2).astype(
        "float32"
    )
    return translated_pointcloud


def download_modelnet40(root_dir):
    DATA_DIR = root_dir
    if not os.path.exists(DATA_DIR):
        os.mkdir(DATA_DIR)
    if not os.path.exists(os.path.join(DATA_DIR, "modelnet40_ply_hdf5_2048")):
        www = "https://shapenet.cs.stanford.edu/media/modelnet40_ply_hdf5_2048.zip"
        zipfile = os.path.basename(www)
        os.system("wget --no-check-certificate %s; unzip %s" % (www, zipfile))
        os.system("mv %s %s" % ("modelnet40_ply_hdf5_2048", DATA_DIR))
        os.system("rm %s" % (zipfile))


def load_data_cls(root_dir, partition):
    download_modelnet40(root_dir)
    DATA_DIR = root_dir
    all_data = []
    all_label = []
    for h5_name in glob.glob(
        os.path.join(DATA_DIR, "modelnet40_ply_hdf5_2048", "*%s*.h5" % partition)
    ):
        f = h5py.File(h5_name, "r+")
        data = f["data"][:].astype("float32")
        label = f["label"][:].astype("int64")
        f.close()
        all_data.append(data)
        all_label.append(label)
    all_data = np.concatenate(all_data, axis=0)
    all_label = np.concatenate(all_label, axis=0)
    return all_data, all_label


def pc_normalize(pc):
    centroid = np.mean(pc, axis=0)
    pc = pc - centroid
    m = np.max(np.sqrt(np.sum(pc**2, axis=1)))
    pc = pc / m
    return pc


class ModelNetDataset(Dataset):
    def __init__(self, root_dir, num_points, partition="train", normalize=False):
        self.data, self.label = load_data_cls(root_dir, partition)
        self.num_points = num_points
        self.partition = partition
        self.normalize = normalize

    def __getitem__(self, item):
        pointcloud = self.data[item][: self.num_points]
        label = self.label[item]
        if self.partition == "train":
            pointcloud = translate_pointcloud(pointcloud)
            np.random.shuffle(pointcloud)
        if self.normalize:
            pointcloud = pc_normalize(pointcloud)
        return pointcloud, label

    def __len__(self):
        return self.data.shape[0]


class ModelNetDataModule(pl.LightningDataModule):
    def __init__(self, hyperparams):
        super().__init__()
        self.data_path = hyperparams.data_path
        self.hyperparams = hyperparams

    def setup(self, stage=None):
        if stage == "fit" or stage is None:
            self.train_dataset = ModelNetDataset(
                root_dir=self.data_path,
                num_points=self.hyperparams.num_points,
                partition="train",
                normalize=self.hyperparams.normalize,
            )
            self.valid_dataset = ModelNetDataset(
                root_dir=self.data_path,
                num_points=self.hyperparams.num_points,
                partition="test",
                normalize=self.hyperparams.normalize,
            )
        if stage == "test":
            self.test_dataset = ModelNetDataset(
                root_dir=self.data_path,
                num_points=self.hyperparams.num_points,
                partition="test",
                normalize=self.hyperparams.normalize,
            )

    def train_dataloader(self):
        train_loader = DataLoader(
            self.train_dataset,
            batch_size=self.hyperparams.batch_size,
            shuffle=True,
            num_workers=self.hyperparams.num_workers,
            drop_last=True,
        )
        return train_loader

    def val_dataloader(self):
        valid_loader = DataLoader(
            self.valid_dataset,
            batch_size=self.hyperparams.batch_size,
            shuffle=True,
            num_workers=self.hyperparams.num_workers,
            drop_last=False,
        )
        return valid_loader

    def test_dataloader(self):
        test_loader = DataLoader(
            self.test_dataset,
            batch_size=self.hyperparams.batch_size,
            shuffle=True,
            num_workers=self.hyperparams.num_workers,
            drop_last=False,
        )
        return test_loader
