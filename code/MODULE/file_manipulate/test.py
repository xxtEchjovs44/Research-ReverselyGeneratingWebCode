import os
import pandas as pd
import numpy as np
import math

data_position = 'D:\datasets\dataset_webpage\data'
root = os.path.join(data_position, 'img_relabelled')
img_root = os.path.join(root, 'img')
label_root = os.path.join(root, 'label')

for l in os.listdir(label_root):
    label = pd.read_csv(os.path.join(label_root, l), index_col=0)

    for col in label.columns.values:
        if 'Unnamed' in col:
            label = label.drop(columns=col)

    label['bx'] = label['bx'].astype('int')
    label['by'] = label['by'].astype('int')
    label['bw'] = label['bw'].astype('int')
    label['bh'] = label['bh'].astype('int')
    label['segment_no'] = label['segment_no'].astype('int')

    for i in range(len(label)):
        ele = label.iloc[i].copy()
        ele['element'] = 'img'
        ele['p'] = 1
        ele['c_img'] = 1

        for j in range(len(ele)):
            if type(ele[j]) is np.float64 and not math.isnan(ele[j]):
                ele[j] = int(ele[j])

        label.iloc[i] = ele

    label.to_csv(os.path.join(label_root, l))
    print('gg')