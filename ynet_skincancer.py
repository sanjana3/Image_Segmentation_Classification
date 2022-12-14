# -*- coding: utf-8 -*-
"""YNET_SkinCancer.ipynb

Automatically generated by Colaboratory.

Original file is located at
    https://colab.research.google.com/drive/1ctNQmP6OxWAV1uCtBrlHytwatRc4tv_H

Mount the drive to access the data files
"""

from google.colab import drive
drive.mount('/content/drive')

import os
import numpy as np
import cv2
import torch
from torch.utils.data import Dataset
import torchvision.transforms.functional as TF

"""DriveDataset performs transformations on image, mask using Dataset library """
class DriveDataset(Dataset):
    def __init__(self, images_path, masks_path, labels):

        self.images_path = images_path
        self.masks_path = masks_path
        self.labels = labels
        self.n_samples = len(images_path)

    def __getitem__(self, index):
        """ Reading image """
        image = cv2.imread(self.images_path[index], cv2.IMREAD_COLOR)
        image = image/255.0 
        image = cv2.resize(np.float32(image),size,interpolation = cv2.INTER_NEAREST ) ## (512, 512, 3)
        image = np.transpose(image, (2, 0, 1))  ## (3, 512, 512)
        image = image.astype(np.float32)
        image = torch.from_numpy(image)
        image = TF.normalize(image,mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225])

        """ Reading mask """
        mask = cv2.imread(self.masks_path[index], cv2.IMREAD_GRAYSCALE)
        mask = mask/255.0   
        mask = cv2.resize(np.float32(mask),size,interpolation = cv2.INTER_NEAREST) ## (512, 512)
        mask = np.expand_dims(mask, axis=0) ## (1, 512, 512)
        mask = mask.astype(np.float32)
        mask = torch.from_numpy(mask)
        mask = TF.normalize(mask,mean=[0.5], std=[0.5])

        """ Reading classification label """
        label = self.labels[index]
        
        return image, mask, label

    def __len__(self):
        return self.n_samples

"""Helper functions"""

import os
import time
import random
import numpy as np
import cv2
import torch

""" Seeding the randomness. """
def seeding(seed):
    random.seed(seed)
    os.environ["PYTHONHASHSEED"] = str(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    torch.cuda.manual_seed(seed)
    torch.backends.cudnn.deterministic = True

""" Create a directory. """
def create_dir(path):
    if not os.path.exists(path):
        os.makedirs(path)

""" Calculate the time taken """
def epoch_time(start_time, end_time):
    elapsed_time = end_time - start_time
    elapsed_mins = int(elapsed_time / 60)
    elapsed_secs = int(elapsed_time - (elapsed_mins * 60))
    return elapsed_mins, elapsed_secs

import torch
import torch.nn as nn
import torch.nn.functional as F

"""Created a custom loss function combining sigmoid and BCELoss for segmentation"""
class CustomBCELoss:

    def __init__(self):
        self.bce = nn.BCELoss()

    def __call__(self, yhat, ys):
        yhat = torch.sigmoid(yhat)
        loss = self.bce(yhat, ys)
        return loss

"""Accuracy metric definition"""
def get_accuracy(y_true, y_prob):
  y_true = y_true.cpu().detach().numpy()
  y_prob = y_prob.cpu().detach().numpy()
  accuracy = metrics.accuracy_score(y_true, y_prob > 0.5)
  return accuracy

"""CNN building blocks for feature learning"""
class conv_block(nn.Module):
    def __init__(self, in_c, out_c):
        super().__init__()

        self.conv1 = nn.Conv2d(in_c, out_c, kernel_size = 3, padding = 1)
        self.bn1 = nn.BatchNorm2d(out_c)

        self.conv2 = nn.Conv2d(out_c, out_c, kernel_size = 3, padding = 1)
        self.bn2 = nn.BatchNorm2d(out_c)

        self.relu = nn.ReLU()

    def forward(self, inputs):
        x = self.conv1(inputs)
        x = self.bn1(x)
        x = self.relu(x)

        x = self.conv2(x)
        x = self.bn2(x)
        x = self.relu(x)

        return x

class encoder_block(nn.Module):
    def __init__(self, in_c, out_c):
        super().__init__()

        self.conv = conv_block(in_c, out_c)
        self.pool = nn.MaxPool2d((2, 2))

    def forward(self, inputs):
        x = self.conv(inputs)
        p = self.pool(x)
        print("Encoder block shapes x & p: ",x.shape, p.shape)

        return x, p

class decoder_block(nn.Module):
    def __init__(self, in_c, out_c):
        super().__init__()

        self.up = nn.ConvTranspose2d(in_c, out_c, kernel_size=2, stride=2, padding=0)
        self.conv = conv_block(out_c+out_c, out_c)

    def forward(self, inputs, skip):
        x = self.up(inputs)
        x = torch.cat([x, skip], axis=1)
        x = self.conv(x)
        # print("Decoder block shapes x: ",x.shape)
        return x

"""Model declaration and definition"""
class build_unet(nn.Module):
    def __init__(self):
        super().__init__()

        """ Encoder """
        self.e1 = encoder_block(3, 32)
        # print(self.e1.shape())
        self.e2 = encoder_block(32, 32) 
        self.e3 = encoder_block(32, 32)
        self.e4 = encoder_block(32, 32)

        """ Bottleneck """
        self.b = conv_block(32, 64)

        """ Decoder """
        self.d1 = decoder_block(64, 32)
        self.d2 = decoder_block(32, 32)
        self.d3 = decoder_block(32, 32)
        self.d4 = decoder_block(32, 32)

        """ Segmentation Classifier """
        self.outputs = nn.Conv2d(32, 1, kernel_size=1, padding=0)

        """ Classification classifier """
        self.e5 = encoder_block(64,64)
        # self.e6 = encoder_block(64,64)
        self.global_avg = nn.AdaptiveAvgPool2d(1)
        self.fc1 = nn.Linear(64, 64)
        self.fc2 = nn.Linear(64, 32)   
        self.fc3 = nn.Linear(32, 1)       ### ---> 2nd dimension is the number of classification labels
        self.sigmoid = nn.Sigmoid()

    def forward(self, inputs):
        """ Encoder """
        s1, p1 = self.e1(inputs)
        s2, p2 = self.e2(p1)
        s3, p3 = self.e3(p2)
        s4, p4 = self.e4(p3)

        """ Bottleneck """
        b = self.b(p4)

        """ Decoder """
        d1 = self.d1(b, s4)
        d2 = self.d2(d1, s3)
        d3 = self.d3(d2, s2)
        d4 = self.d4(d3, s1)

        outputs = self.outputs(d4)

        """ Diagnostic branch """
        s5, p5 = self.e5(b)
        print("shapes of b and p5: ",b.shape, p5.shape)
        # s6, p6 = self.e6(p5)
        avg = self.global_avg(p5)
        print("shape after average pool: ",avg.shape)
        avg = avg.view(avg.size(0), -1)
        print("shape after average pool: ",avg.shape)

        fc1 = self.fc1(avg)
        print("shape after 1st linear: ",avg.shape)

        fc2 = self.fc2(fc1)
        print("shape after 2nd linear: ",avg.shape)

        fc3 = self.fc3(fc2)
        print("shape after 3rd linear: ",avg.shape)

        label = self.sigmoid(fc3)
        # print("Final output shpes: output & label: ",outputs.shape, label.shape)

        return outputs, label

from torchvision import models
from torchsummary import summary
# # # input = input.to(device, dtype=torch.float32)
x = ( 64,16,16)
model = encoder_block(3,32)
# print(model.state_dict)


# Print model's state_dict
print("Model's state_dict:")
for param_tensor in model.state_dict():
    print(param_tensor, "\t", model.state_dict()[param_tensor].size())

"""Load the classification labels(melanocytic nevi)"""
import pandas as pd

df1 = pd.read_csv('/content/drive/MyDrive/YNET/SkinCancerData/TrainLabels200.csv')
df2 = pd.read_csv('/content/drive/MyDrive/YNET/SkinCancerData/ValLabels.csv')
df3 = pd.read_csv('/content/drive/MyDrive/YNET/SkinCancerData/TestLabels.csv')
trainLabels, validLabels, testLabels = [], [], []
trainLabels = df1['NV'].astype(int)
validLabels = df2['NV'].astype(int)
testLabels = df3['NV'].astype(int)

print(len(trainLabels),len(validLabels),len(testLabels))

import os
import time
from glob import glob

import torch
from torch.utils.data import DataLoader
import torch.nn as nn
import torch.optim as optim

import os, time
from operator import add
import numpy as np
from glob import glob
import cv2
from tqdm import tqdm
import imageio
import torch
import sklearn.metrics as metrics
from sklearn.metrics import accuracy_score, f1_score, jaccard_score, precision_score, recall_score
from google.colab.patches import cv2_imshow

def train(model, loader, optimizer, loss_seg, loss_class, device):
    seg_loss = 0.0
    class_loss = 0.0
    total_loss = 0.0
    meanIOU = 0.0
    pixelacc = 0.0

    model.train()
    for i,(input, target, target2) in enumerate(loader):
      # torch.cuda.empty_cache()
      input = input.to(device, dtype=torch.float32)
      target = target.to(device, dtype=torch.float32)
      target2 = target2.to(device)

      optimizer.zero_grad()
      # run the model : output -> predicted mask, label -> predicted label for classification
      output, label = model(input)

      # compute the loss
      loss1 = loss_seg(output, target)
      label = torch.reshape(label, (batch_size,1))
      target2 = torch.reshape(target2, (batch_size,1))
   
      loss2 = loss_class(label.float(), target2.float())
      trainAcc = get_accuracy(target2, label)

      loss = loss1 + loss2
      loss.backward()
      optimizer.step()
      
      seg_loss += loss1.item()
      class_loss += loss2.item()
      total_loss += loss.item()

    total_loss1 = total_loss/ len(loader)
    seg_loss1 = seg_loss/ len(loader)
    class_loss1 = class_loss/ len(loader)

    return total_loss1, seg_loss1, class_loss1, trainAcc

def evaluate(model, loader, loss_seg, loss_class, device):
    epoch_loss_seg = 0.0
    epoch_loss_class = 0.0
    epoch_total_loss = 0.0

    model.eval()
    with torch.no_grad():
        for i,(input, target, target2) in enumerate(loader):
          input = input.to(device, dtype=torch.float32)
          target = target.to(device, dtype=torch.float32)
          target2 = target2.to(device)
  
          output, label = model(input)
          label = torch.reshape(label, (batch_size,1))
          target2 = torch.reshape(target2, (batch_size,1))

          loss1 = loss_seg(output, target)
          loss2 = loss_class(label.float(), target2.float())
          validAcc = get_accuracy(target2, label)
          loss = loss1 + loss2

          epoch_total_loss += loss.item()
          epoch_loss_seg += loss1.item()
          epoch_loss_class += loss2.item()

        epoch_total_loss1 = epoch_total_loss/len(loader)
        epoch_loss_seg1 = epoch_loss_seg/len(loader)
        epoch_loss_class1 = epoch_loss_class/len(loader)

    return epoch_total_loss1, epoch_loss_seg1, epoch_loss_class1 , validAcc

trainImageLoss, trainClassLoss, validImageLoss = [], [], []
validClassLoss, totalTrainLoss, totalValidLoss = [], [], []

if __name__ == "__main__":
    """ Seeding """
    # seeding(49)

    """ Directories """
    create_dir("/content/drive/MyDrive/YNET/SavedModel")

    """ Load dataset """
    train_x = sorted(glob("/content/drive/MyDrive/YNET/SkinCancerData/TrainImages200/*"))
    train_y = sorted(glob("/content/drive/MyDrive/YNET/SkinCancerData/TrainMasks200/*"))

    valid_x = sorted(glob("/content/drive/MyDrive/YNET/SkinCancerData/ValImages/*"))
    valid_y = sorted(glob("/content/drive/MyDrive/YNET/SkinCancerData/ValMasks/*"))

    data_str = f"Dataset Size:\nTrain: {len(train_x)} - Valid: {len(valid_x)}\n"
    print(data_str)

    """ Hyperparameters """
    H = 256
    W = 256
    size = (H, W)
    batch_size = 5
    num_epochs = 1
    lr = 3e-5
    checkpoint_path = "/content/drive/MyDrive/YNET/SavedModel/YNETcheckpoint200_dummy.pth"

    """ Dataset and loader """
    train_dataset = DriveDataset(train_x, train_y, trainLabels)
    valid_dataset = DriveDataset(valid_x, valid_y, validLabels)
    
    train_loader = DataLoader(dataset=train_dataset, batch_size=batch_size, shuffle=True, num_workers=1)

    valid_loader = DataLoader(dataset=valid_dataset, batch_size=batch_size, shuffle=True, num_workers=1)
    
    totalTrainLoss, trainImageLoss, trainClassLoss, trainAccuracy = [], [], [], []
    totalValidLoss, validImageLoss, validClassLoss, validAccuracy = [], [], [], []

    device = torch.device('cuda')   ## GTX 1060 6GB
    model = build_unet()
    model = model.to(device)

    # optimizer = torch.optim.Adam(model.parameters(), lr=lr)
    optimizer = optim.SGD(model.parameters(), lr=lr, momentum=0.9)
    scheduler = torch.optim.lr_scheduler.ReduceLROnPlateau(optimizer, 'min', patience=5, verbose=True)

    # Segmentation loss function
    loss_seg = CustomBCELoss()

    # classification loss function               
    loss_class = nn.BCELoss()
    # loss_class = nn.CrossEntropyLoss()

    """ Training the model """
    best_valid_loss_seg = float("inf")
    best_valid_loss_class = float("inf")
    best_valid_total_loss = float("inf")

    for epoch in range(num_epochs):
        start_time = time.time()

        total_train_loss, train_loss_seg, train_loss_class, trainAcc = train(model, train_loader, optimizer, loss_seg, loss_class, device)
        total_valid_loss, valid_loss_seg, valid_loss_class, validAcc = evaluate(model, valid_loader, loss_seg, loss_class, device)

        trainImageLoss.append(train_loss_seg)
        trainClassLoss.append(train_loss_class)
        validImageLoss.append(valid_loss_seg)
        validClassLoss.append(valid_loss_class)
        totalTrainLoss.append(total_train_loss)
        totalValidLoss.append(total_valid_loss)
        trainAccuracy.append(trainAcc)
        validAccuracy.append(validAcc)

        """ Saving the model """

        if total_valid_loss < best_valid_total_loss:
            data_str = f"Valid loss improved from {best_valid_total_loss:2.4f} to {total_valid_loss:2.4f}. Saving checkpoint: {checkpoint_path}"

            # print(data_str)

            best_valid_total_loss = total_valid_loss
            torch.save(model.state_dict(), checkpoint_path)

        end_time = time.time()
        epoch_mins, epoch_secs = epoch_time(start_time, end_time)

        data_str = f'Epoch: {epoch+1:02} | Epoch Time: {epoch_mins}m {epoch_secs}s\n'
        data_str += f'\t Train Loss for segmentation: {train_loss_seg:.3f}\n'
        data_str += f'\t Val. Loss for segmentation: {valid_loss_seg:.3f}\n'
        data_str += f'\t Train Loss for classification: {train_loss_class:.3f}\n'
        data_str += f'\t Val. Loss for classification: {valid_loss_class:.3f}\n'
        data_str += f'\t Total Train Loss: {total_train_loss:.3f}\n'
        data_str += f'\t Total Valid Loss: {total_valid_loss:.3f}\n'
        # print(data_str)

import matplotlib.pyplot as plt
import numpy as np


x = np.arange(150)
fig, (ax1, ax2, ax3) = plt.subplots(1, 3, sharey=True)
fig.set_size_inches(20,5)
fig.suptitle('Training & Validation Loss over 150 epochs')
ax1.plot(x, trainImageLoss)
ax1.plot(x, validImageLoss)
ax1.set_title("Segmentation loss")
ax2.plot(x, trainClassLoss, label='TrainLoss' )
ax2.plot(x, validClassLoss, label='ValLoss' )
ax2.set_title("Classification loss")
# ax3.plot(x, trainAccuracy,label='TrainAcc')
# ax3.plot(x, validAccuracy,label='ValAcc')
# ax3.set_title("classification task accuracy")
ax3.plot(x, totalTrainLoss)
ax3.plot(x, totalValidLoss)
ax3.set_title("Joint loss for Ynet")
plt.legend()
plt.show()

def dice_loss(pred, target):
    """ This definition generalize to real valued pred and target vector.
        This should be differentiable.
    pred: tensor with first dimension as batch
    target: tensor with first dimension as batch
    """
    smooth = 1.

    # have to use contiguous since they may from a torch.view op
    iflat = torch.from_numpy(pred)
    tflat = torch.from_numpy(target)
    intersection = (iflat * tflat).sum()

    A_sum = torch.sum(iflat * iflat)
    B_sum = torch.sum(tflat * tflat)
    
    return 1 - ((2. * intersection + smooth) / (A_sum + B_sum + smooth) )

def iou_pytorch(outputs, labels):
    """  You can comment out this line if you are passing tensors of equal shape
    But if you are passing output from UNet or something it will most probably
    be with the BATCH x 1 x H x W shape
    outputs = outputs.squeeze(1) 
    BATCH x 1 x H x W => BATCH x H x W
    outputs = outputs >= 0.5    
    """

    print(outputs.shape, labels.shape)
    SMOOTH = 1e-6
    
    intersection = (outputs & labels)  # Will be zero if Truth=0 or Prediction=0
    union = (outputs | labels)          #.float().sum((1, 2))         # Will be zzero if both are 0
    
    iou = (intersection + SMOOTH) / (union + SMOOTH)  # We smooth our devision to avoid 0/0
    
    thresholded = torch.clamp(20 * (iou - 0.5), 0, 10).ceil() / 10  # This is equal to comparing with thresolds
    
    return thresholded.mean()  # Or thresholded.mean() if you are interested in average across the batch

"""Model Evaluation"""
import os, time
from operator import add
import numpy as np
from glob import glob
import cv2
from tqdm import tqdm
from sklearn.metrics import confusion_matrix
import imageio
import torch
from google.colab.patches import cv2_imshow
from sklearn.metrics import accuracy_score, f1_score, jaccard_score, precision_score, recall_score
# Segmentation loss function
loss_seg = CustomBCELoss()

# classification loss function               
loss_class = nn.BCELoss()

def calculate_metrics(y_true, y_pred):
  BCE = loss_seg(y_pred, y_true)
  """ Ground truth """
  y_true = y_true.cpu().numpy()
  y_true = y_true > 0.5
  y_true = y_true.astype(np.uint8)
  y_true = y_true.reshape(-1)

  """ Prediction """
  y_pred = y_pred.cpu().numpy()
  y_pred = y_pred > 0.5
  y_pred = y_pred.astype(np.uint8)
  y_pred = y_pred.reshape(-1)

  score_jaccard = jaccard_score(y_true, y_pred)
  score_f1 = f1_score(y_true, y_pred)
  score_recall = recall_score(y_true, y_pred)
  score_precision = precision_score(y_true, y_pred)
  score_acc = accuracy_score(y_true, y_pred)
  diceScore = dice_loss(y_pred, y_true)
  iou = iou_pytorch(torch.from_numpy(y_pred),  torch.from_numpy(y_true))
  
  return [score_jaccard, score_f1, score_recall, score_precision, score_acc, diceScore, iou, BCE]

def mask_parse(mask):
  mask = np.expand_dims(mask, axis=-1)    ## (256, 256, 1)
  mask = np.concatenate([mask, mask, mask], axis=-1)  ## (512, 512, 3)
  return mask

Jaccard, F1,Recall, Precision, Accuracy = [],[],[],[],[]

if __name__ == "__main__":
  """ Seeding """
  # seeding(49)

  """ Folders """
  # create_dir("/content/drive/MyDrive/IDRID/YNet/datasets/files")

  """ Load dataset """
  test_x = sorted(glob("/content/drive/MyDrive/YNET/SkinCancerData/TestImages/*"))
  test_y = sorted(glob("/content/drive/MyDrive/YNET/SkinCancerData/TestMasks/*"))

  """ Hyperparameters """
  H = 256
  W = 256
  size = (W, H)
  checkpoint_path = "/content/drive/MyDrive/YNET/SavedModel/YNETcheckpoint1200.pth"

  """ Load the checkpoint """
  device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')

  model = build_unet()
  model = model.to(device)
  model.load_state_dict(torch.load(checkpoint_path, map_location=device))
  model.eval()

  metrics_score = [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0]
  predicted_labels = []
  time_taken = []

  for i, (x, y, target2) in tqdm(enumerate(zip(test_x, test_y, testLabels)), total=len(test_x)):
    """ Extract the name """
    name = x.split("/")[-1].split(".")[0]

    """ Reading image """
    image = cv2.imread(x, cv2.IMREAD_COLOR) ## (256, 256, 3)
    image = cv2.resize(image, size)
    x = np.transpose(image, (2, 0, 1))      ## (3, 256, 256)
    x = x/255.0
    x = np.expand_dims(x, axis=0)           ## (1, 3, 256, 256)
    x = x.astype(np.float32)
    x = torch.from_numpy(x)
    x = TF.normalize(x,mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225])
    x = x.to(device)

    """ Reading mask """
    mask = cv2.imread(y, cv2.IMREAD_GRAYSCALE)  ## (256, 256)
    mask = cv2.resize(mask, size)
    y = np.expand_dims(mask, axis=0)            ## (1, 256, 256)
    y = y/255.0
    y = np.expand_dims(y, axis=0)               ## (1, 1, 256, 256)
    y = y.astype(np.float32)
    y = torch.from_numpy(y)
    y = TF.normalize(y,mean=[0.5], std=[0.5])
    y = y.to(device)
    # print(y)

    """Reading classification label"""
    # label = target2[i]

    with torch.no_grad():
      """ Prediction and Calculating FPS """
      # start_time = time.time()

      pred_y, pred_label  = model(x)
      pred_y = torch.sigmoid(pred_y)

      # total_time = time.time() - start_time
      # time_taken.append(total_time)
      # pred_y = pred_y >= 0.5
      score = calculate_metrics(y, pred_y)
      metrics_score = list(map(add, metrics_score, score))
      pred_y = pred_y[0].cpu().numpy()        ## (1, 256, 256)
      pred_y = np.squeeze(pred_y, axis=0)     ## (256, 256)
      pred_y = pred_y > 0.5
      pred_y = np.array(pred_y, dtype=np.uint8)
       
      # pred_label = torch.sigmoid(pred_label)
      pred_label = 1 if pred_label > 0.5 else 0
      print("Predicted class label: ",pred_label)
      predicted_labels.append(pred_label)

    """ Saving masks """
    ori_mask = mask_parse(mask)
    pred_y = mask_parse(pred_y)
    line = np.ones((size[1], 10, 3)) * 128

    cat_images = np.concatenate(
        [image, line, ori_mask, line, pred_y * 255], axis=1
    )
    predImage = pred_y*255
    cv2.imwrite(f"/content/drive/MyDrive/YNET/SavedModel/results/ynet_results/{name}_ynet.png", image)
    cv2.imwrite(f"/content/drive/MyDrive/YNET/SavedModel/results/ynet_results/{name}_ynet_mask.png", ori_mask)
    cv2.imwrite(f"/content/drive/MyDrive/YNET/SavedModel/results/ynet_results/{name}_ynet_pred.png", predImage)
    cv2_imshow(cat_images)

  jaccard = metrics_score[0]/len(test_x)
  f1 = metrics_score[1]/len(test_x)
  recall = metrics_score[2]/len(test_x)
  precision = metrics_score[3]/len(test_x)
  acc = metrics_score[4]/len(test_x)
  diceScore = metrics_score[5]/len(test_x)
  iou = metrics_score[6]/len(test_x)
  BCE = metrics_score[7]/len(test_x)
  
  Jaccard.append(jaccard)
  F1.append(f1)
  Recall.append(recall)
  Precision.append(precision)
  Accuracy.append(acc)
  print(f"Jaccard: {jaccard:1.4f} - F1: {f1:1.4f} - Recall: {recall:1.4f} - Precision: {precision:1.4f} - Acc: {acc:1.4f}")
  print(f"Dice score: {diceScore} - IOU score: {iou} - BCE Loss:{BCE}")

from sklearn.metrics import confusion_matrix, ConfusionMatrixDisplay
import matplotlib.pyplot as plt
from sklearn.metrics import classification_report

print("True Labels: ",list(testLabels))
print("Predicted Labels: ",predicted_labels)
target_names = ['class 0', 'class 1']
cr = classification_report(testLabels, predicted_labels, target_names=target_names)
print("Classification Report: ",cr)
disp = ConfusionMatrixDisplay(confusion_matrix=confusion_matrix(predicted_labels,list(testLabels)), display_labels=[0,1])
disp.plot()

True_Labels =        [1, 0, 0, 1, 0, 0, 0, 1, 1, 1, 0, 1, 1, 1, 0, 1, 1, 1, 0, 0, 1, 1, 1, 1, 1, 1, 1, 0, 0, 0, 1, 0, 1, 1, 1, 1, 1, 1, 1, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0]
Predicted_Labels  =  [1, 0, 0, 1, 0, 0, 0, 1, 1, 1, 0, 1, 1, 1, 0, 1, 1, 1, 0, 0, 1, 1, 1, 0, 1, 1, 0, 0, 0, 0, 0, 0, 0, 1, 0, 1, 1, 1, 1, 0, 0, 1, 1, 0, 0, 0, 0, 0, 0, 0]

from sklearn.metrics import confusion_matrix, ConfusionMatrixDisplay
import matplotlib.pyplot as plt
from sklearn.metrics import classification_report

# print("True Labels: ",list(testLabels))
# print("Predicted Labels: ",predicted_labels)
target_names = ['class 0', 'class 1']
cr = classification_report(True_Labels, Predicted_Labels, target_names=target_names)
print("Classification Report: ",cr)
disp = ConfusionMatrixDisplay(confusion_matrix=confusion_matrix(Predicted_Labels,True_Labels), display_labels=[0,1])
disp.plot()